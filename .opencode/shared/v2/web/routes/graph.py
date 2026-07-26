"""
routes/graph.py — 图谱数据 API

GET /api/graph                → 全量图谱数据（nodes+edges，供 viz 前端使用）
GET /api/graph/neighbors/{id} → Ego Network（?depth=1|2）
GET /api/graph/timeline/{id}  → 时间线数据
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from graph_store import NarrativeUnit
from graph_schema import UnitType, UnitStatus, RelationType
from web.deps import get_project_root
from handlers.handlers_graph import _get_store

router = APIRouter(prefix="/api/graph", tags=["graph"])

UNIT_TYPE_LABELS = {
    UnitType.CHARACTER_ARC: "角色",
    UnitType.SCENE: "场景",
    UnitType.PLOT_THREAD: "情节线",
    UnitType.WORLD_RULE: "世界观",
    UnitType.THEMATIC_MOTIF: "主题意象",
    UnitType.NOTE: "笔记",
    UnitType.CHUNK: "正文",
    UnitType.OUTLINE: "总纲",
    UnitType.ARC_PLAN: "部篇大纲",
    UnitType.VOLUME_PLAN: "卷大纲",
    UnitType.CHAPTER_PLAN: "章纲",
}

UNIT_TYPE_COLORS = {
    UnitType.CHARACTER_ARC: {"bg": "#5B9BD5", "border": "#2E75B6", "text": "#fff"},
    UnitType.SCENE: {"bg": "#A5A5A5", "border": "#7A7A7A", "text": "#fff"},
    UnitType.PLOT_THREAD: {"bg": "#FFC000", "border": "#BF8F00", "text": "#000"},
    UnitType.WORLD_RULE: {"bg": "#70AD47", "border": "#4E6B31", "text": "#fff"},
    UnitType.THEMATIC_MOTIF: {"bg": "#B4A7D6", "border": "#8E7CC3", "text": "#fff"},
    UnitType.NOTE: {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"},
    UnitType.CHUNK: {"bg": "#CD853F", "border": "#8B6914", "text": "#fff"},
    UnitType.OUTLINE: {"bg": "#4472C4", "border": "#2E5090", "text": "#fff"},
    UnitType.ARC_PLAN: {"bg": "#5B9BD5", "border": "#3A72B0", "text": "#fff"},
    UnitType.VOLUME_PLAN: {"bg": "#7FCDBB", "border": "#4EA08A", "text": "#000"},
    UnitType.CHAPTER_PLAN: {"bg": "#A8D08D", "border": "#70AD47", "text": "#000"},
}

RELATION_LABELS = {
    RelationType.PARTICIPATES_IN: "参与",
    RelationType.CAUSES: "导致",
    RelationType.PRECEDES: "先于",
    RelationType.CONTRADICTS: "矛盾",
    RelationType.IMPLEMENTS: "实现",
    RelationType.BELONGS_TO: "属于",
    RelationType.REFERENCES: "引用",
    RelationType.IMPLIES: "隐含",
    RelationType.PARALLEL: "并列",
    RelationType.INSPIRES: "启发",
    RelationType.REFINES: "细化",
    RelationType.LOCATED_AT: "位于",
    RelationType.ALLIED_WITH: "同盟",
    RelationType.CONTAINS: "包含",
    RelationType.CONTROLS: "统治",
    RelationType.MEMBER_OF: "成员",
    RelationType.HAS_MEMBER: "拥有成员",
    RelationType.LOCATION_OF: "所在",
    RelationType.CONTROLLED_BY: "受制",
}

RELATION_COLORS = {
    RelationType.PARTICIPATES_IN: "#5B9BD5",
    RelationType.CAUSES: "#FF4444",
    RelationType.PRECEDES: "#FFC000",
    RelationType.CONTRADICTS: "#FF6600",
    RelationType.IMPLEMENTS: "#70AD47",
    RelationType.BELONGS_TO: "#ED7D31",
    RelationType.REFERENCES: "#8888AA",
    RelationType.IMPLIES: "#8888AA",
    RelationType.PARALLEL: "#B4A7D6",
    RelationType.INSPIRES: "#B4A7D6",
    RelationType.REFINES: "#70AD47",
    RelationType.LOCATED_AT: "#00B0F0",
    RelationType.ALLIED_WITH: "#92D050",
    RelationType.CONTAINS: "#ED7D31",
    RelationType.CONTROLS: "#FF6600",
    RelationType.MEMBER_OF: "#5B9BD5",
    RelationType.HAS_MEMBER: "#5B9BD5",
    RelationType.LOCATION_OF: "#00B0F0",
    RelationType.CONTROLLED_BY: "#FF6600",
}


def _node_to_viz(u: NarrativeUnit, extra: dict = None) -> dict:
    """NarrativeUnit → vis-network 兼容的节点 dict"""
    import json
    colors = UNIT_TYPE_COLORS.get(u.type, {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"})
    extra_data = extra or {}
    if not extra_data and u.content:
        if isinstance(u.content, str) and u.content.strip().startswith("{"):
            try:
                extra_data = json.loads(u.content)
            except json.JSONDecodeError:
                extra_data = {}
    return {
        "id": u.id,
        "label": u.unit_name,
        "type": u.type.value,
        "type_label": UNIT_TYPE_LABELS.get(u.type, u.type.value),
        "color": colors,
        "size": 20,
        "status": u.status.value,
        "confidence": u.confidence,
        "tags": u.tags,
        "extra": extra_data,
    }


def _rel_to_viz(r) -> dict:
    """Relation → vis-network 兼容的边 dict"""
    label = r.label or RELATION_LABELS.get(r.relation_type, r.relation_type.value)
    color = RELATION_COLORS.get(r.relation_type, "#4a4a6a")
    return {
        "from": r.source_id,
        "to": r.target_id,
        "label": label,
        "color": color,
        "width": 1.5 if r.weight >= 0.7 else 1.0,
        "relation_type": r.relation_type.value,
    }


# ── GET /api/graph ────────────────────────────────────────────────

@router.get("")
def get_full_graph(project_root: str = Depends(get_project_root)):
    """返回全量图谱数据（用于前端 vis-network 渲染）"""
    store = _get_store(project_root)
    nodes = {}
    for u in store._units.values():
        if u.status == UnitStatus.ARCHIVED:
            continue
        nodes[u.id] = _node_to_viz(u)

    edges = []
    seen = set()
    for r in store._relations.values():
        if r.source_id in nodes and r.target_id in nodes:
            key = f"{r.source_id}-{r.target_id}-{r.relation_type.value}"
            if key not in seen:
                seen.add(key)
                edges.append(_rel_to_viz(r))

    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


# ── GET /api/graph/neighbors/{id} ─────────────────────────────────

@router.get("/neighbors/{id}")
def get_neighbors(
    id: str,
    depth: int = Query(1, description="Ego Network 深度: 1 或 2"),
    project_root: str = Depends(get_project_root),
):
    store = _get_store(project_root)
    center = store.get_unit(id)
    if not center:
        # 按名称查找
        center = store.get_unit_by_name(id)
    if not center:
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")

    nodes = {center.id: _node_to_viz(center)}
    edges = []
    visited = {center.id}
    edge_set = set()

    def _add_edge(r):
        key = f"{r.source_id}-{r.target_id}-{r.relation_type.value}"
        if key not in edge_set:
            edge_set.add(key)
            edges.append(_rel_to_viz(r))

    # 1-hop
    n1 = store.get_neighbors(center.id, max_depth=1).get(1, set())
    for nid in n1:
        u = store.get_unit(nid)
        if u and u.status != UnitStatus.ARCHIVED:
            nodes[nid] = _node_to_viz(u, hop=1)
            visited.add(nid)

    # 中心的关系
    for r in store.get_relations(center.id):
        other = r.target_id if r.source_id == center.id else r.source_id
        if other in visited:
            _add_edge(r)

    # 1-hop 之间的关系
    for nid in n1:
        for r in store.get_relations(nid):
            other = r.target_id if r.source_id == nid else r.source_id
            if other in visited and other != center.id:
                _add_edge(r)

    # 2-hop
    if depth >= 2:
        for nid in list(n1):
            n2 = store.get_neighbors(nid, max_depth=1).get(1, set())
            for nid2 in n2:
                if nid2 not in visited:
                    u2 = store.get_unit(nid2)
                    if u2 and u2.status != UnitStatus.ARCHIVED:
                        nodes[nid2] = _node_to_viz(u2, hop=2)
                        visited.add(nid2)
            for r in store.get_relations(nid):
                other = r.target_id if r.source_id == nid else r.source_id
                if other in visited:
                    _add_edge(r)

    return {
        "center_id": center.id,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ── GET /api/graph/timeline/{id} ──────────────────────────────────

@router.get("/timeline/{id}")
def get_timeline(id: str, project_root: str = Depends(get_project_root)):
    """获取指定实体的时间线数据"""
    store = _get_store(project_root)
    from time_utils import get_story_ordinal, get_story_label

    center = store.get_unit(id)
    if not center:
        center = store.get_unit_by_name(id)
    if not center:
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")

    events = []

    # 角色参与的场景
    for rel in store.get_relations(id, direction="incoming"):
        source = store.get_unit(rel.source_id)
        if source and source.type == UnitType.SCENE and source.status != UnitStatus.ARCHIVED:
            import json as _json
            content = source.content
            if isinstance(content, str):
                try:
                    content = _json.loads(content)
                except (json.JSONDecodeError, ValueError):
                    content = {}
            loc = content.get("地点", "") if isinstance(content, dict) else ""
            from graph_schema import get_unit_chapter
            events.append({
                "sort_key": get_unit_chapter(source) or 0,
                "time_label": f"第{get_unit_chapter(source) or '?'}章",
                "story_ordinal": get_story_ordinal(source),
                "story_time_label": get_story_label(source) or "",
                "event": source.unit_name,
                "source_type": "chapter",
                "node_id": source.id,
                "location": loc,
            })

    # 关联的情节线
    for rel in store.get_relations(id, direction="outgoing"):
        target = store.get_unit(rel.target_id)
        if target and target.type == UnitType.PLOT_THREAD and target.status != UnitStatus.ARCHIVED:
            events.append({
                "sort_key": -1,
                "time_label": "情节线",
                "event": f"参与情节线: {target.unit_name}",
                "source_type": "plot",
                "node_id": target.id,
            })

    # 关联的世界观
    for rel in store.get_relations(id, direction="outgoing"):
        target = store.get_unit(rel.target_id)
        if target and target.type == UnitType.WORLD_RULE:
            events.append({
                "sort_key": -2,
                "time_label": "世界观",
                "event": f"{rel.label or RELATION_LABELS.get(rel.relation_type, rel.relation_type.value)}: {target.unit_name}",
                "source_type": "world",
                "node_id": target.id,
            })

    events.sort(key=lambda e: (
        0 if e.get("story_ordinal") is not None else 1,
        e.get("story_ordinal") or e["sort_key"],
        e["event"],
    ))

    return {
        "entity": {
            "id": center.id,
            "name": center.unit_name,
            "type": UNIT_TYPE_LABELS.get(center.type, center.type.value),
        },
        "events": events,
    }