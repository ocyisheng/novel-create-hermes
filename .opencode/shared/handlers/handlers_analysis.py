"""
handlers_analysis.py — 聚合分析改进清单持久化。

用户说"分析优化线索"/"综合分析"时，编排层聚合历史总结产出改进清单，
通过 analysis.save 写入 .engine/analysis/clues_aggregated.md（引擎级存储）。

存储结构（引擎级，跨项目）：
  .engine/analysis/clues_aggregated.md   — 改进清单（Markdown，原子写）

注意：清单是聚合分析的产物，由编排层通过命令写入/覆盖，代码层不直接读写
（区别于 subagents/summaries 的追加写模式）。
"""

import os
from datetime import datetime, timezone
from pathlib import Path


def _resolve_engine_analysis_dir() -> str:
    """解析 .engine/analysis/ 目录路径。"""
    # handlers_analysis.py 在 shared/handlers/ 下，工具根目录在 ../../../
    current = Path(__file__).resolve().parent  # handlers/
    shared = current.parent                     # shared/
    opencode = shared.parent                    # .opencode/
    tool_root = opencode.parent                 # novel-create-hermes/
    analysis_dir = tool_root / ".engine" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    return str(analysis_dir)


def handle_save_analysis(content: str = "") -> dict:
    """
    保存聚合分析改进清单（引擎级存储）。

    Args:
        content: 改进清单全文（Markdown 格式）。为空则仅创建/初始化文件。

    Returns:
        dict: {"file": "保存路径", "updated_at": 时间戳}
    """
    analysis_dir = _resolve_engine_analysis_dir()
    filepath = os.path.join(analysis_dir, "clues_aggregated.md")

    timestamp = datetime.now(timezone.utc)

    # 为空时写入带时间戳的初始化头，避免空文件
    if not content or not content.strip():
        content = f"<!-- 改进清单已初始化: {timestamp.isoformat()} -->\n"

    # 原子写：先写临时文件再替换，避免中断导致清单损坏
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return {"file": filepath, "updated_at": timestamp.isoformat()}


def handle_read_analysis() -> dict:
    """
    读取聚合分析改进清单。

    Returns:
        dict: {"file": "路径", "content": 清单内容}；文件不存在时 content 为空串
    """
    analysis_dir = _resolve_engine_analysis_dir()
    filepath = os.path.join(analysis_dir, "clues_aggregated.md")

    if not os.path.exists(filepath):
        return {"file": filepath, "content": ""}

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    return {"file": filepath, "content": content}
