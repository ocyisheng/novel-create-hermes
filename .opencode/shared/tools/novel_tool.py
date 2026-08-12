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
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, Optional

# 确保 shared/ 和 shared/v2/ 在 sys.path 中
_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

from engine_log import EngineLogWriter  # noqa: E402  (sys.path 设置后导入)


# ── 守护进程日志 ─────────────────────────────────────────────────────

class _DaemonLogger(EngineLogWriter):
    """守护进程结构化日志，按天新建文件（复用 EngineLogWriter 写入机制）。"""

    def __init__(self):
        super().__init__(subdir="daemon", prefix="daemon-", ext=".log")

    def open(self, graph_dir: str):
        """惰性打开今日日志文件（graph_dir 兼容旧签名；路径由 engine root 解析）。"""
        today, _ = self._date_stamped_path()
        if today != self._current_date or not self._log_file:
            self._rotate(today)

    def log(self, event: str, **fields):
        """写入一条事件记录（跨天自动轮转，失败静默）。"""
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        self.write(entry)


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
    """将项目名解析为绝对路径。

    - 已是绝对路径 → 直接返回
    - 相对路径 → 用 handlers_project.NOVELS_ROOT 拼接（与 handler 一致，支持测试 patch）
    - NOVELS_ROOT 不可用时回退到 cwd/novels 拼接
    - 候选目录不存在时仍返回拼接结果（由 handler 判断是否已存在）
    """
    if not project:
        return ""
    if os.path.isabs(project):
        return project
    try:
        import handlers.handlers_project as hp
        novels_root = hp.NOVELS_ROOT
    except (ImportError, AttributeError):
        novels_root = _find_novels_root()
    return os.path.join(novels_root, project)


def _project_basename(project: str) -> str:
    """从 project 参数提取纯项目名（遥测记录用，避免存完整路径）。

    兼容：完整路径（含 Windows 反斜杠/正斜杠/尾斜杠）、项目名、空值。
    实现委托给 telemetry.project_basename（唯一实现），避免两处漂移。
    """
    from telemetry import project_basename
    return project_basename(project)


# ── 参数适配：novel_tool 参数名 → 规范参数名 ────────────────────────────

# novel_tool.py 参数 → handler 规范参数名的映射表
_PARAM_MAP = {
    # 通用
    "id": "id", "ids": "ids", "name": "name",
    "unit_type": "unit_type", "rel_type": "rel_type", "focus_type": "focus_type",
    "content": "content", "file": "file_path",
    "tags": "tags", "chapter": "chapter", "volume": "volume",
    "actor": "actor", "limit": "limit", "offset": "offset",
    "keyword": "keyword", "pattern": "pattern", "verbose": "verbose",
    "scope": "scope", "regex": "regex",
    "case_sensitive": "case_sensitive",
    "since_version": "since_version",
    "version": "version",
    "sources": "sources",
    "status": "status",
    "out": "out",
    "force": "force",
    "dry_run": "dry_run",
    "parent_id": "parent_id",
    "if_exists": "if_exists",
    "skip_constraint_check": "skip_constraint_check",
    "full": "full",
    "tag": "tag",
    # 关系
    "source": "source", "target": "target",
    "bidirectional": "bidirectional",
    "label": "label",
    "label_substring": "label_substring",
    "source_role": "source_role",
    "target_role": "target_role",
    "role": "role",
    "role_substring": "role_substring",
    "weight": "weight",
    "min_weight": "min_weight",
    "max_weight": "max_weight",
    "description": "description",
    "payload": "payload",
    "direction": "direction",
    # 迁移
    "verify": "verify", "report": "report",
    # 类型变更
    "new_type": "new_type",
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
    "session_id": "session_id",
    # summary
    "focus_name": "focus_name",
    # 偏差
    "findings": "findings",
    "severity": "severity", "dimension": "dimension",
    "scan_version": "scan_version",
    "full_scan_version": "full_scan_version",
    # 知识库
    "slug": "slug", "topic": "topic",
    # server
    "host": "host", "port": "port",
    # subagent
    "task_id": "task_id",
    "subagent": "subagent",
    "result": "result",
    "record_type": "record_type",
    "preheat_level": "preheat_level",
    "humanize": "humanize",
    "prompt_summary": "prompt_summary",
    "result_summary": "result_summary",
    "new_units": "new_units",
    "updated_units": "updated_units",
    "duration_estimate_ms": "duration_estimate_ms",
    "error_summary": "error_summary",
    "user_intent": "user_intent",
    "conflict_decision": "conflict_decision",
    "failure_analysis": "failure_analysis",
    "optimization_clue": "optimization_clue",
    # analysis
    "clue": "clue",
    "note": "note",
    # analyze
    "mode": "mode",
    "json_output": "json_output",
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
    # project.*: handler 收 project_root（绝对路径），别名从 project/name 派生
    "project.new": {"project_root": ["project", "name"], "v2_default": True},
    "project.import": {"project_root": ["project", "name"], "source_path": ["source", "source_path"]},
    "project.status": {"project_root": ["project", "name"]},
    "project.resume": {"project_root": ["project", "name"]},
    "project.switch": {"project_root": ["project", "name"]},
    "project.delete": {"project_root": ["project", "name"]},
    # read 类操作：file 会被 _PARAM_MAP 误映射为 file_path，
    # 需在别名层映射回 file，否则 run_operation 按注册的 file 过滤时丢失
    "summary.read": {"file": ["file", "file_path"]},
    # analysis 类操作：file 同 summary.read，映射回 file
    "analysis.read": {"file": ["file", "file_path"]},
    "analysis.resolve": {"file": ["file", "file_path"]},
}


