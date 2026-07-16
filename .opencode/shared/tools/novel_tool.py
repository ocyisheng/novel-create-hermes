#!/usr/bin/env python3
"""
novel_tool.py — V2 小说创作统一工具句柄

被 novel-tool.ts 调用，直接 import GraphStore 等模块（不走 CLI）。
接收 JSON request，返回 JSON response。

用法: python novel_tool.py '<json-string>'
"""

import sys, os, json
from pathlib import Path
from typing import Any, Dict, Optional

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
_PROJECT_DIR = os.path.join(_SHARED_DIR, "project")
_ENV_DIR = os.path.join(_SHARED_DIR, "env")
for _d in [_SHARED_DIR, _V2_DIR, _PROJECT_DIR, _ENV_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


def _ok(data: Any) -> str:
    return json.dumps({"success": True, "data": data}, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"success": False, "error": str(msg)}, ensure_ascii=False)


def _get_store(project_path: str):
    from graph_store import GraphStore
    store = GraphStore(project_path)
    store.initialize()
    return store


def _get_engine(project_path: str):
    from search_engine import SearchEngine
    store = _get_store(project_path)
    return store, SearchEngine(store)


def _find_novels_root() -> str:
    env = os.environ.get("NOVELS_ROOT")
    if env and os.path.isdir(env):
        return env
    cwd = os.path.join(os.getcwd(), "novels")
    if os.path.isdir(cwd):
        return cwd
    tool = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "novels"))
    if os.path.isdir(tool):
        return tool
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


def _unit_to_dict(u) -> dict:
    return {
        "id": u.id,
        "name": u.unit_name,
        "type": u.type.value if hasattr(u.type, "value") else str(u.type),
        "status": u.status.value if hasattr(u.status, "value") else str(u.status),
        "confidence": u.confidence,
        "tags": list(u.tags) if u.tags else [],
        "chapter": u.chapter_number,
        "volume": None,
        "version": u.version,
        "content": u.content,
        "created_at": str(u.created_at) if u.created_at else None,
        "updated_at": str(u.updated_at) if u.updated_at else None,
    }


# ──────────────────────────────────────────────
#  Graph 操作
# ──────────────────────────────────────────────

def _validate_content_schema(unit_type, content: str) -> list:
    """校验 content JSON 是否符合该类型的字段 Schema，返回错误列表。"""
    if not content or not content.startswith("{"):
        return []
    try:
        from schemas import validate_content
        import json
        content_dict = json.loads(content)
        if not isinstance(content_dict, dict):
            return []
        return validate_content(unit_type, content_dict)
    except Exception:
        return []


