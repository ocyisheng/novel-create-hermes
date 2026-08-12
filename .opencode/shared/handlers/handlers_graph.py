"""
handlers_graph.py — graph 领域纯业务逻辑函数。

涵盖 26 个操作：graph CRUD、搜索、导出、关系管理、层级查询、迁移、可视化。
每个 handler 接受规范化参数名，返回 Python dict。
"""

import io
import json
import logging
import os
import re
from contextlib import redirect_stdout

from pathlib import Path
from typing import Any, Optional

from ._common import (
    ensure_sys_path,
    _SHARED_DIR, _V2_DIR,
    _find_novels_root, _resolve_project,
    _paginate,
    _derive_progress, _vol_num, _vol_name,
    set_orchestrator_write_blocked, check_write_permission,
    check_planner_restriction,
    _repair_content, _parse_tags, _unit_to_dict,
    _validate_content_schema, _auto_detect_chapter,
    _chunk_source_path, _read_chunk_text,
    _resolve_rel_type,
)

logger = logging.getLogger(__name__)

# _GET_STORE 注入钩子（守护进程模式使用）
# 由 novel_tool.py --daemon 通过 set_store_provider() 注入缓存版 _get_store。
# 非 daemon 模式下保持 None，_get_store 行为不变。
_GET_STORE_IMPL = None


def set_store_provider(provider):
    """供守护进程注入缓存版 _get_store。
    
    Args:
        provider: 一个可调用对象，签名同 _get_store(project_root: str) -> GraphStore
    """
    global _GET_STORE_IMPL
    _GET_STORE_IMPL = provider


# 确保 sys.path 包含 shared/ 和 v2/
ensure_sys_path()


def _get_store(project_root: str):
    if _GET_STORE_IMPL is not None:
        return _GET_STORE_IMPL(project_root)
    if not project_root:
        raise ValueError("项目路径为空")
    resolved = _resolve_project(project_root)
    from graph_store import GraphStore
    store = GraphStore(resolved)
    store.initialize()
    # 自动注册约束引擎到 post_flush 钩子
    _register_constraint_engine(store)
    return store


def _register_constraint_engine(store):
    """注册约束引擎到 GraphStore 的 post_flush 钩子。"""
    try:
        from constraint_engine import ConstraintEngine
        engine = ConstraintEngine(store)
        engine.register_with_store()
    except Exception:
        pass  # 约束引擎注册失败不影响核心功能


def _get_engine(project_root: str):
    from search_engine import SearchEngine
    store = _get_store(project_root)
    return store, SearchEngine(store)


# ── Handler 函数 ─────────────────────────────────────────────────────────

def handle_list_relation_types() -> dict:
    """列出所有可用关系类型，含中文显示名。"""
    from graph_schema import RelationType
    return {
        "relation_types": [
            {
                "value": rt.value, "name": rt.name,
                "inverse": rt.inverse.value if rt.inverse != rt else rt.value,
                "label_zh": RelationType.label(rt),
            }
            for rt in RelationType
        ]
    }


def handle_get_unit(project_root: str, id: str = "", name: str = "") -> dict:
    """获取叙事单元详情。"""
    store = _get_store(project_root)
    if id:
        u = store.get_unit(id)
    elif name:
        u = store.get_unit_by_name(name)
    else:
        return {"error": "get_unit 需要 id 或 name"}
    if not u:
        return {"unit": None}
    return {"unit": _unit_to_dict(u)}


def handle_find_unit(project_root: str, name: str = "", keyword: str = "", limit: int = 10) -> dict:
    """按名称或关键词查找叙事单元 ID。
    
    Args:
        name: 精确单元名称（name 和 keyword 至少提供一个）
        keyword: 模糊关键词搜索（name 和 keyword 至少提供一个）
        limit: 最大返回结果数（默认 10）
    
    Returns:
        单个精确 ID（name 匹配时），或候选列表（keyword 搜索时）
    """
    store, engine = _get_engine(project_root)
    
    if name and not keyword:
        # 精确匹配（原有逻辑）
        u = store.get_unit_by_name(name)
        if not u:
            return {"id": None, "found": False, "message": f"未找到名称为「{name}」的叙事单元"}
        return {"id": u.id, "found": True}
    
    if keyword and not name:
        # 模糊搜索
        result = engine.search(keyword=keyword, max_results=limit)
        items = []
        for r in result.results:
            items.append({
                "unit_id": r.unit_id,
                "unit_name": r.unit_name,
                "unit_type": r.unit_type.value if hasattr(r.unit_type, "value") else str(r.unit_type),
                "content_preview": r.content_preview[:120] + "..." if len(r.content_preview) > 120 else r.content_preview,
                "score": r.score,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            })
        return {"id": None, "found": len(items) > 0, "candidates": items, "total": result.total,
                "message": f"找到 {result.total} 个匹配结果，请指定精确 name 或从 candidates 中选择"}
    
    return {"id": None, "found": False, "message": "请提供 name（精确匹配）或 keyword（模糊搜索）"}


