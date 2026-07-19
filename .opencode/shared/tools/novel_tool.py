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

# 确保 shared/ 在 sys.path 中
_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)


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
    "id": "id", "name": "name", "type": "type",
    "content": "content", "file": "file_path",
    "tags": "tags", "chapter": "chapter",
    "actor": "actor", "limit": "limit",
    "keyword": "keyword", "pattern": "pattern",
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
    # 偏差
    "findings": "findings",
    "scan_version": "scan_version",
    "full_scan_version": "full_scan_version",
    # 知识库
    "slug": "slug", "topic": "topic",
}

# 需要额外处理别名/兼容性的操作
_PARAM_ALIASES = {
    # graph.search: novel_tool 接受 scope/unit_type/unitType
    "graph.search": {"scope": ["scope", "unit_type", "unitType"]},
    # graph.get_neighbors: rel_type/relType
    "graph.get_neighbors": {"rel_type": ["rel_type", "relType"]},
    # graph.get_relations: type/rel_type/relType
    "graph.get_relations": {"rel_type": ["type", "rel_type", "relType"]},
    # graph.remove_relation: type/rel_type/relType → canonical "type"
    "graph.remove_relation": {"type": ["type", "rel_type", "relType"]},
    # graph.get_relations: type/rel_type/relType → canonical "type"
    "graph.get_relations": {"type": ["type", "rel_type", "relType"]},
    # graph.add_relation: novel_tool 传 rel_type/relType，handler 要求 type
    "graph.add_relation": {"type": ["rel_type", "relType", "type"]},
    # graph.update_unit: data 是 content 的别名
    "graph.update_unit": {"content": ["content", "data"]},
    # graph.create_unit: data 是 content 的别名
    "graph.create_unit": {"content": ["content", "data"]},
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
    """
    try:
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


# ── CLI 入口（被 novel-tool.ts 调用） ─────────────────────────────────────

if __name__ == "__main__":
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
