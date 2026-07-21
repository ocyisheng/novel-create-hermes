"""
handlers_summary.py — 会话总结持久化逻辑。

创作对话记录（思考过程、工具调用、冲突、成败）的结构化存储。
每次用户说"记录这次会话的总结"时触发。

存储路径: {project_root}/.omo/analysis/logs/{YYYY-MM-DD_HHmmss}.summary.md
索引文件: {project_root}/.omo/analysis/index.json
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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


def handle_save_summary(
    project_root: str,
    content: str,
    session_id: str = "",
    focus_type: str = "",
    focus_name: str = "",
    tags: str = "",
) -> dict:
    """
    保存一次会话总结。
    
    Args:
        project_root: 项目路径
        content: 总结内容（Markdown 格式）
        session_id: 可选，关联的 session ID
        focus_type: 可选，本次会话的焦点类型
        focus_name: 可选，本次会话的焦点名称
        tags: 可选，逗号分隔的标签（如 "冲突修复,时间线对齐,成功"）
    
    Returns:
        dict: {"file": "保存路径", "index": 累计条数}
    """
    project = _resolve_project(project_root)
    if not project or not os.path.isdir(os.path.join(project, "graph")):
        return {"error": f"项目路径无效: {project}"}
    
    # 准备存储目录
    log_dir = Path(project) / ".omo" / "analysis" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    index_path = Path(project) / ".omo" / "analysis" / "index.json"
    
    # 文件名：带时间戳
    timestamp = datetime.now(timezone.utc)
    filename = timestamp.strftime("%Y-%m-%d_%H%M%S") + ".summary.md"
    filepath = log_dir / filename
    
    # 构建 YAML front matter
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    
    front_matter = {
        "type": "session_summary",
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
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except (json.JSONDecodeError, Exception):
            index_data = {"entries": [], "total": 0}
    
    entry = {
        "file": filename,
        "timestamp": timestamp.isoformat(),
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
        "file": str(filepath),
        "index_total": index_data["total"],
    }


def handle_list_summaries(project_root: str, limit: int = 20, tag: str = "") -> dict:
    """列出最近的会话总结。"""
    project = _resolve_project(project_root)
    if not project:
        return {"error": "项目路径无效"}
    
    index_path = Path(project) / ".omo" / "analysis" / "index.json"
    if not index_path.exists():
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
    
    # 按时间倒序，取最新的 N 条
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    entries = entries[:limit]
    
    return {
        "entries": entries,
        "total": len(entries),
    }


def handle_read_summary(project_root: str, file: str) -> dict:
    """读取一次会话总结的内容。"""
    project = _resolve_project(project_root)
    if not project:
        return {"error": "项目路径无效"}
    
    # 支持绝对路径和相对路径（相对 .omo/analysis/logs/）
    filepath = Path(file)
    if not filepath.is_absolute():
        filepath = Path(project) / ".omo" / "analysis" / "logs" / file
    
    if not filepath.exists():
        return {"error": f"文件不存在: {filepath}"}
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    return {
        "file": str(filepath),
        "content": content,
    }