def handle_search(
    project_root: str,
    keyword: str = "",
    pattern: str = "",
    name: str = "",
    scope: Optional[list[str]] = None,
    regex: bool = False,
    case_sensitive: bool = False,
    limit: int = 20,
    verbose: bool = False,
    tags: Optional[list] = None,
    chapter: Optional[int] = None,
) -> dict:
    """搜索叙事单元。接受 scope 为列表或逗号分隔字符串。"""
    from graph_schema import UnitType
    # 兼容 string → list（novel_tool 可能传 "CHARACTER_ARC,SCENE" 这样的字符串）
    if isinstance(scope, str):
        scope = [s.strip() for s in scope.split(",") if s.strip()]
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    types = None
    if scope:
        types = [UnitType[s.upper()] for s in scope if s.strip()]
    _store, engine = _get_engine(project_root)
    result = engine.search(
        keyword=keyword, pattern=pattern, name=name,
        scope=types, regex=regex, case_sensitive=case_sensitive,
        max_results=limit,
        tags=tags, chapter=chapter,
    )
    items = []
    for r in result.results:
        item = {
            "unit_id": r.unit_id, "unit_name": r.unit_name,
            "unit_type": r.unit_type.value if hasattr(r.unit_type, "value") else str(r.unit_type),
            "content_preview": r.content_preview,
            "content_length": r.content_length, "chapter": r.chapter,
            "score": r.score, "tags": r.tags,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "version": r.version, "neighbors": r.neighbors,
            "created_at": r.created_at, "updated_at": r.updated_at,
        }
        if verbose:
            u = _store.get_unit(r.unit_id)
            if u:
                item["content"] = u.content
        items.append(item)
    items, total = _paginate(items, limit, 0)
    return {
        "total": total,
        "returned": len(items),
        "truncated": len(items) < total,
        "time_ms": result.time_ms,
        "results": items,
    }


def handle_list_units(project_root: str, unit_type: str = "", limit: int = 0, status: str = "", tags: Optional[list] = None, chapter: Optional[int] = None, volume: Optional[int] = None, offset: int = 0) -> dict:
    """列出叙事单元。status 可选：archived/mature/sprout/growing/frozen。为空时默认排除 archived。"""
    from graph_schema import UnitType, UnitStatus
    ut = UnitType[unit_type.upper()] if unit_type and unit_type.upper() != "ALL" else None
    store = _get_store(project_root)
    status_obj = UnitStatus[status.upper()] if status and status.upper() else None
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    units = store.find_units(type=ut, status=status_obj, tags=tags, chapter=chapter, volume=volume)
    units, total = _paginate(units, limit, offset)
    return {
        "units": [
            {
                "id": u.id, "name": u.unit_name,
                "type": u.type.value if hasattr(u.type, "value") else str(u.type),
                "status": u.status.value if hasattr(u.status, "value") else str(u.status),
                "created_at": str(u.created_at) if u.created_at else None,
                "updated_at": str(u.updated_at) if u.updated_at else None,
            }
            for u in units
        ],
        "total": total,
        "returned": len(units),
        "truncated": len(units) < total,
    }


def handle_stats(project_root: str) -> dict:
    """graph 统计。"""
    store = _get_store(project_root)
    return store.stats()


def handle_get_modified_units(project_root: str, since_version: int = 0, limit: int = 0, offset: int = 0) -> dict:
    """获取从指定版本号以来修改过的单元。"""
    _store, engine = _get_engine(project_root)
    changed = engine.get_modified_units(since_version=since_version)
    changed, total = _paginate(changed, limit, offset)
    return {
        "units": [
            {
                "id": u.id, "name": u.unit_name,
                "type": u.type.value if hasattr(u.type, "value") else str(u.type),
                "version": u.version,
                "status": u.status.value if hasattr(u.status, "value") else str(u.status),
                "created_at": str(u.created_at) if u.created_at else None,
                "updated_at": str(u.updated_at) if u.updated_at else None,
            }
            for u in changed
        ],
        "total": total,
        "returned": len(changed),
        "truncated": len(changed) < total,
    }


def handle_get_neighbors(project_root: str, id: str, rel_type: str = "", limit: int = 0, max_depth: int = 1) -> dict:
    """查询关联关系。"""
    from graph_schema import RelationType
    store = _get_store(project_root)
    rt = RelationType[rel_type.upper()] if rel_type else None
    neighbors = store.get_neighbors(id, relation_type=rt, max_depth=max_depth)
    result = []
    for nid in neighbors.get(1, set()):
        n = store.get_unit(nid)
        if n:
            # 获取该邻居与源单元的关系权重
            rels = store.get_relations(unit_id=nid, direction="both")
            weight = 0.0
            for r in rels:
                if (r.source_id == id and r.target_id == nid) or (r.source_id == nid and r.target_id == id):
                    weight = r.weight
                    break
            result.append({
                "id": n.id, "name": n.unit_name,
                "type": n.type.value if hasattr(n.type, "value") else str(n.type),
                "weight": weight,
                "created_at": str(n.created_at) if n.created_at else None,
                "updated_at": str(n.updated_at) if n.updated_at else None,
            })
    # 确定性排序：weight 降序，id 升序
    result.sort(key=lambda x: (-x["weight"], x["id"]))
    result, total = _paginate(result, limit, 0)
    return {"neighbors": result, "total": total, "returned": len(result), "truncated": len(result) < total}


def handle_check_consistency(project_root: str) -> dict:
    """一致性检查。"""
    _store, engine = _get_engine(project_root)
    results = engine.check_consistency()
    return {
        "total": len(results),
        "findings": [
            {
                "rule_id": r.rule_id, "rule_name": r.rule_name,
                "severity": r.severity, "description": r.description,
                "units_involved": r.units_involved, "detail": r.detail,
            }
            for r in results
        ],
    }


