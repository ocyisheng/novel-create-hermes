"""
routes/edges.py — 关系 CRUD API

GET    /api/edges       → 关系列表（支持 ?type=&source=&target=&limit=）
GET    /api/edges/{id}  → 单条关系详情
POST   /api/edges       → 创建关系
PUT    /api/edges/{id}  → 更新关系（label/weight/description/payload）
DELETE /api/edges/{id}  → 删除关系

读写分工：写操作（POST/PUT/DELETE）统一通过 run_operation 调 handlers 层
（保证 actor 审计 + 事件溯源 + 脏边增量标记）；只读操作（GET）直接走
_get_store 读取。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from graph_store import Relation
from graph_schema import RelationType
from web.deps import get_project_root
from handlers import run_operation
from handlers.handlers_graph import _get_store
from web.models import EdgeCreate, EdgeUpdate
import json

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
        "payload": r.payload or {},
    }


# ── GET /api/edges ────────────────────────────────────────────────

@router.get("")
def list_edges(
    type: str = Query("", description="筛选关系类型"),
    source: str = Query("", description="筛选源ID"),
    target: str = Query("", description="筛选目标ID"),
    limit: int = Query(0, description="最大返回数, 0=不限"),
    project_root: str = Depends(get_project_root),
):
    """列出关系。通过统一 _get_store 获取完整数据。"""
    store = _get_store(project_root)
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
def get_edge(id: str, project_root: str = Depends(get_project_root)):
    """获取单条关系详情。无对应 handler，直接通过统一 _get_store 获取。"""
    store = _get_store(project_root)
    rel = store._relations.get(id)
    if not rel:
        raise HTTPException(status_code=404, detail=f"关系不存在: {id}")
    return {"edge": _rel_to_out(rel)}


# ── PUT /api/edges/{id} ────────────────────────────────────────────

@router.put("/{id}")
def update_edge(id: str, body: EdgeUpdate, project_root: str = Depends(get_project_root)):
    """更新关系（label/weight/description/payload）。通过 run_operation 调 handlers 层。"""
    result = run_operation(
        "graph.update_relation",
        project_root=project_root,
        id=id,
        label=body.label or "",
        weight=body.weight,
        description=body.description or "",
        payload=json.dumps(body.payload, ensure_ascii=False) if body.payload is not None else None,
        actor=body.actor or "web-ui",
    )
    if "error" in result:
        status = 404 if "不存在" in result["error"] else 400
        raise HTTPException(status_code=status, detail=result["error"])

    # 回读完整关系数据（handler 返回格式较简）
    store = _get_store(project_root)
    rel = store._relations.get(id)
    if rel:
        return {"edge": _rel_to_out(rel)}
    return {"updated": True, "id": id}


# ── POST /api/edges ───────────────────────────────────────────────

@router.post("", status_code=201)
def create_edge(body: EdgeCreate, project_root: str = Depends(get_project_root)):
    """创建关系。通过 run_operation 调 handlers 层。"""
    # 验证 source/target 存在
    src = run_operation("graph.get_unit", project_root=project_root, id=body.source)
    if "error" in src or not src.get("unit"):
        raise HTTPException(status_code=404, detail=f"源节点不存在: {body.source}")
    tgt = run_operation("graph.get_unit", project_root=project_root, id=body.target)
    if "error" in tgt or not tgt.get("unit"):
        raise HTTPException(status_code=404, detail=f"目标节点不存在: {body.target}")

    result = run_operation(
        "graph.add_relation",
        project_root=project_root,
        source=body.source,
        target=body.target,
        rel_type=body.rel_type,
        label=body.label or "",
        weight=body.weight,
        bidirectional=body.bidirectional or False,
        actor=body.actor or "web-ui",
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # 回读完整关系数据（handler 返回格式较简）
    store = _get_store(project_root)
    rel = store._relations.get(result["id"])
    if rel:
        return {"edge": _rel_to_out(rel)}
    return {"edge": result}


# ── DELETE /api/edges/{id} ────────────────────────────────────────

@router.delete("/{id}")
def delete_edge(id: str, project_root: str = Depends(get_project_root)):
    """删除关系。通过 run_operation 调 handlers 层。"""
    result = run_operation(
        "graph.remove_relation",
        project_root=project_root,
        id=id,
        actor="web-ui",
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"deleted": True, "id": id}