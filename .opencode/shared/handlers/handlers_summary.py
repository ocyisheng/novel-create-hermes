"""
handlers_summary.py — 会话总结持久化逻辑（主 Agent 会话 + 子 Agent 调用统一脚本）。

创作对话记录（思考过程、工具调用、冲突、成败）的结构化存储。
主 Agent 会话总结：每次用户说"记录这次会话的总结"时触发；
子 Agent 调用总结：每次 task() 返回后编排层记录（record_type="subagent"）。

同一套脚本（本文件）处理两种记录，record_type 区分来源，
存储路径按类型分流（各自独立目录 + 独立索引）：
  .engine/summaries/index.json                     — 主 Agent 会话总结索引
  .engine/summaries/{YYYY-MM}/{project}_{ts}.summary.md   — 主 Agent 会话总结
  .engine/subagents/index.json                     — 子 Agent 调用总结索引
  .engine/subagents/{YYYY-MM}/{project}_{ts}.subagent.md  — 子 Agent 调用总结
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _resolve_engine_kind_dir(kind: str) -> str:
    """解析 .engine/{kind}/ 目录路径（kind: summaries | subagents）。"""
    # 本文件在 shared/handlers/ 下，工具根目录在 ../../../
    current = Path(__file__).resolve().parent  # handlers/
    shared = current.parent                     # shared/
    opencode = shared.parent                    # .opencode/
    tool_root = opencode.parent                 # novel-create-hermes/
    kind_dir = tool_root / ".engine" / kind
    kind_dir.mkdir(parents=True, exist_ok=True)
    return str(kind_dir)


def _kind_for(record_type: str) -> str:
    """record_type → 存储目录名。"""
    return "summaries" if record_type == "main" else "subagents"


def _resolve_project_name(project: str) -> str:
    """从 project 参数解析项目名（非完整路径）。"""
    if not project:
        return ""
    if os.path.isabs(project):
        return os.path.basename(project)
    return project


def _build_subagent_sections(
    prompt_summary: str,
    result_summary: str,
    user_intent: str,
    conflict_decision: str,
    failure_analysis: str,
    error_summary: str,
    optimization_clue: str,
) -> list:
    """子 Agent 总结的正文小节（非空才写，对齐 session-summary 的"（如有）"风格）。"""
    sections = []
    if prompt_summary:
        sections.append(f"## 任务摘要\n\n{prompt_summary.strip()}\n")
    if result_summary:
        sections.append(f"## 结果摘要\n\n{result_summary.strip()}\n")
    if user_intent:
        sections.append(f"## 用户意图\n\n{user_intent.strip()}\n")
    if conflict_decision:
        sections.append(f"## 冲突决策\n\n{conflict_decision.strip()}\n")
    if failure_analysis:
        sections.append(f"## 失败复盘\n\n{failure_analysis.strip()}\n")
    if error_summary:
        sections.append(f"## 错误信息\n\n{error_summary.strip()}\n")
    if optimization_clue:
        sections.append(f"### 优化线索\n\n{optimization_clue.strip()}\n")
    return sections


def _load_index(index_path: str) -> dict:
    """读取 index.json，损坏或缺失时返回空索引。"""
    if not os.path.exists(index_path):
        return {"entries": [], "total": 0}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"entries": [], "total": 0}
        return data
    except Exception:
        return {"entries": [], "total": 0}


def _atomic_write_json(path: str, data: dict) -> None:
    """原子写 JSON：先写临时文件再替换，避免中断导致 index.json 损坏。"""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _paginate(items: list, limit: int = 0, offset: int = 0) -> tuple:
    """返回 (切片后的 items, 真实总数)。limit<=0 表示不限制。"""
    total = len(items)
    if limit and limit > 0:
        items = items[offset:offset + limit]
    elif offset:
        items = items[offset:]
    return items, total


def handle_save_summary(
    project_root: str,
    content: str = "",
    session_id: str = "",
    focus_type: str = "",
    focus_name: str = "",
    tags: str = "",
    record_type: str = "main",
    task_id: str = "",
    subagent: str = "",
    result: str = "unknown",
    preheat_level: str = "",
    cycle_type: str = "",
    humanize: bool = False,
    prompt_summary: str = "",
    result_summary: str = "",
    new_units: int = 0,
    updated_units: int = 0,
    duration_estimate_ms: int = 0,
    error_summary: str = "",
    user_intent: str = "",
    conflict_decision: str = "",
    failure_analysis: str = "",
    optimization_clue: str = "",
) -> dict:
    """
    保存一次会话总结（主 Agent 与子 Agent 统一入口，存储路径按类型分流）。

    Args:
        project_root: 项目路径或项目名
        content: 总结内容（Markdown 格式；主/子 Agent 通用正文，record_type 只决定存储路径）
        session_id: 可选，关联的 session ID
        focus_type: 可选，本次会话的焦点类型
        focus_name: 可选，本次会话的焦点名称
        tags: 可选，逗号分隔的标签（如 "冲突修复,时间线对齐,成功"）
        record_type: 记录类型，"main"（主 Agent 会话总结，默认）或 "subagent"（子 Agent 调用总结）
        task_id: 子 Agent 任务 ID（如 bg_xxx / ses_xxx），record_type="subagent" 时使用
        subagent: 子 Agent 类型（explore / novel-v2-crafter / novel-ideation 等）
        result: 子 Agent 结果（success / partial / failed）
        preheat_level: 预热级别
        cycle_type: 循环类型
        humanize: 是否去 AI 味
        prompt_summary: 子 Agent prompt 自然语言摘要
        result_summary: 子 Agent 结果自然语言摘要
        new_units: 子 Agent 新建单元数
        updated_units: 子 Agent 更新单元数
        duration_estimate_ms: 预估耗时（ms）
        error_summary: 错误摘要（如有）
        user_intent: 用户原始输入摘要（简短，用于聚合分析"同一输入→不同路由"模式）
        conflict_decision: 冲突决策（如何取舍，对齐会话总结 A.1 维度）
        failure_analysis: 失败复盘（失败原因/被否决方案，对齐 A.1 维度）
        optimization_clue: 优化线索（复用 `### 优化线索` 段落格式，进聚合分析）

    Returns:
        dict: {"file": "保存路径", "index_total": 累计条数}
    """
    project_name = _resolve_project_name(project_root)
    if not project_name:
        return {"error": f"无法解析项目名: {project_root}"}

    if record_type not in ("main", "subagent"):
        return {"error": f"未知 record_type: {record_type}（应为 main 或 subagent）"}

    kind = _kind_for(record_type)
    base_dir = _resolve_engine_kind_dir(kind)

    # 按月分目录
    timestamp = datetime.now(timezone.utc)
    month_dir = os.path.join(base_dir, timestamp.strftime("%Y-%m"))
    os.makedirs(month_dir, exist_ok=True)

    index_path = os.path.join(base_dir, "index.json")

    # 文件名：{project}_{timestamp}_{ms}.{summary|subagent}.md
    # 毫秒级时间戳防同秒多条记录（子 Agent 并行返回时容易同秒）互相覆盖
    suffix = "summary" if record_type == "main" else "subagent"
    ts_str = timestamp.strftime('%Y-%m-%d_%H%M%S')
    ms = int(timestamp.microsecond / 1000)
    filename = f"{project_name}_{ts_str}_{ms:03d}.{suffix}.md"
    filepath = os.path.join(month_dir, filename)

    # 构建 front matter（JSON 单行）
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    front_matter = {
        "type": "session_summary" if record_type == "main" else "subagent_summary",
        "record_type": record_type,
        "project": project_name,
        "created": timestamp.isoformat(),
        "session_id": session_id or "",
        "focus_type": focus_type or "",
        "focus_name": focus_name or "",
        "tags": tag_list,
    }
    if record_type == "subagent":
        front_matter.update({
            "task_id": task_id or "",
            "subagent": subagent or "",
            "result": result,
            "preheat_level": preheat_level or "",
            "cycle_type": cycle_type or "",
            "humanize": bool(humanize) or "",
            "new_units": new_units or 0,
            "updated_units": updated_units or 0,
            "duration_estimate_ms": duration_estimate_ms or 0,
        })

    # 正文：content 对主/子 Agent 一视同仁（统一流程，整篇 Markdown）；
    # content 为空时，子 Agent 回退用结构化字段组装分节（兼容旧调用方式）
    if content.strip():
        body = content.strip()
    elif record_type == "subagent":
        sections = _build_subagent_sections(
            prompt_summary, result_summary, user_intent,
            conflict_decision, failure_analysis, error_summary, optimization_clue,
        )
        body = "\n".join(sections) if sections else "（无总结内容）"
    else:
        body = "（无总结内容）"

    # 写入文件
    lines = ["---", json.dumps(front_matter, ensure_ascii=False), "---", "", body, ""]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 更新索引
    index_data = _load_index(index_path)
    entry = {
        "file": filename,
        "month": timestamp.strftime("%Y-%m"),
        "timestamp": timestamp.isoformat(),
        "project": project_name,
        "record_type": record_type,
        "tags": tag_list,
        "session_id": session_id or "",
        "focus_type": focus_type or "",
        "focus_name": focus_name or "",
    }
    if record_type == "subagent":
        entry.update({
            "task_id": task_id or "",
            "subagent": subagent or "",
            "result": result,
        })
    index_data["entries"].append(entry)
    index_data["total"] = len(index_data["entries"])
    _atomic_write_json(index_path, index_data)

    return {
        "file": filepath,
        "index_total": index_data["total"],
    }


def handle_list_summaries(
    project_root: str = "",
    limit: int = 20,
    offset: int = 0,
    tag: str = "",
    project: str = "",
    record_type: str = "main",
    subagent: str = "",
    result: str = "",
) -> dict:
    """
    列出会话总结（主 Agent 与子 Agent 统一脚本，按 record_type 分流）。

    Args:
        project_root: 兼容旧格式（忽略，使用 engine 路径）
        limit: 返回条数上限
        offset: 偏移量（用于分页）
        tag: 按标签过滤
        project: 按项目名过滤（可选，不传则显示所有项目）
        record_type: 按记录类型过滤（默认 "main" 只列主 Agent；"subagent" 只列子 Agent；""=全部合并）
        subagent: 按子 Agent 类型过滤（record_type="subagent" 时有效）
        result: 按结果过滤（success / partial / failed，record_type="subagent" 时有效）
    """
    summaries_path = os.path.join(_resolve_engine_kind_dir("summaries"), "index.json")
    subagents_path = os.path.join(_resolve_engine_kind_dir("subagents"), "index.json")

    if record_type == "subagent":
        entries = _load_index(subagents_path).get("entries", [])
    elif record_type == "main":
        entries = _load_index(summaries_path).get("entries", [])
    else:
        # 全部：合并两个索引
        entries = _load_index(summaries_path).get("entries", []) + _load_index(subagents_path).get("entries", [])

    # 按标签过滤
    if tag:
        entries = [e for e in entries if tag in e.get("tags", [])]

    # 按子 Agent 类型 / 结果过滤（main 记录无这两个字段，不会命中）
    if subagent:
        entries = [e for e in entries if e.get("subagent") == subagent]
    if result:
        entries = [e for e in entries if e.get("result") == result]

    # 按项目名过滤（project 参数优先于从 project_root 推断）
    if project:
        entries = [e for e in entries if e.get("project") == project]
    elif project_root:
        proj_name = _resolve_project_name(project_root)
        if proj_name:
            entries = [e for e in entries if e.get("project") == proj_name]

    # 兼容新旧索引：新条目用 timestamp，旧条目用 ts
    entries.sort(key=lambda e: e.get("timestamp") or e.get("ts") or "", reverse=True)
    entries, total = _paginate(entries, limit, offset)

    return {
        "entries": entries,
        "total": total,
        "returned": len(entries),
        "truncated": len(entries) < total,
    }


def handle_read_summary(project_root: str = "", file: str = "", record_type: str = "main") -> dict:
    """
    读取一次会话总结的内容（主 Agent 与子 Agent 统一脚本）。

    支持绝对路径、相对路径（相对 .engine/{summaries|subagents}/ 按月子目录查找，
    按 record_type 决定搜索目录）。

    Args:
        project_root: 兼容旧格式
        file: 文件名或路径
        record_type: "main"（.engine/summaries/，默认）或 "subagent"（.engine/subagents/）
    """
    if not file:
        return {"error": "缺少 file 参数"}

    kind = _kind_for(record_type if record_type in ("main", "subagent") else "main")

    filepath = Path(file)
    if not filepath.is_absolute():
        # 相对路径：在 .engine/{kind}/ 下按月目录查找
        base_dir = _resolve_engine_kind_dir(kind)
        found = False
        for month_dir in sorted(os.listdir(base_dir), reverse=True):
            candidate = os.path.join(base_dir, month_dir, file)
            if os.path.exists(candidate):
                filepath = Path(candidate)
                found = True
                break
        if not found:
            return {"error": f"文件不存在: {file}（在 {base_dir}/**/ 下未找到）"}

    if not filepath.exists():
        return {"error": f"文件不存在: {filepath}"}

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {
        "file": str(filepath),
        "content": content,
    }