def handle_quality_check(
    project_root: str,
    layers: Optional[str] = None,
    full: bool = False,
) -> dict:
    """统一质量检查。"""
    from narrative_quality_engine import NarrativeQualityEngine
    from quality_checkers.types import QualityReport

    store = _get_store(project_root)
    engine = NarrativeQualityEngine(store)

    layer_list = None
    if layers:
        layer_list = [l.strip() for l in layers.split(",")]

    report = engine.run(layers=layer_list)

    return {
        "mechanical_results": [
            {
                "rule_id": r.rule_id, "rule_name": r.rule_name,
                "severity": r.severity, "description": r.description,
                "units_involved": r.units_involved, "detail": r.detail,
                "source": r.source.value if hasattr(r.source, "value") else str(r.source),
            }
            for r in report.mechanical_results
        ],
        "statistical_signals": [
            {
                "rule_id": s.rule_id, "rule_name": s.rule_name,
                "signal_type": s.signal_type,
                "signal_data": s.signal_data,
                "units_involved": s.units_involved,
                "raw_value": s.raw_value,
                "threshold": s.threshold,
            }
            for s in report.statistical_signals
        ],
        "deviations_created": report.deviations_created,
        "timestamp": report.timestamp,
    }


def handle_recent_events(project_root: str, limit: int = 10) -> dict:
    """最近事件。"""
    store = _get_store(project_root)
    events = store._events[-int(limit):] if hasattr(store, "_events") else []
    return {
        "events": [
            {
                "timestamp": str(e.timestamp), "actor": e.actor,
                "event_type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
                "session_id": getattr(e, "session_id", None),
            }
            for e in events
        ],
    }


def handle_create_unit(
    project_root: str,
    unit_type: str,
    name: str,
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    tags: Optional[str] = None,
    chapter: Optional[int] = None,
    actor: str = "orchestrator",
    parent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    if_exists: Optional[str] = None,
) -> dict:
    """创建叙事单元。

    Args:
        if_exists: 单元已存在时的处理策略（防重复创建的硬保障，透传给
                   GraphStore.create_unit）：
            - 不传 / "error"（默认）: 同名同类型单元已存在 → 返回错误，拒绝重复创建
            - "skip": 已存在 → 幂等返回已有单元（不重新建边/抽事件）
            - "create": 强制新建（旧行为，通常仅内部流程用）
    """
    blocked = check_write_permission(actor, "graph.create_unit")
    if blocked:
        return blocked
    from graph_schema import UnitType, UnitStatus
    from relation_inferrer import RelationInferrer

    ut = UnitType[unit_type.upper()]

    # novel-planner 仅允许创建 NOTE 单元（D17 白名单物理强制）
    if actor == "novel-planner" and ut != UnitType.NOTE:
        return check_planner_restriction(
            actor, "graph.create_unit",
            allowed_hint="规划主 agent 只能创建 note（创作笔记）。如需创建其他类型，请切换到 novel-writer",
        )

    # 内容读取优先级：file_path > content
    if file_path:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    if content:
        content = _repair_content(content)

    tags_list = _parse_tags(tags)

    # 自动推断章节号
    if chapter is None:
        chapter = _auto_detect_chapter(content or "", name)

    store = _get_store(project_root)
    source_channel = "llm" if actor in ("novel-v2-crafter", "v2-crafter", "novel-writer") else ("planner" if actor == "novel-planner" else "manual")
    store.set_session_context(session_id)
    try:
        # skip 模式前置查重：已存在（非归档）则直接返回已有单元，跳过关系推断/事件抽取
        if_exists_effective = if_exists or "error"
        if if_exists_effective == "skip":
            existing = store.get_unit_by_name(name)
            if (existing is not None and existing.type == ut
                    and existing.status != UnitStatus.ARCHIVED):
                return {
                    "id": existing.id,
                    "name": existing.unit_name,
                    "unit_name": existing.unit_name,
                    "type": ut.value,
                    "created_at": str(existing.created_at) if existing.created_at else None,
                    "updated_at": str(existing.updated_at) if existing.updated_at else None,
                    "duplicated": True,
                    "skipped": True,
                    "relations_created": 0,
                    "temporal_events_created": 0,
                    "schema_errors": [],
                    "hint": "单元已存在，if_exists=skip 幂等返回已有单元，未重复创建",
                }

        try:
            u = store.create_unit(
                type=ut, unit_name=name, content=content,
                tags=tags_list, chapter_number=chapter,
                parent_id=parent_id, actor=actor,
                session_id=session_id,
                if_exists=if_exists_effective,
            )
        except ValueError as e:
            return {
                "error": f"创建叙事单元失败: {e}",
                "hint": f"单元「{name}」可能已存在。请使用 novel-tool(operation=\"graph.find_unit\", name=\"{name}\") "
                        f"确认，改用 graph.update_unit 修改，或显式传 if_exists=create / if_exists=skip。",
            }

        inferrer = RelationInferrer(store)
        created = inferrer.infer_on_create(u)

        # 事件抽取：从 content 自动提取并创建 TEMPORAL_EVENT
        # （内部建 te_ 单元统一用 if_exists=skip，杜绝重复事件）
        temporal_count = _run_event_extractor(store, u, actor=actor, if_exists="skip")

        store.flush()
    finally:
        store.clear_session_context()

    schema_errors = _validate_content_schema(ut, content)

    return {
        "id": u.id,
        "name": u.unit_name,
        "unit_name": u.unit_name,
        "type": ut.value,
        "created_at": str(u.created_at) if u.created_at else None,
        "updated_at": str(u.updated_at) if u.updated_at else None,
        "relations_created": created,
        "temporal_events_created": temporal_count,
        "schema_errors": schema_errors,
    }


