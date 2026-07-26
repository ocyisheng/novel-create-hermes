"""
routes/nodes.py — 叙事单元 CRUD API

GET    /api/nodes          → 节点列表（支持 ?type=&status=&limit=&offset=）
GET    /api/nodes/{id}     → 单节点详情（含 content）
POST   /api/nodes          → 创建节点
PUT    /api/nodes/{id}     → 更新节点
DELETE /api/nodes/{id}     → 归档节点（?purge=true 彻底删除）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from graph_store import GraphStore, NarrativeUnit
from graph_schema import UnitType, UnitStatus
from web.deps import get_store
from web.models import NodeOut, NodeCreate, NodeUpdate

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
        "tags": u.tags,
        "chapter": getattr(u, "chapter", None),
        "volume": getattr(u, "volume", None),
        "content": content_raw if len(content_raw) < 5000 else content_raw[:5000] + "...",
        "extra": extra,
        "version": u.version,
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


# ── GET /api/nodes ────────────────────────────────────────────────

@router.get("")
def list_nodes(
    type: str = Query("", description="筛选类型: scene/character_arc/..."),
    status: str = Query("", description="筛选状态: sprout/growing/mature/archived"),
    limit: int = Query(0, description="最大返回数, 0=不限"),
    offset: int = Query(0, description="偏移量"),
    store: GraphStore = Depends(get_store),
):
    units = list(store._units.values())

    # 筛选类型
    if type:
        utype = UnitType(type) if type else None
        if utype:
            units = [u for u in units if u.type == utype]

    # 筛选状态
    if status:
        ustatus = UnitStatus(status) if status else None
        if ustatus:
            units = [u for u in units if u.status == ustatus]
    else:
        # 默认排除 archived
        units = [u for u in units if u.status != UnitStatus.ARCHIVED]

    total = len(units)

    # 排序: type + name
    units.sort(key=lambda u: (u.type.value, u.unit_name))

    # 分页
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
def get_node(id: str, store: GraphStore = Depends(get_store)):
    u = store.get_unit(id)
    if not u:
        # 尝试按名称查找
        u = store.get_unit_by_name(id)
    if not u:
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")
    return {"node": _unit_to_out(u)}


# ── POST /api/nodes ───────────────────────────────────────────────

@router.post("", status_code=201)
def create_node(body: NodeCreate, store: GraphStore = Depends(get_store)):
    # 解析 unit_type
    try:
        utype = UnitType(body.unit_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的单元类型: {body.unit_type}")

    # 解析 content
    content = None
    if body.content is not None:
        if isinstance(body.content, (dict, list)):
            import json
            content = json.dumps(body.content, ensure_ascii=False)
        else:
            content = str(body.content)

    # 创建单元
    try:
        unit = store.create_unit(
            unit_type=utype,
            name=body.name,
            content=content,
            tags=body.tags,
            chapter=body.chapter,
            actor=body.actor,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 如果指定了 parent_id，自动建立 CONTAINS 关系
    if body.parent_id:
        try:
            store.add_relation(
                source_id=body.parent_id,
                target_id=unit.id,
                rel_type="contains",
                actor=body.actor,
            )
        except Exception:
            pass

    return {"node": _unit_to_out(unit)}


# ── PUT /api/nodes/{id} ───────────────────────────────────────────

@router.put("/{id}")
def update_node(id: str, body: NodeUpdate, store: GraphStore = Depends(get_store)):
    u = store.get_unit(id)
    if not u:
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")

    # 解析 content
    content = None
    if body.content is not None:
        if isinstance(body.content, (dict, list)):
            import json
            content = json.dumps(body.content, ensure_ascii=False)
        else:
            content = str(body.content)

    # 解析 status
    status = None
    if body.status:
        try:
            status = UnitStatus(body.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态: {body.status}")

    try:
        unit = store.update_unit(
            unit_id=id,
            content=content,
            name=body.name,
            tags=body.tags,
            status=status,
            actor=body.actor,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"node": _unit_to_out(unit)}


# ── DELETE /api/nodes/{id} ────────────────────────────────────────

@router.delete("/{id}")
def delete_node(
    id: str,
    purge: bool = Query(False, description="true=彻底删除, false=归档"),
    store: GraphStore = Depends(get_store),
):
    u = store.get_unit(id)
    if not u:
        raise HTTPException(status_code=404, detail=f"节点不存在: {id}")

    if purge:
        # 彻底删除（hard delete）：标记为 archived，然后调用 purge
        store.archive_unit(id, actor="web-ui")
        # 删除关联关系
        for rel in store.get_relations(id):
            store.remove_relation(rel.id, actor="web-ui")
        return {"deleted": True, "id": id, "mode": "purge"}
    else:
        store.archive_unit(id, actor="web-ui")
        return {"deleted": True, "id": id, "mode": "archive"}