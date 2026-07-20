"""
handlers_session.py — 会话管理纯业务逻辑函数。

涵盖 5 个操作：start / build_workspace / info / set_cycle / set_phase。
提取自 novel_tool.py _handle_session。
"""

import json
import os
import sys
from typing import Optional

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


def _resolve_project(project: str) -> str:
    if not project:
        return ""
    if os.path.isabs(project):
        return project
    env = os.environ.get("NOVELS_ROOT")
    novels_root = env if env and os.path.isdir(env) else os.path.join(os.getcwd(), "novels")
    cand = os.path.join(novels_root, project)
    if os.path.isdir(cand):
        return cand
    return os.path.abspath(project)


def _get_store(project_root: str):
    from graph_store import GraphStore
    store = GraphStore(project_root)
    store.initialize()
    return store


def _validate_project(project_root: str) -> bool:
    return bool(project_root) and os.path.isfile(os.path.join(project_root, "config.yaml"))


def handle_session_start(project_root: str, type: str, id: str) -> dict:
    """启动/恢复创作会话。"""
    from graph_schema import UnitType
    from session import SessionManager

    project = _resolve_project(project_root)
    if not _validate_project(project):
        return {"error": f"项目不存在或路径无效: {project}"}

    mgr = SessionManager(project)
    mgr.load_user_state()

    if mgr.active_session:
        s = mgr.resume_session()
    else:
        ft = UnitType[type.upper()]
        s = mgr.start_session(focus_type=ft, focus_unit_id=id)

    mgr.save_user_state()
    return {"session_id": s.id if hasattr(s, 'id') else str(s)}


def handle_session_build_workspace(project_root: str, id: str, level: str = "warm") -> dict:
    """构建工作空间上下文。"""
    from workspace import WorkspaceBuilder

    project = _resolve_project(project_root)
    if not _validate_project(project):
        return {"error": f"项目不存在或路径无效: {project}"}

    store = _get_store(project)
    b = WorkspaceBuilder(store)
    ws = b.build(id, preheat_level=level)

    return {"context": ws.to_prompt_block(level)}


def handle_session_info(project_root: str) -> dict:
    """返回当前会话状态。"""
    from session import SessionManager, CycleType, SessionPhase

    project = _resolve_project(project_root)
    if not _validate_project(project):
        return {"error": f"项目不存在或路径无效: {project}"}

    mgr = SessionManager(project)
    mgr.load_user_state()

    if not mgr.active_session:
        return {
            "has_session": False,
            "cycle_type": None,
            "session_phase": None,
            "iteration_count": 0,
            "exist_chunks": [],
            "preheat": "cold",
        }

    s = mgr.active_session
    iteration_count = 0
    exist_chunks = []

    if s.focus and s.focus.type and hasattr(s.focus.unit_id, '__str__'):
        try:
            from graph_store import GraphStore
            from graph_schema import UnitType, get_unit_chapter

            store = GraphStore(project)
            store.initialize()
            focus_unit = store.get_unit(s.focus.unit_id)

            if focus_unit and focus_unit.type == UnitType.CHUNK:
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
                neighbors = store.get_neighbors(s.focus.unit_id, max_depth=1)
                chunk_ids = set()
                for neighbors_at_depth in neighbors.values():
                    for nid in neighbors_at_depth:
                        n = store.get_unit(nid)
                        if n and n.type == UnitType.CHUNK:
                            chunk_ids.add(nid)
                iteration_count = len(chunk_ids)
        except Exception:
            pass

    return {
        "has_session": True,
        "session_id": s.id if hasattr(s, 'id') else str(s),
        "focus_type": s.focus.type.value if hasattr(s.focus.type, 'value') else str(s.focus.type) if s.focus.type else None,
        "cycle_type": s.cycle_type.value if hasattr(s.cycle_type, 'value') else str(s.cycle_type) if s.cycle_type else None,
        "session_phase": s.phase.value if hasattr(s.phase, 'value') else str(s.phase) if hasattr(s, 'phase') and s.phase else None,
        "iteration_count": iteration_count,
        "exist_chunks": exist_chunks,
        "preheat": mgr.recommend_preheat_level(),
    }


def handle_session_set_cycle(project_root: str, cycle_type: str) -> dict:
    """设置会话循环类型。"""
    from session import SessionManager, CycleType

    project = _resolve_project(project_root)
    if not _validate_project(project):
        return {"error": f"项目不存在或路径无效: {project}"}

    mgr = SessionManager(project)
    mgr.load_user_state()

    if not mgr.active_session:
        return {"error": "没有活跃会话，请先启动会话"}

    try:
        ct = CycleType[cycle_type.upper()]
    except KeyError:
        return {"error": f"无效 cycle_type: {cycle_type}"}

    mgr.set_cycle_type(ct)
    mgr.save_user_state()
    return {"cycle_type": ct.value}


def handle_session_set_phase(project_root: str, phase: str) -> dict:
    """设置会话阶段。"""
    from session import SessionManager, SessionPhase

    project = _resolve_project(project_root)
    if not _validate_project(project):
        return {"error": f"项目不存在或路径无效: {project}"}

    mgr = SessionManager(project)
    mgr.load_user_state()

    if not mgr.active_session:
        return {"error": "没有活跃会话，请先启动会话"}

    try:
        ph = SessionPhase[phase.upper()]
    except KeyError:
        return {"error": f"无效 phase: {phase}"}

    mgr.set_phase(ph)
    mgr.save_user_state()
    return {"phase": ph.value}