def handle_update_unit(
    project_root: str,
    id: str,
    content: Optional[str] = None,
    file_path: Optional[str] = None,
    name: Optional[str] = None,
    tags: Optional[str] = None,
    status: Optional[str] = None,
    actor: str = "orchestrator",
    session_id: Optional[str] = None,
) -> dict:
    """更新叙事单元。"""
    blocked = check_write_permission(actor, "graph.update_unit")
    if blocked:
        return blocked
    from graph_schema import UnitStatus, UnitType
    from relation_inferrer import RelationInferrer

    # 内容读取优先级：file_path > content
    if file_path:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
    if content:
        content = _repair_content(content)

    tags_list = _parse_tags(tags)
    status_obj = UnitStatus[status.upper()] if status else None

    store = _get_store(project_root)
    store.set_session_context(session_id)
    try:
        # 预读取旧单元，判断内容是否有实际变更
        old_unit = store.get_unit(id)
        # novel-planner 仅允许更新 NOTE 单元
        if actor == "novel-planner" and old_unit and old_unit.type != UnitType.NOTE:
            return check_planner_restriction(
                actor, "graph.update_unit",
                allowed_hint="规划主 agent 只能修改 note（创作笔记）",
            )
        old_content = old_unit.content if old_unit else None
        content_changed = (content is not None and content != old_content)

        u = store.update_unit(
            unit_id=id, content=content,
            unit_name=name if name else None,
            tags=tags_list, status=status_obj, actor=actor,
            session_id=session_id,
        )
        if not u:
            return {"error": "更新失败：叙事单元不存在"}

        # 仅在内容实际变更时才运行关系推断和事件抽取（避免 O(n) 全量扫描）
        created = 0
        temporal_count = 0
        if content_changed:
            inferrer = RelationInferrer(store)
            created = inferrer.infer_on_create(u)
            temporal_count = _run_event_extractor(store, u, actor=actor, old_content=old_content)
        store.flush()
    finally:
        store.clear_session_context()

    schema_errors = _validate_content_schema(u.type, content) if content else []

    return {
        "id": u.id,
        "name": u.unit_name,
        "version": u.version,
        "tags": list(u.tags),
        "created_at": str(u.created_at) if u.created_at else None,
        "updated_at": str(u.updated_at) if u.updated_at else None,
        "relations_created": created,
        "temporal_events_created": temporal_count,
        "schema_errors": schema_errors,
    }


def handle_archive_unit(project_root: str, id: str, actor: str = "orchestrator") -> dict:
    """归档叙事单元。"""
    blocked = check_write_permission(actor, "graph.archive_unit")
    if blocked:
        return blocked
    # novel-planner 不允许归档任何单元（统一白名单校验）
    blocked = check_planner_restriction(actor, "graph.archive_unit")
    if blocked:
        return blocked
    store = _get_store(project_root)
    ok = store.archive_unit(id, actor=actor)
    if ok:
        store.flush()
        return {"archived": True}
    return {"error": "归档失败：叙事单元不存在"}


def handle_purge_archived(project_root: str, ids: str = "", force: bool = False, actor: str = "orchestrator") -> dict:
    """
    物理删除已归档的叙事单元及其关联边。

    安全规则：
    - 传 ids（逗号分隔）→ 只删除指定 ID
    - 不传 ids → 默认报错（防止误删全部），仅当 force=true 时才允许删除全部已归档单元
    """
    blocked = check_write_permission(actor, "graph.purge_archived")
    if blocked:
        return blocked
    # novel-planner 不允许物理删除（统一白名单校验）
    blocked = check_planner_restriction(
        actor, "graph.purge_archived",
        allowed_hint="规划主 agent 不获得物理删除权限",
    )
    if blocked:
        return blocked
    store = _get_store(project_root)
    id_list = [i.strip() for i in ids.split(",") if i.strip()] if ids else None
    if id_list is None and not force:
        return {
            "error": (
                "未指定 ids，默认不执行全量删除（防止误删）。"
                "如需删除指定单元请传 ids='id1,id2'；"
                "如确需删除全部已归档单元请传 force=true。"
            )
        }
    result = store.purge_archived(ids=id_list, actor=actor)
    store.flush()
    count = result["purged_units"]
    rel_count = result["removed_relations"]
    if count == 0:
        return {"purged": 0, "removed_relations": 0, "message": "没有已归档的叙事单元需要删除"}
    return {
        "purged": count,
        "removed_relations": rel_count,
        "unit_ids": result["unit_ids"],
        "message": f"已物理删除 {count} 个归档单元，移除 {rel_count} 条关联关系",
    }


