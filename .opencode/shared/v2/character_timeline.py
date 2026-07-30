"""
CharacterTimelineLedger — 角色时间线账本。

核心职责：
1. 扫描所有 SCENE 叙事单元，基于 extra.time 序数建立排序时间线
2. 为缺少序数的场景自动计算序数（ordinal = chapter * 10000 + position * 100 + 0.5）
3. 支持手动序数覆盖（闪回/插叙）
4. 支持平行场景（同序数 + precision="same"）
5. 提供排序视图供 WorkspaceBuilder 和 search-analysis 消费

与 GraphStore 的关系：
- Ledger 是只读计算视图，不修改 graph
- 每次 build() 重新计算（保持简单，不引入缓存失效问题）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

from graph_schema import (
    NarrativeUnit, UnitType, UnitStatus, RelationType,
    get_unit_chapter,
)
from time_utils import (
    get_story_time, get_story_ordinal, compute_ordinal, STORY_TIME_KEY,
)


# ── 数据类 ──────────────────────────────────────────────────────────────────


@dataclass
class CharacterSnapshot:
    """角色在某剧情节点的状态快照。每个角色每种状态每章一条。"""
    character_name: str
    chapter: int                       # 叙事章节号
    story_ordinal: Optional[float]     # 故事时间坐标
    location: str                      # 该场景位置（从 SCENE.地点）
    status: str                        # 该场景角色状态（从 出场角色[].状态）
    description: str                   # 场景作用描述
    source_scene_id: str               # 来源场景 ID
    source_scene_name: str             # 来源场景名称
    scene_order: int = 0               # 场景在章内顺序


@dataclass
class TimelineView:
    """
    排序后的时间线视图。

    scenes 按 (ordinal, precision, scene_name) 排序。
    提供按角色和按章节的索引，避免重复扫描。
    """
    scenes: List[TimelineScene] = field(default_factory=list)
    total_scenes: int = 0

    # 按角色索引：角色名 → [TimelineScene]（已按 ordinal 排序）
    by_character: Dict[str, List[TimelineScene]] = field(default_factory=dict)

    # 按章节索引：章节号 → [TimelineScene]
    by_chapter: Dict[int, List[TimelineScene]] = field(default_factory=dict)

    # 统计
    manual_overrides: int = 0
    parallel_groups: int = 0


@dataclass
class TimelineScene:
    """时间线中的单个场景条目，含排序元数据和角色列表"""
    unit_id: str
    unit_name: str
    chapter: int
    ordinal: float
    precision: str                    # exact | same | approximate | override | vague
    label: str                        # 原始时间标签
    location: str                     # 场景地点
    characters: List[str] = field(default_factory=list)
    is_manual_ordinal: bool = False


# ── 时间线账本 ──────────────────────────────────────────────────────────────


class CharacterTimelineLedger:
    """
    角色时间线账本。

    使用方式：
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        sorted_scenes = view.scenes          # 按故事时间排序的全部场景
        char_timeline = view.by_character.get("林昭", [])  # 角色时间线
        chap_scenes = view.by_chapter.get(3, [])           # 某章的场景

    build() 每次重新计算。场景数量通常 < 5000，O(n) 开销可接受。
    """

    def __init__(self, store):
        self.store = store

    # ── 主构建方法 ──────────────────────────────────────────────────────

    def build(self) -> TimelineView:
        """扫描所有 SCENE 单元，构建排序后的时间线视图"""
        scenes: List[TimelineScene] = []
        manual_count = 0

        # 收集所有活跃 SCENE
        for unit in self.store._units.values():
            if unit.type != UnitType.SCENE:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue

            ts = self._build_timeline_scene(unit)
            if ts is None:
                continue
            if ts.is_manual_ordinal:
                manual_count += 1
            scenes.append(ts)

        # 排序：有 ordinal 的在前 → ordinal 升序 → precision 优先 → 名称兜底
        _prec_order = {"exact": 0, "same": 1, "approximate": 2, "override": 3, "vague": 4}
        scenes.sort(key=lambda s: (
            0 if s.ordinal >= 0 else 1,
            s.ordinal,
            _prec_order.get(s.precision, 99),
            s.unit_name or "",
        ))

        # 构建索引
        view = TimelineView(
            scenes=scenes,
            total_scenes=len(scenes),
            manual_overrides=manual_count,
        )

        # 按角色索引
        char_map: Dict[str, List[TimelineScene]] = defaultdict(list)
        for ts in scenes:
            for char_name in ts.characters:
                char_map[char_name].append(ts)
        view.by_character = dict(char_map)

        # 按章节索引
        ch_map: Dict[int, List[TimelineScene]] = defaultdict(list)
        for ts in scenes:
            if ts.chapter > 0:
                ch_map[ts.chapter].append(ts)
        view.by_chapter = dict(ch_map)

        # 统计平行场景组
        view.parallel_groups = self._count_parallel_groups(scenes)

        return view

    def _build_timeline_scene(self, unit: NarrativeUnit) -> Optional[TimelineScene]:
        """从单个 SCENE 单元构建 TimelineScene"""
        content = self._parse_content(unit)
        if not content:
            return None

        label = content.get("time_text", "") or ""
        location = content.get("location", "") or ""
        chapter = get_unit_chapter(unit) or 0

        # 提取出场角色列表
        characters: List[str] = []
        raw_chars = content.get("cast", [])
        if isinstance(raw_chars, list):
            for c in raw_chars:
                if isinstance(c, dict):
                    name = c.get("name", "")
                    if name:
                        characters.append(name)
                elif isinstance(c, str):
                    characters.append(c)

        # 序数检测：优先 manual → auto
        st = get_story_time(unit)
        if st and st.get("ordinal") is not None:
            # 手动覆盖
            return TimelineScene(
                unit_id=unit.id,
                unit_name=unit.unit_name or "",
                chapter=chapter,
                ordinal=float(st["ordinal"]),
                precision=st.get("precision", "override"),
                label=label,
                location=location,
                characters=characters,
                is_manual_ordinal=True,
            )

        # 自动计算序数（延迟到排序后，先占位）
        # 使用 chapter * 10000 + position * 100 + 0.5 作为基序号，
        # position 按创建时间在同章场景中的排序确定
        ordinal = self._auto_ordinal(unit, chapter)
        return TimelineScene(
            unit_id=unit.id,
            unit_name=unit.unit_name or "",
            chapter=chapter,
            ordinal=ordinal,
            precision="exact",
            label=label,
            location=location,
            characters=characters,
            is_manual_ordinal=False,
        )

    def _auto_ordinal(self, unit: NarrativeUnit, chapter: int) -> float:
        """自动计算序数：同章场景按创建时间排序定位"""
        if chapter == 0:
            return compute_ordinal(0, 0)

        # 收集同章其他场景，按创建时间排序
        peers: List[NarrativeUnit] = []
        for u in self.store._units.values():
            if u.type == UnitType.SCENE and u.status != UnitStatus.ARCHIVED:
                ch = get_unit_chapter(u) or 0
                if ch == chapter and u.id != unit.id:
                    peers.append(u)

        peers.sort(key=lambda u: u.created_at)

        position = 0
        for i, peer in enumerate(peers):
            if unit.created_at < peer.created_at:
                position = i
                break
            position = i + 1

        return compute_ordinal(chapter, position)

    def _count_parallel_groups(self, scenes: List[TimelineScene]) -> int:
        """统计平行场景组数（连续相同 ordinal 的 same 场景计为一组）"""
        if not scenes:
            return 0
        groups = 0
        prev_ordinal = scenes[0].ordinal
        in_group = False
        for s in scenes[1:]:
            if s.ordinal == prev_ordinal and s.precision == "same":
                if not in_group:
                    groups += 1
                    in_group = True
            else:
                in_group = False
            prev_ordinal = s.ordinal
        return groups

    @staticmethod
    def _parse_content(unit: NarrativeUnit) -> dict:
        """安全解析 content 为 dict"""
        if not unit or not unit.content:
            return {}
        if isinstance(unit.content, dict):
            return unit.content
        try:
            return json.loads(unit.content)
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}

    # ── 查询方法 ──────────────────────────────────────────────────────────

    def get_snapshots(self, view: TimelineView, character_name: str) -> List[CharacterSnapshot]:
        """获取角色完整时间线快照（按 ordinal 排序后）"""
        timeline = view.by_character.get(character_name, [])
        if not timeline:
            return []
        return [
            CharacterSnapshot(
                character_name=character_name,
                chapter=ts.chapter,
                story_ordinal=ts.ordinal,
                location=ts.location,
                status="",      # 快照级别暂不提取个体状态（后面可从 Ledger 扩展）
                description="",
                source_scene_id=ts.unit_id,
                source_scene_name=ts.unit_name,
            )
            for ts in timeline
        ]

    def get_snapshot_before(
        self, view: TimelineView, character_name: str, chapter: int
    ) -> Optional[CharacterSnapshot]:
        """
        获取角色在某章之前的最后已知状态。
        查阅该角色时间线中 chapter < 指定值且排序最后的场景。
        """
        timeline = view.by_character.get(character_name, [])
        for ts in reversed(timeline):
            if ts.chapter < chapter:
                return CharacterSnapshot(
                    character_name=character_name,
                    chapter=ts.chapter,
                    story_ordinal=ts.ordinal,
                    location=ts.location,
                    status="",
                    description="",
                    source_scene_id=ts.unit_id,
                    source_scene_name=ts.unit_name,
                )
        return None

    def get_scene_order(self, view: TimelineView, scene_id: str) -> int:
        """获取场景在时间线中的位置索引（0-based），不存在返回 -1"""
        for i, ts in enumerate(view.scenes):
            if ts.unit_id == scene_id:
                return i
        return -1

    def get_state_at_ordinal(
        self, view: TimelineView, character_name: str, at_ordinal: float
    ) -> Optional[TimelineScene]:
        """
        获取角色在指定序数时刻的最新场景（≤ at_ordinal）。
        用于回答"在这个时间点，角色是什么状态？"
        """
        timeline = view.by_character.get(character_name, [])
        for s in reversed(timeline):
            if s.ordinal <= at_ordinal:
                return s
        return None
