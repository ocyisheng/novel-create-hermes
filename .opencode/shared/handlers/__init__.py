"""
handlers — 纯业务逻辑函数库。

每个 handler 函数接受规范化参数名，返回 Python dict。
不依赖 argparse、不 print、不 sys.exit。
供 novel_tool.py（JSON 层）和 cli.py（格式化输出层）共同调用。
"""

from .handlers_graph import (
    handle_list_relation_types,
    handle_get_unit,
    handle_find_unit,
    handle_search,
    handle_list_units,
    handle_stats,
    handle_get_modified_units,
    handle_get_neighbors,
    handle_check_consistency,
    handle_recent_events,
    handle_create_unit,
    handle_update_unit,
    handle_archive_unit,
    handle_purge_archived,
    handle_add_relation,
    handle_update_relation,
    handle_flush,
    handle_fix_asymmetry,
    handle_get_relations,
    handle_remove_relation,
    handle_batch_infer,
    handle_export_docs,
    handle_export_chunks,
    handle_migrate,
    handle_find_descendants,
    handle_find_ancestors,
    handle_rebuild_structure_path,
    handle_migrate_structure_to_edges,
    handle_schema_info,
    handle_change_type,
    handle_constraint_check,
    handle_quality_check,
)

from .handlers_project import (
    handle_project_new,
    handle_project_import,
    handle_project_status,
    handle_project_resume,
    handle_project_switch,
    handle_project_delete,
)

from .handlers_env import (
    handle_env_check,
    handle_env_fix,
    handle_env_force,
)

from .handlers_session import (
    handle_session_start,
    handle_session_build_workspace,
    handle_session_info,
    handle_session_set_cycle,
    handle_session_set_phase,
)

from .handlers_deviation import (
    handle_deviation_merge,
    handle_deviation_list,
    handle_deviation_pending,
    handle_deviation_resolve,
    handle_deviation_retain,
    handle_deviation_delete,
    handle_deviation_stats,
    handle_deviation_summary,
)

from .handlers_knowledge import (
    handle_knowledge_read,
    handle_knowledge_list_books,
)

from .handlers_analyze import (
    handle_analyze_usage,
    handle_analyze_telemetry,
)

from .handlers_summary import (
    handle_save_summary,
    handle_list_summaries,
    handle_read_summary,
)

from .handlers_analysis import (
    handle_save_analysis,
    handle_resolve_analysis,
    handle_read_analysis,
    handle_list_analysis,
)

from .handlers_server import (
    handle_server_start,
    handle_server_restart,
    handle_server_stop,
)


