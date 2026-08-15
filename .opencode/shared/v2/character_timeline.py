"""
character_timeline.py — [已弃用] 角色时间线账本。

T3.1 统一时间模型：本模块已由 unified_timeline.UnifiedTimelineIndex 取代。

保留 CharacterTimelineLedger 作为薄包装（DeprecationWarning），
CharacterSnapshot / TimelineView / TimelineScene 从 unified_timeline 再导出，
保证既有导入路径（web/routes/graph.py / workspace.py）不中断。

删除时机：所有调用方迁移到 UnifiedTimelineIndex 后，本模块可整体移除。
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional

from graph_schema import NarrativeUnit

from unified_timeline import (
    CharacterSnapshot,
    TimelineView,
    TimelineScene,
    UnifiedTimelineIndex,
)

__all__ = [
    "CharacterSnapshot",
    "TimelineView",
    "TimelineScene",
    "CharacterTimelineLedger",
]


class CharacterTimelineLedger:
    """
    [已弃用] 角色时间线账本。

    请改用 unified_timeline.UnifiedTimelineIndex：
        index = UnifiedTimelineIndex(store)
        view = index.build_timeline_view()               # 原 ledger.build()
        view = index.build_timeline_view(event_mode=True)  # 原 ledger.build_events()
    """

    def __init__(self, store):
        warnings.warn(
            "CharacterTimelineLedger 已弃用，请改用 unified_timeline.UnifiedTimelineIndex",
            DeprecationWarning,
            stacklevel=2,
        )
        self.store = store
        self._index = UnifiedTimelineIndex(store)

    # ── 主构建方法 ──────────────────────────────────────────────────────

    def build(self) -> TimelineView:
        """扫描所有 SCENE 单元，构建排序后的时间线视图（委托 UnifiedTimelineIndex）。"""
        return self._index.build_timeline_view(event_mode=False)

    def build_events(self) -> TimelineView:
        """temporal_event 版时间线，用于无 SCENE 项目兜底（委托 UnifiedTimelineIndex）。"""
        return self._index.build_timeline_view(event_mode=True)

    # ── 查询方法 ──────────────────────────────────────────────────────────

    def get_snapshots(self, view: TimelineView, character_name: str) -> List[CharacterSnapshot]:
        """获取角色完整时间线快照（按 ordinal 排序后）"""
        return self._index.get_snapshots(view, character_name)

    def get_snapshot_before(
        self, view: TimelineView, character_name: str, chapter: int
    ) -> Optional[CharacterSnapshot]:
        """获取角色在某章之前的最后已知状态。"""
        return self._index.get_snapshot_before(view, character_name, chapter)

    def get_scene_order(self, view: TimelineView, scene_id: str) -> int:
        """获取场景在时间线中的位置索引（0-based），不存在返回 -1"""
        return self._index.get_scene_order(view, scene_id)

    def get_state_at_ordinal(
        self, view: TimelineView, character_name: str, at_ordinal: float
    ) -> Optional[TimelineScene]:
        """获取角色在指定序数时刻的最新场景（≤ at_ordinal）。"""
        return self._index.get_state_at_ordinal(view, character_name, at_ordinal)