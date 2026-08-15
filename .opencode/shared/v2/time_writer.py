"""
time_writer.py — 统一时间写入入口（TimeWriter）。

所有故事时间的写入统一经由 TimeWriter，内部委托 UnifiedTimelineIndex
完成自动序数派生，确保时间坐标与时间线索引一致。

用法：
    writer = TimeWriter(store)
    writer.set_time(unit, {"label": "清晨", "ordinal": 10100.5, "precision": "exact"})
    writer.set_time(unit, "清晨")          # 仅标签，ordinal 自动派生
    writer.auto_sync(unit)                 # 从 content 自动同步
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from graph_schema import NarrativeUnit, get_unit_chapter
from graph_store import GraphStore
from type_registry import TypeRegistry
from time_utils import set_story_time, auto_sync_story_time
from unified_timeline import UnifiedTimelineIndex


TimeSpec = Union[str, Dict[str, Any]]


class TimeWriter:
    """
    故事时间写入器 — 时间操作唯一写入入口。

    职责：
      - set_time() / write()：写入 extra["time"]（label / ordinal / precision）
      - auto_sync()：从 content JSON 自动同步时间字段
      - auto_ordinal()：自动序数派生（委托 UnifiedTimelineIndex）
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

    # ── 写入入口 ─────────────────────────────────────────────────────────

    def set_time(
        self,
        unit: NarrativeUnit,
        time_spec: TimeSpec,
        chapter: Optional[int] = None,
        auto_ordinal: bool = True,
    ) -> Dict[str, Any]:
        """
        写入故事时间到 unit.extra["time"]。

        Args:
            unit: 目标叙事单元
            time_spec: 时间规格
                - dict: {"label": str, "ordinal": float|None, "precision": str}
                - str: 仅时间标签，ordinal 自动派生
            chapter: 章节号（ordinal 自动派生时使用；缺省从单元推导）
            auto_ordinal: 当 ordinal 缺失时是否自动派生

        Returns:
            写入后的 {"label", "ordinal", "precision"}
        """
        label, ordinal, precision = self._parse_time_spec(time_spec)

        if ordinal is None and auto_ordinal:
            ch = chapter if chapter is not None else (get_unit_chapter(unit) or 0)
            ordinal = self.auto_ordinal(unit, ch)
            if precision == "vague":
                precision = "exact"

        set_story_time(unit, label=label, ordinal=ordinal, precision=precision)
        return {"label": label, "ordinal": ordinal, "precision": precision}

    def write(
        self,
        unit: NarrativeUnit,
        time_spec: TimeSpec,
        chapter: Optional[int] = None,
        auto_ordinal: bool = True,
    ) -> Dict[str, Any]:
        """set_time 的别名（兼容任务命名）。"""
        return self.set_time(unit, time_spec, chapter=chapter, auto_ordinal=auto_ordinal)

    # ── 自动同步 ─────────────────────────────────────────────────────────

    def auto_sync(self, unit: NarrativeUnit) -> bool:
        """
        从 content JSON 自动同步时间字段到 extra["time"]。
        仅在 extra["time"] 为空且 content 中有时间字段时写入。
        返回 True 表示有变更。
        """
        return auto_sync_story_time(unit)

    # ── 序数派生 ─────────────────────────────────────────────────────────

    def auto_ordinal(self, unit: NarrativeUnit, chapter: int) -> float:
        """
        自动计算序数：同章场景按创建时间排序定位。
        委托 UnifiedTimelineIndex，保证与时间线索引一致。
        """
        index = UnifiedTimelineIndex(self.store, self.registry)
        return index.auto_ordinal(unit, chapter)

    # ── 内部 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_time_spec(time_spec: TimeSpec) -> tuple:
        """解析时间规格为 (label, ordinal, precision)。"""
        if isinstance(time_spec, str):
            return time_spec, None, "vague"
        if isinstance(time_spec, dict):
            label = str(time_spec.get("label", ""))
            ordinal = time_spec.get("ordinal")
            if ordinal is not None:
                try:
                    ordinal = float(ordinal)
                except (TypeError, ValueError):
                    ordinal = None
            precision = str(time_spec.get("precision", "vague"))
            return label, ordinal, precision
        raise ValueError(
            f"time_spec 必须是 str 或 dict，收到 {type(time_spec).__name__}"
        )