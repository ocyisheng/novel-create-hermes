#!/usr/bin/env python3
"""
novel_tool.py — V2 小说创作统一工具句柄（薄 JSON 适配层）。

被 novel-tool.ts 调用，将 JSON request 适配为规范化参数后交给 handlers 模块。
不再包含业务逻辑——纯参数映射 + JSON 包装。

用法: python novel_tool.py '<json-string>'
"""

import sys
import os
import json
import time
import signal
from datetime import datetime, timezone
from typing import Dict, Optional

# 确保 shared/ 和 shared/v2/ 在 sys.path 中
_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


# ── 守护进程日志 ─────────────────────────────────────────────────────

class _DaemonLogger:
    """守护进程结构化日志，写入 graph/daemon.log。"""
    
    def __init__(self):
        self._log_file = None
    
    def open(self, graph_dir: str):
        # 写入 .engine/daemon/daemon.log（引擎级日志，非项目级）
        _tool_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        _engine_dir = os.path.join(_tool_root, ".engine", "daemon")
        os.makedirs(_engine_dir, exist_ok=True)
        log_path = os.path.join(_engine_dir, "daemon.log")
        try:
            self._log_file = open(log_path, "a", encoding="utf-8")
        except OSError:
            self._log_file = None
    
    def log(self, event: str, **fields):
        if not self._log_file:
            return
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        try:
            self._log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._log_file.flush()
        except Exception:
            pass
    
    def close(self):
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None


_DAEMON_LOG = _DaemonLogger()


# ── JSON 响应工具 ───────────────────────────────────────────────────────

def _ok(data) -> str:
    return json.dumps({"success": True, "data": data}, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"success": False, "error": str(msg)}, ensure_ascii=False)


# ── 项目路径解析 ─────────────────────────────────────────────────────────

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


# ── 参数适配：novel_tool 参数名 → 规范参数名 ────────────────────────────

# novel_tool.py 参数 → handler 规范参数名的映射表
_PARAM_MAP = {
    # 通用
    "id": "id", "name": "name",
    "unit_type": "unit_type", "rel_type": "rel_type", "focus_type": "focus_type",
    "content": "content", "file": "file_path",
    "tags": "tags", "chapter": "chapter",
    "actor": "actor", "limit": "limit",
    "keyword": "keyword", "pattern": "pattern", "verbose": "verbose",
    "scope": "scope", "regex": "regex",
    "case_sensitive": "case_sensitive",
    "since_version": "since_version",
    "status": "status",
    "out": "out",
    "force": "force",
    "dry_run": "dry_run",
    "parent_id": "parent_id",
    # 关系
    "source": "source", "target": "target",
    "bidirectional": "bidirectional",
    "label": "label",
    "direction": "direction",
    # 可视化
    "character": "character", "timeline": "timeline",
    "open": "open_browser",
    "incremental": "incremental",
    # 迁移
    "verify": "verify", "report": "report",
    # 层级查询
    "max_depth": "max_depth",
    # 项目
    "genre": "genre", "volumes": "volumes",
    "acts": "acts", "structure": "structure",
    "v2": "v2",
    "source_path": "source_path",
    "phase": "phase",
    # 会话
    "cycle_type": "cycle_type",
    "level": "level",
    "session_id": "session_id",
    # summary
    "focus_name": "focus_name",
    # 偏差
    "findings": "findings",
    "scan_version": "scan_version",
    "full_scan_version": "full_scan_version",
    # 知识库
    "slug": "slug", "topic": "topic",
    # subagent trace
    "task_id": "task_id",
    "subagent": "subagent",
    "preheat_level": "preheat_level",
    "humanize": "humanize",
    "prompt_summary": "prompt_summary",
    "result_summary": "result_summary",
    "new_units": "new_units",
    "updated_units": "updated_units",
    "duration_estimate_ms": "duration_estimate_ms",
    "error_summary": "error_summary",
}

