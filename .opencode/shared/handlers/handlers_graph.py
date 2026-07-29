"""
handlers_graph.py — graph 领域纯业务逻辑函数。

涵盖 26 个操作：graph CRUD、搜索、导出、关系管理、层级查询、迁移、可视化。
每个 handler 接受规范化参数名，返回 Python dict。
"""

import io
import json
import os
import re
import sys

from pathlib import Path
from typing import Any, Optional

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


# ── 内部工具函数 ──────────────────────────────────────────────────────────

def _syspath_insert(p: str):
    if p not in sys.path:
        sys.path.insert(0, p)


_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
_syspath_insert(_SHARED_DIR)
_syspath_insert(_V2_DIR)


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


def _find_novels_root() -> str:
    env = os.environ.get("NOVELS_ROOT")
    if env and os.path.isdir(env):
        return env
    cwd = os.path.join(os.getcwd(), "novels")
    if os.path.isdir(cwd):
        return cwd
    tool_root = os.path.abspath(os.path.join(_SHARED_DIR, "..", ".."))
    tool_novels = os.path.join(tool_root, "novels")
    if os.path.isdir(tool_novels):
        return tool_novels
    return cwd


def _resolve_project(project: str) -> str:
    if not project:
        return ""
    if os.path.isabs(project):
        return project
    novels = _find_novels_root()
    cand = os.path.join(novels, project)
    if os.path.isdir(cand):
        return cand
    return os.path.abspath(project)


def _repair_content(content: str) -> str:
    """解析并修复 JSON 内容字符串，返回规范化的 JSON 字符串。"""
    if not content:
        return content
    try:
        from json_repair import loads as repair_loads
        content = json.dumps(repair_loads(content), ensure_ascii=False)
    except ModuleNotFoundError:
        # json_repair 未安装时不做修复
        pass
    except Exception:
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
    return content


def _parse_tags(tags_str: Optional[str]) -> Optional[list[str]]:
    """解析逗号分隔的标签字符串为列表，None 表示未提供。"""
    if not tags_str:
        return None
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def _unit_to_dict(u) -> dict:
    return {
        "id": u.id,
        "name": u.unit_name,
        "type": u.type.value if hasattr(u.type, "value") else str(u.type),
        "status": u.status.value if hasattr(u.status, "value") else str(u.status),
        "confidence": u.confidence,
        "tags": list(u.tags) if u.tags else [],
        "chapter": u.chapter_number,
        "version": u.version,
        "content": u.content,
        "created_at": str(u.created_at) if u.created_at else None,
        "updated_at": str(u.updated_at) if u.updated_at else None,
    }


def _validate_content_schema(unit_type, content: str) -> list:
    """校验 content JSON 是否符合该类型的字段 Schema，返回错误列表。"""
    if not content or not content.startswith("{"):
        return []
    try:
        from schemas import validate_content
        content_dict = json.loads(content)
        if not isinstance(content_dict, dict):
            return []
        return validate_content(unit_type, content_dict)
    except Exception:
        return []


