"""
temporal_index.py — [已弃用] 全类型时间线索引。

T3.1 统一时间模型：本模块已由 unified_timeline.UnifiedTimelineIndex 取代。

保留 TemporalEventIndex 作为薄包装（DeprecationWarning），
TemporalEvent / TemporalQuery / _ContentExtractor 从 unified_timeline 再导出，
保证既有导入路径（workspace.py / web/routes/graph.py / handlers）不中断。

删除时机：所有调用方迁移到 UnifiedTimelineIndex 后，本模块可整体移除。
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Set, Tuple

from graph_schema import NarrativeUnit
from graph_store import GraphStore
from type_registry import TypeRegistry

from unified_timeline import (
    TemporalEvent,
    UnifiedTimelineIndex,
    UnifiedTimelineQuery,
    _ContentExtractor,
)

__all__ = [
    "TemporalEvent",
    "TemporalQuery",
    "TemporalEventIndex",
    "_ContentExtractor",
]


class TemporalQuery(UnifiedTimelineQuery):
    """[已弃用] 链式查询构建器（UnifiedTimelineQuery 的别名）。"""

    def __init__(self, index):
        super().__init__(index)


class TemporalEventIndex:
    """
    [已弃用] 全类型时间线索引。

    请改用 unified_timeline.UnifiedTimelineIndex：
        index = UnifiedTimelineIndex(store).build()
        events = index.query().for_entity("吕明理").range(0, 5000).by_type("cultivation").all()
    """

    def __init__(
        self,
        store: GraphStore,
        registry: Optional[TypeRegistry] = None,
    ):
        warnings.warn(
            "TemporalEventIndex 已弃用，请改用 unified_timeline.UnifiedTimelineIndex",
            DeprecationWarning,
            stacklevel=2,
        )
        self._index = UnifiedTimelineIndex(store, registry)
        self.store = store
        self.registry = registry or TypeRegistry.get_global(
            project_root=str(store.project_root)
        )
        self._events: List[TemporalEvent] = []
        self._by_entity: Dict[str, List[int]] = {}
        self._by_type: Dict[str, List[int]] = {}
        self._by_source: Dict[str, List[int]] = {}

    def build(
        self,
        use_content_fallback: Optional[bool] = None,
    ) -> "TemporalEventIndex":
        """构建时间线索引（委托 UnifiedTimelineIndex）。"""
        self._index.build(use_content_fallback=use_content_fallback)
        self._events = self._index._events
        self._by_entity = self._index._by_entity
        self._by_type = self._index._by_type
        self._by_source = self._index._by_source
        return self

    def query(self) -> TemporalQuery:
        """返回查询构建器。"""
        return TemporalQuery(self._index)

    @staticmethod
    def _parse_content(unit) -> dict:
        """安全解析 content。"""
        return UnifiedTimelineIndex._parse_content(unit)