# 需要额外处理别名/兼容性的操作
_PARAM_ALIASES = {
    # graph.search: novel_tool 接受 scope/unit_type/unitType
    "graph.search": {"scope": ["scope", "unit_type", "unitType"]},
    # graph.get_neighbors: rel_type/relType
    "graph.get_neighbors": {"rel_type": ["rel_type", "relType"]},
    # graph.add_relation: old type/rel_type → canonical rel_type
    "graph.add_relation": {"rel_type": ["rel_type", "relType", "type"]},
    # graph.get_relations: old type → canonical rel_type
    "graph.get_relations": {"rel_type": ["type", "rel_type"]},
    # graph.remove_relation: old type → canonical rel_type
    "graph.remove_relation": {"rel_type": ["type", "rel_type"]},
    # graph.list_units: old type → canonical unit_type
    "graph.list_units": {"unit_type": ["type", "unit_type", "unitType"]},
    # graph.create_unit: old type → unit_type; data 是 content 的别名
    "graph.create_unit": {"unit_type": ["type", "unit_type"], "content": ["content", "data"]},
    # session.start: type → focus_type
    "session.start": {"focus_type": ["type", "focus_type"]},
    # graph.update_unit: data 是 content 的别名
    "graph.update_unit": {"content": ["content", "data"]},
    # project.new: v2 默认为 True
    "project.new": {"v2_default": True},
    # project.import: novel_tool 传 source，handler 需要 source_path
    "project.import": {"source_path": ["source", "source_path"]},
}


def _build_canonical_params(op: str, request: dict) -> dict:
    """将 novel_tool.py 的 flat request dict 转为规范化参数 dict。

    - 不在 _PARAM_MAP 中的参数会被忽略
    - 特殊操作通过 _PARAM_ALIASES 处理别名
    """
    canonical = {}

    # 1. 基础映射
    for novel_key, canonical_key in _PARAM_MAP.items():
        if novel_key in request:
            canonical[canonical_key] = request[novel_key]

    # 2. 别名处理
    aliases = _PARAM_ALIASES.get(op, {})
    for canonical_key, source_keys in aliases.items():
        if canonical_key == "v2_default":
            if "v2" not in request:
                canonical["v2"] = True
            continue
        # 已通过基础映射拿到值的跳过
        if canonical_key in canonical:
            continue
        for src in source_keys:
            if src in request:
                canonical[canonical_key] = request[src]
                break

    # 3. project_root：从 project 字段解析
    if "project" in request:
        canonical["project_root"] = _resolve_project(request["project"])

    return canonical


# ── 统一入口 ─────────────────────────────────────────────────────────────

def handle_request(request: dict) -> str:
    """统一请求处理入口。

    将 request dict 适配为规范化参数，交给 handlers 模块处理。
    自动记录遥测数据到 graph/telemetry.ndjson。
    """
    import time as _time
    _start = _time.time()
    op = request.get("operation", "")
    project = request.get("project", "")
    # caller 标识：优先 caller 字段，其次 actor 字段（子 agent 已有 --actor 惯例）
    caller = request.get("caller", request.get("actor", "unknown"))
    canonical = {}
    proj_root = ""
    proj_name = project  # 项目名（非完整路径），用于遥测记录
    
    try:
        if not op:
            return _err("缺少 operation 字段")

        # subagent.trace/save 记录子 agent 调用信息，不经过 handler
        if op in ("subagent.trace", "subagent.save"):
            return _handle_subagent_trace(request)

        canonical = _build_canonical_params(op, request)
        proj_root = canonical.get("project_root", "") or _resolve_project(project)

        from handlers import run_operation
        result = run_operation(op, **canonical)

        duration_ms = (_time.time() - _start) * 1000
        
        if "error" in result:
            _record_failure(proj_name, caller, op, canonical, duration_ms, result["error"])
            return _err(result["error"])
        
        _record_success(proj_name, caller, op, canonical, duration_ms, result)
        return _ok(result)

    except Exception as e:
        duration_ms = (_time.time() - _start) * 1000
        stack = traceback.format_exc()
        _record_failure(proj_name, caller, op, canonical, duration_ms, f"{e}\n{stack}")
        return _err(f"{e}\n{stack}")


def _record_success(proj_name: str, caller: str, op: str, canonical: dict, duration_ms: float, result: dict):
    """记录成功的工具调用到遥测（全局 .engine/telemetry/ 存储）。"""
    try:
        from telemetry import get_recorder
        recorder = get_recorder()
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        unit_count = 0
        relation_count = 0
        for key in ("unit", "units", "nodes", "node"):
            val = result.get(key)
            if isinstance(val, list):
                unit_count += len(val)
            elif isinstance(val, dict):
                unit_count += 1
        for key in ("relation", "relations", "edges"):
            val = result.get(key)
            if isinstance(val, list):
                relation_count += len(val)
            elif isinstance(val, dict):
                relation_count += 1
        recorder.record(
            operation=op, params=canonical, success=True,
            duration_ms=duration_ms, result_size=len(result_str),
            unit_count=unit_count, relation_count=relation_count,
            project=proj_name, caller=caller,
        )
    except Exception:
        pass


