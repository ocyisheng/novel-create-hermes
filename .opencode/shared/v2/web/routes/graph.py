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
    # 适应深色背景 (#0f0f1a)，高饱和 + 白色文字保证可读性
    UnitType.CHARACTER_ARC:   {"bg": "#4FC3F7", "border": "#0288D1", "text": "#fff"},
    UnitType.SCENE:           {"bg": "#E0E0E0", "border": "#9E9E9E", "text": "#222"},
    UnitType.PLOT_THREAD:     {"bg": "#FFD54F", "border": "#F9A825", "text": "#222"},
    UnitType.WORLD_RULE:      {"bg": "#81C784", "border": "#388E3C", "text": "#fff"},
    UnitType.THEMATIC_MOTIF:  {"bg": "#CE93D8", "border": "#7B1FA2", "text": "#fff"},
    UnitType.NOTE:            {"bg": "#BDBDBD", "border": "#757575", "text": "#222"},
    UnitType.CHUNK:           {"bg": "#FF8A65", "border": "#D84315", "text": "#fff"},
    UnitType.OUTLINE:         {"bg": "#42A5F5", "border": "#1565C0", "text": "#fff"},
    UnitType.ARC_PLAN:        {"bg": "#29B6F6", "border": "#0277BD", "text": "#fff"},
    UnitType.VOLUME_PLAN:     {"bg": "#80CBC4", "border": "#00695C", "text": "#fff"},
    UnitType.CHAPTER_PLAN:    {"bg": "#AED581", "border": "#558B2F", "text": "#fff"},
}




def _node_to_viz(u: NarrativeUnit, extra: dict = None, hop: int = 0) -> dict:
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
    label = r.label or RelationType.label(r.relation_type)
    color = RelationType.color(r.relation_type)
    return {
        "id": r.id,
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


# ── GET /api/graph/timeline ──────────────────────────────────────

@router.get("/timeline")
def get_global_timeline(project_root: str = Depends(get_project_root)):
    """返回全局时间线：所有 SCENE 按故事时间排序，按章节分组，含角色索引"""
    store = _get_store(project_root)
    from character_timeline import CharacterTimelineLedger

    ledger = CharacterTimelineLedger(store)
    view = ledger.build()

    # 按章节分组
    chapters: dict[int, list] = {}
    for ts in view.scenes:
        ch = ts.chapter or 0
        if ch not in chapters:
            chapters[ch] = []
        chapters[ch].append({
            "unit_id": ts.unit_id,
            "unit_name": ts.unit_name,
            "ordinal": ts.ordinal,
            "precision": ts.precision,
            "time_label": ts.label,
            "location": ts.location,
            "characters": ts.characters,
            "chapter": ts.chapter,
            "is_manual_ordinal": ts.is_manual_ordinal,
        })

    # 角色索引（精简版）
    by_character = {}
    for name, scenes in view.by_character.items():
        by_character[name] = [
            {
                "unit_id": s.unit_id,
                "unit_name": s.unit_name,
                "ordinal": s.ordinal,
                "chapter": s.chapter,
                "location": s.location,
                "time_label": s.label,
            }
            for s in scenes
        ]

    return {
        "total_scenes": view.total_scenes,
        "manual_overrides": view.manual_overrides,
        "parallel_groups": view.parallel_groups,
        "chapters": [
            {"chapter": ch, "scenes": scenes}
            for ch, scenes in sorted(chapters.items())
        ],
        "by_character": by_character,
    }


# ── GET /api/graph/timeline/{id} ──────────────────────────────────

@router.get("/timeline/{id}")
def get_timeline(id: str, project_root: str = Depends(get_project_root)):
    """获取指定实体的时间线数据（跨类型，含 scene/cultivation/plot/chronicle 等）"""
    store = _get_store(project_root)

    center = store.get_unit(id)
    if not center:
        center = store.get_unit_by_name(id)
    if not center:
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")

    from temporal_index import TemporalEventIndex
    index = TemporalEventIndex(store).build()
    focus_name = center.unit_name

    # 通过实体名查询所有关联事件
    raw_events = index.query().for_entity(focus_name).limit(100).all()

    events = []
    for e in raw_events:
        events.append({
            "sort_key": e.ordinal if e.ordinal is not None else 0,
            "time_label": e.time_label,
            "story_ordinal": e.ordinal,
            "story_time_label": e.time_label,
            "event": f"[{e.event_type}] {e.summary}" if e.event_type != "scene_event" else e.summary,
            "source_type": e.source_type,
            "node_id": e.source_id,
            "location": e.location,
            "event_type": e.event_type,
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