def _build_canonical_params(op: str, request: dict) -> dict:
    """将 novel_tool.py 的 flat request dict 转为规范化参数 dict。

    - 不在 _PARAM_MAP 中的参数会被忽略
    - 特殊操作通过 _PARAM_ALIASES 处理别名
    - 被别名消费的来源键（如 project.* 的 name、project.import 的 source、
      graph.search 的 unit_type）不再同时经基础映射进入 canonical，
      避免 run_operation 过滤时产生"参数被静默过滤"噪音
    """
    canonical = {}

    # 1. 基础映射
    for novel_key, canonical_key in _PARAM_MAP.items():
        if novel_key in request:
            canonical[canonical_key] = request[novel_key]

    # 2. 别名处理
    aliases = _PARAM_ALIASES.get(op, {})
    alias_set = set()  # 由别名实际设置了值的 canonical 键
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
                alias_set.add(canonical_key)
                break

    # 2b. 别名消费清理：来源键被别名重定向后，不应再以其自身规范名残留。
    #     否则 run_operation 按 registry 过滤时会报"参数被静默过滤"（如
    #     project.* 的 {'name'}、project.import 的 {'name', 'source'}）。
    for canonical_key, source_keys in aliases.items():
        if canonical_key == "v2_default" or canonical_key not in alias_set:
            continue
        for src in source_keys:
            if src not in request:
                continue
            if src == canonical_key:
                # 同键重定向（如 summary.read 的 file→file）：基础映射已把它
                # 映射到别的规范名（file→file_path），需移除该映射产物
                for nk, ck in _PARAM_MAP.items():
                    if (nk == src and ck != canonical_key
                            and ck in canonical and canonical[ck] == request[src]):
                        canonical.pop(ck, None)
            elif src in canonical and canonical[src] == request[src]:
                # 异键重定向（如 project.* 的 name→project_root）：移除残留的 name
                canonical.pop(src, None)

    # 3. project 身份注入：按 OPERATION_REGISTRY 声明的参数裁剪，只填该 op
    #    实际消费的形态，避免 project_root / project / name 三形态同时进 params。
    #    - 存储类 ops（graph.*/session.*/deviation.* 等）：registry 声明 project_root → 只填绝对路径
    #    - 过滤类 ops（analyze.*/summary.list）：registry 声明 project → 填 basename（遥测归因匹配）
    #    - project.* ops：别名已将 project/name 映射为 project_root → 统一绝对路径
    if "project" in request:
        root = _resolve_project(request["project"])
        base = _project_basename(request["project"])
        from handlers import OPERATION_REGISTRY
        accepted = set(OPERATION_REGISTRY.get(op, {}).get("params", {}).keys())
        if "project_root" in accepted:
            canonical["project_root"] = root
        if "project" in accepted:
            canonical["project"] = base
    elif "project_root" in canonical and not os.path.isabs(canonical["project_root"]):
        # 别名从 name 派生 project_root（如 project.* 传 name=项目名），
        # 相对路径需解析为绝对路径
        canonical["project_root"] = _resolve_project(canonical["project_root"])

    # 4. actor 默认值：未指定时用 "novel-tool"（在白名单中），避免 handler 默认 "orchestrator" 被拦截
    if "actor" not in canonical:
        canonical["actor"] = "novel-tool"

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
    # caller 标识：优先 caller 字段，其次 actor 字段（子 agent 提示词中统一传 actor="xxx"）
    # 均未传时默认 "orchestrator"（编排层直接调 tool 的常见路径），避免遥测归因丢失
    caller = request.get("caller") or request.get("actor") or "orchestrator"
    canonical = {}
    proj_root = ""
    proj_name = _project_basename(project)  # 项目名（非完整路径），用于遥测记录
    
    try:
        if not op:
            return _err("缺少 operation 字段")

        canonical = _build_canonical_params(op, request)
        proj_root = canonical.get("project_root", "") or _resolve_project(project)

        # 诊断：调用方显式传了 actor="orchestrator"（旧 prompt 模式）→ 输出警告到 stderr
        # 新 prompt 已改为「不需要传 actor 参数」，此警告帮助发现未更新的 prompt 或旧习惯
        # 注意：仅对显式传入的 actor="orchestrator" 警告；caller 默认值 orchestrator 不触发
        if request.get("actor") == "orchestrator":
            import sys as _sys
            print(f"[actor-mismatch] caller={caller}, actor={canonical.get('actor')}: "
                  f"编排层传入了已废弃的 actor='orchestrator'。"
                  f"§1 规则6 已更新为「不需要传 --actor」。请更新编排层 prompt。", file=_sys.stderr)

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