def _record_failure(proj_name: str, caller: str, op: str, canonical: dict, duration_ms: float, error_str: str):
    """记录失败的工具调用到遥测（全局 .engine/telemetry/ 存储）。"""
    try:
        from telemetry import get_recorder, classify_error
        recorder = get_recorder()
        error_summary = error_str.split("\n")[0] if "\n" in error_str else error_str[:300]
        recorder.record_error(
            operation=op, params=canonical,
            error_type=classify_error(error_summary, error_str),
            error_msg=error_summary, duration_ms=duration_ms,
            project=proj_name, caller=caller,
        )
    except Exception:
        pass


def _handle_subagent_trace(request: dict) -> str:
    """处理 subagent.trace 操作：记录子 agent 调度信息到 .engine/subagents/。"""
    import json as _json
    from datetime import datetime, timezone as _timezone

    project = request.get("project", "")
    if not project:
        return _err("subagent.trace 缺少 project 字段")

    # 解析 .engine/ 路径（4 级 dirname 到达工具根目录）
    _tool_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    _engine_dir = os.path.join(_tool_root, ".engine", "subagents")
    os.makedirs(_engine_dir, exist_ok=True)

    now = datetime.now(_timezone.utc)
    month_key = now.strftime("%Y-%m")
    trace_path = os.path.join(_engine_dir, f"{month_key}.ndjson")

    record = {
        "ts": now.isoformat(),
        "project": project,
        "task_id": request.get("task_id", request.get("session_id", "")),
        "subagent": request.get("subagent", ""),
        "focus_type": request.get("focus_type", ""),
        "focus_name": request.get("focus_name", ""),
        "preheat_level": request.get("preheat_level", ""),
        "cycle_type": request.get("cycle_type", ""),
        "humanize": request.get("humanize", False),
        "session_id": request.get("session_id", ""),
        "result": request.get("result", "unknown"),
        "prompt_summary": request.get("prompt_summary", ""),
        "result_summary": request.get("result_summary", ""),
        "new_units": request.get("new_units", 0),
        "updated_units": request.get("updated_units", 0),
        "duration_estimate_ms": request.get("duration_estimate_ms", 0),
        "error_summary": request.get("error_summary", ""),
    }

    try:
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return _ok({"ok": True, "file": trace_path})
    except Exception as e:
        return _err(f"subagent.trace 写入失败: {e}")


# ── 守护进程模式 ───────────────────────────────────────────────────────

# GraphStore 进程内缓存（LRU 池）
_STORES: Dict[str, 'GraphStore'] = {}
_LRU_ORDER: list[str] = []
_MAX_STORES = int(os.environ.get("NOVEL_DAEMON_MAX_STORES", "5"))


def _get_store_cached(project_root: str):
    """带 LRU 淘汰的 GraphStore 缓存。替换 _get_store 的默认行为。"""
    if project_root in _STORES:
        # 移到 LRU 末尾（最近使用）
        _LRU_ORDER.remove(project_root)
        _LRU_ORDER.append(project_root)
        return _STORES[project_root]
    
    from graph_store import GraphStore
    store = GraphStore(project_root)
    store.initialize()
    
    # LRU 淘汰
    while len(_STORES) >= _MAX_STORES:
        evict_key = _LRU_ORDER.pop(0)
        evicted = _STORES.pop(evict_key)
        try:
            if evicted._dirty_nodes or evicted._dirty_edges or evicted._dirty_events:
                evicted.flush()
        except Exception as exc:
            print(f"[daemon] LRU evict flush failed: {exc}", file=sys.stderr)
    
    _STORES[project_root] = store
    _LRU_ORDER.append(project_root)
    _DAEMON_LOG.log("store_cache_miss", project=project_root, pool_size=len(_STORES))
    return store


def _daemon_handle_request(request: dict) -> str:
    """守护进程版的 handle_request：复用 _build_canonical_params 和 run_operation，
       但由 _get_store_cached 提供 GraphStore 缓存。"""
    try:
        # Lazy open daemon log when project becomes known
        project = request.get("project", "")
        if project and not _DAEMON_LOG._log_file:
            resolved = _resolve_project(project)
            graph_dir = os.path.join(resolved, "graph")
            if os.path.isdir(graph_dir):
                _DAEMON_LOG.open(graph_dir)
        
        op = request.get("operation", "")
        if not op:
            return _err("缺少 operation 字段")
        
        canonical = _build_canonical_params(op, request)
        
        from handlers import run_operation
        result = run_operation(op, **canonical)
        
        if "error" in result:
            return _err(result["error"])
        return _ok(result)
    
    except Exception as e:
        import traceback
        return _err(f"{e}\n{traceback.format_exc()}")