def _handle_graph(op: str, params: dict) -> str:
    project = _resolve_project(params.get("project", ""))

    # Operations that don't need a project
    if op == "graph.list_relation_types":
        from graph_schema import RelationType
        return _ok([
            {"value": rt.value, "name": rt.name, "inverse": rt.inverse.value if rt.inverse != rt else rt.value}
            for rt in RelationType
        ])

    if not project or not os.path.isfile(os.path.join(project, "config.yaml")):
        return _err(f"项目不存在或路径无效: {project}")

    store = _get_store(project)

    if op == "graph.get_unit":
        uid = params.get("id") or ""
        name = params.get("name") or ""
        if uid:
            u = store.get_unit(uid)
        elif name:
            u = store.get_unit_by_name(name)
        else:
            return _err("get_unit 需要 id 或 name")
        if not u:
            return _ok(None)
        result = _unit_to_dict(u)
        return _ok(result)

    if op == "graph.find_unit":
        name = params.get("name", "")
        if not name:
            return _err("find_unit 需要 name")
        u = store.get_unit_by_name(name)
        if not u:
            return _ok({"id": None, "found": False, "message": f"未找到名称为「{name}」的叙事单元"})
        return _ok({"id": u.id, "found": True})

    if op == "graph.search":
        from graph_schema import UnitType
        keyword = params.get("keyword", "")
        pattern = params.get("pattern", "")
        name = params.get("name", "")
        scope_raw = params.get("scope") or params.get("unit_type") or params.get("unitType") or ""
        regex = params.get("regex", False)
        case_sensitive = params.get("case_sensitive", False)
        limit = params.get("limit", 20)
        if scope_raw:
            if isinstance(scope_raw, str):
                types = [UnitType[t.strip().upper()] for t in scope_raw.split(",") if t.strip()]
            else:
                types = [UnitType[t.upper()] for t in scope_raw]
        else:
            types = None
        _s, engine = _get_engine(project)
        result = engine.search(
            keyword=keyword, pattern=pattern, name=name,
            scope=types, regex=regex, case_sensitive=case_sensitive,
            max_results=limit,
        )
        return _ok({
            "total": result.total,
            "time_ms": result.time_ms,
            "results": [
                {
                    "unit_id": r.unit_id,
                    "unit_name": r.unit_name,
                    "unit_type": r.unit_type.value if hasattr(r.unit_type, "value") else str(r.unit_type),
                    "content_preview": r.content_preview,
                    "content_length": r.content_length,
                    "chapter": r.chapter,
                    "score": r.score,
                    "tags": r.tags,
                    "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                    "version": r.version,
                    "neighbors": r.neighbors,
                }
                for r in result.results
            ],
        })

    if op == "graph.list_units":
        from graph_schema import UnitType
        t = params.get("unit_type") or params.get("type") or ""
        ut = UnitType[t.upper()] if t and t.upper() != "ALL" else None
        limit = params.get("limit", 0)
        units = store.find_units(type=ut)
        if limit and limit > 0:
            units = units[:limit]
        return _ok([
            {"id": u.id, "name": u.unit_name, "type": u.type.value if hasattr(u.type, "value") else str(u.type), "status": u.status.value if hasattr(u.status, "value") else str(u.status)}
            for u in units
        ])

    if op == "graph.stats":
        return _ok(store.stats())

    if op == "graph.get_modified_units":
        since = params.get("since_version", 0)
        _st, engine = _get_engine(project)
        changed = engine.get_modified_units(since_version=since)
        return _ok([
            {
                "id": u.id,
                "name": u.unit_name,
                "type": u.type.value if hasattr(u.type, "value") else str(u.type),
                "version": u.version,
                "status": u.status.value if hasattr(u.status, "value") else str(u.status),
            }
            for u in changed
        ])

    if op == "graph.get_neighbors":
        uid = params.get("id", "")
        if not uid:
            return _err("get_neighbors 需要 id")
        from graph_schema import RelationType
        rt = params.get("rel_type") or params.get("relType") or ""
        rel_type = RelationType[rt.upper()] if rt else None
        limit = params.get("limit", 0)
        neighbors = store.get_neighbors(uid, relation_type=rel_type, max_depth=1)
        result = []
        count = 0
        for nid in neighbors.get(1, set()):
            n = store.get_unit(nid)
            if n:
                result.append({"id": n.id, "name": n.unit_name, "type": n.type.value if hasattr(n.type, "value") else str(n.type)})
                count += 1
                if limit and count >= limit:
                    break
        return _ok(result)

    if op == "graph.check":
        _st, engine = _get_engine(project)
        results = engine.check_consistency()
        return _ok([
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "severity": r.severity,
                "description": r.description,
                "units_involved": r.units_involved,
                "detail": r.detail,
            }
            for r in results
        ])

    if op == "graph.recent_events":
        limit = params.get("limit", 10)
        events = store._events[-int(limit):] if hasattr(store, "_events") else []
        return _ok([
            {"timestamp": str(e.timestamp), "actor": e.actor, "event_type": e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)}
            for e in events
        ])

    if op == "graph.create_unit":
        from graph_schema import UnitType
        from relation_inferrer import RelationInferrer
        ut = UnitType[params.get("type", "").upper()]
        unit_name = params.get("name", "")
        content = params.get("content", "")
        file_path = params.get("file")
        if file_path:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        if content:
            import json
            from json_repair import loads as repair_loads
            try:
                content = json.dumps(repair_loads(content), ensure_ascii=False)
            except Exception:
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False)
        tags = [t.strip() for t in params.get("tags", "").split(",") if t.strip()] if params.get("tags") else None
        chapter = params.get("chapter") or None
        volume = params.get("volume") or None
        parent_id = params.get("parent_id") or None
        actor = params.get("actor", "novel-tool")
        if chapter:
            chapter = int(chapter)
        u = store.create_unit(
            type=ut, unit_name=unit_name, content=content, tags=tags,
            chapter_number=chapter,
            parent_id=parent_id, actor=actor,
        )
        inferrer = RelationInferrer(store) if hasattr(RelationInferrer, "__call__") else None
        created = None
        if inferrer and hasattr(inferrer, "infer_on_create"):
            created = inferrer.infer_on_create(u)
        store.flush()
        schema_errors = _validate_content_schema(ut, content)
        return _ok({"id": u.id, "relations_created": created, "schema_errors": schema_errors})

    if op == "graph.update_unit":
        from graph_schema import UnitStatus
        uid = params.get("id", "")
        content = params.get("content")
        file_path = params.get("file")
        if file_path:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        if content:
            import json
            from json_repair import loads as repair_loads
            try:
                content = json.dumps(repair_loads(content), ensure_ascii=False)
            except Exception:
                if isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False)
        unit_name = params.get("name")
        tags_raw = params.get("tags")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
        status_raw = params.get("status")
        status = UnitStatus[status_raw.upper()] if status_raw else None
        actor = params.get("actor", "novel-tool")
        u = store.update_unit(unit_id=uid, content=content, unit_name=unit_name, tags=tags, status=status, actor=actor)
        if u:
            store.flush()
            schema_errors = _validate_content_schema(u.type, content)
            return _ok({"id": u.id, "name": u.unit_name, "version": u.version, "tags": list(u.tags), "schema_errors": schema_errors})
        return _err("更新失败：叙事单元不存在")

    if op == "graph.archive_unit":
        uid = params.get("id", "")
        actor = params.get("actor", "novel-tool")
        ok = store.archive_unit(uid, actor=actor)
        if ok:
            store.flush()
            return _ok({"archived": True})
        return _err("归档失败：叙事单元不存在")

    if op == "graph.add_relation":
        from graph_schema import RelationType
        source = params.get("source", "")
        target = params.get("target", "")
        rtype = RelationType[params.get("type", "").upper()]
        bidirectional = params.get("bidirectional", False)
        actor = params.get("actor", "novel-tool")
        rel = store.add_relation(source, target, rtype, actor=actor)
        if not rel:
            return _err("关系建立失败")
        result = {"id": rel.id, "type": rtype.value}
        if bidirectional:
            inv = rtype.inverse
            inv_rel = store.add_relation(target, source, inv, actor=actor)
            if inv_rel:
                result["inverse_id"] = inv_rel.id
        store.flush()
        return _ok(result)

    if op == "graph.flush":
        store.flush()
        return _ok({"ok": True})

    if op == "graph.fix_asymmetry":
        from graph_schema import RelationType
        created = 0
        skipped = 0
        for rel in list(store._relations.values()):
            rtype = rel.relation_type
            inv = rtype.inverse
            rev_source, rev_target = (rel.target_id, rel.source_id)
            rev_type = inv if inv != rtype else rtype
            exists = any(
                r.source_id == rev_source and r.target_id == rev_target and r.relation_type == rev_type
                for r in store._relations.values()
            )
            if exists:
                skipped += 1
                continue
            r = store.add_relation(rev_source, rev_target, rev_type, weight=rel.weight, description="auto-filled reverse", actor="novel-tool")
            if r:
                created += 1
        store.flush()
        return _ok({"created": created, "skipped": skipped})

    if op == "graph.get_relations":
        from graph_schema import RelationType
        uid = params.get("id", "")
        rel_type_name = params.get("type", "") or params.get("rel_type", "") or params.get("relType", "") or ""
        direction = params.get("direction", "both")
        rel_type = RelationType[rel_type_name.upper()] if rel_type_name else None
        relations = store.get_relations(unit_id=uid or None, relation_type=rel_type, direction=direction)
        return _ok([
            {
                "id": r.id,
                "source_id": r.source_id,
                "target_id": r.target_id,
                "type": r.relation_type.value,
                "weight": r.weight,
                "description": r.description,
            }
            for r in relations
        ])

    if op == "graph.remove_relation":
        rid = params.get("id", "")
        source = params.get("source", "")
        target = params.get("target", "")
        rtype_name = params.get("type", "") or params.get("rel_type", "") or params.get("relType", "") or ""
        actor = params.get("actor", "novel-tool")

        if rid:
            ok = store.remove_relation(rid, actor=actor)
            removed_id = rid
        elif source and target and rtype_name:
            from graph_schema import RelationType
            rtype = RelationType[rtype_name.upper()]
            found = None
            for r in store.get_relations():
                if r.source_id == source and r.target_id == target and r.relation_type == rtype:
                    found = r
                    break
            if found:
                ok = store.remove_relation(found.id, actor=actor)
                removed_id = found.id
            else:
                return _err("未找到匹配的关系")
        else:
            return _err("remove_relation 需要 id 或 source+target+type")
        if not ok:
            return _err("关系不存在或删除失败")
        store.flush()
        return _ok({"removed": True, "relation_id": removed_id})

    if op == "graph.batch_infer":
        from relation_inferrer import RelationInferrer
        before = store.stats()["total_relations"]
        inferrer = RelationInferrer(store)
        total = inferrer.batch_infer_all()
        store.flush()
        after = store.stats()["total_relations"]
        return _ok({"new_relations": total, "total_before": before, "total_after": after})

    if op == "graph.export_docs":
        from projection_engine import ProjectionEngine
        p = ProjectionEngine(store, project)
        out = params.get("out", "")
        written = p.export_docs(output_dir=out or None)
        return _ok({"files": list(written)})

    if op == "graph.export_chunks":
        from graph_schema import UnitType
        from collections import defaultdict
        chunks = store.find_units(type=UnitType.CHUNK)
        if not chunks:
            return _ok({"files": []})
        project_root = Path(project)
        out_dir = Path(params.get("out", "")) if params.get("out") else project_root / "chapters"
        out_dir.mkdir(parents=True, exist_ok=True)

        def _read_chunk_text(c):
            try:
                cd = json.loads(c.content) if isinstance(c.content, str) else (c.content or {})
            except (json.JSONDecodeError, ValueError):
                cd = {}
            slice_info = cd.get("正文分片")
            if slice_info:
                sp = slice_info.get("文件", "")
                if sp:
                    src = project_root / sp
                    if src.exists():
                        return src.read_text(encoding="utf-8")
            source_path = cd.get("正文路径", "")
            if source_path:
                src = project_root / source_path
                if src.exists():
                    return src.read_text(encoding="utf-8")
            return ""

        from graph_schema import get_unit_chapter
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
                text = _read_chunk_text(c)
                if text:
                    parts.append(text)
            full_text = "\n\n".join(parts)
            fname = f"第{ch}章.txt"
            fpath = out_dir / fname
            fpath.write_text(full_text, encoding="utf-8")
            files.append(str(fpath))

        return _ok({"files": files})

    if op == "graph.viz":
        from v2_graph_viz import main as viz_main
        viz_argv = ["v2_graph_viz.py", "--project-root", str(Path(project).resolve())]
        if params.get("character"):
            viz_argv.extend(["--character", params["character"]])
        if params.get("timeline"):
            viz_argv.extend(["--timeline", params["timeline"]])
        if params.get("output"):
            viz_argv.extend(["--output", params["output"]])
        if params.get("open"):
            viz_argv.append("--open")
        if params.get("force"):
            viz_argv.append("--force")
        if params.get("incremental"):
            viz_argv.append("--incremental")
        sys.argv = viz_argv
        # redirect viz stdout to stderr so JSON response is clean
        import io
        _old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            viz_main()
        finally:
            sys.stdout = _old_stdout
        return _ok({"viz_generated": True})

    if op == "graph.migrate":
        from migrate import main as migrate_main
        verify = params.get("verify", True)
        report = params.get("report", True)
        dry_run = params.get("dry_run", False)
        sys.argv = ["migrate.py", "--project-root", project]
        if verify:
            sys.argv.append("--verify")
        if report:
            sys.argv.append("--report")
        if dry_run:
            sys.argv.append("--dry-run")
        import io
        _old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            migrate_main()
        finally:
            sys.stdout = _old_stdout
        return _ok({"migrated": True})

    # ── CONTAINS 层级查询 ───────────────────────────────────────────────

    if op == "graph.find_descendants":
        uid = params.get("id", "")
        if not uid:
            return _err("find_descendants 需要 id")
        max_depth = params.get("max_depth", 10)
        descendant_ids = store.find_descendants(uid, max_depth=max_depth)
        result = []
        for did in descendant_ids:
            u = store.get_unit(did)
            if u:
                result.append(_unit_to_dict(u))
        return _ok(result)

    if op == "graph.find_ancestors":
        uid = params.get("id", "")
        if not uid:
            return _err("find_ancestors 需要 id")
        ancestor_ids = store.find_ancestors(uid)
        result = []
        for aid in ancestor_ids:
            u = store.get_unit(aid)
            if u:
                result.append(_unit_to_dict(u))
        return _ok(result)

    if op == "graph.rebuild_structure_path":
        uid = params.get("id", "")
        if not uid:
            return _err("rebuild_structure_path 需要 id")
        path = store.rebuild_structure_path_from_edges(uid)
        return _ok({"id": uid, "structure_path": path})

    if op == "graph.migrate_structure_to_edges":
        actor = params.get("actor", "novel-tool")
        result = store.migrate_structure_path_to_edges(actor=actor)
        return _ok(result)

    return _err(f"未知 graph 操作: {op}")


