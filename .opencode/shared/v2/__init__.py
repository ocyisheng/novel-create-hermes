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
from adapter import LegacyFileAdapter

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
    "LegacyFileAdapter",
]