# ── 守护进程模式 ───────────────────────────────────────────────────────

# GraphStore 进程内缓存（LRU 池，线程安全）
_STORES: Dict[str, 'GraphStore'] = {}
_LRU_ORDER: list[str] = []
_MAX_STORES = int(os.environ.get("NOVEL_DAEMON_MAX_STORES", "5"))
_STORE_LOCK = threading.Lock()


def _get_store_cached(project_root: str):
    """带 LRU 淘汰的 GraphStore 缓存（线程安全）。"""
    # 快速路径：缓存命中
    with _STORE_LOCK:
        if project_root in _STORES:
            _LRU_ORDER.remove(project_root)
            _LRU_ORDER.append(project_root)
            return _STORES[project_root]
    
    from graph_store import GraphStore
    store = GraphStore(project_root)
    store.initialize()

    # 与非 daemon 路径（handlers_graph._get_store）保持一致：
    # 注册约束引擎到 post_flush 钩子，使 flush 后自动运行约束检查并持久化偏差
    try:
        from handlers.handlers_graph import _register_constraint_engine
        _register_constraint_engine(store)
    except Exception:
        pass  # 约束引擎注册失败不影响核心功能

    with _STORE_LOCK:
        # double-check：可能在初始化期间被另一个线程抢先创建
        if project_root in _STORES:
            return _STORES[project_root]
        
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
       但由 _get_store_cached 提供 GraphStore 缓存。
       与 handle_request 一致记录遥测（修复 daemon 模式请求缺失遥测数据的缺口）。"""
    import time as _time
    _start = _time.time()
    project = request.get("project", "")
    # Lazy open daemon log when project becomes known
    if project and not _DAEMON_LOG._log_file:
        resolved = _resolve_project(project)
        graph_dir = os.path.join(resolved, "graph")
        if os.path.isdir(graph_dir):
            _DAEMON_LOG.open(graph_dir)

    op = request.get("operation", "")
    # caller 标识：与 handle_request 一致（caller 优先，其次 actor，默认 orchestrator）
    caller = request.get("caller") or request.get("actor") or "orchestrator"
    proj_name = _project_basename(project)
    canonical = {}

    try:
        if not op:
            return _err("缺少 operation 字段")

        canonical = _build_canonical_params(op, request)

        from handlers import run_operation
        result = run_operation(op, **canonical)

        duration_ms = (_time.time() - _start) * 1000

        if "error" in result:
            _record_failure(proj_name, caller, op, canonical, duration_ms, result["error"])
            return _err(result["error"])

        _record_success(proj_name, caller, op, canonical, duration_ms, result)
        return _ok(result)

    except Exception as e:
        import traceback
        duration_ms = (_time.time() - _start) * 1000
        _record_failure(proj_name, caller, op, canonical, duration_ms, f"{e}\n{traceback.format_exc()}")
        return _err(f"{e}\n{traceback.format_exc()}")


def _daemon_main():
    """守护进程主循环（异步线程池版）。由 novel_tool.py --daemon 调用。"""
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
    
    # 线程池（最多 4 个并行 worker）
    max_workers = int(os.environ.get("NOVEL_DAEMON_WORKERS", "4"))
    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="daemon")
    stdout_lock = threading.Lock()
    
    _DAEMON_LOG.log("daemon_start", pid=os.getpid(), stores=0, workers=max_workers)
    
    # 握手信号
    sys.stdout.write(json.dumps({
        "ready": True,
        "pid": os.getpid(),
        "python_version": f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}",
        "max_stores": _MAX_STORES,
        "max_workers": max_workers,
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
            with stdout_lock:
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
            with stdout_lock:
                sys.stdout.write(
                    json.dumps({"_req_id": client_req_id, "success": True, "data": {"pong": True}},
                               ensure_ascii=False) + "\n")
                sys.stdout.flush()
            continue
        
        # ── 普通请求：提交到线程池并行处理 ──
        t0 = time.time()
        future = executor.submit(_daemon_handle_request, request)
        
        def _on_done(fut, _req_id=client_req_id, _op=request.get("operation", "?"),
                     _project=request.get("project", ""), _t0=t0):
            """线程池任务完成回调：写入 stdout 并记录日志。"""
            try:
                result_str = fut.result()
                elapsed = (time.time() - _t0) * 1000
                
                # 在响应中注入 _req_id
                try:
                    result_obj = json.loads(result_str)
                    result_obj["_req_id"] = _req_id
                    result_str = json.dumps(result_obj, ensure_ascii=False)
                except Exception:
                    pass
                
                with stdout_lock:
                    sys.stdout.write(result_str + "\n")
                    sys.stdout.flush()
                
                _DAEMON_LOG.log("request_end", req_id=_req_id,
                                operation=_op, project=_project,
                                duration_ms=round(elapsed, 1))
            except Exception as e:
                err_str = json.dumps(
                    {"success": False, "error": f"daemon worker error: {e}"},
                    ensure_ascii=False)
                with stdout_lock:
                    sys.stdout.write(err_str + "\n")
                    sys.stdout.flush()
        
        future.add_done_callback(_on_done)
    
    # 清理：等待所有未完成的任务 + flush 所有 store
    executor.shutdown(wait=True)
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
        # 去除 UTF-8 BOM（PowerShell 管道会带；循环处理单/双重 BOM）
        while raw and ord(raw[0]) == 0xFEFF:
            raw = raw[1:].strip()

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
