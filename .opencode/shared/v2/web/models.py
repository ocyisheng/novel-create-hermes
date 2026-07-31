"""
models.py — Pydantic 请求/响应模型
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


# ── 节点模型 ──────────────────────────────────────────────────────────

class NodeOut(BaseModel):
    id: str
    name: str = Field(alias="unit_name")
    type: str
    type_label: str = ""
    status: str = "sprout"
    confidence: float = 0.5
    tags: list[str] = []
    chapter: Optional[int] = None
    volume: Optional[int] = None
    content: Any = None
    extra: dict[str, Any] = {}
    version: int = 0


class NodeCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    unit_type: str = Field(alias="type")
    content: Optional[Any] = None
    tags: Optional[list[str]] = None
    chapter: Optional[int] = None
    parent_id: Optional[str] = None
    actor: str = "web-ui"


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[Any] = None
    tags: Optional[list[str]] = None
    status: Optional[str] = None
    actor: str = "web-ui"


# ── 关系模型 ──────────────────────────────────────────────────────────

class EdgeOut(BaseModel):
    id: str
    source: str
    target: str
    type: str
    label: str = ""
    weight: float = 0.5
    description: str = ""


class EdgeCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str
    target: str
    rel_type: str = Field(alias="type")
    label: Optional[str] = None
    bidirectional: bool = False
    actor: str = "web-ui"


class EdgeUpdate(BaseModel):
    label: Optional[str] = None
    actor: str = "web-ui"


# ── 图谱模型 ──────────────────────────────────────────────────────────

class GraphData(BaseModel):
    nodes: dict[str, NodeOut]
    edges: list[EdgeOut]


class NeighborNode(BaseModel):
    id: str
    name: str
    type: str
    type_label: str = ""
    relation: str = ""
    relation_label: str = ""
    direction: str = ""
    hop: int = 1


class TimelineEvent(BaseModel):
    sort_key: int = 0
    time_label: str = ""
    story_ordinal: Optional[float] = None
    story_time_label: str = ""
    event: str
    source_type: str = ""
    node_id: str = ""
    location: str = ""
    event_type: str = ""


class TimelineData(BaseModel):
    entity: dict[str, str]
    events: list[TimelineEvent]


# ── 搜索模型 ──────────────────────────────────────────────────────────

class SearchResultItem(BaseModel):
    unit_id: str
    unit_name: str
    unit_type: str
    content_preview: str = ""
    chapter: Optional[int] = None
    tags: list[str] = []
    status: str = ""
    score: float = 0.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SearchResults(BaseModel):
    query: str
    total: int
    results: list[SearchResultItem]
    time_ms: float = 0.0


# ── 统计模型 ──────────────────────────────────────────────────────────

class StatsData(BaseModel):
    total_units: int = 0
    total_relations: int = 0
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    archived: int = 0


# ── 项目模型 ──────────────────────────────────────────────────────────

class ProjectInfo(BaseModel):
    name: str
    root: str
    is_v2: bool = True
    stats: StatsData = StatsData()


# ── 通用 ──────────────────────────────────────────────────────────────

class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    error: str = ""