def handle_add_relation(
    project_root: str,
    source: str,
    target: str,
    rel_type: str,
    bidirectional: bool = False,
    label: str = "",
    source_role: str = "",
    target_role: str = "",
    weight: Optional[float] = None,
    actor: str = "orchestrator",
    session_id: Optional[str] = None,
    payload: Optional[str] = None,
) -> dict:
    """建立关系。

    bidirectional 按 auto_reverse 三态处理：
    - always（对称/配对）：建正向即物化反向边
    - optional（层级）：显式 bidirectional=True 时允许物化
    - never（单向断言）：忽略 bidirectional，不建反向（返回警告）

    证据锚点：payload 合并 source 通道（crafter → llm，其余 → manual），
    再与调用方传入的 payload（JSON 字符串，可选）合并。
    """
    blocked = check_write_permission(actor, "graph.add_relation")
    if blocked:
        return blocked
    from graph_schema import RelationType, UnitType
    rtype, fallback_label = _resolve_rel_type(rel_type)
    effective_label = label or fallback_label
    store = _get_store(project_root)
    # novel-planner 仅允许建立涉及 NOTE 的关系
    if actor == "novel-planner":
        src_unit = store.get_unit(source)
        tgt_unit = store.get_unit(target)
        src_is_note = src_unit and src_unit.type == UnitType.NOTE
        tgt_is_note = tgt_unit and tgt_unit.type == UnitType.NOTE
        if not (src_is_note or tgt_is_note):
            return check_planner_restriction(
                actor, "graph.add_relation",
                allowed_hint="规划主 agent 只能为 note 建立关系。如需角色↔角色关系请切换到 novel-writer",
            )
    store.set_session_context(session_id)
    # 证据锚点：按 actor 判定来源通道
    source_channel = "llm" if actor in ("novel-v2-crafter", "v2-crafter", "novel-writer") else ("planner" if actor == "novel-planner" else "manual")
    payload_dict = {}
    if payload:
        try:
            parsed = json.loads(payload) if isinstance(payload, str) else payload
            if isinstance(parsed, dict):
                payload_dict = parsed
        except json.JSONDecodeError:
            payload_dict = {}
    payload_dict.setdefault("source", source_channel)
    try:
        rel = store.add_relation(source, target, rtype, actor=actor, label=effective_label,
                                 source_role=source_role or "", target_role=target_role or "",
                                 weight=weight if weight is not None else 0.5,
                                 session_id=session_id, payload=payload_dict)
        if not rel:
            return {"error": "关系建立失败"}
        result = {"id": rel.id, "type": rtype.value}
        if effective_label:
            result["label"] = effective_label
        if source_role:
            result["source_role"] = source_role
        if target_role:
            result["target_role"] = target_role
        if payload_dict:
            result["payload"] = payload_dict

        if bidirectional and rtype.auto_reverse != "never":
            # 统一翻转规则：交换端点 + 类型 inverse + role 跟随端点 + label 保持
            inv = rtype.inverse
            inv_rel = store.add_relation(target, source, inv, actor=actor, label=effective_label,
                                         source_role=target_role or "", target_role=source_role or "",
                                         weight=weight if weight is not None else 0.5,
                                         session_id=session_id, payload=payload_dict)
            if inv_rel:
                result["inverse_id"] = inv_rel.id
        elif bidirectional and rtype.auto_reverse == "never":
            result["warning"] = (
                f"关系类型 {rtype.value} 为单向断言（auto_reverse=never），未创建反向边"
            )
        store.flush()
    finally:
        store.clear_session_context()
    return result


def handle_update_relation(
    project_root: str,
    id: str,
    label: str = "",
    weight: Optional[float] = None,
    description: str = "",
    payload: Optional[str] = None,
    source_role: str = "",
    target_role: str = "",
    actor: str = "orchestrator",
) -> dict:
    """更新单条关系（label/weight/description/payload/source_role/target_role）。

    统一走 store 的事件记录 + 脏边标记，保证 RELATION_UPDATED 事件
    与 _dirty_relation_ids 增量检查不缺失（Web PUT 此前直改 store 绕过此处）。
    """
    from datetime import datetime, timezone
    from graph_schema import EventType
    blocked = check_write_permission(actor, "graph.update_relation")
    if blocked:
        return blocked
    # novel-planner 不允许更新关系（统一白名单校验）
    blocked = check_planner_restriction(
        actor, "graph.update_relation",
        allowed_hint="规划主 agent 不获得更新关系权限",
    )
    if blocked:
        return blocked
    store = _get_store(project_root)
    rel = store.get_relation(id)
    if not rel:
        return {"error": f"关系不存在: {id}"}

    changed = False
    if label and label != rel.label:
        rel.label = label
        changed = True
    if weight is not None and weight != rel.weight:
        rel.weight = weight
        changed = True
    if description and description != rel.description:
        rel.description = description
        changed = True
    if source_role and source_role != rel.source_role:
        rel.source_role = source_role
        changed = True
    if target_role and target_role != rel.target_role:
        rel.target_role = target_role
        changed = True
    if payload is not None:
        try:
            payload_dict = json.loads(payload) if isinstance(payload, str) else payload
        except json.JSONDecodeError:
            return {"error": f"payload 不是合法 JSON: {payload}"}
        if not isinstance(payload_dict, dict):
            return {"error": "payload 必须是 JSON 对象"}
        if payload_dict != rel.payload:
            # update_relation_payload 内部完成事件 + 脏标记（公共 API，已封装）
            store.update_relation_payload(id, payload_dict, actor=actor)
            changed = True

    # 封装缺口：非 payload 字段（label/weight/description/source_role/target_role）
    # 目前 graph_store 尚无公共 API（仅 update_relation_payload 存在），因此这里
    # 直接改 rel 字段并触碰私有 _dirty_edges / _record_event。引擎 Agent 正在并行
    # 添加 store 侧 update_relation_meta()，届时应改为委托。注意 payload 分支已由
    # update_relation_payload 内部记录 RELATION_UPDATED 事件，此处不再重复判定。
    if changed:
        rel.updated_at = datetime.now(timezone.utc)
        store._dirty_edges = True
        store._record_event(
            EventType.RELATION_UPDATED,
            actor=actor,
            target_type="relation",
            target_ids=[id],
            payload={
                "relation_type": rel.relation_type.value,
                "source_id": rel.source_id,
                "target_id": rel.target_id,
            },
        )
        store.flush()
    return {"id": id, "updated": changed}


def handle_flush(project_root: str, skip_constraint_check: bool = False) -> dict:
    """持久化 graph 数据。flush 后自动触发约束检查（除非跳过）。"""
    from deviation_manager import DeviationManager
    store = _get_store(project_root)
    store.flush(skip_constraint_check=skip_constraint_check)
    
    # 收集本次约束检查产生的偏差概要（不阻断 flush）
    try:
        dm = DeviationManager(project_root)
        pending = dm.filter_for_presentation()
        stats = dm.stats()
        return {
            "ok": True,
            "constraint_check": {
                "pending_count": len(pending),
                "total_deviations": stats["total"],
                "by_severity": stats.get("by_severity", {}),
                "by_status": stats.get("by_status", {}),
            }
        }
    except Exception as e:
        logger.warning("flush 后约束检查概要收集失败: %s", e)
        return {"ok": True, "constraint_check": None}


