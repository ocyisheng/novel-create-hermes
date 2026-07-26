"""
routes/edges.py — 关系 CRUD API

GET    /api/edges       → 关系列表（支持 ?type=&source=&target=&limit=）
POST   /api/edges       → 创建关系
DELETE /api/edges/{id}  → 删除关系
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from graph_store import GraphStore, Relation
from graph_schema import RelationType
from web.deps import get_store
from web.models import EdgeCreate

router = APIRouter(prefix="/api/edges", tags=["edges"])


def _rel_to_out(r: Relation) -> dict:
    return {
        "id": r.id,
        "source": r.source_id,
        "target": r.target_id,
        "type": r.relation_type.value,
        "label": r.label or "",
        "weight": r.weight,
        "description": r.description or "",
    }


# ── GET /api/edges ────────────────────────────────────────────────

@router.get("")
def list_edges(
    type: str = Query("", description="筛选关系类型"),
    source: str = Query("", description="筛选源ID"),
    target: str = Query("", description="筛选目标ID"),
    limit: int = Query(0, description="最大返回数, 0=不限"),
    store: GraphStore = Depends(get_store),
):
    rels = list(store._relations.values())

    if type:
        try:
            rtype = RelationType(type)
            rels = [r for r in rels if r.relation_type == rtype]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的关系类型: {type}")

    if source:
        rels = [r for r in rels if r.source_id == source]

    if target:
        rels = [r for r in rels if r.target_id == target]

    total = len(rels)

    if limit > 0:
        rels = rels[:limit]

    return {
        "total": total,
        "returned": len(rels),
        "edges": [_rel_to_out(r) for r in rels],
    }


# ── GET /api/edges/{id} ───────────────────────────────────────────

@router.get("/{id}")
def get_edge(id: str, store: GraphStore = Depends(get_store)):
    rel = store._relations.get(id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"关系不存在: {id}")
    return {"edge": _rel_to_out(rel)}


# ── POST /api/edges ───────────────────────────────────────────────

@router.post("", status_code=201)
def create_edge(body: EdgeCreate, store: GraphStore = Depends(get_store)):
    # 验证 source/target 存在
    if not store.get_unit(body.source):
        raise HTTPException(status_code=404, detail=f"源节点不存在: {body.source}")
    if not store.get_unit(body.target):
        raise HTTPException(status_code=404, detail=f"目标节点不存在: {body.target}")

    try:
        rel = store.add_relation(
            source_id=body.source,
            target_id=body.target,
            rel_type=body.rel_type,
            label=body.label or "",
            bidirectional=body.bidirectional,
            actor=body.actor,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"edge": _rel_to_out(rel)}


# ── DELETE /api/edges/{id} ────────────────────────────────────────

@router.delete("/{id}")
def delete_edge(id: str, store: GraphStore = Depends(get_store)):
    rel = store._relations.get(id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"关系不存在: {id}")
    store.remove_relation(id, actor="web-ui")
    return {"deleted": True, "id": id}