# ──────────────────────────────────────────────
#  项目管理操作
# ──────────────────────────────────────────────

def _handle_project(op: str, params: dict) -> str:
    NOVELS_ROOT = _find_novels_root()
    name = params.get("name", "").strip()
    if not name:
        # fallback: extract name from "project" param
        proj = params.get("project", "").strip()
        name = os.path.basename(proj) if proj else ""
    proj_path = os.path.join(NOVELS_ROOT, name)

    if op == "project.new":
        genre = params.get("genre", "未分类").strip()
        is_v2 = params.get("v2", True)
        volumes = params.get("volumes", 3)
        acts = params.get("acts", 3)
        structure = params.get("structure", "三幕")

        if os.path.exists(proj_path):
            return _err(f"项目已存在: {proj_path}")

        dirs_v2 = ["graph", "quality", "styles", "output"]
        dirs_v1 = ["chapters", "chapters/.metas", "characters", "ideation",
                    f"outline/分纲", "outline/分卷", "outline/情节线", "outline/追踪",
                    "output", "quality", "styles", "worldbuilding"]

        if is_v2:
            for d in dirs_v2:
                os.makedirs(os.path.join(proj_path, d), exist_ok=True)
            try:
                from graph_store import GraphStore
                from graph_schema import EventType
                store = GraphStore(str(proj_path))
                store.initialize()
                store._record_event(EventType.SYSTEM_EVENT, actor="project_init",
                    payload={"action": "project_created", "project": name})
                store.flush()
                for fn in ["nodes.jsonl", "edges.jsonl"]:
                    fp = os.path.join(proj_path, "graph", fn)
                    if not os.path.exists(fp):
                        open(fp, "w", encoding="utf-8").close()
            except Exception as e:
                pass
        else:
            for d in dirs_v1:
                os.makedirs(os.path.join(proj_path, d), exist_ok=True)
            for v in range(1, volumes + 1):
                os.makedirs(os.path.join(proj_path, f"outline/分纲/第{v}卷"), exist_ok=True)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        import yaml
        config = {
            "架构": "v2" if is_v2 else "v1",
            "项目名称": name,
            "项目类型": genre,
            "活跃风格": "通俗网文风",
            "当前状态": "起步",
            "预期结构": "待定",
            "创建时间": now,
            "写作进度": {
                "当前卷": 0,
                "当前章": 0,
                "卷大纲状态": "",
                "卷大纲完成数": 0,
            },
            "创作目标": {"目标字数": 200000, "目标章节数": 40, "每日目标": 2000},
            "上下文预热": {
                "cold": {"角色上限": 3, "情节线上限": 1, "世界观上限": 1},
                "warm": {"角色上限": 5, "情节线上限": 3, "世界观上限": 3},
                "hot": {"角色上限": 10, "情节线上限": 5, "世界观上限": 5},
                "弱信号检测": False,
            },
            "叙事密度": {
                "舒缓系数": 1.3,
                "标准系数": 1.0,
                "密集系数": 0.7,
                "场景期望字数": 3000,
                "密度表覆盖": {},  # 按子类型覆盖默认字数范围: {"开篇": {"舒缓": [4000,7000]}}
            },
        }
        if not is_v2:
            pass  # V1 兼容：不写额外字段

        cfg_path = os.path.join(proj_path, "config.yaml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        return _ok({"path": proj_path, "v2": is_v2})

    if op == "project.import":
        source = params.get("source_path") or params.get("source") or ""
        if isinstance(source, str):
            source = source.strip()
        if not os.path.exists(source):
            return _err(f"源路径不存在: {source}")
        if os.path.exists(proj_path):
            return _err(f"目标项目已存在: {proj_path}")
        import shutil
        shutil.copytree(source, proj_path)
        return _ok({"path": proj_path})

    if op == "project.status":
        if not os.path.isdir(proj_path):
            return _err(f"项目不存在: {name}")
        import yaml
        cfg_path = os.path.join(proj_path, "config.yaml")
        config = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        result = {"name": name, "path": proj_path, "config": config}
        is_v2 = config.get("架构") == "v2" or os.path.isdir(os.path.join(proj_path, "graph"))
        result["is_v2"] = is_v2
        if is_v2 and os.path.isfile(os.path.join(proj_path, "graph", "nodes.jsonl")):
            try:
                st = _get_store(proj_path)
                result["stats"] = st.stats()
            except Exception:
                result["stats"] = None
        phase = params.get("phase")
        if phase:
            config["写作阶段"] = phase
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            result["phase_updated"] = phase
        return _ok(result)

    if op == "project.resume":
        if not os.path.isdir(proj_path):
            return _err(f"项目不存在: {name}")
        import yaml
        from datetime import datetime, timezone
        cfg_path = os.path.join(proj_path, "config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        config["最后编辑"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        return _ok({"ok": True})

    if op == "project.switch":
        if not os.path.isdir(proj_path) and not params.get("dry_run"):
            return _err(f"项目不存在: {name}")
        import yaml
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        config = {}
        cfg_path = os.path.join(proj_path, "config.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        genre = config.get("项目类型", "未知")
        style = config.get("活跃风格", "通俗网文风")
        tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        ctx_dir = os.path.join(tool_root, ".omo", "notepads")
        os.makedirs(ctx_dir, exist_ok=True)
        ctx_path = os.path.join(ctx_dir, "novel-context.md")
        context = f"""__CURRENT_PROJECT__: {name}

# 项目上下文: {name}

> 由项目管理器自动生成。不要手动编辑此文件。

## 项目信息
- 项目名称：{name}
- 项目类型：{genre}
- 项目路径：{proj_path}
- 环境已初始化：True

## 当前状态
- 活跃风格：{style}
- 切换时间：{now}
"""
        with open(ctx_path, "w", encoding="utf-8") as f:
            f.write(context)
        return _ok({"ok": True, "project": name, "path": proj_path})

    if op == "project.delete":
        if not os.path.isdir(proj_path):
            return _err(f"项目不存在: {name}")
        if not params.get("force"):
            return _err("删除需要 --force 确认")
        import shutil
        shutil.rmtree(proj_path, ignore_errors=True)
        return _ok({"deleted": True})

    if op == "project.update_progress":
        if not os.path.isdir(proj_path):
            return _err(f"项目不存在: {name}")
        import yaml
        cfg_path = os.path.join(proj_path, "config.yaml")
        with open(cfg_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        progress = config.setdefault("写作进度", {})
        changed = []
        for key, fallback, pkey in [("current_volume", "currentVolume", "当前卷"), ("current_chapter", "currentChapter", "当前章"),
                                    ("volume_outline_status", "volumeOutlineStatus", "卷大纲状态"), ("volume_outline_done", "volumeOutlineDone", "卷大纲完成数")]:
            val = params.get(key) if key in params else params.get(fallback)
            if val is not None:
                progress[pkey] = val
                changed.append(f"{pkey}={val}")
        if changed:
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            return _ok({"updated": changed})
        return _ok({"updated": [], "info": "未指定任何进度字段"})

    return _err(f"未知 project 操作: {op}")


# ──────────────────────────────────────────────
#  环境操作
# ──────────────────────────────────────────────

def _handle_env(op: str, params: dict) -> str:
    import platform, subprocess
    from pathlib import Path

    def _discover_venv():
        cwd = Path.cwd().resolve()
        for p in [cwd, cwd.parent] + list(cwd.parents):
            if (p / ".venv").exists():
                return p / ".venv"
        tool_root = Path(_SHARED_DIR).parent.parent
        return tool_root / ".venv"

    VENV_DIR = _discover_venv()
    if op == "env.check":
        def get_ver():
            return sys.version_info[:2], f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
        py_ver, py_str = get_ver()
        venv_ok = (VENV_DIR / "Scripts" / "python.exe").exists() if platform.system() == "Windows" else (VENV_DIR / "bin" / "python3").exists()
        deps_ok = False
        missing = []
        if venv_ok:
            venv_python = VENV_DIR / "Scripts" / "python.exe" if platform.system() == "Windows" else VENV_DIR / "bin" / "python3"
            try:
                r = subprocess.run([str(venv_python), "-c", "import yaml; print(yaml.__version__)"], capture_output=True, text=True, timeout=10)
                deps_ok = r.returncode == 0
                if not deps_ok:
                    missing.append("PyYAML")
            except Exception:
                missing.append("PyYAML")
        return _ok({
            "python_version": py_str,
            "python_ok": py_ver >= (3, 8),
            "venv_exists": venv_ok,
            "venv_path": str(VENV_DIR),
            "deps_ok": deps_ok,
            "missing_deps": missing,
        })

    if op == "env.fix":
        import subprocess, platform
        venv_python = VENV_DIR / "Scripts" / "python.exe" if platform.system() == "Windows" else VENV_DIR / "bin" / "python3"
        req = Path(_SHARED_DIR) / "env" / "scripts" / "requirements.txt"
        if not req.exists():
            req = Path(_SHARED_DIR).parent.parent / ".opencode" / "shared" / "env" / "scripts" / "requirements.txt"
        if req.exists():
            r = subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(req)], capture_output=True, text=True, timeout=120)
            ok = r.returncode == 0
        else:
            r = subprocess.run([str(venv_python), "-m", "pip", "install", "pyyaml"], capture_output=True, text=True, timeout=60)
            ok = r.returncode == 0
        return _ok({"ok": ok, "stdout": r.stdout[-500:] if hasattr(r, 'stdout') else ""})

    if op == "env.force":
        import shutil, platform, subprocess
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        python_cmd = "python" if platform.system() == "Windows" else "python3"
        r1 = subprocess.run([python_cmd, "-m", "venv", str(VENV_DIR)], capture_output=True, text=True, timeout=60)
        if r1.returncode != 0:
            return _err(f"创建虚拟环境失败: {r1.stderr}")
        req = Path(_SHARED_DIR) / "env" / "scripts" / "requirements.txt"
        if not req.exists():
            req = Path(_SHARED_DIR).parent.parent / ".opencode" / "shared" / "env" / "scripts" / "requirements.txt"
        venv_python = VENV_DIR / "Scripts" / "python.exe" if platform.system() == "Windows" else VENV_DIR / "bin" / "python3"
        if req.exists():
            r2 = subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(req)], capture_output=True, text=True, timeout=120)
            ok = r2.returncode == 0
        else:
            r2 = subprocess.run([str(venv_python), "-m", "pip", "install", "pyyaml"], capture_output=True, text=True, timeout=60)
            ok = r2.returncode == 0
        return _ok({"ok": ok})

    return _err(f"未知 env 操作: {op}")