def handle_constraint_check(project_root: str, full: bool = False) -> dict:
    """手动触发约束检查。

    run() / run_incremental() 内部已自动持久化到 DeviationManager
    （constraint_engine.run → _persist_results），此处不再重复调用
    _persist_results，避免每次手动检查让偏差 detection_count 翻倍。
    """
    from constraint_engine import ConstraintEngine
    store = _get_store(project_root)
    engine = ConstraintEngine(store)
    if full:
        results = engine.run(full=True)
    else:
        results = engine.run_incremental()
    return {
        "checked": True,
        "total_results": len(results),
        "results": [
            {"rule_id": r.rule_id, "severity": r.severity,
             "description": r.description, "units_involved": r.units_involved}
            for r in results
        ],
    }


def handle_fix_asymmetry(project_root: str) -> dict:
    """补齐 auto_reverse=always 类型的缺失反向边。

    三态过滤：
    - always（对称/配对）：补齐缺失反向边（inverse 类型）
    - optional（层级 CONTAINS/BELONGS_TO）：跳过——层级一条边足够，补反向可能制造环
    - never（单向断言 CAUSES/PRECEDES 等）：跳过——A→B 不蕴含 B→A，补反向是语义错误
    """
    from graph_schema import RelationType
    store = _get_store(project_root)
    created = 0
    skipped = 0
    for rel in list(store._relations.values()):
        rtype = rel.relation_type
        if rtype.auto_reverse != "always":
            skipped += 1
            continue
        inv = rtype.inverse
        rev_source, rev_target = rel.target_id, rel.source_id
        rev_type = inv if inv != rtype else rtype
        exists = any(
            r.source_id == rev_source and r.target_id == rev_target and r.relation_type == rev_type
            for r in store._relations.values()
        )
        if exists:
            skipped += 1
            continue
        # role 跟随端点：反向边的 source_role 取原边 target_role，target_role 取原边 source_role
        r = store.add_relation(rev_source, rev_target, rev_type,
                               weight=rel.weight, description="auto-filled reverse",
                               source_role=rel.target_role or "", target_role=rel.source_role or "",
                               actor="fix-asymmetry",
                               payload={"source": "auto", "auto_filled_reverse": True})
        if r:
            created += 1
    store.flush()
    return {"created": created, "skipped": skipped}


def handle_get_relations(
    project_root: str,
    id: str = "",
    rel_type: str = "",
    direction: str = "both",
    label: str = "",
    label_substring: bool = False,
    role: str = "",
    role_substring: bool = False,
    min_weight: Optional[float] = None,
    max_weight: Optional[float] = None,
    limit: int = 0,
    offset: int = 0,
) -> dict:
    """获取关系列表。"""
    from graph_schema import RelationType
    store = _get_store(project_root)
    rt = RelationType[rel_type.upper()] if rel_type else None
    relations = store.get_relations(unit_id=id or None, relation_type=rt, direction=direction,
                                    label=label or None, label_substring=label_substring,
                                    role=role or None, role_substring=role_substring,
                                    min_weight=min_weight, max_weight=max_weight)
    relations, total = _paginate(relations, limit, offset)
    return {
        "relations": [
            {
                "id": r.id, "source_id": r.source_id,
                "target_id": r.target_id,
                "type": r.relation_type.value,
                "weight": r.weight, "description": r.description,
                "label": r.label,
                "source_role": r.source_role,
                "target_role": r.target_role,
                "payload": r.payload or {},
            }
            for r in relations
        ],
        "total": total,
        "returned": len(relations),
        "truncated": len(relations) < total,
    }


def handle_remove_relation(
    project_root: str,
    id: str = "",
    source: str = "",
    target: str = "",
    rel_type: str = "",
    actor: str = "orchestrator",
) -> dict:
    """删除关系。"""
    blocked = check_write_permission(actor, "graph.remove_relation")
    if blocked:
        return blocked
    # novel-planner 不允许删除关系（统一白名单校验）
    blocked = check_planner_restriction(
        actor, "graph.remove_relation",
        allowed_hint="规划主 agent 不获得删除关系权限",
    )
    if blocked:
        return blocked
    from graph_schema import RelationType
    store = _get_store(project_root)

    if id:
        ok = store.remove_relation(id, actor=actor)
        removed_id = id
    elif source and target and rel_type:
        rtype = RelationType[rel_type.upper()]
        found = None
        for r in store.get_relations():
            if r.source_id == source and r.target_id == target and r.relation_type == rtype:
                found = r
                break
        if found:
            ok = store.remove_relation(found.id, actor=actor)
            removed_id = found.id
        else:
            return {"error": "未找到匹配的关系"}
    else:
        return {"error": "remove_relation 需要 id 或 source+target+type"}

    if not ok:
        return {"error": "关系不存在或删除失败"}
    store.flush()
    return {"removed": True, "relation_id": removed_id}


