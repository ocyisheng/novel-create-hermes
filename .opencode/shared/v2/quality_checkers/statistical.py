"""
StatisticalDetector — 信号收集层。

从 graph 中收集统计信号（R7/R10/R11/R12），返回 SignalResult。
不做裁决判断，裁决由 skill 层完成。

职责边界：
  ✅ 信号收集：位置变化(R7)、节奏单调(R10)、密度偏离(R11)、主角能动性(R12)
  ✅ 返回 SignalResult（含 raw_value 和 threshold）
  ❌ 裁决判断 → skill 层
  ❌ LLM 调用 → 本层纯确定性
"""
from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

from graph_schema import (
    NarrativeUnit, UnitType, UnitStatus, RelationType,
    get_unit_chapter,
)
from graph_store import GraphStore
from time_utils import get_story_ordinal, ORDINAL_BASE

from quality_checkers.types import SignalResult

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "location_change": 5000.0,
    "pacing_monotony": 0.3,
    "density_deviation": 0.5,
    "protagonist_agency": 0.3,
}


class StatisticalDetector:
    """
    统计信号检测器 — 收集 R7/R10/R11/R12 信号，返回 SignalResult。

    用法：
        detector = StatisticalDetector(store)
        signals = detector.detect_all()

    或自定义阈值：
        detector = StatisticalDetector(store, thresholds={"pacing_monotony": 0.5})
    """

    def __init__(
        self,
        store: GraphStore,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.store = store
        self._thresholds = {**_DEFAULT_THRESHOLDS}
        if thresholds:
            self._thresholds.update(thresholds)

    # ── 主入口 ──────────────────────────────────────────────────────────────

    def detect_all(self) -> List[SignalResult]:
        """运行所有信号收集规则。"""
        signals: List[SignalResult] = []
        signals.extend(self._signal_location_change())
        signals.extend(self._signal_pacing_monotony())
        signals.extend(self._signal_density_deviation())
        signals.extend(self._signal_protagonist_agency())
        return signals

    # ── R7: 位置变化检测 ───────────────────────────────────────────────────

    def _signal_location_change(self) -> List[SignalResult]:
        """
        检测同一角色在相邻时间切片中的地点变化。
        输出 gap 值，阈值由构造函数配置。
        """
        threshold = self._thresholds["location_change"]

        # 建立场景基础信息索引
        scene_info: dict = {}  # scene_id → (location, ordinal, chapter, name)
        for unit in self.store._units.values():
            if unit.type != UnitType.SCENE or unit.status == UnitStatus.ARCHIVED:
                continue
            content = unit.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    content = {}
            loc = content.get("location", "") if isinstance(content, dict) else ""
            ordinal = get_story_ordinal(unit)
            ch = get_unit_chapter(unit) or 0
            scene_info[unit.id] = (loc, ordinal, ch, unit.unit_name or "?")

        # 建立角色→场景映射（通过 PARTICIPATES_IN 边）
        # 对称类型（PARTICIPATES_IN inverse==自身）：物理方向无意义，任一端是场景即视为出场
        char_scenes: dict = defaultdict(list)
        for rel_id, rel in self.store._relations.items():
            if rel.relation_type != RelationType.PARTICIPATES_IN:
                continue
            if rel.target_id in scene_info and rel.source_id not in scene_info:
                scene_id, char_id = rel.target_id, rel.source_id
            elif rel.source_id in scene_info and rel.target_id not in scene_info:
                scene_id, char_id = rel.source_id, rel.target_id
            else:
                continue  # 场景↔场景或非场景端点，不构成角色出场
            loc, ordinal, ch, sname = scene_info[scene_id]
            char_scenes[char_id].append(
                (scene_id, loc, ordinal, ch, sname)
            )

        results: List[SignalResult] = []

        # 逐角色检查位置变化
        for char_id, scenes in char_scenes.items():
            char_unit = self.store.get_unit(char_id)
            if not char_unit or char_unit.type != UnitType.CHARACTER_ARC:
                continue
            char_name = char_unit.unit_name or char_id

            # 按 ordinal 排序
            scenes_sorted = sorted(scenes, key=lambda s: (
                0 if s[2] is not None else 1,
                s[2] if s[2] is not None else 0,
                s[3],
                s[4],
            ))

            for i in range(len(scenes_sorted) - 1):
                sid_a, loc_a, ord_a, ch_a, sname_a = scenes_sorted[i]
                sid_b, loc_b, ord_b, ch_b, sname_b = scenes_sorted[i + 1]

                if loc_a == loc_b or not loc_a or not loc_b:
                    continue

                # 计算间隔
                if ord_a is not None and ord_b is not None:
                    gap = ord_b - ord_a
                elif ch_a > 0 and ch_b > 0:
                    gap = (ch_b - ch_a) * ORDINAL_BASE
                else:
                    gap = 99999

                results.append(SignalResult(
                    rule_id="R7",
                    rule_name="位置变化",
                    signal_type="location_change",
                    signal_data={
                        "from_location": loc_a,
                        "to_location": loc_b,
                        "gap": gap,
                        "character": char_name,
                        "scene_a": sname_a,
                        "scene_b": sname_b,
                    },
                    units_involved=[sid_a, sid_b, char_id],
                    raw_value=gap,
                    threshold=threshold,
                ))

        return results

    # ── R10: 节奏单调检测 ──────────────────────────────────────────────────

    def _signal_pacing_monotony(self) -> List[SignalResult]:
        """
        检测连续章节的场景数量是否过于均匀。
        使用滑动窗口计算场景数量的标准差。
        """
        threshold = self._thresholds["pacing_monotony"]

        # 统计每章的场景数
        chapter_scenes: Dict[int, int] = defaultdict(int)
        for unit in self.store._units.values():
            if unit.type != UnitType.SCENE or unit.status == UnitStatus.ARCHIVED:
                continue
            ch = get_unit_chapter(unit) or 0
            if ch > 0:
                chapter_scenes[ch] += 1

        if len(chapter_scenes) < 3:
            return []

        # 按章节号排序，提取场景数序列
        sorted_chapters = sorted(chapter_scenes.keys())
        scene_counts = [chapter_scenes[ch] for ch in sorted_chapters]

        # 滑动窗口（窗口大小取 5 章或总章数，取较小值）
        window_size = min(5, len(scene_counts))
        signals: List[SignalResult] = []

        for i in range(len(scene_counts) - window_size + 1):
            window = scene_counts[i : i + window_size]
            window_mean = statistics.mean(window)
            window_std = statistics.stdev(window) if len(window) > 1 else 0.0

            if window_std < threshold:
                ch_start = sorted_chapters[i]
                ch_end = sorted_chapters[i + window_size - 1]
                signals.append(SignalResult(
                    rule_id="R10",
                    rule_name="节奏单调",
                    signal_type="pacing_monotony",
                    signal_data={
                        "window_std": window_std,
                        "window_mean": window_mean,
                        "chapters": f"{ch_start}-{ch_end}",
                        "scene_counts": window,
                    },
                    units_involved=[],
                    raw_value=window_std,
                    threshold=threshold,
                ))

        return signals

    # ── R11: 密度偏离检测 ──────────────────────────────────────────────────

    def _signal_density_deviation(self) -> List[SignalResult]:
        """
        检测单章场景数偏离整体均值的程度。
        输出 abs(chapter_count - mean) / mean。
        """
        threshold = self._thresholds["density_deviation"]

        # 统计每章的场景数
        chapter_scenes: Dict[int, int] = defaultdict(int)
        for unit in self.store._units.values():
            if unit.type != UnitType.SCENE or unit.status == UnitStatus.ARCHIVED:
                continue
            ch = get_unit_chapter(unit) or 0
            if ch > 0:
                chapter_scenes[ch] += 1

        if len(chapter_scenes) < 2:
            return []

        counts = list(chapter_scenes.values())
        mean = statistics.mean(counts)
        if mean == 0:
            return []

        signals: List[SignalResult] = []

        for ch, count in sorted(chapter_scenes.items()):
            deviation = abs(count - mean) / mean
            if deviation > threshold:
                signals.append(SignalResult(
                    rule_id="R11",
                    rule_name="密度偏离",
                    signal_type="density_deviation",
                    signal_data={
                        "chapter": ch,
                        "scene_count": count,
                        "mean": mean,
                    },
                    units_involved=[],
                    raw_value=deviation,
                    threshold=threshold,
                ))

        return signals

    # ── R12: 主角能动性检测 ────────────────────────────────────────────────

    def _signal_protagonist_agency(self) -> List[SignalResult]:
        """
        检测主角在场景中是否只是被动参与者。
        计算主角参与的场景中，主角作为源端的关系比例。
        """
        threshold = self._thresholds["protagonist_agency"]

        # 查找主角（假设第一个 CHARACTER_ARC 为主角，或通过 tag 标记）
        protagonist_id: Optional[str] = None
        for unit in self.store._units.values():
            if unit.type != UnitType.CHARACTER_ARC:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue
            # 优先查找有 protagonist tag 的角色
            tags = unit.tags if hasattr(unit, "tags") else []
            if "protagonist" in tags or "主角" in tags:
                protagonist_id = unit.id
                break
            # 回退：取第一个非归档角色
            if protagonist_id is None:
                protagonist_id = unit.id

        if not protagonist_id:
            return []

        # 收集主角参与的场景（PARTICIPATES_IN 对称类型：物理方向无意义）
        protagonist_scenes: List[str] = []
        for rel in self.store._relations.values():
            if rel.relation_type != RelationType.PARTICIPATES_IN:
                continue
            if rel.source_id == protagonist_id:
                protagonist_scenes.append(rel.target_id)
            elif rel.target_id == protagonist_id:
                protagonist_scenes.append(rel.source_id)

        if not protagonist_scenes:
            return []

        # 计算主动比例：主角作为源端（或对称类型任一端）的关系数 / 主角参与的场景数
        active_count = 0
        passive_count = 0

        for scene_id in protagonist_scenes:
            scene_unit = self.store.get_unit(scene_id)
            if not scene_unit:
                continue

            # 检查主角在该场景中是否有主动关系（除 PARTICIPATES_IN 外）。
            # 方向性类型只算主角为源端的出边；对称类型方向无意义，任一端关联即算。
            has_active = False
            for rel in self.store._relations.values():
                if rel.relation_type == RelationType.PARTICIPATES_IN:
                    continue
                connects_scene = (
                    (rel.source_id == protagonist_id and rel.target_id == scene_id)
                    or (rel.target_id == protagonist_id and rel.source_id == scene_id)
                )
                if connects_scene and (
                    rel.source_id == protagonist_id or rel.relation_type.is_symmetric
                ):
                    has_active = True
                    break

            if has_active:
                active_count += 1
            else:
                passive_count += 1

        total = active_count + passive_count
        if total == 0:
            return []

        active_ratio = active_count / total
        passive_ratio = passive_count / total

        return [SignalResult(
            rule_id="R12",
            rule_name="主角能动性",
            signal_type="protagonist_agency",
            signal_data={
                "active_ratio": active_ratio,
                "passive_ratio": passive_ratio,
                "active_scenes": active_count,
                "passive_scenes": passive_count,
            },
            units_involved=[protagonist_id],
            raw_value=active_ratio,
            threshold=threshold,
        )]