# ──────────────────────────────────────────────
#  知识库操作
# ──────────────────────────────────────────────

def _handle_knowledge(op: str, params: dict) -> str:
    if op == "knowledge.read":
        slug = params.get("slug", "")
        if not slug:
            return _err("knowledge.read 需要 slug")
        topic = params.get("topic", "概要")
        novels_root = _find_novels_root()
        proj = _resolve_project(params.get("project", "."))
        from knowledge_reader import KnowledgeReader, resolve_knowledge_root
        root = resolve_knowledge_root(str(proj)) if hasattr(resolve_knowledge_root, '__call__') else str(proj)
        reader = KnowledgeReader(root)
        import yaml
        slug_dir = Path(proj) / "knowledge" / slug
        if not slug_dir.exists():
            slug_dir = Path(novels_root).parent / "knowledge" / slug
        if not slug_dir.exists():
            slug_dir = Path(_SHARED_DIR).parent.parent / "knowledge" / slug
        source_info = {}
        sp = slug_dir / "source.yaml"
        if sp.exists():
            with open(sp, "r", encoding="utf-8") as f:
                source_info = yaml.safe_load(f) or {}
        title = source_info.get("title", slug)
        author = source_info.get("author", "")
        chapter_count = source_info.get("chapter_count", "?")
        topics = [t.strip() for t in topic.split("|") if t.strip()]
        content = reader.get(slug, topics=topics, max_chars=2000) if hasattr(reader, 'get') else ""
        return _ok({"slug": slug, "title": title, "author": author, "chapter_count": chapter_count, "content": content})

    if op == "knowledge.list_books":
        novels_root = _find_novels_root()
        from knowledge_reader import resolve_knowledge_root
        root = resolve_knowledge_root(str(novels_root)) if hasattr(resolve_knowledge_root, '__call__') else str(novels_root)
        reader = __import__("knowledge_reader", fromlist=["KnowledgeReader"])
        if hasattr(reader, "KnowledgeReader"):
            r = reader.KnowledgeReader(root)
            if hasattr(r, "list_available_books"):
                return _ok(r.list_available_books())
        books = []
        kdir = Path(root) / "knowledge"
        if kdir.exists():
            for d in kdir.iterdir():
                if d.is_dir() and (d / "source.yaml").exists():
                    import yaml
                    with open(d / "source.yaml", "r", encoding="utf-8") as f:
                        info = yaml.safe_load(f) or {}
                    books.append({"slug": d.name, "title": info.get("title", d.name), "author": info.get("author", ""), "chapter_count": info.get("chapter_count", "?")})
        return _ok(books)

    return _err(f"未知 knowledge 操作: {op}")