def handle_batch_infer(project_root: str, actor: str = "orchestrator") -> dict:
    """批量推断：扫描所有已有单元，自动建立关系。"""
    blocked = check_write_permission(actor, "graph.batch_infer")
    if blocked:
        return blocked
    # novel-planner 不允许批量推断（统一白名单校验）
    blocked = check_planner_restriction(
        actor, "graph.batch_infer",
        allowed_hint="规划主 agent 不获得批量推断权限",
    )
    if blocked:
        return blocked
    from relation_inferrer import RelationInferrer
    store = _get_store(project_root)
    before = store.stats()["total_relations"]
    inferrer = RelationInferrer(store)
    total = inferrer.batch_infer_all()
    store.flush()
    after = store.stats()["total_relations"]
    return {"new_relations": total, "total_before": before, "total_after": after}


def handle_export_docs(project_root: str, out: str = "") -> dict:
    """导出结构化文档（Markdown）。"""
    from projection_engine import ProjectionEngine
    store = _get_store(project_root)
    p = ProjectionEngine(store, project_root)
    written = p.export_docs(output_dir=out or None)
    return {"files": list(written)}


def handle_export_chunks(project_root: str, out: str = "") -> dict:
    """导出 CHUNK 单元为章节 TXT 文件。"""
    from graph_schema import UnitType, get_unit_chapter
    from collections import defaultdict

    store = _get_store(project_root)
    chunks = store.find_units(type=UnitType.CHUNK)
    if not chunks:
        return {"files": []}

    project_root_path = Path(project_root)
    out_dir = Path(out) if out else project_root_path / "chapters"
    out_dir.mkdir(parents=True, exist_ok=True)

    chapter_groups = defaultdict(list)
    for c in chunks:
        ch = get_unit_chapter(c)
        if ch:
            chapter_groups[ch].append(c)

    files = []
    for ch in sorted(chapter_groups.keys()):
        group = chapter_groups[ch]

        def _sort_key(c):
            try:
                cd = json.loads(c.content) if isinstance(c.content, str) else (c.content or {})
            except (json.JSONDecodeError, ValueError):
                cd = {}
            si = cd.get("正文分片")
            return si.get("序号", 0) if si else 0

        group.sort(key=_sort_key)
        parts = []
        seen_sources: set = set()
        for c in group:
            # 同章节多版本 CHUNK（v1/v2）指向同一文件时只读一次，避免重复拼接
            src = _chunk_source_path(c, project_root)
            if src in seen_sources:
                continue
            seen_sources.add(src)
            text = _read_chunk_text(c, project_root)
            if text:
                parts.append(text)
        full_text = "\n\n".join(parts)
        fname = f"第{ch}章.txt"
        fpath = out_dir / fname
        fpath.write_text(full_text, encoding="utf-8")
        files.append(str(fpath))

    return {"files": files}





def handle_migrate(
    project_root: str,
    dry_run: bool = False,
    verify: bool = True,
    report: bool = True,
) -> dict:
    """V1→V2 迁移。

    用 contextlib.redirect_stdout 临时静音迁移器输出（scoped、线程安全），
    避免全局替换 sys.stdout 破坏 daemon / 并发输出。
    """
    from migrate import run_migration

    with redirect_stdout(io.StringIO()):
        run_migration(
            project_root=project_root,
            dry_run=dry_run,
            verify=verify,
            report=report,
        )
    return {"migrated": True}


def handle_find_descendants(project_root: str, id: str, max_depth: int = 10) -> dict:
    """递归查找所有后代（CONTAINS）。"""
    store = _get_store(project_root)
    descendant_ids = store.find_descendants(id, max_depth=max_depth)
    result = []
    for did in descendant_ids:
        u = store.get_unit(did)
        if u:
            result.append(_unit_to_dict(u))
    return {"descendants": result, "total": len(result)}


def handle_find_ancestors(project_root: str, id: str) -> dict:
    """递归查找所有祖先（CONTAINS）。"""
    store = _get_store(project_root)
    ancestor_ids = store.find_ancestors(id)
    result = []
    for aid in ancestor_ids:
        u = store.get_unit(aid)
        if u:
            result.append(_unit_to_dict(u))
    return {"ancestors": result, "total": len(result)}


def handle_rebuild_structure_path(project_root: str, id: str) -> dict:
    """从 CONTAINS 关系重建结构路径。"""
    store = _get_store(project_root)
    path = store.rebuild_structure_path_from_edges(id)
    return {"id": id, "structure_path": path}


def handle_migrate_structure_to_edges(project_root: str, actor: str = "novel-tool") -> dict:
    """将结构路径字段迁移为 CONTAINS 边。"""
    store = _get_store(project_root)
    result = store.migrate_structure_path_to_edges(actor=actor)
    return result


def handle_schema_info(unit_type: str) -> dict:
    """返回指定叙事单元类型的 content JSON 字段要求（供 LLM/CLI 参考）。"""
    from graph_schema import UnitType
    from schemas import schema_info
    try:
        ut = UnitType[unit_type.upper()]
    except KeyError:
        return {"error": f"未知单元类型: {unit_type}", "available_types": [t.name for t in UnitType]}
    lines = schema_info(ut)
    return {"unit_type": unit_type, "fields": lines}


def handle_change_type(
    project_root: str,
    id: str,
    new_type: str,
    actor: str = "orchestrator",
) -> dict:
    """变更叙事单元的类型（world_rule→plot_thread 等）。

    流程：创建新类型单元 → 搬运 content/relations → 归档旧单元。
    编排逻辑在模块级 _change_unit_type 中（handler 保持薄封装）。
    """
    blocked = check_write_permission(actor, "graph.change_type")
    if blocked:
        return blocked
    # novel-planner 不允许变更类型（统一白名单校验）
    blocked = check_planner_restriction(
        actor, "graph.change_type",
        allowed_hint="规划主 agent 不获得变更类型权限",
    )
    if blocked:
        return blocked

    store = _get_store(project_root)
    return _change_unit_type(store, id, new_type, actor)


