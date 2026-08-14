"""
novel-create-hermes V2 核心引擎

基于叙事单元网络的创作数据层。
取代现有的离散 YAML 文件 + 手动索引架构。

核心概念：
- NarrativeUnit: 叙事单元（场景/角色弧线/情节线/主题意象/世界观规则/笔记）
- Relation: 单元间关系（causes/precedes/contradicts/implements/...）
- EventSourcing: 所有变更追溯
- Projection: graph → 文件的自动投影

使用方式:
    from .opencode.shared.v2 import NarrativeUnit, GraphStore, ProjectionEngine

    store = GraphStore(project_root)
    unit = store.create_unit(type="scene", content="...")
    store.add_relation(unit.id, other_id, "precedes")
    store.commit("写了一个新场景")
"""

import sys
import os

# 确保 v2 目录在 sys.path 中（兼容 pytest 直接收集的场景）
V2_DIR = os.path.abspath(os.path.dirname(__file__))
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)

try:
    from graph_schema import (
        NarrativeUnit,
        UnitType,
        RelationType,
        UnitStatus,
        Relation,
        Event,
        EventType,
        ProjectionView,
    )
    from graph_store import GraphStore
    from projection_engine import ProjectionEngine
    from search_engine import SearchEngine, SearchResult, SearchResultSet
    from quality_checkers.types import CheckResult
    from deviation_manager import DeviationManager, DeviationItem, DeviationState
    from type_registry import TypeRegistry
    from temporal_index import TemporalEventIndex, TemporalEvent, TemporalQuery

    __all__ = [
        "NarrativeUnit",
        "UnitType",
        "RelationType",
        "UnitStatus",
        "Relation",
        "Event",
        "EventType",
        "ProjectionView",
        "GraphStore",
        "ProjectionEngine",
        "SearchEngine",
        "SearchResult",
        "SearchResultSet",
        "CheckResult",
        "DeviationManager",
        "DeviationItem",
        "DeviationState",
        "TypeRegistry",
        "TemporalEventIndex",
        "TemporalEvent",
        "TemporalQuery",
    ]
except ImportError:
    # 在 pytest 或部分导入场景下，graph_schema 可能尚未就绪
    # conftest.py 中的 sys.path 设置会在收集阶段处理此问题
    import warnings
    warnings.warn("V2 核心模块导入失败：graph_schema 或依赖模块未找到", ImportWarning)
    __all__ = []
