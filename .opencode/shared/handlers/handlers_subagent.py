"""
handlers_subagent.py — 子 Agent 调用记录持久化逻辑。

每次 task() 返回后（同步或 background_output），编排层将完整的
子 Agent 对话信息保存到 .engine/subagents/，供后续分析使用。

存储结构（引擎级，跨项目）：
  .engine/subagents/index.json                         — 统一索引
  .engine/subagents/{yyyy-mm}/{task_id}.json           — 完整记录（含 conversation）
  .engine/subagents/{yyyy-mm}.ndjson                   — 元数据快速扫描（兼容旧格式）
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _resolve_engine_subagents_dir() -> str:
    """解析 .engine/subagents/ 目录路径。"""
    current = Path(__file__).resolve().parent  # handlers/
    shared = current.parent                     # shared/
    opencode = shared.parent                    # .opencode/
    tool_root = opencode.parent                 # novel-create-hermes/
    subagents_dir = tool_root / ".engine" / "subagents"
    subagents_dir.mkdir(parents=True, exist_ok=True)
    return str(subagents_dir)


def _resolve_project_name(project: str) -> str:
    """从 project 参数解析项目名。"""
    if not project:
        return ""
    if os.path.isabs(project):
        return os.path.basename(project)
    return project


def handle_subagent_save(
    project_root: str = "",
    task_id: str = "",
    subagent: str = "",
    focus_type: str = "",
    focus_name: str = "",
    preheat_level: str = "",
    cycle_type: str = "",
    humanize: bool = False,
    session_id: str = "",
    result: str = "unknown",
    prompt_summary: str = "",
    result_summary: str = "",
    conversation: str = "",
    new_units: int = 0,
    updated_units: int = 0,
    duration_estimate_ms: int = 0,
    error_summary: str = "",
) -> dict:
    """
    保存一次子 Agent 调用记录（引擎级存储）。

    像会话总结一样，将完整的子 Agent 信息结构化保存，
    同时生成元数据 JSONL 用于快速扫描。

    Args:
        project_root: 项目路径或项目名
        task_id: 子 Agent 任务的 task_id（如 bg_xxx / ses_xxx）
        subagent: 子 Agent 类型（explore / novel-v2-crafter / novel-ideation 等）
        focus_type: 焦点类型
        focus_name: 焦点名称
        preheat_level: 预热级别
        cycle_type: 循环类型
        humanize: 是否去 AI 味
        session_id: 关联的创作 session ID
        result: success / partial / failed
        prompt_summary: prompt 自然语言摘要
        result_summary: 结果自然语言摘要
        conversation: 完整的 background_output / task 返回数据（JSON 字符串）
        new_units: 新建单元数
        updated_units: 更新单元数
        duration_estimate_ms: 预估耗时（ms）
        error_summary: 错误摘要（如有）

    Returns:
        dict: {"file": "保存路径", "index_total": 累计条数}
    """
    subagents_dir = _resolve_engine_subagents_dir()
    timestamp = datetime.now(timezone.utc)
    month_dir = os.path.join(subagents_dir, timestamp.strftime("%Y-%m"))
    os.makedirs(month_dir, exist_ok=True)

    index_path = os.path.join(subagents_dir, "index.json")
    ndjson_path = os.path.join(subagents_dir, timestamp.strftime("%Y-%m") + ".ndjson")

    # 生成唯一标识：用 task_id 或自动生成
    record_id = task_id.strip() or f"sa_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"

    # ── 完整记录（带 conversation）→ 存为 JSON 文件 ──
    full_record = {
        "id": record_id,
        "ts": timestamp.isoformat(),
        "project": _resolve_project_name(project_root) or project_root,
        "task_id": task_id,
        "subagent": subagent,
        "focus_type": focus_type,
        "focus_name": focus_name,
        "preheat_level": preheat_level,
        "cycle_type": cycle_type,
        "humanize": humanize,
        "session_id": session_id,
        "result": result,
        "prompt_summary": prompt_summary,
        "result_summary": result_summary,
        "new_units": new_units,
        "updated_units": updated_units,
        "duration_estimate_ms": duration_estimate_ms,
        "error_summary": error_summary,
    }

    # conversation 是完整的 background_output 数据（JSON 字符串）
    if conversation:
        try:
            full_record["conversation"] = json.loads(conversation)
        except (json.JSONDecodeError, TypeError):
            full_record["conversation"] = conversation

    # 写入完整记录文件：{task_id}.json
    record_filename = f"{record_id}.json"
    record_filepath = os.path.join(month_dir, record_filename)
    with open(record_filepath, "w", encoding="utf-8") as f:
        json.dump(full_record, f, ensure_ascii=False, indent=2)

    # ── 元数据 JSONL（兼容旧格式，用于快速扫描）──
    ndjson_record = {k: v for k, v in full_record.items() if k != "conversation"}
    with open(ndjson_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(ndjson_record, ensure_ascii=False, default=str) + "\n")

    # ── 更新索引 ──
    index_data = {"entries": [], "total": 0}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except (json.JSONDecodeError, Exception):
            index_data = {"entries": [], "total": 0}

    entry = {
        "id": record_id,
        "file": record_filename,
        "month": timestamp.strftime("%Y-%m"),
        "timestamp": timestamp.isoformat(),
        "project": _resolve_project_name(project_root) or project_root,
        "task_id": task_id,
        "subagent": subagent,
        "focus_type": focus_type,
        "focus_name": focus_name,
        "result": result,
        "prompt_summary": prompt_summary,
    }
    index_data["entries"].append(entry)
    index_data["total"] = len(index_data["entries"])

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    return {
        "id": record_id,
        "file": record_filepath,
        "index_total": index_data["total"],
    }


def handle_subagent_list(
    project_root: str = "",
    limit: int = 20,
    subagent: str = "",
    result: str = "",
    project: str = "",
) -> dict:
    """
    列出子 Agent 调用记录。

    Args:
        project_root: 兼容旧格式
        limit: 返回条数上限
        subagent: 按子 Agent 类型过滤
        result: 按结果过滤（success / partial / failed）
        project: 按项目名过滤

    Returns:
        dict: {"entries": [...], "total": N}
    """
    subagents_dir = _resolve_engine_subagents_dir()
    index_path = os.path.join(subagents_dir, "index.json")

    if not os.path.exists(index_path):
        return {"entries": [], "total": 0}

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    except (json.JSONDecodeError, Exception):
        return {"entries": [], "total": 0}

    entries = index_data.get("entries", [])

    # 按子 Agent 类型过滤
    if subagent:
        entries = [e for e in entries if e.get("subagent") == subagent]

    # 按结果过滤
    if result:
        entries = [e for e in entries if e.get("result") == result]

    # 按项目名过滤
    filter_project = project or _resolve_project_name(project_root)
    if filter_project:
        entries = [e for e in entries if e.get("project") == filter_project]

    # 按时间倒序，取最新的 N 条
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    entries = entries[:limit]

    return {
        "entries": entries,
        "total": len(entries),
    }


def handle_subagent_read(
    project_root: str = "",
    task_id: str = "",
    id: str = "",
) -> dict:
    """
    读取一次子 Agent 调用记录的完整内容（含 conversation）。

    支持按 task_id 或 id 查找。
    """
    if not task_id and not id:
        return {"error": "需要 task_id 或 id 参数"}

    subagents_dir = _resolve_engine_subagents_dir()
    lookup_id = task_id.strip() or id.strip()

    # 先在索引中查找文件名
    index_path = os.path.join(subagents_dir, "index.json")
    target_file = ""
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
            for entry in index_data.get("entries", []):
                if entry.get("id") == lookup_id or entry.get("task_id") == lookup_id:
                    target_file = entry.get("file", "")
                    month = entry.get("month", "")
                    if target_file and month:
                        break
        except Exception:
            pass

    # 按文件名查找
    if target_file:
        for month_dir in sorted(os.listdir(subagents_dir), reverse=True):
            candidate = os.path.join(subagents_dir, month_dir, target_file)
            if os.path.exists(candidate):
                with open(candidate, "r", encoding="utf-8") as f:
                    content = json.load(f)
                return {"record": content}

    # 回退：逐月扫描
    for month_dir in sorted(os.listdir(subagents_dir), reverse=True):
        month_path = os.path.join(subagents_dir, month_dir)
        if not os.path.isdir(month_path):
            continue
        for fname in os.listdir(month_path):
            if not fname.endswith(".json") or fname == "index.json":
                continue
            fpath = os.path.join(month_path, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                if rec.get("task_id") == lookup_id or rec.get("id") == lookup_id:
                    return {"record": rec, "file": fpath}
            except Exception:
                continue

    return {"error": f"未找到子 Agent 记录: {lookup_id}"}
