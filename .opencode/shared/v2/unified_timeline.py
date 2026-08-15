"""
unified_timeline.py — 统一时间线索引（UnifiedTimelineIndex）。

合并 CharacterTimelineLedger（SCENE 时间线视图）与 TemporalEventIndex（全类型事件索引）
为单一 UnifiedTimelineIndex，作为所有时间线查询的唯一入口。

时间写入 / 派生统一由 TimeWriter / TimeUtils 负责：
- TimeWriter.set_time() → 写 extra.time（唯一写入入口）
- TimeUtils.derive_ordinal() → 序数派生（唯一派生入口）
- UnifiedTimelineIndex → 时间线查询（事件索引 + 场景视图）

架构：
  UnifiedTimelineIndex.build()
    ├─ 来源 A: TEMPORAL_EVENT 节点（通过 HAS_EVENT 边关联到实体）[主数据源]
    └─ 来源 B: 存量 content JSON（events[] / key_events[] / scene）[已弃用，仅存量兼容]

  build_timeline_view(event_mode=False)
    ├─ SCENE 单元 → TimelineView（原 CharacterTimelineLedger.build）
    └─ TEMPORAL_EVENT 单元 → TimelineView（原 CharacterTimelineLedger.build_events）

设计原则：
  - 无持久化：每次 build() 重新计算（全量扫描，O(n) 仅 n=事件数）
  - 无状态：UnifiedTimelineIndex 是值对象，用完即弃
  - 来源 B 已弃用：新项目应在 EventExtractor 就绪后关闭此选项
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from graph_schema import (
    NarrativeUnit, UnitType, UnitStatus, RelationType, get_unit_chapter,
)
from graph_store import GraphStore
from type_registry import TypeRegistry
from time_utils import (
    get_story_time, compute_ordinal, ORDINAL_BASE, ORDINAL_OFFSET, VOLUME_BASE,
)


# ── 数据类 ────────────────────────────────────────────────────────────────


@dataclass
class TemporalEvent:
    """统一时间线事件"""

    # 来源标识
    source_id: str                          # 来源单元 ID
    source_name: str                        # 来源单元名称
    source_type: str                        # "temporal_event" | "scene" | ...
    event_id: str                           # 来源内唯一标识
    event_type: str                         # "scene_event" | "cultivation" | ...

    # 时间坐标
    ordinal: Optional[float] = None         # 统一时间坐标
    precision: str = "vague"                # exact / chapter / volume / vague
    time_label: str = ""                    # 人类可读时间标签

    # 内容
    summary: str = ""                       # 事件简述
    location: str = ""                      # 地点名称
    characters: List[str] = field(default_factory=list)  # 参与者
    details: Dict[str, Any] = field(default_factory=dict)  # 类型特定详情

    # 元数据
    is_from_node: bool = False              # True=来自 TEMPORAL_EVENT 节点
    chapter: int = 0                        # 推导的章节号

    def ordinal_sort_key(self) -> Tuple:
        """统一排序键：有 ordinal 的在前"""
        if self.ordinal is not None:
            return (0, self.ordinal, _PREC_ORDER.get(self.precision, 99), self.source_name)
        return (1, 0, _PREC_ORDER.get(self.precision, 99), self.source_name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "ordinal": self.ordinal,
            "precision": self.precision,
            "time_label": self.time_label,
            "summary": self.summary,
            "location": self.location,
            "characters": self.characters,
            "details": self.details,
        }


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
    scenes: List["TimelineScene"] = field(default_factory=list)
    total_scenes: int = 0

    # 按角色索引：角色名 → [TimelineScene]（已按 ordinal 排序）
    by_character: Dict[str, List["TimelineScene"]] = field(default_factory=dict)

    # 按章节索引：章节号 → [TimelineScene]
    by_chapter: Dict[int, List["TimelineScene"]] = field(default_factory=dict)

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


_PREC_ORDER = {"exact": 0, "same": 1, "approximate": 2, "chapter": 3, "volume": 4, "vague": 5}

# 场景视图排序用的精度序（与事件索引 _PREC_ORDER 略有差异，保持原 Ledger 行为）
_SCENE_PREC_ORDER = {"exact": 0, "same": 1, "approximate": 2, "override": 3, "vague": 4}


# ── 统一时间线索引 ─────────────────────────────────────────────────────────


class UnifiedTimelineIndex:
    """
    统一时间线索引：合并 CharacterTimelineLedger + TemporalEventIndex。

    用法：
        index = UnifiedTimelineIndex(store).build()
        events = index.query().for_entity("吕明理").range(0, 5000).by_type("cultivation").all()
        view = index.build_timeline_view()          # SCENE 时间线视图（原 Ledger.build）
        view = index.build_timeline_view(event_mode=True)  # TEMPORAL_EVENT 视图
    """

    def __init__(
        self,
        store: GraphStore,
        registry: Optional[TypeRegistry] = None,
    ):
        self.store = store
        self.registry = registry or TypeRegistry.get_global(
            project_root=str(store.project_root)
        )
        self._events: List[TemporalEvent] = []

        # 索引
        self._by_entity: Dict[str, List[int]] = {}       # entity_name → [indices]
        self._by_type: Dict[str, List[int]] = {}         # event_type → [indices]
        self._by_source: Dict[str, List[int]] = {}       # source_id → [indices]

    # ── 事件索引构建（原 TemporalEventIndex） ─────────────────────────────

    def build(
        self,
        use_content_fallback: Optional[bool] = None,
    ) -> "UnifiedTimelineIndex":
        """
        构建时间线事件索引。

        Args:
            use_content_fallback: 是否使用存量 content JSON 回退提取。
                True=启用回退（向后兼容），False=禁用回退（仅 TEMPORAL_EVENT 节点），
                None=读取环境变量 NOVEL_TEMPORAL_CONTENT_FALLBACK（默认 True）。

        注意：
            _extract_from_content 已弃用。新项目应确保所有事件通过 EventExtractor
            创建 TEMPORAL_EVENT 节点后，将 use_content_fallback 设为 False。
        """
        if use_content_fallback is None:
            use_content_fallback = os.environ.get(
                "NOVEL_TEMPORAL_CONTENT_FALLBACK", "0"
            ) in ("1", "true", "yes")

        self._events.clear()
        self._by_entity.clear()
        self._by_type.clear()
        _covered: Set[str] = set()

        # 来源 A: TEMPORAL_EVENT 节点（主数据源）
        self._extract_from_event_nodes(_covered)

        # 来源 B: 存量 content JSON（已弃用，仅存量兼容）
        if use_content_fallback:
            self._extract_from_content(_covered)

        # 全局排序
        self._events.sort(key=lambda e: e.ordinal_sort_key())

        # 重要：排序后 _events 中元素位置已变，但 _add_event 时建的
        # _by_entity/_by_type/_by_source 存的 idx 指向的是排序前的旧位置。
        # 必须重建全部索引，使 idx 与排序后的事件位置一致。
        self._rebuild_indices()
        return self

    def query(self) -> "UnifiedTimelineQuery":
        return UnifiedTimelineQuery(self)

    # ── 场景时间线视图（原 CharacterTimelineLedger） ─────────────────────

    def build_timeline_view(self, event_mode: bool = False) -> TimelineView:
        """
        构建排序后的时间线视图。

        Args:
            event_mode: False=扫描 SCENE 单元（原 Ledger.build）；
                        True=扫描 TEMPORAL_EVENT 单元（原 Ledger.build_events，
                        用于无 SCENE 项目兜底）。
        """
        scenes: List[TimelineScene] = []
        manual_count = 0

        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if event_mode:
                if unit.type != UnitType.TEMPORAL_EVENT:
                    continue
                ts = self._build_timeline_event(unit)
            else:
                if unit.type != UnitType.SCENE:
                    continue
                ts = self._build_timeline_scene(unit)
            if ts is None:
                continue
            if ts.is_manual_ordinal:
                manual_count += 1
            scenes.append(ts)

        return self._finalize(scenes, manual_count)

    # ── 查询方法（原 CharacterTimelineLedger） ───────────────────────────

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
                status="",      # 快照级别暂不提取个体状态
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

    def auto_ordinal(self, unit: NarrativeUnit, chapter: int) -> float:
        """自动计算序数：同章场景按创建时间排序定位（供 TimeWriter 委托）。"""
        return self._auto_ordinal(unit, chapter)

    # ── 内部辅助：事件索引 ───────────────────────────────────────────────

    def _rebuild_indices(self):
        """在排序后重建所有索引，确保 idx 指向排序后的正确位置。"""
        self._by_entity.clear()
        self._by_type.clear()
        self._by_source.clear()
        for idx, evt in enumerate(self._events):
            for char_name in evt.characters:
                self._by_entity.setdefault(char_name, []).append(idx)
            self._by_type.setdefault(evt.event_type, []).append(idx)
            self._by_source.setdefault(evt.source_id, []).append(idx)

    def _add_event(self, evt: TemporalEvent):
        """添加一个事件到列表并更新索引。"""
        idx = len(self._events)
        self._events.append(evt)
        for char_name in evt.characters:
            self._by_entity.setdefault(char_name, []).append(idx)
        self._by_type.setdefault(evt.event_type, []).append(idx)
        self._by_source.setdefault(evt.source_id, []).append(idx)

    # ── 来源 A：从 TEMPORAL_EVENT 节点提取 ──────────────────────────────

    def _extract_from_event_nodes(self, covered_entities: Set[str] = set()):
        """遍历 TEMPORAL_EVENT 节点，通过 HAS_EVENT 边关联到实体。

        关系查询使用 GraphStore 的 per-unit 索引（O(events+relations)），
        不再逐事件全量扫描关系表。
        """
        for unit in self.store._units.values():
            if unit.type != UnitType.TEMPORAL_EVENT:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue

            content = self._parse_content(unit)
            if not content:
                continue

            # 通过 HAS_EVENT 入边找到关联实体（per-unit 索引查询）
            entity_names: Set[str] = set()
            source_entity: Optional[str] = None
            for rel in self.store.get_relations(
                unit.id, relation_type=RelationType.HAS_EVENT, direction="incoming"
            ):
                parent = self.store.get_unit(rel.source_id)
                if parent:
                    entity_names.add(parent.unit_name)
                    source_entity = parent.unit_name

            # 通过 LOCATED_AT 出边找到地点
            location = content.get("location", "") or ""
            for rel in self.store.get_relations(
                unit.id, relation_type=RelationType.LOCATED_AT, direction="outgoing"
            ):
                loc = self.store.get_unit(rel.target_id)
                if loc:
                    location = location or loc.unit_name

            # 通过 INVOLVES 出边找到参与者
            for rel in self.store.get_relations(
                unit.id, relation_type=RelationType.INVOLVES, direction="outgoing"
            ):
                participant = self.store.get_unit(rel.target_id)
                if participant and participant.unit_name:
                    entity_names.add(participant.unit_name)

            ordinal = content.get("ordinal")
            if ordinal is not None:
                ordinal = float(ordinal)

            precision = content.get("precision", "vague")

            # 从 ordinal 推导章节号
            chapter = 0
            if ordinal is not None:
                chapter = int(ordinal // ORDINAL_BASE)

            self._add_event(TemporalEvent(
                source_id=unit.id,
                source_name=unit.unit_name or "?",
                source_type=UnitType.TEMPORAL_EVENT.value,
                event_id=unit.id,
                event_type=content.get("event_type", "note"),
                ordinal=ordinal,
                precision=precision,
                time_label=content.get("time_label", "") or "",
                summary=content.get("summary", "") or unit.unit_name or "",
                location=location,
                characters=list(entity_names),
                details=content.get("details", {}),
                is_from_node=True,
                chapter=chapter,
            ))

            # 标记涉及实体已覆盖（防止来源 B 重复提取）
            if source_entity:
                covered_entities.add(source_entity)
            for name in entity_names:
                covered_entities.add(name)

    # ── 来源 B：从存量 content JSON 提取（已弃用） ───────────────────────
    #
    # 此方法将在未来版本中移除。新项目应在 EventExtractor 就绪后：
    #   1. 运行 scripts/migrate_content_events_to_temporal.py
    #   2. 设置 NOVEL_TEMPORAL_CONTENT_FALLBACK=0 或调 build(use_content_fallback=False)
    # 届时此方法和 _ContentExtractor 类均可安全删除。
    #

    def _extract_from_content(self, covered_entities: Set[str] = set()):
        """[已弃用] 从存量 content JSON 中提取事件。
        替代方案：event_extractor.EventExtractor + TEMPORAL_EVENT 节点。"""
        extractor = _ContentExtractor(self.store, self.registry)
        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            # 跳过已有 TEMPORAL_EVENT 节点覆盖的实体——CHARACTER_ARC 与 SCENE
            # 均可能由内容提取出与节点重复的 scene_event，防止重复事件入索引
            if unit.type in (UnitType.CHARACTER_ARC, UnitType.SCENE) \
                    and unit.unit_name in covered_entities:
                continue
            events = extractor.extract(unit)
            for evt in events:
                self._add_event(evt)

    # ── 内部辅助：场景视图 ───────────────────────────────────────────────

    def _finalize(self, scenes: List[TimelineScene], manual_count: int = 0) -> TimelineView:
        """排序 + 构建索引 + 统计（build_timeline_view 共用）"""
        # 排序：有 ordinal 的在前 → ordinal 升序 → precision 优先 → 名称兜底
        scenes.sort(key=lambda s: (
            0 if s.ordinal >= 0 else 1,
            s.ordinal,
            _SCENE_PREC_ORDER.get(s.precision, 99),
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

    def _build_timeline_event(self, unit: NarrativeUnit) -> Optional[TimelineScene]:
        """从单个 TEMPORAL_EVENT 单元构建 TimelineScene"""
        content = self._parse_content(unit)
        if not content:
            return None

        # 字段解析：ordinal / precision / time_label / location / summary
        raw_ordinal = content.get("ordinal")
        ordinal = float(raw_ordinal) if raw_ordinal is not None else 0.0
        precision = content.get("precision", "approximate") or "approximate"
        label = content.get("time_label", "") or ""
        location = content.get("location", "") or ""
        summary = content.get("summary", "") or ""

        # 提取角色列表（数组元素为 {"name":..} dict 或 str）
        characters: List[str] = []
        raw_chars = content.get("characters", [])
        if isinstance(raw_chars, list):
            for c in raw_chars:
                if isinstance(c, dict):
                    name = c.get("name", "")
                    if name:
                        characters.append(name)
                elif isinstance(c, str):
                    characters.append(c)

        return TimelineScene(
            unit_id=unit.id,
            unit_name=unit.unit_name or summary or "",
            chapter=0,  # temporal_event 无章节
            ordinal=ordinal,
            precision=precision,
            label=label,
            location=location,
            characters=characters,
            is_manual_ordinal=raw_ordinal is not None,
        )

    def _auto_ordinal(self, unit: NarrativeUnit, chapter: int) -> float:
        """[已弃用] 自动计算序数：同章场景按创建时间排序定位。

        此方法将在未来版本中移除。序数应由 EventExtractor 在内容创建时
        根据焦点上下文确定并写入 TEMPORAL_EVENT 节点。
        替代方案：event_extractor.EventExtractor._resolve_ordinal()
        """
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
    def _parse_content(unit) -> dict:
        """安全解析 content 为 dict"""
        if not unit or not unit.content:
            return {}
        if isinstance(unit.content, dict):
            return unit.content
        try:
            return json.loads(unit.content)
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}


# ── 查询构建器 ────────────────────────────────────────────────────────────


class UnifiedTimelineQuery:
    """链式查询构建器。"""

    def __init__(self, index: UnifiedTimelineIndex):
        self._index = index
        self._entity_filter: Optional[str] = None
        self._type_filter: Optional[Set[str]] = None
        self._ordinal_lo: Optional[float] = None
        self._ordinal_hi: Optional[float] = None
        self._source_filter: Optional[str] = None
        self._limit: int = 50

    def for_entity(self, name: str) -> "UnifiedTimelineQuery":
        """按实体名称过滤。"""
        self._entity_filter = name
        return self

    def by_type(self, *types: str) -> "UnifiedTimelineQuery":
        """按事件类型过滤。"""
        self._type_filter = set(types)
        return self

    def range(self, lo: Optional[float] = None, hi: Optional[float] = None) -> "UnifiedTimelineQuery":
        """按 ordinal 范围过滤。"""
        self._ordinal_lo = lo
        self._ordinal_hi = hi
        return self

    def around(self, ordinal: float, window: float = 500.0) -> "UnifiedTimelineQuery":
        """以某序数为中心、窗口为半宽的邻域查询。"""
        self._ordinal_lo = ordinal - window
        self._ordinal_hi = ordinal + window
        return self

    def from_source(self, source_id: str) -> "UnifiedTimelineQuery":
        """按来源单元 ID 过滤。"""
        self._source_filter = source_id
        return self

    def limit(self, n: int) -> "UnifiedTimelineQuery":
        """限制返回数量。"""
        self._limit = n
        return self

    def count(self) -> int:
        """返回匹配数量（不截断）。"""
        return len(self._filtered_indices())

    def all(self) -> List[TemporalEvent]:
        """执行查询。"""
        indices = self._filtered_indices()
        sorted_idx = sorted(indices, key=lambda i: self._index._events[i].ordinal_sort_key())
        return [self._index._events[i] for i in sorted_idx[:self._limit]]

    def first(self) -> Optional[TemporalEvent]:
        """返回第一个匹配事件。"""
        results = self.all()
        return results[0] if results else None

    def last(self) -> Optional[TemporalEvent]:
        """返回最后一个匹配事件。"""
        results = self.all()
        return results[-1] if results else None

    # ── 内部 ──────────────────────────────────────────────────────────────

    def _filtered_indices(self) -> Set[int]:
        candidate = set(range(len(self._index._events)))

        if self._entity_filter:
            indices = self._index._by_entity.get(self._entity_filter, [])
            candidate &= set(indices)

        if self._type_filter:
            combined: Set[int] = set()
            for t in self._type_filter:
                combined |= set(self._index._by_type.get(t, []))
            candidate &= combined

        if self._source_filter:
            indices = self._index._by_source.get(self._source_filter, [])
            candidate &= set(indices)

        if self._ordinal_lo is not None or self._ordinal_hi is not None:
            filtered: Set[int] = set()
            for idx in candidate:
                e = self._index._events[idx]
                if self._ordinal_lo is not None and (e.ordinal is None or e.ordinal < self._ordinal_lo):
                    continue
                if self._ordinal_hi is not None and (e.ordinal is not None and e.ordinal > self._ordinal_hi):
                    continue
                filtered.add(idx)
            candidate = filtered

        return candidate


# ── 内容提取器（来源 B：从存量 content JSON 提取） ─────────────────────


class _ContentExtractor:
    """
    从现有类型的 content JSON 中提取时间事件。

    覆盖类型：
      SCENE           → scene_event
      CHARACTER_ARC   → cultivation / battle（从 events[] 提取）
      PLOT_THREAD     → plot_event（从 key_events[] 提取）
      WORLD_RULE      → chronicle（从 event_location / event_volume 提取）

    不覆盖：
      THEMATIC_MOTIF  → 未来扩展（occurrences[] 主要是主题分析，非时序事件）
      NOTE / CHUNK    → 无时间字段
      结构类（OUTLINE / ARC_PLAN / VOLUME_PLAN / CHAPTER_PLAN）→ 已有 CONTAINS 边
    """

    # 事件类型映射（英文 → content JSON 中的中文值）
    _TYPE_MAP = {
        "cultivation": ("修炼", "突破", "晋级", "渡劫", "悟道"),
        "battle": ("战斗", "厮杀", "对决", "切磋", "斗法"),
        "plot_event": ("剧情", "事件", "转折", "发现"),
        "relationship": ("结交", "决裂", "仇视", "联盟"),
    }

    def __init__(self, store: GraphStore, registry: TypeRegistry):
        self.store = store
        self.registry = registry

    def extract(self, unit) -> List[TemporalEvent]:
        """根据单元类型提取事件。"""
        type_name = unit.type.value if hasattr(unit.type, "value") else str(unit.type)
        handler = {
            "scene": self._extract_scene,
            "character_arc": self._extract_character_arc,
            "plot_thread": self._extract_plot_thread,
            "world_rule": self._extract_world_rule,
        }.get(type_name)
        if handler:
            return handler(unit)
        return []

    # ── SCENE ────────────────────────────────────────────────────────────

    def _extract_scene(self, unit) -> List[TemporalEvent]:
        """从 SCENE 提取 scene_event。"""
        content = self._parse_content(unit)
        if not content:
            return []

        ordinal = None
        precision = "vague"

        # 优先 extra.time（已自动同步）
        st = get_story_time(unit)
        if st:
            st_ord = st.get("ordinal")
            if st_ord is not None:
                ordinal = float(st_ord)
                precision = st.get("precision", "exact")

        # 其次 content 中的显式序数
        if ordinal is None:
            ordinal = self._field_num(content, "time_ordinal", "时间序数")
            if ordinal is not None:
                precision = "exact"

        time_label = self._field_str(content, "time_text", "时间")
        summary = self._field_str(content, "one_line_summary", "一句话概要")
        if not summary:
            summary = unit.unit_name or "?"
        location = self._field_str(content, "location", "地点")
        characters = self._extract_cast_names(content)

        chapter = 0
        if ordinal is not None:
            chapter = int(ordinal // ORDINAL_BASE)
        else:
            # 从 chapter_number 推算自动序数（兼容原 Ledger 行为）
            ch = getattr(unit, 'chapter_number', None) or 0
            if ch:
                ordinal = compute_ordinal(int(ch), 0)
                precision = "chapter"
                chapter = int(ch)

        return [TemporalEvent(
            source_id=unit.id,
            source_name=unit.unit_name or "?",
            source_type="scene",
            event_id="scene",
            event_type="scene_event",
            ordinal=ordinal,
            precision=precision,
            time_label=time_label,
            summary=summary,
            location=location,
            characters=characters,
            details={"subtype": self._field_str(content, "subtype", "子类型")},
            is_from_node=False,
            chapter=chapter,
        )]

    # ── CHARACTER_ARC ───────────────────────────────────────────────────

    def _extract_character_arc(self, unit) -> List[TemporalEvent]:
        """从 CHARACTER_ARC 的 events[] / 关键事件 数组提取事件。"""
        content = self._parse_content(unit)
        if not content:
            return []

        # 兼容中英文字段名
        raw_events = self._field_list(content, "events", "关键事件")
        if not raw_events:
            return []

        results = []
        for i, item in enumerate(raw_events):
            if not isinstance(item, dict):
                continue
            evt = self._build_from_arc_event(unit, item, i)
            if evt:
                results.append(evt)

        return results

    def _build_from_arc_event(self, unit, item: dict, index: int) -> Optional[TemporalEvent]:
        """从 character_arc events[] / 关键事件 的单个条目构建事件。"""
        ordinal = self._field_num(item, "ordinal", "序数")

        # 推导事件类型：从 item 的 type/事件获取
        type_label = self._field_str(item, "type", "类型", "事件")
        event_type = self._infer_event_type(type_label)
        location = self._field_str(item, "location", "地点")
        realm = self._field_str(item, "realm", "修为")
        age = self._field_num(item, "age", "年龄")

        # 构建摘要
        summary = type_label or self._field_str(item, "event", "事件") or unit.unit_name or f"事件#{index}"

        # 时间标签
        time_label = f"#{ordinal:.1f}" if ordinal is not None else ""

        chapter = int(ordinal // ORDINAL_BASE) if ordinal is not None else 0

        return TemporalEvent(
            source_id=unit.id,
            source_name=unit.unit_name or "?",
            source_type="character_arc",
            event_id=f"events[{index}]",
            event_type=event_type,
            ordinal=ordinal,
            precision="exact" if ordinal is not None else "vague",
            time_label=time_label,
            summary=summary,
            location=location,
            characters=[unit.unit_name] if unit.unit_name else [],
            details={"type": type_label, "age": age, "realm": realm},
            is_from_node=False,
            chapter=chapter,
        )

    # ── PLOT_THREAD ────────────────────────────────────────────────────

    def _extract_plot_thread(self, unit) -> List[TemporalEvent]:
        """从 PLOT_THREAD 的 key_events[] / 关键事件 数组提取 plot_event。"""
        content = self._parse_content(unit)
        if not content:
            return []

        raw_events = self._field_list(content, "key_events", "关键事件")
        if not raw_events:
            return []

        results = []
        for i, item in enumerate(raw_events):
            if not isinstance(item, dict):
                continue

            ch = self._field_num(item, "chapter_number", "章节")
            if ch is None:
                continue

            ordinal = float(ch) * ORDINAL_BASE
            summary = self._field_str(item, "event", "事件")
            if not summary:
                continue

            results.append(TemporalEvent(
                source_id=unit.id,
                source_name=unit.unit_name or "?",
                source_type="plot_thread",
                event_id=f"key_events[{i}]",
                event_type="plot_event",
                ordinal=ordinal,
                precision="chapter",
                time_label=f"第{int(ch)}章",
                summary=summary,
                location="",
                characters=[],
                details={},
                is_from_node=False,
                chapter=int(ch),
            ))

        return results

    # ── WORLD_RULE ─────────────────────────────────────────────────────

    def _extract_world_rule(self, unit) -> List[TemporalEvent]:
        """从 WORLD_RULE 的纪年事件字段提取 chronicle_event。"""
        content = self._parse_content(unit)
        if not content:
            return []

        event_location = self._field_str(content, "event_location", "位置")
        event_volume = self._field_num(content, "event_volume", "所属卷")
        if not event_location and event_volume is None:
            return []

        ordinal = float(event_volume) * VOLUME_BASE if event_volume is not None else None

        details = {}
        if event_location:
            details["location"] = event_location
        if event_volume is not None:
            details["volume"] = event_volume

        summary = event_location or unit.unit_name or "纪年事件"

        return [TemporalEvent(
            source_id=unit.id,
            source_name=unit.unit_name or "?",
            source_type="world_rule",
            event_id="chronicle",
            event_type="chronicle",
            ordinal=ordinal,
            precision="volume" if event_volume is not None else "vague",
            time_label=f"第{int(event_volume)}卷" if event_volume else "",
            summary=summary,
            location=event_location,
            characters=[],
            details=details,
            is_from_node=False,
            chapter=0,
        )]

    # ── 辅助方法 ───────────────────────────────────────────────────────

    @staticmethod
    def _infer_event_type(raw_type: str) -> str:
        """从中文事件类型推导标准化 event_type。"""
        if not raw_type:
            return "note"
        for etype, keywords in _ContentExtractor._TYPE_MAP.items():
            for kw in keywords:
                if kw in raw_type:
                    return etype
        return "note"

    # ── 中英文兼容字段读取 ──────────────────────────────────────────────

    @staticmethod
    def _field(d: dict, *keys: str) -> Any:
        """按优先级尝试多个 key 读取字段（英文优先，中文 fallback）。"""
        for k in keys:
            if k in d:
                return d[k]
        return None

    @staticmethod
    def _field_str(d: dict, *keys: str) -> str:
        val = _ContentExtractor._field(d, *keys)
        return str(val) if val else ""

    @staticmethod
    def _field_list(d: dict, *keys: str) -> list:
        val = _ContentExtractor._field(d, *keys)
        return val if isinstance(val, list) else []

    @staticmethod
    def _field_num(d: dict, *keys: str) -> Optional[float]:
        val = _ContentExtractor._field(d, *keys)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _extract_cast_names(content: dict) -> List[str]:
        """从 SCENE content 的 cast[] / 出场角色 提取角色名列表。"""
        raw = _ContentExtractor._field_list(content, "cast", "出场角色")
        names = []
        for item in raw:
            if isinstance(item, dict):
                n = _ContentExtractor._field_str(item, "name", "角色名")
                if n:
                    names.append(n)
            elif isinstance(item, str):
                names.append(item)
        return names

    @staticmethod
    def _parse_content(unit) -> dict:
        if not unit or not unit.content:
            return {}
        if isinstance(unit.content, dict):
            return unit.content
        try:
            return json.loads(unit.content)
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}