# ──────────────────────────────────────────────
#  会话管理操作
# ──────────────────────────────────────────────

def _handle_session(op: str, params: dict) -> str:
    project = _resolve_project(params.get("project", ""))
    if not project or not os.path.isfile(os.path.join(project, "config.yaml")):
        return _err(f"项目不存在或路径无效: {project}")

    from session import SessionManager, CycleType, SessionPhase
    mgr = SessionManager(project)
    mgr.load_user_state()

    if op == "session.start":
        from graph_schema import UnitType
        if mgr.active_session:
            s = mgr.resume_session()
        else:
            ft = UnitType[params.get("type", "SCENE").upper()]
            fid = params.get("id", "")
            s = mgr.start_session(focus_type=ft, focus_unit_id=fid)
        mgr.save_user_state()
        return _ok({"session_id": s.id if hasattr(s, 'id') else str(s)})

    if op == "session.build_workspace":
        from workspace import WorkspaceBuilder
        store = _get_store(project)
        b = WorkspaceBuilder(store)
        fid = params.get("id", "")
        level = params.get("level", "warm")
        ws = b.build(fid, preheat_level=level)
        return _ok({"context": ws.to_prompt_block(level)})

    if op == "session.info":
        """
        返回当前会话状态，供编排层决策。
        
        chunk 焦点时：
          - iteration_count: 该章节已有 CHUNK 数量（决定版本标签）
          - exist_chunks: 已有正文路径列表（供 preheat 加载）
          - cycle_type: 当前循环类型
          - session_phase: 当前阶段
          - preheat: 推荐的预热级别
        """
        if not mgr.active_session:
            return _ok({
                "has_session": False,
                "cycle_type": None,
                "session_phase": None,
                "iteration_count": 0,
                "exist_chunks": [],
                "preheat": "cold",
            })
        s = mgr.active_session
        iteration_count = 0
        exist_chunks = []
        preheat = "warm"

        # chunk 焦点：从 graph 统计已有正文数
        if s.focus and s.focus.type and hasattr(s.focus.unit_id, '__str__'):
            try:
                from graph_store import GraphStore
                from graph_schema import UnitType
                store = GraphStore(project)
                store.initialize()
                focus_unit = store.get_unit(s.focus.unit_id)
                if focus_unit and focus_unit.type == UnitType.CHUNK:
                    from graph_schema import get_unit_chapter
                    chapter = get_unit_chapter(focus_unit)
                    if chapter:
                        chunks = store.find_units(type=UnitType.CHUNK)
                        same_chapter = [c for c in chunks if get_unit_chapter(c) == chapter]
                        iteration_count = len(same_chapter)
                        paths = []
                        for c in same_chapter:
                            if c.content:
                                try:
                                    meta = json.loads(c.content) if isinstance(c.content, str) else c.content
                                    p = meta.get("正文路径", "")
                                    if p:
                                        full = os.path.join(project, p)
                                        paths.append(full)
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        exist_chunks = paths
                elif focus_unit and focus_unit.type == UnitType.SCENE:
                    # scene 焦点时找关联的 CHUNK
                    neighbors = store.get_neighbors(s.focus.unit_id, max_depth=1)
                    chunk_ids = set()
                    for neighbors_at_depth in neighbors.values():
                        for nid in neighbors_at_depth:
                            n = store.get_unit(nid)
                            if n and n.type == UnitType.CHUNK:
                                chunk_ids.add(nid)
                    iteration_count = len(chunk_ids)
                    if iteration_count > 0:
                        preheat = "hot"
            except Exception as e:
                pass

        return _ok({
            "has_session": True,
            "session_id": s.id if hasattr(s, 'id') else str(s),
            "focus_type": s.focus.type.value if hasattr(s.focus.type, 'value') else str(s.focus.type) if s.focus.type else None,
            "cycle_type": s.cycle_type.value if hasattr(s.cycle_type, 'value') else str(s.cycle_type) if s.cycle_type else None,
            "session_phase": s.phase.value if hasattr(s.phase, 'value') else str(s.phase) if hasattr(s, 'phase') and s.phase else None,
            "iteration_count": iteration_count,
            "exist_chunks": exist_chunks,
            "preheat": preheat,
        })

    if op == "session.set_cycle":
        if not mgr.active_session:
            return _err("没有活跃会话，请先启动会话")
        cycle_raw = params.get("cycle_type", "")
        if not cycle_raw:
            return _err("set_cycle 需要 cycle_type 参数")
        try:
            ct = CycleType[cycle_raw.upper()]
        except KeyError:
            return _err(f"无效 cycle_type: {cycle_raw}，可选: {', '.join(c.name for c in CycleType)}")
        mgr.set_cycle_type(ct)
        mgr.save_user_state()
        return _ok({"cycle_type": ct.value})

    if op == "session.set_phase":
        if not mgr.active_session:
            return _err("没有活跃会话，请先启动会话")
        phase_raw = params.get("phase", "")
        if not phase_raw:
            return _err("set_phase 需要 phase 参数")
        try:
            ph = SessionPhase[phase_raw.upper()]
        except KeyError:
            return _err(f"无效 phase: {phase_raw}，可选: {', '.join(p.name for p in SessionPhase)}")
        mgr.set_phase(ph)
        mgr.save_user_state()
        return _ok({"phase": ph.value})

    return _err(f"未知 session 操作: {op}")