def _change_unit_type(store, id: str, new_type: str, actor: str) -> dict:
    """执行单元类型变更编排：建新单元 → 搬运关系 → 归档旧单元。

    从 handler 中提取的模块级辅助函数（handlers_graph.py 文件内），
    便于单元测试与复用。graph_store 尚无公共 change-type API，
    由引擎 Agent 并行补上后此处可改为委托。
    """
    from graph_schema import UnitType

    old = store.get_unit(id)
    if not old:
        return {"error": f"单元 {id} 不存在"}

    old_type = old.type.value if hasattr(old.type, "value") else str(old.type)
    try:
        new_ut = UnitType[new_type.upper()]
    except KeyError:
        return {"error": f"未知类型: {new_type}", "available_types": [t.name for t in UnitType]}
    new_type_val = new_ut.value

    if old_type == new_type_val:
        return {"error": f"单元 {id} 已经是 {old_type} 类型，无需变更"}

    # 1. 读取旧单元数据
    unit_name = old.unit_name
    content = old.content
    tags = list(old.tags) if old.tags else []
    chapter = old.chapter_number

    # 2. 获取旧单元的所有关系
    old_relations = store.get_relations(unit_id=id, direction="both")

    # 3. 创建新单元
    try:
        new_unit = store.create_unit(
            type=new_ut, unit_name=unit_name, content=content,
            tags=tags, chapter_number=chapter, actor=actor,
        )
    except ValueError as e:
        return {"error": f"创建新单元失败: {e}"}

    new_id = new_unit.id

    # 4. 搬运关系：删除旧关系 + 在新单元上重建
    from graph_schema import RelationType
    moved = 0
    for r in old_relations:
        rtype = r.relation_type
        # 确定新关系两端
        if r.source_id == id:
            src, tgt = new_id, r.target_id
        else:
            src, tgt = r.source_id, new_id
        # 添加新关系
        new_rel = store.add_relation(src, tgt, rtype, actor=actor, label=r.label or "")
        if new_rel:
            moved += 1
        # 删除旧关系
        store.remove_relation(r.id, actor=actor)

    # 5. 归档旧单元
    store.archive_unit(id, actor=actor)
    store.flush()

    return {
        "old_id": id,
        "new_id": new_id,
        "old_type": old_type,
        "new_type": new_type_val,
        "unit_name": unit_name,
        "relations_moved": moved,
    }


# ── EventExtractor 集成 ─────────────────────────────────────────────────────


def _run_event_extractor(
    store,
    unit,
    actor: str = "orchestrator",
    old_content: Any = None,
    if_exists: str = "skip",
) -> int:
    """
    对刚写入的单元运行事件抽取，自动创建 TEMPORAL_EVENT 节点和 HAS_EVENT 边。

    这是 EventExtractor 与 handler 层的集成点，在每次 create_unit /
    update_unit 后自动触发。

    Args:
        old_content: 更新前的旧 content（用于 diff 检测变化）

    Returns:
        创建的事件数
    """
    from graph_schema import UnitType, RelationType
    try:
        from event_extractor import EventExtractor
    except ImportError:
        return 0

    ut = unit.type
    # 只对焦点类型运行事件抽取（跳过 CHUNK 正文等无结构化事件的类型）
    # TEMPORAL_EVENT 本身不抽（避免循环）
    extractable_types = {
        UnitType.SCENE,
        UnitType.CHARACTER_ARC,
        UnitType.PLOT_THREAD,
        UnitType.WORLD_RULE,
    }
    if ut not in extractable_types:
        return 0

    extractor = EventExtractor(store)
    events = extractor.extract(
        unit.id, unit.content, ut, actor=actor, old_content=old_content,
    )
    if not events:
        return 0

    created_count = 0
    for evt in events:
        try:
            # 1. 创建 TEMPORAL_EVENT 节点（if_exists=skip 幂等：同一事件重复抽取不重建）
            event_unit = store.create_unit(
                type=UnitType.TEMPORAL_EVENT,
                unit_name=evt.summary[:80],  # 截断过长的名称
                content=json.dumps(evt.to_temporal_content(), ensure_ascii=False),
                actor=actor,
                if_exists=if_exists,
            )
            if not event_unit:
                continue

            # 2. 从主实体 → 事件：HAS_EVENT
            if evt.source_entity_id:
                store.add_relation(
                    source_id=evt.source_entity_id,
                    target_id=event_unit.id,
                    relation_type=RelationType.HAS_EVENT,
                    actor=actor,
                )

            # 3. 事件 → 地点：LOCATED_AT
            if evt.location and evt.source_entity_id:
                # 从主实体的 outgoing relations 中找地点
                for rel in store.get_relations(evt.source_entity_id, direction="outgoing"):
                    if rel.relation_type == RelationType.LOCATED_AT:
                        store.add_relation(
                            source_id=event_unit.id,
                            target_id=rel.target_id,
                            relation_type=RelationType.LOCATED_AT,
                            actor=actor,
                        )
                        break

            # 4. 事件 → 参与者：INVOLVES（如果有额外的参与者）
            for char_name in evt.characters:
                if char_name == evt.source_entity_name:
                    continue  # 主实体已在 source_entity_id
                char_unit = store.get_unit_by_name(char_name)
                if char_unit:
                    store.add_relation(
                        source_id=event_unit.id,
                        target_id=char_unit.id,
                        relation_type=RelationType.INVOLVES,
                        actor=actor,
                    )

            created_count += 1

        except Exception:
            logger.exception(f"创建 TEMPORAL_EVENT 失败: {evt.summary}")
            continue

    return created_count