OPERATION_REGISTRY = {
    # graph reads
    "graph.list_relation_types": {
        "handler": handle_list_relation_types,
        "params": {},
    },
    "graph.get_unit": {
        "handler": handle_get_unit,
        "params": {"project_root": {"required": True}, "id": {}, "name": {}},
    },
    "graph.find_unit": {
        "handler": handle_find_unit,
        "params": {"project_root": {"required": True}, "name": {}, "keyword": {}, "limit": {}},
    },
    "graph.search": {
        "handler": handle_search,
        "params": {"project_root": {"required": True}, "keyword": {}, "pattern": {}, "name": {}, "scope": {}, "regex": {}, "case_sensitive": {}, "limit": {}, "verbose": {}, "tags": {}, "chapter": {}},
    },
    "graph.list_units": {
        "handler": handle_list_units,
        "params": {"project_root": {"required": True}, "unit_type": {}, "limit": {}, "status": {}, "tags": {}, "chapter": {}, "volume": {}, "offset": {}},
    },
    "graph.stats": {
        "handler": handle_stats,
        "params": {"project_root": {"required": True}},
    },
    "graph.get_modified_units": {
        "handler": handle_get_modified_units,
        "params": {"project_root": {"required": True}, "since_version": {}, "limit": {}, "offset": {}},
    },
    "graph.get_neighbors": {
        "handler": handle_get_neighbors,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "rel_type": {}, "limit": {}, "max_depth": {}},
    },
    "graph.check": {
        "handler": handle_check_consistency,
        "params": {"project_root": {"required": True}},
    },
    "graph.recent_events": {
        "handler": handle_recent_events,
        "params": {"project_root": {"required": True}, "limit": {}},
    },
    # graph writes
    "graph.create_unit": {
        "handler": handle_create_unit,
        "params": {"project_root": {"required": True}, "unit_type": {"required": True}, "name": {"required": True}, "content": {}, "file_path": {}, "tags": {}, "chapter": {}, "parent_id": {}, "actor": {}, "session_id": {}, "if_exists": {}},
    },
    "graph.update_unit": {
        "handler": handle_update_unit,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "content": {}, "file_path": {}, "name": {}, "tags": {}, "status": {}, "actor": {}, "session_id": {}},
    },
    "graph.archive_unit": {
        "handler": handle_archive_unit,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "actor": {}},
    },
    "graph.purge_archived": {
        "handler": handle_purge_archived,
        "params": {"project_root": {"required": True}, "ids": {}, "force": {}, "actor": {}},
    },
    "graph.add_relation": {
        "handler": handle_add_relation,
        "params": {"project_root": {"required": True}, "source": {"required": True}, "target": {"required": True}, "rel_type": {"required": True}, "bidirectional": {}, "label": {}, "source_role": {}, "target_role": {}, "weight": {}, "actor": {}, "session_id": {}, "payload": {}},
    },
    "graph.update_relation": {
        "handler": handle_update_relation,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "label": {}, "weight": {}, "description": {}, "payload": {}, "source_role": {}, "target_role": {}, "actor": {}},
    },
    "graph.flush": {
        "handler": handle_flush,
        "params": {"project_root": {"required": True}, "skip_constraint_check": {}},
    },
    "constraint.check": {
        "handler": handle_constraint_check,
        "params": {"project_root": {"required": True}, "full": {}},
    },
    "graph.quality_check": {
        "handler": handle_quality_check,
        "params": {
            "project_root": {"required": True},
            "layers": {"required": False},
            "full": {"required": False},
        },
    },
    "graph.fix_asymmetry": {
        "handler": handle_fix_asymmetry,
        "params": {"project_root": {"required": True}},
    },
    "graph.get_relations": {
        "handler": handle_get_relations,
        "params": {"project_root": {"required": True}, "id": {}, "rel_type": {}, "direction": {}, "label": {}, "label_substring": {}, "role": {}, "role_substring": {}, "min_weight": {}, "max_weight": {}, "limit": {}, "offset": {}},
    },
    "graph.remove_relation": {
        "handler": handle_remove_relation,
        "params": {"project_root": {"required": True}, "id": {}, "source": {}, "target": {}, "rel_type": {}, "actor": {}},
    },
    "graph.batch_infer": {
        "handler": handle_batch_infer,
        "params": {"project_root": {"required": True}, "actor": {}},
    },
    "graph.export_docs": {
        "handler": handle_export_docs,
        "params": {"project_root": {"required": True}, "out": {}},
    },
    "graph.export_chunks": {
        "handler": handle_export_chunks,
        "params": {"project_root": {"required": True}, "out": {}},
    },
    "graph.migrate": {
        "handler": handle_migrate,
        "params": {"project_root": {"required": True}, "dry_run": {}, "verify": {}, "report": {}},
    },
    # hierarchy
    "graph.find_descendants": {
        "handler": handle_find_descendants,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "max_depth": {}},
    },
    "graph.find_ancestors": {
        "handler": handle_find_ancestors,
        "params": {"project_root": {"required": True}, "id": {"required": True}},
    },
    "graph.rebuild_structure_path": {
        "handler": handle_rebuild_structure_path,
        "params": {"project_root": {"required": True}, "id": {"required": True}},
    },
    "graph.migrate_structure_to_edges": {
        "handler": handle_migrate_structure_to_edges,
        "params": {"project_root": {"required": True}, "actor": {}},
    },
    "graph.schema_info": {
        "handler": handle_schema_info,
        "params": {"unit_type": {"required": True}},
    },
    "graph.change_type": {
        "handler": handle_change_type,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "new_type": {"required": True}, "actor": {}},
    },
    # project
    "project.new": {
        "handler": handle_project_new,
        "params": {"project_root": {"required": True}, "genre": {"required": True}, "v2": {}, "volumes": {}, "acts": {}, "structure": {}},
    },
    "project.import": {
        "handler": handle_project_import,
        "params": {"project_root": {"required": True}, "source_path": {"required": True}},
    },
    "project.status": {
        "handler": handle_project_status,
        "params": {"project_root": {"required": True}, "phase": {}},
    },
    "project.resume": {
        "handler": handle_project_resume,
        "params": {"project_root": {"required": True}},
    },
    "project.switch": {
        "handler": handle_project_switch,
        "params": {"project_root": {"required": True}, "dry_run": {}},
    },
    "project.delete": {
        "handler": handle_project_delete,
        "params": {"project_root": {"required": True}, "force": {}},
    },
    # env
    "env.check": {
        "handler": handle_env_check,
        "params": {},
    },
    "env.fix": {
        "handler": handle_env_fix,
        "params": {},
    },
    "env.force": {
        "handler": handle_env_force,
        "params": {},
    },
    # session
    "session.start": {
        "handler": handle_session_start,
        "params": {"project_root": {"required": True}, "focus_type": {"required": True}, "id": {"required": True}},
    },
    "session.build_workspace": {
        "handler": handle_session_build_workspace,
        "params": {"project_root": {"required": True}, "id": {"required": True}, "preheat_level": {}},
    },
    "session.info": {
        "handler": handle_session_info,
        "params": {"project_root": {"required": True}},
    },
    "session.set_cycle": {
        "handler": handle_session_set_cycle,
        "params": {"project_root": {"required": True}, "cycle_type": {"required": True}},
    },
    "session.set_phase": {
        "handler": handle_session_set_phase,
        "params": {"project_root": {"required": True}, "phase": {"required": True}},
    },
    # deviation
    "deviation.merge": {
        "handler": handle_deviation_merge,
        "params": {"project_root": {"required": True}, "findings": {"required": True}, "source": {}, "scan_version": {}, "full_scan_version": {}},
    },
    "deviation.list": {
        "handler": handle_deviation_list,
        "params": {"project_root": {"required": True}, "status": {}, "limit": {}, "offset": {}, "severity": {}, "dimension": {}},
    },
    "deviation.pending": {
        "handler": handle_deviation_pending,
        "params": {"project_root": {"required": True}, "limit": {}, "offset": {}},
    },
    "deviation.resolve": {
        "handler": handle_deviation_resolve,
        "params": {"project_root": {"required": True}, "id": {"required": True}},
    },
    "deviation.retain": {
        "handler": handle_deviation_retain,
        "params": {"project_root": {"required": True}, "id": {"required": True}},
    },
    "deviation.delete": {
        "handler": handle_deviation_delete,
        "params": {"project_root": {"required": True}, "id": {"required": True}},
    },
    "deviation.stats": {
        "handler": handle_deviation_stats,
        "params": {"project_root": {"required": True}},
    },
    "deviation.summary": {
        "handler": handle_deviation_summary,
        "params": {"project_root": {"required": True}},
    },
    # knowledge
    "knowledge.read": {
        "handler": handle_knowledge_read,
        "params": {"project_root": {"required": True}, "slug": {"required": True}, "topic": {}},
    },
    "knowledge.list_books": {
        "handler": handle_knowledge_list_books,
        "params": {},
    },
    # analyze
    "analyze.usage": {
        "handler": handle_analyze_usage,
        "params": {"project_root": {"required": True}, "mode": {}, "json_output": {}},
    },
    "analyze.telemetry": {
        "handler": handle_analyze_telemetry,
        "params": {"project_root": {}},
    },
    # summary（统一脚本：主 Agent 会话 + 子 Agent 调用，record_type 区分，路径分流）
    "summary.save": {
        "handler": handle_save_summary,
        "params": {"project_root": {"required": True}, "content": {},
                    "session_id": {}, "focus_type": {}, "focus_name": {}, "tags": {},
                    "record_type": {},
                    "task_id": {}, "subagent": {}, "result": {}, "preheat_level": {},
                    "cycle_type": {}, "humanize": {}, "prompt_summary": {}, "result_summary": {},
                    "new_units": {}, "updated_units": {}, "duration_estimate_ms": {}, "error_summary": {},
                    "user_intent": {}, "conflict_decision": {}, "failure_analysis": {},
                    "optimization_clue": {}},
    },
    "summary.list": {
        "handler": handle_list_summaries,
        "params": {"project_root": {"required": True}, "limit": {}, "offset": {}, "tag": {},
                    "record_type": {}, "subagent": {}, "result": {}, "project": {}},
    },
    "summary.read": {
        "handler": handle_read_summary,
        "params": {"project_root": {"required": True}, "file": {"required": True}, "record_type": {}},
    },
    # analysis
    "analysis.save": {
        "handler": handle_save_analysis,
        "params": {"content": {}, "sources": {}, "project": {}},
    },
    "analysis.read": {
        "handler": handle_read_analysis,
        "params": {"version": {}, "file": {}},
    },
    "analysis.resolve": {
        "handler": handle_resolve_analysis,
        "params": {"file": {}, "clue": {}, "note": {}},
    },
    "analysis.list": {
        "handler": handle_list_analysis,
        "params": {},
    },
    # server
    "web.start": {
        "handler": handle_server_start,
        "params": {"project_root": {"required": True}, "host": {}, "port": {}},
    },
    "web.stop": {
        "handler": handle_server_stop,
        "params": {},
    },
    "web.restart": {
        "handler": handle_server_restart,
        "params": {"project_root": {}, "host": {}, "port": {}},
    },
}


def run_operation(op_name: str, **params) -> dict:
    """调度到对应的 handler 函数。

    只传递 registry 中注册的参数，自动过滤无关参数（如 project_root
    对无需它的操作）。

    Args:
        op_name: 操作名，如 "graph.create_unit"
        **params: 规范化参数（参数名已映射为规范名）

    Returns:
        handler 返回的 dict（可能含 "error" 键表示失败）
    """
    entry = OPERATION_REGISTRY.get(op_name)
    if not entry:
        return {"error": f"未知操作: {op_name}"}
    accepted = set(entry["params"].keys())
    filtered = {k: v for k, v in params.items() if k in accepted}
    try:
        return entry["handler"](**filtered)
    except Exception as e:
        import traceback
        return {"error": f"{e}\n{traceback.format_exc()}"}