def _derive_progress(project_path: str) -> dict:
    """从 graph 实时推算写作进度。"""
    from graph_schema import UnitType, UnitStatus, get_unit_chapter
    store = _get_store(project_path)
    result = {}
    chunks = store.find_units(type=UnitType.CHUNK)
    chunk_chapters = sorted(set(
        get_unit_chapter(c) for c in chunks if get_unit_chapter(c) > 0
    ))
    result["current_chapter"] = max(chunk_chapters) if chunk_chapters else 0
    result["written_chapters"] = len(chunk_chapters)
    volumes = store.find_units(type=UnitType.VOLUME_PLAN)
    all_cp = store.find_units(type=UnitType.CHAPTER_PLAN)
    volume_progress = []
    for vol in sorted(volumes, key=lambda v: _vol_num(v)):
        vn = _vol_num(vol)
        vname = _vol_name(vol)
        descendant_ids = set(store.find_descendants(vol.id, max_depth=3))
        vol_cps = [cp for cp in all_cp if cp.id in descendant_ids]
        total = len(vol_cps)
        mature = sum(1 for cp in vol_cps if cp.status == UnitStatus.MATURE)
        ch_nums = sorted(set(
            get_unit_chapter(cp) for cp in vol_cps if get_unit_chapter(cp) > 0
        ))
        ch_range = (
            f"{ch_nums[0]}-{ch_nums[-1]}"
            if len(ch_nums) >= 2
            else (str(ch_nums[0]) if ch_nums else "")
        )
        if total > 0 and mature == total:
            status = "completed"
        elif mature > 0:
            status = "in_progress"
        else:
            status = "pending"
        volume_progress.append({
            "volume": vn, "name": vname, "chapter_range": ch_range,
            "total_chapter_plans": total, "mature_chapter_plans": mature, "status": status,
        })
    result["volume_progress"] = volume_progress
    cur_vol = 0
    for vp in volume_progress:
        if vp["chapter_range"]:
            parts = vp["chapter_range"].split("-")
            try:
                lo, hi = int(parts[0]), int(parts[-1])
                if lo <= result["current_chapter"] <= hi:
                    cur_vol = vp["volume"]
                    break
            except (ValueError, IndexError):
                pass
    if cur_vol == 0 and volume_progress:
        cur_vol = volume_progress[-1]["volume"]
    result["current_volume"] = cur_vol
    result["total_chunks"] = len(chunks)
    result["total_chapter_plans"] = len(all_cp)
    return result


def _vol_num(unit) -> int:
    try:
        if unit.content and unit.content.startswith("{"):
            c = json.loads(unit.content)
            return int(c.get("卷号", 0))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        pass
    return 0


def _vol_name(unit) -> str:
    try:
        if unit.content and unit.content.startswith("{"):
            c = json.loads(unit.content)
            return str(c.get("卷名称", ""))
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return ""


def _read_chunk_text(c, project_root: str) -> str:
    """从 CHUNK 单元读取正文文本。"""
    try:
        cd = json.loads(c.content) if isinstance(c.content, str) else (c.content or {})
    except (json.JSONDecodeError, ValueError):
        cd = {}
    slice_info = cd.get("正文分片")
    if slice_info:
        sp = slice_info.get("文件", "")
        if sp:
            src = Path(project_root) / sp
            if src.exists():
                return src.read_text(encoding="utf-8")
    source_path = cd.get("正文路径", "")
    if source_path:
        src = Path(project_root) / source_path
        if src.exists():
            return src.read_text(encoding="utf-8")
    return ""


def _auto_detect_chapter(content: str, unit_name: str) -> Optional[int]:
    """自动推断章节号：从 content JSON 或单元名称提取。"""
    chapter = None
    if content and content.startswith("{"):
        try:
            content_dict = json.loads(content)
            if isinstance(content_dict, dict) and "章节号" in content_dict:
                chapter = int(content_dict["章节号"])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if not chapter and unit_name:
        m = re.search(r'第(\d+)章', unit_name)
        if m:
            chapter = int(m.group(1))
    return chapter


# ── 编排层写操作拦截 ──────────────────────────────────────────────────

_ORCHESTRATOR_WRITE_BLOCKED = True

def set_orchestrator_write_blocked(blocked: bool):
    """设置是否禁止编排层直接写 graph（默认禁止）"""
    global _ORCHESTRATOR_WRITE_BLOCKED
    _ORCHESTRATOR_WRITE_BLOCKED = blocked

