"""
handlers_summary.py — 会话总结持久化逻辑。

创作对话记录（思考过程、工具调用、冲突、成败）的结构化存储。
每次用户说"记录这次会话的总结"时触发。

存储路径（引擎级，跨项目）:
  .engine/summaries/index.json                     — 跨项目统一索引
  .engine/summaries/{YYYY-MM}/{project}_{ts}.md    — 按月归档的总结文件
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _resolve_engine_summaries_dir() -> str:
    """解析 .engine/summaries/ 目录路径。"""
    # handlers_summary.py 在 shared/handlers/ 下，工具根目录在 ../../../
    current = Path(__file__).resolve().parent  # handlers/
    shared = current.parent                     # shared/
    opencode = shared.parent                    # .opencode/
    tool_root = opencode.parent                 # novel-create-hermes/
    summaries_dir = tool_root / ".engine" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    return str(summaries_dir)


def _resolve_project_name(project: str) -> str:
    """从 project 参数解析项目名（非完整路径）。"""
    if not project:
        return ""
    if os.path.isabs(project):
        return os.path.basename(project)
    return project


def handle_save_summary(
    project_root: str,
    content: str,
    session_id: str = "",
    focus_type: str = "",
    focus_name: str = "",
    tags: str = "",
) -> dict:
    """
    保存一次会话总结（引擎级存储）。
    
    Args:
        project_root: 项目路径或项目名
        content: 总结内容（Markdown 格式）
        session_id: 可选，关联的 session ID
        focus_type: 可选，本次会话的焦点类型
        focus_name: 可选，本次会话的焦点名称
        tags: 可选，逗号分隔的标签（如 "冲突修复,时间线对齐,成功"）
    
    Returns:
        dict: {"file": "保存路径", "index_total": 累计条数}
    """
    project_name = _resolve_project_name(project_root)
    if not project_name:
        return {"error": f"无法解析项目名: {project_root}"}
    
    summaries_dir = _resolve_engine_summaries_dir()
    
    # 按月分目录
    timestamp = datetime.now(timezone.utc)
    month_dir = os.path.join(summaries_dir, timestamp.strftime("%Y-%m"))
    os.makedirs(month_dir, exist_ok=True)
    
    index_path = os.path.join(summaries_dir, "index.json")
    
    # 文件名：{project}_{timestamp}.summary.md
    filename = f"{project_name}_{timestamp.strftime('%Y-%m-%d_%H%M%S')}.summary.md"
    filepath = os.path.join(month_dir, filename)
    
    # 构建 YAML front matter
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    
    front_matter = {
        "type": "session_summary",
        "project": project_name,
        "created": timestamp.isoformat(),
        "session_id": session_id or "",
        "focus_type": focus_type or "",
        "focus_name": focus_name or "",
        "tags": tag_list,
    }
    
    # 写入文件
    lines = []
    lines.append("---")
    lines.append(json.dumps(front_matter, ensure_ascii=False))
    lines.append("---")
    lines.append("")
    lines.append(content.strip())
    lines.append("")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    # 更新索引
    index_data = {"entries": [], "total": 0}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except (json.JSONDecodeError, Exception):
            index_data = {"entries": [], "total": 0}
    
    entry = {
        "file": filename,
        "month": timestamp.strftime("%Y-%m"),
        "timestamp": timestamp.isoformat(),
        "project": project_name,
        "tags": tag_list,
        "session_id": session_id or "",
        "focus_type": focus_type or "",
        "focus_name": focus_name or "",
    }
    index_data["entries"].append(entry)
    index_data["total"] = len(index_data["entries"])
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    return {
        "file": filepath,
        "index_total": index_data["total"],
    }


def handle_list_summaries(project_root: str = "", limit: int = 20, tag: str = "", project: str = "") -> dict:
    """
    列出最近的会话总结（跨项目）。
    
    Args:
        project_root: 兼容旧格式（忽略，使用 engine 路径）
        limit: 返回条数上限
        tag: 按标签过滤
        project: 按项目名过滤（可选，不传则显示所有项目）
    """
    summaries_dir = _resolve_engine_summaries_dir()
    index_path = os.path.join(summaries_dir, "index.json")
    
    if not os.path.exists(index_path):
        return {"entries": [], "total": 0}
    
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    except (json.JSONDecodeError, Exception):
        return {"entries": [], "total": 0}
    
    entries = index_data.get("entries", [])
    
    # 按标签过滤
    if tag:
        entries = [e for e in entries if tag in e.get("tags", [])]
    
    # 按项目名过滤（project 参数优先于从 project_root 推断）
    if project:
        entries = [e for e in entries if e.get("project") == project]
    elif project_root:
        proj_name = _resolve_project_name(project_root)
        if proj_name:
            entries = [e for e in entries if e.get("project") == proj_name]
    
    # 按时间倒序，取最新的 N 条
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    entries = entries[:limit]
    
    return {
        "entries": entries,
        "total": len(entries),
    }


def handle_read_summary(project_root: str = "", file: str = "") -> dict:
    """
    读取一次会话总结的内容。
    
    支持绝对路径、相对路径（相对 .engine/summaries/ 按月子目录查找）。
    """
    if not file:
        return {"error": "缺少 file 参数"}
    
    filepath = Path(file)
    if not filepath.is_absolute():
        # 相对路径：在 .engine/summaries/ 下按月目录查找
        summaries_dir = _resolve_engine_summaries_dir()
        found = False
        for month_dir in sorted(os.listdir(summaries_dir), reverse=True):
            candidate = os.path.join(summaries_dir, month_dir, file)
            if os.path.exists(candidate):
                filepath = Path(candidate)
                found = True
                break
        if not found:
            return {"error": f"文件不存在: {file}（在 {summaries_dir}/**/ 下未找到）"}
    
    if not filepath.exists():
        return {"error": f"文件不存在: {filepath}"}
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    return {
        "file": str(filepath),
        "content": content,
    }