def _daemon_main():
    """守护进程主循环。由 novel_tool.py --daemon 调用。"""
    # 预加载 handlers（触发 sys.path.insert + 模块编译）
    import handlers  # noqa: F401
    
    # 注入缓存版 _get_store
    from handlers.handlers_graph import set_store_provider
    set_store_provider(_get_store_cached)
    
    # 忽略 SIGINT（让父进程管理生命周期）
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    # 空闲超时
    idle_timeout = int(os.environ.get("NOVEL_DAEMON_IDLE_TIMEOUT", "300"))
    last_request_time = time.time()
    total_requests = 0
    request_id = 0
    
    # 打开 daemon.log（写到项目无关的临时目录；首次真实请求时会切换）
    _DAEMON_LOG.log("daemon_start", pid=os.getpid(), stores=0)
    
    # 握手信号
    sys.stdout.write(json.dumps({
        "ready": True,
        "pid": os.getpid(),
        "python_version": f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}",
        "max_stores": _MAX_STORES,
    }, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            # 检查空闲超时
            if time.time() - last_request_time > idle_timeout:
                break
            continue
        
        last_request_time = time.time()
        total_requests += 1
        request_id += 1
        req_id = f"req_{request_id:04d}"
        
        # 解析 JSON
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stdout.write(
                json.dumps({"success": False, "error": f"JSON parse error: {e}"},
                           ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        
        # 注入 _req_id（若有则透传，无则自动生成）
        client_req_id = request.pop("_req_id", req_id)
        
        # ── 特殊操作 ──
        if request.get("operation") == "shutdown":
            _DAEMON_LOG.log("daemon_shutdown", uptime_s=int(time.time() - last_request_time + 1),
                            total_requests=total_requests, peak_pool_size=len(_STORES))
            break
        
        if request.get("operation") == "__ping__":
            sys.stdout.write(
                json.dumps({"_req_id": client_req_id, "success": True, "data": {"pong": True}},
                           ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue
        
        # ── 普通请求 ──
        t0 = time.time()
        result_str = _daemon_handle_request(request)
        elapsed = (time.time() - t0) * 1000
        
        # 在响应中注入 _req_id
        try:
            result_obj = json.loads(result_str)
            result_obj["_req_id"] = client_req_id
            result_str = json.dumps(result_obj, ensure_ascii=False)
        except Exception:
            pass
        
        sys.stdout.write(result_str + "\n")
        sys.stdout.flush()
        
        # 日志
        _DAEMON_LOG.log("request_end", req_id=client_req_id,
                        operation=request.get("operation", "?"),
                        project=request.get("project", ""),
                        duration_ms=round(elapsed, 1))
    
    # 清理：flush 所有 store
    for path, store in _STORES.items():
        try:
            store.flush()
        except Exception:
            pass
    _STORES.clear()
    _LRU_ORDER.clear()
    _DAEMON_LOG.close()


# ── CLI 入口（被 novel-tool.ts 调用） ─────────────────────────────────────

if __name__ == "__main__":
    # 守护进程模式
    if "--daemon" in sys.argv:
        _daemon_main()
        sys.exit(0)
    
    raw = ""
    if len(sys.argv) >= 2:
        raw = sys.argv[1]
        # Windows shell 兼容：去除首尾多余引号/空格
        while raw and raw[0] in ('"', "'", " ", "\t"):
            raw = raw[1:]
        while raw and raw[-1] in ('"', "'", " ", "\t"):
            raw = raw[:-1]
    else:
        # 从 stdin 读取（novel-tool.ts 通过 stdin 传入 JSON 避免 Windows 转义问题）
        raw = sys.stdin.read().strip()

    request = None
    err_msg = None

    # 1. 标准 json.loads
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as e:
        err_msg = str(e)

    # 2. 尝试 json_repair 容错解析
    if request is None:
        try:
            from json_repair import loads as repair_loads
            request = repair_loads(raw)
        except Exception:
            pass

    # 3. Windows 路径反斜杠修复
    if request is None:
        try:
            import re
            fixed = re.sub(r'(?<!\\)\\(?!\\|"|/|b|f|n|r|t|u[0-9a-fA-F]{4})', r'\\\\', raw)
            request = json.loads(fixed)
        except json.JSONDecodeError:
            pass

    # 4. 单引号 → 双引号修复
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