def _check_orchestrator_write(actor: str, operation: str) -> Optional[dict]:
    """检查调用者是否有权限直接写 graph。返回 dict | None 而非抛异常。
    
    允许的 actor：novel-v2-crafter / v2-crafter（创作通路）、script（迁移脚本）、fix-asymmetry、novel-tool
    禁止的 actor：orchestrator（编排层应通过 crafter）或其他未识别值
    
    Returns: None（允许）或 {"error": ..., "blocked_operation": ...}（拒绝，error 含修正指引）
    """
    if not _ORCHESTRATOR_WRITE_BLOCKED:
        return None
    
    ALLOWED_WRITE_ACTORS = {"novel-v2-crafter", "v2-crafter", "script", "fix-asymmetry", "novel-tool", "web-ui"}
    if actor not in ALLOWED_WRITE_ACTORS:
        return {
            "error": (
                f"不允许直接调用 {operation}（actor={actor}）。"
                f"叙事内容写操作必须通过 novel-v2-crafter 子 agent 执行。"
                f"请使用 task(subagent_type='novel-v2-crafter', load_skills=['novel-v2'], ...)"
            ),
            "blocked_operation": operation,
        }
    return None


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


def handle_find_unit(project_root: str, name: str = "", keyword: str = "") -> dict:
    """按名称或关键词查找叙事单元 ID。
    
    Args:
        name: 精确单元名称（name 和 keyword 至少提供一个）
        keyword: 模糊关键词搜索（name 和 keyword 至少提供一个）
    
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
        result = engine.search(keyword=keyword, max_results=10)
        items = []
        for r in result.results:
            items.append({
                "unit_id": r.unit_id,
                "unit_name": r.unit_name,
                "unit_type": r.unit_type.value if hasattr(r.unit_type, "value") else str(r.unit_type),
                "content_preview": r.content_preview[:120] + "..." if len(r.content_preview) > 120 else r.content_preview,
                "score": r.score,
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
) -> dict:
    """搜索叙事单元。接受 scope 为列表或逗号分隔字符串。"""
    from graph_schema import UnitType
    # 兼容 string → list（novel_tool 可能传 "CHARACTER_ARC,SCENE" 这样的字符串）
    if isinstance(scope, str):
        scope = [s.strip() for s in scope.split(",") if s.strip()]
    types = None
    if scope:
        types = [UnitType[s.upper()] for s in scope if s.strip()]
    _store, engine = _get_engine(project_root)
    result = engine.search(
        keyword=keyword, pattern=pattern, name=name,
        scope=types, regex=regex, case_sensitive=case_sensitive,
        max_results=limit,
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
        }
        if verbose:
            u = _store.get_unit(r.unit_id)
            if u:
                item["content"] = u.content
        items.append(item)
    return {
        "total": result.total,
        "time_ms": result.time_ms,
        "results": items,
    }


def handle_list_units(project_root: str, unit_type: str = "", limit: int = 0, status: str = "") -> dict:
    """列出叙事单元。status 可选：archived/mature/sprout/growing/frozen。为空时默认排除 archived。"""
    from graph_schema import UnitType, UnitStatus
    ut = UnitType[unit_type.upper()] if unit_type and unit_type.upper() != "ALL" else None
    store = _get_store(project_root)
    status_obj = UnitStatus[status.upper()] if status and status.upper() else None
    units = store.find_units(type=ut, status=status_obj)
    if limit and limit > 0:
        units = units[:limit]
    return {
        "units": [
            {
                "id": u.id, "name": u.unit_name,
                "type": u.type.value if hasattr(u.type, "value") else str(u.type),
                "status": u.status.value if hasattr(u.status, "value") else str(u.status),
            }
            for u in units
        ],
        "total": len(units),
    }


def handle_stats(project_root: str) -> dict:
    """graph 统计。"""
    store = _get_store(project_root)
    return store.stats()


def handle_get_modified_units(project_root: str, since_version: int = 0) -> dict:
    """获取从指定版本号以来修改过的单元。"""
    _store, engine = _get_engine(project_root)
    changed = engine.get_modified_units(since_version=since_version)
    return {
        "units": [
            {
                "id": u.id, "name": u.unit_name,
                "type": u.type.value if hasattr(u.type, "value") else str(u.type),
                "version": u.version,
                "status": u.status.value if hasattr(u.status, "value") else str(u.status),
            }
            for u in changed
        ],
        "total": len(changed),
    }


def handle_get_neighbors(project_root: str, id: str, rel_type: str = "", limit: int = 0) -> dict:
    """查询关联关系。"""
    from graph_schema import RelationType
    store = _get_store(project_root)
    rt = RelationType[rel_type.upper()] if rel_type else None
    neighbors = store.get_neighbors(id, relation_type=rt, max_depth=1)
    result = []
    count = 0
    for nid in neighbors.get(1, set()):
        n = store.get_unit(nid)
        if n:
            result.append({
                "id": n.id, "name": n.unit_name,
                "type": n.type.value if hasattr(n.type, "value") else str(n.type),
            })
            count += 1
            if limit and count >= limit:
                break
    return {"neighbors": result, "total": len(result)}


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


def handle_recent_events(project_root: str, limit: int = 10) -> dict:
    """最近事件。"""
    store = _get_store(project_root)
    events = store._events[-int(limit):] if hasattr(store, "_events") else []
    return {
        "events": [
            {
                "timestamp": str(e.timestamp), "actor": e.actor,
                "event_type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
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
) -> dict:
    """创建叙事单元。"""
    blocked = _check_orchestrator_write(actor, "graph.create_unit")
    if blocked:
        return blocked
    from graph_schema import UnitType
    from relation_inferrer import RelationInferrer

    ut = UnitType[unit_type.upper()]

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
    try:
        u = store.create_unit(
            type=ut, unit_name=name, content=content,
            tags=tags_list, chapter_number=chapter,
            parent_id=parent_id, actor=actor,
        )
    except ValueError as e:
        return {
            "error": f"创建叙事单元失败: {e}",
            "hint": f"请检查 content JSON 是否包含 {ut.value} 类型的所有必填字段。"
                    f"使用 novel-tool --operation graph.schema_info --unit_type {unit_type} 查看字段要求。",
        }

    inferrer = RelationInferrer(store)
    created = inferrer.infer_on_create(u)
    store.flush()

    schema_errors = _validate_content_schema(ut, content)

    return {
        "id": u.id,
        "name": u.unit_name,
        "type": ut.value,
        "relations_created": created,
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
) -> dict:
    """更新叙事单元。"""
    blocked = _check_orchestrator_write(actor, "graph.update_unit")
    if blocked:
        return blocked
    from graph_schema import UnitStatus
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

    # 预读取旧单元，判断内容是否有实际变更
    old_unit = store.get_unit(id)
    old_content = old_unit.content if old_unit else None
    content_changed = (content is not None and content != old_content)

    u = store.update_unit(
        unit_id=id, content=content,
        unit_name=name if name else None,
        tags=tags_list, status=status_obj, actor=actor,
    )
    if not u:
        return {"error": "更新失败：叙事单元不存在"}

    # 仅在内容实际变更时才运行关系推断（避免 O(n) 全量扫描）
    created = 0
    if content_changed:
        inferrer = RelationInferrer(store)
        created = inferrer.infer_on_create(u)
    store.flush()

    schema_errors = _validate_content_schema(u.type, content) if content else []

    return {
        "id": u.id,
        "name": u.unit_name,
        "version": u.version,
        "tags": list(u.tags),
        "relations_created": created,
        "schema_errors": schema_errors,
    }


def handle_archive_unit(project_root: str, id: str, actor: str = "orchestrator") -> dict:
    """归档叙事单元。"""
    blocked = _check_orchestrator_write(actor, "graph.archive_unit")
    if blocked:
        return blocked
    store = _get_store(project_root)
    ok = store.archive_unit(id, actor=actor)
    if ok:
        store.flush()
        return {"archived": True}
    return {"error": "归档失败：叙事单元不存在"}


def handle_purge_archived(project_root: str, ids: str = "", actor: str = "orchestrator") -> dict:
    """
    物理删除已归档的叙事单元及其关联边。
    """
    blocked = _check_orchestrator_write(actor, "graph.purge_archived")
    if blocked:
        return blocked
    store = _get_store(project_root)
    id_list = [i.strip() for i in ids.split(",") if i.strip()] if ids else None
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


def _resolve_rel_type(rel_type: str):
    """解析关系类型：先按 name 查，再按 value 查，都失败时返回 REFERENCES + 原始输入作为 label。"""
    from graph_schema import RelationType
    try:
        rtype = RelationType[rel_type.upper()]
        return rtype, ""
    except KeyError:
        try:
            rtype = RelationType(rel_type.lower())
            return rtype, ""
        except ValueError:
            # 非枚举值（如"师徒""母子"）→ 降级为 REFERENCES，原始输入存为语义标签
            return RelationType.REFERENCES, rel_type


def handle_add_relation(
    project_root: str,
    source: str,
    target: str,
    rel_type: str,
    bidirectional: bool = False,
    label: str = "",
    actor: str = "orchestrator",
) -> dict:
    """建立关系。"""
    blocked = _check_orchestrator_write(actor, "graph.add_relation")
    if blocked:
        return blocked
    from graph_schema import RelationType
    rtype, fallback_label = _resolve_rel_type(rel_type)
    effective_label = label or fallback_label
    store = _get_store(project_root)
    rel = store.add_relation(source, target, rtype, actor=actor, label=effective_label)
    if not rel:
        return {"error": "关系建立失败"}
    result = {"id": rel.id, "type": rtype.value}
    if effective_label:
        result["label"] = effective_label
    if bidirectional:
        inv = rtype.inverse
        inv_label = effective_label  # 反向关系携带相同语义标签
        inv_rel = store.add_relation(target, source, inv, actor=actor, label=inv_label)
        if inv_rel:
            result["inverse_id"] = inv_rel.id
    store.flush()
    return result


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
    except Exception:
        return {"ok": True, "constraint_check": None}


def handle_constraint_check(project_root: str, full: bool = False) -> dict:
    """手动触发约束检查。"""
    from constraint_engine import ConstraintEngine
    store = _get_store(project_root)
    engine = ConstraintEngine(store)
    if full:
        results = engine.run(full=True)
    else:
        results = engine.run_incremental()
    engine._persist_results(results)
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
    """补齐所有对称关系类型的缺失反向边。"""
    from graph_schema import RelationType
    store = _get_store(project_root)
    created = 0
    skipped = 0
    for rel in list(store._relations.values()):
        rtype = rel.relation_type
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
        r = store.add_relation(rev_source, rev_target, rev_type,
                               weight=rel.weight, description="auto-filled reverse",
                               actor="fix-asymmetry")
        if r:
            created += 1
    store.flush()
    return {"created": created, "skipped": skipped}


def handle_get_relations(
    project_root: str,
    id: str = "",
    rel_type: str = "",
    direction: str = "both",
) -> dict:
    """获取关系列表。"""
    from graph_schema import RelationType
    store = _get_store(project_root)
    rt = RelationType[rel_type.upper()] if rel_type else None
    relations = store.get_relations(unit_id=id or None, relation_type=rt, direction=direction)
    return {
        "relations": [
            {
                "id": r.id, "source_id": r.source_id,
                "target_id": r.target_id,
                "type": r.relation_type.value,
                "weight": r.weight, "description": r.description,
                "label": r.label,
            }
            for r in relations
        ],
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
    blocked = _check_orchestrator_write(actor, "graph.remove_relation")
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
    blocked = _check_orchestrator_write(actor, "graph.batch_infer")
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
        for c in group:
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
    """V1→V2 迁移。"""
    from migrate import run_migration

    _old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        run_migration(
            project_root=project_root,
            dry_run=dry_run,
            verify=verify,
            report=report,
        )
    finally:
        sys.stdout = _old_stdout
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
    """
    blocked = _check_orchestrator_write(actor, "graph.change_type")
    if blocked:
        return blocked
    from graph_schema import UnitType

    store = _get_store(project_root)
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