# ──────────────────────────────────────────────
#  偏差管理操作
# ──────────────────────────────────────────────

def _handle_deviation(op: str, params: dict) -> str:
    project = _resolve_project(params.get("project", ""))
    if not project or not os.path.isdir(os.path.join(project, "graph")):
        return _err(f"项目路径无效: {project}")

    from deviation_manager import DeviationManager, DeviationItem
    mgr = DeviationManager(project)

    if op == "deviation.merge":
        findings = params.get("findings", [])
        if isinstance(findings, str):
            findings = json.loads(findings)
        source = params.get("source", "novel-tool")
        scan_version = params.get("scan_version", 0)
        items = []
        for f in findings:
            item = DeviationItem(
                id="",
                dimension=f.get("dimension", "unknown"),
                entity=f.get("entity", ""),
                entity_id=f.get("entity_id", ""),
                scanned_version=f.get("scanned_version", scan_version),
                status=f.get("status", "pending"),
                severity=f.get("severity", "info"),
                summary=f.get("summary", ""),
                detail=f.get("detail", ""),
                suggested_changeset=f.get("suggested_changeset"),
            )
            items.append(item)
        mgr.merge(items)
        full_sv = params.get("full_scan_version")
        if full_sv is not None:
            mgr.full_scan_version = int(full_sv)
        mgr.save()
        stats = mgr.stats()
        return _ok({"merged": len(findings), "total": stats["total"], "full_scan_version": mgr.full_scan_version})

    if op == "deviation.list":
        status_filter = params.get("status", "")
        all_items = mgr.list_all() if not status_filter else [d for d in mgr.list_all() if d.status == status_filter]
        return _ok([
            {
                "id": d.id,
                "dimension": d.dimension,
                "entity": d.entity,
                "status": d.status,
                "severity": d.severity,
                "summary": d.summary,
                "detail": d.detail,
                "detection_count": d.detection_count,
            }
            for d in all_items
        ])

    if op == "deviation.pending":
        items = mgr.filter_for_presentation()
        return _ok([
            {
                "id": d.id,
                "dimension": d.dimension,
                "entity": d.entity,
                "severity": d.severity,
                "summary": d.summary,
            }
            for d in items
        ])

    if op == "deviation.resolve":
        did = params.get("id", "")
        ok = mgr.resolve(did)
        if ok:
            mgr.save()
            return _ok({"resolved": True})
        return _err(f"偏差不存在: {did}")

    if op == "deviation.retain":
        did = params.get("id", "")
        ok = mgr.retain(did)
        if ok:
            mgr.save()
            return _ok({"retained": True})
        return _err(f"偏差不存在: {did}")

    if op == "deviation.delete":
        did = params.get("id", "")
        ok = mgr.delete(did)
        if ok:
            mgr.save()
            return _ok({"deleted": True})
        return _err(f"偏差不存在: {did}")

    if op == "deviation.stats":
        return _ok(mgr.stats())

    return _err(f"未知 deviation 操作: {op}")


