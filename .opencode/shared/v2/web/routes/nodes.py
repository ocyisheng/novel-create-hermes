"""
routes/nodes.py — 叙事单元 CRUD API

GET    /api/nodes          → 节点列表（支持 ?type=&status=&limit=&offset=）
GET    /api/nodes/{id}     → 单节点详情（含 content）
POST   /api/nodes          → 创建节点
PUT    /api/nodes/{id}     → 更新节点
DELETE /api/nodes/{id}     → 归档节点（?purge=true 彻底删除）

统一通过 run_operation 调用 handlers 层，不再直接操作 GraphStore。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from graph_store import NarrativeUnit
from graph_schema import UnitType, UnitStatus
from web.deps import get_project_root
from handlers import run_operation
from web.models import NodeCreate, NodeUpdate

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


def _unit_to_out(u: NarrativeUnit) -> dict:
    """NarrativeUnit → JSON 响应 dict"""
    import json
    extra = {}
    content_raw = u.content or ""
    if isinstance(content_raw, str) and content_raw.strip().startswith("{"):
        try:
            extra = json.loads(content_raw)
        except json.JSONDecodeError:
            extra = {"_raw": content_raw[:200]}
    elif content_raw:
        extra = {"_raw": content_raw[:200]}

    return {
        "id": u.id,
        "name": u.unit_name,
        "type": u.type.value,
        "type_label": _type_label(u.type),
        "status": u.status.value,
        "confidence": u.confidence,
        "tags": list(u.tags) if u.tags else [],
        "chapter": u.chapter_number,
        "volume": getattr(u, "volume", None),
        "content": content_raw if len(content_raw) < 5000 else content_raw[:5000] + "...",
        "extra": extra,
        "version": u.version,
        "created_at": str(u.created_at) if u.created_at else None,
        "updated_at": str(u.updated_at) if u.updated_at else None,
    }


def _handler_unit_to_out(unit_dict: dict) -> dict:
    """将 handler get_unit 返回的 dict 转为 _unit_to_out 格式（含 extra 和 type_label）。"""
    import json
    content_raw = unit_dict.get("content") or ""
    extra = {}
    if isinstance(content_raw, str) and content_raw.strip().startswith("{"):
        try:
            extra = json.loads(content_raw)
        except json.JSONDecodeError:
            extra = {"_raw": content_raw[:200]}
    elif content_raw:
        extra = {"_raw": content_raw[:200]}
    utype = unit_dict.get("type", "")
    return {
        "id": unit_dict["id"],
        "name": unit_dict.get("name", ""),
        "type": utype,
        "type_label": _type_label_str(utype),
        "status": unit_dict.get("status", ""),
        "confidence": unit_dict.get("confidence", 0),
        "tags": unit_dict.get("tags", []),
        "chapter": unit_dict.get("chapter"),
        "volume": unit_dict.get("volume"),
        "content": content_raw if len(content_raw) < 5000 else content_raw[:5000] + "...",
        "extra": extra,
        "version": unit_dict.get("version", 0),
        "created_at": unit_dict.get("created_at"),
        "updated_at": unit_dict.get("updated_at"),
    }


def _type_label(t: UnitType) -> str:
    labels = {
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
    return labels.get(t, t.value)


def _type_label_str(t: str) -> str:
    """字符串版 type_label，供 handler dict 使用。"""
    labels = {
        "character_arc": "角色", "scene": "场景",
        "plot_thread": "情节线", "world_rule": "世界观",
        "thematic_motif": "主题意象", "note": "笔记",
        "chunk": "正文", "outline": "总纲",
        "arc_plan": "部篇大纲", "volume_plan": "卷大纲",
        "chapter_plan": "章纲", "structure": "结构",
        "narrative_voice": "叙述腔调",
    }
    return labels.get(t, t)


# ── GET /api/nodes ────────────────────────────────────────────────

@router.get("")
def list_nodes(
    type: str = Query("", description="筛选类型: scene/character_arc/..."),
    status: str = Query("", description="筛选状态: sprout/growing/mature/archived"),
    limit: int = Query(0, description="最大返回数, 0=不限"),
    offset: int = Query(0, description="偏移量"),
    project_root: str = Depends(get_project_root),
):
    """列出叙事单元。handlers 层 list_units 不返回完整数据，直接调 _get_store 获取。"""
    # 通过 handlers 的统一 _get_store 获取完整数据（list_units handler 数据量不足）
    from handlers.handlers_graph import _get_store
    store = _get_store(project_root)
    ut = UnitType(type) if type else None
    us = UnitStatus(status) if status else None
    units = store.find_units(type=ut, status=us)
    if not status:
        units = [u for u in units if u.status != UnitStatus.ARCHIVED]

    total = len(units)
    units.sort(key=lambda u: (u.type.value, u.unit_name))

    if offset > 0:
        units = units[offset:]
    if limit > 0:
        units = units[:limit]

    return {
        "total": total,
        "returned": len(units),
        "nodes": [_unit_to_out(u) for u in units],
    }


# ── GET /api/nodes/{id} ───────────────────────────────────────────

@router.get("/{id}")
def get_node(id: str, project_root: str = Depends(get_project_root)):
    result = run_operation("graph.get_unit", project_root=project_root, id=id)
    if "error" in result or not result.get("unit"):
        # 尝试按名称查找
        find = run_operation("graph.find_unit", project_root=project_root, name=id)
        if find.get("found") and find.get("id"):
            result = run_operation("graph.get_unit", project_root=project_root, id=find["id"])
    if "error" in result or not result.get("unit"):
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")
    return {"node": _handler_unit_to_out(result["unit"])}


# ── POST /api/nodes ───────────────────────────────────────────────

@router.post("", status_code=201)
def create_node(body: NodeCreate, project_root: str = Depends(get_project_root)):
    # 解析 content
    content = None
    if body.content is not None:
        if isinstance(body.content, (dict, list)):
            import json
            content = json.dumps(body.content, ensure_ascii=False)
        else:
            content = str(body.content)

    tags_str = ",".join(body.tags) if body.tags else None

    result = run_operation(
        "graph.create_unit",
        project_root=project_root,
        unit_type=body.unit_type,
        name=body.name,
        content=content,
        tags=tags_str,
        chapter=body.chapter,
        actor=body.actor or "web-ui",
        parent_id=body.parent_id,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # 重新获取完整单元数据以生成响应
    created_id = result["id"]
    get_result = run_operation("graph.get_unit", project_root=project_root, id=created_id)
    unit = get_result.get("unit", {})
    return {"node": _handler_unit_to_out(unit)}


# ── PUT /api/nodes/{id} ───────────────────────────────────────────

@router.put("/{id}")
def update_node(id: str, body: NodeUpdate, project_root: str = Depends(get_project_root)):
    # 解析 content
    content = None
    if body.content is not None:
        if isinstance(body.content, (dict, list)):
            import json
            content = json.dumps(body.content, ensure_ascii=False)
        else:
            content = str(body.content)

    tags_str = ",".join(body.tags) if body.tags else None

    result = run_operation(
        "graph.update_unit",
        project_root=project_root,
        id=id,
        content=content,
        name=body.name,
        tags=tags_str,
        status=body.status,
        actor=body.actor or "web-ui",
    )
    if "error" in result:
        # 区分「不存在」和其他错误
        if "不存在" in str(result["error"]):
            raise HTTPException(status_code=404, detail=f"节点不存在: {id}")
        raise HTTPException(status_code=400, detail=result["error"])

    # 重新获取完整数据
    get_result = run_operation("graph.get_unit", project_root=project_root, id=id)
    unit = get_result.get("unit", {})
    return {"node": _handler_unit_to_out(unit)}


# ── DELETE /api/nodes/{id} ────────────────────────────────────────

@router.delete("/{id}")
def delete_node(
    id: str,
    purge: bool = Query(False, description="true=彻底删除, false=归档"),
    project_root: str = Depends(get_project_root),
):
    # 先确认存在
    check = run_operation("graph.get_unit", project_root=project_root, id=id)
    if "error" in check or not check.get("unit"):
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")

    if purge:
        # 归档后 purge：退回到统一 _get_store 直接操作（handler 不支持批量移除关系）
        from handlers.handlers_graph import _get_store
        store = _get_store(project_root)
        store.archive_unit(id, actor="web-ui")
        for rel in store.get_relations(id):
            store.remove_relation(rel.id, actor="web-ui")
        store.flush()
        return {"deleted": True, "id": id, "mode": "purge"}
    else:
        result = run_operation("graph.archive_unit", project_root=project_root, id=id, actor="web-ui")
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"deleted": True, "id": id, "mode": "archive"}