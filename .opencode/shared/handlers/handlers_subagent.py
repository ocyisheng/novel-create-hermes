"""
handlers_subagent.py — 子 Agent 调用摘要记录。

每次 task() 返回后，编排层将子 Agent 调用的摘要信息（task_id、类型、
焦点、结果摘要等）记录到 .engine/subagents/，供后续分析使用。

存储结构（引擎级，跨项目）：
  .engine/subagents/index.json              — 统一索引
  .engine/subagents/{yyyy-mm}.ndjson        — 元数据行（追加写）

注意：只存摘要 metadata，不存完整对话。如需查看子 Agent 的完整对话，
直接用 task(task_id=bg_xxx) 恢复会话。
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
    new_units: int = 0,
    updated_units: int = 0,
    duration_estimate_ms: int = 0,
    error_summary: str = "",
) -> dict:
    """
    记录一次子 Agent 调用的摘要信息。

    和会话总结一样，编排层在 task() 返回后 review 结果，
    提取关键信息写入。只存 metadata，不存原始对话。

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
        prompt_summary: prompt 自然语言摘要（简短）
        result_summary: 结果自然语言摘要（简短）
        new_units: 新建单元数
        updated_units: 更新单元数
        duration_estimate_ms: 预估耗时（ms）
        error_summary: 错误摘要（如有）

    Returns:
        dict: {"id": "...", "index_total": N}
    """
    subagents_dir = _resolve_engine_subagents_dir()
    timestamp = datetime.now(timezone.utc)
    month_key = timestamp.strftime("%Y-%m")

    index_path = os.path.join(subagents_dir, "index.json")
    ndjson_path = os.path.join(subagents_dir, f"{month_key}.ndjson")

    # 生成唯一标识
    record_id = task_id.strip() or f"sa_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"
    project_name = _resolve_project_name(project_root) or project_root

    record = {
        "id": record_id,
        "ts": timestamp.isoformat(),
        "project": project_name,
        "task_id": task_id,
        "subagent": subagent,
        "focus_type": focus_type,
        "focus_name": focus_name,
        "result": result,
        "prompt_summary": prompt_summary,
        "result_summary": result_summary,
        "new_units": new_units,
        "updated_units": updated_units,
        "duration_estimate_ms": duration_estimate_ms,
        "error_summary": error_summary,
        # 扩展字段（非必需，有值才存）
        "preheat_level": preheat_level or None,
        "cycle_type": cycle_type or None,
        "humanize": humanize or None,
        "session_id": session_id or None,
    }
    # 去掉 None 值保持简洁
    record = {k: v for k, v in record.items() if v is not None}

    # 追加到 ndjson（快速扫描）
    with open(ndjson_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # 更新索引
    index_data = {"entries": [], "total": 0}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except (json.JSONDecodeError, Exception):
            index_data = {"entries": [], "total": 0}

    entry = {
        "id": record_id,
        "ts": record["ts"],
        "project": project_name,
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

    return {"id": record_id, "index_total": index_data["total"]}


def handle_subagent_list(
    project_root: str = "",
    limit: int = 20,
    subagent: str = "",
    result: str = "",
    project: str = "",
) -> dict:
    """
    列出子 Agent 调用摘要记录。

    Args:
        project_root: 兼容旧格式
        limit: 返回条数上限
        subagent: 按子 Agent 类型过滤（explore / novel-v2-crafter 等）
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

    if subagent:
        entries = [e for e in entries if e.get("subagent") == subagent]
    if result:
        entries = [e for e in entries if e.get("result") == result]

    filter_project = project or _resolve_project_name(project_root)
    if filter_project:
        entries = [e for e in entries if e.get("project") == filter_project]

    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    entries = entries[:limit]

    return {"entries": entries, "total": len(entries)}