# ──────────────────────────────────────────────
#  统一入口
# ──────────────────────────────────────────────

def handle_request(request: dict) -> str:
    try:
        op = request.get("operation", "")
        if not op:
            return _err("缺少 operation 字段")
        if op.startswith("graph."):
            return _handle_graph(op, request)
        if op.startswith("project."):
            return _handle_project(op, request)
        if op.startswith("env."):
            return _handle_env(op, request)
        if op.startswith("knowledge."):
            return _handle_knowledge(op, request)
        if op.startswith("session."):
            return _handle_session(op, request)
        if op.startswith("deviation."):
            return _handle_deviation(op, request)
        return _err(f"未知操作领域: {op}")
    except Exception as e:
        import traceback
        return _err(f"{e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    raw = ""
    if len(sys.argv) >= 2:
        raw = sys.argv[1]
        # Windows shell 兼容：去除首尾多余引号/空格
        # PowerShell/CMD 传递带空格的参数时，外层引号会残留
        while raw and raw[0] in ('"', "'", " ", "\t"):
            raw = raw[1:]
        while raw and raw[-1] in ('"', "'", " ", "\t"):
            raw = raw[:-1]
    else:
        # 从 stdin 读取（novel-tool.ts 通过 stdin 传入 JSON 避免 Windows 转义问题）
        import sys
        raw = sys.stdin.read().strip()

    request = None
    err_msg = None

    # 1. 标准 json.loads
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        err_msg = str(e)

    # 2. 尝试 json_repair 容错解析（项目已依赖 json_repair）
    if request is None:
        try:
            from json_repair import loads as repair_loads
            request = repair_loads(raw)
        except Exception:
            pass

    # 3. 针对 Windows 路径反斜杠导致 JSON 非法的额外修复：
    # 将未转义的反斜杠替换为双反斜杠后再次尝试
    if request is None:
        try:
            import re
            # 把 JSON 字符串中 "C:\Users" 这种反斜杠统一替换成双反斜杠
            fixed = re.sub(r'(?<!\\)\\(?!\\|"|/|b|f|n|r|t|u[0-9a-fA-F]{4})', r'\\\\', raw)
            request = json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # 4. 某些终端/环境会把 JSON 内部的双引号替换成单引号，尝试恢复
    if request is None:
        try:
            fixed = raw.replace("'", '"')
            request = json.loads(fixed)
        except json.JSONDecodeError:
            pass

    if request is None:
        print(_err(f"JSON 解析失败: {err_msg}"))
        sys.exit(1)

    result = handle_request(request)
    print(result)
