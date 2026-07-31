"""
handlers_analysis.py — 聚合分析改进清单持久化（版本化归档）。

用户说"分析优化线索"/"综合分析"时，编排层聚合历史总结产出改进清单，
通过 analysis.save 写入 .engine/analysis/clues_aggregated.md（引擎级存储）。

存储结构（引擎级，跨项目）：
  .engine/analysis/clues_aggregated.md        — 当前改进清单（Markdown，原子写）
  .engine/analysis/history/clues_YYYYMMDD_HHMMSS.md — 历史版本归档（每次 save 前自动归档旧版）

操作：
  analysis.save    content={清单}   覆盖写当前清单，旧版自动归档到 history/
  analysis.read    [version={文件名}]  读取当前或指定历史版本
  analysis.list    列出当前 + 全部历史版本

注意：清单是聚合分析的产物，由编排层通过命令写入/覆盖，代码层不直接读写
（区别于 subagents/summaries 的追加写模式）。
"""

import os
import re
from datetime import datetime
from pathlib import Path


def _resolve_engine_analysis_dir() -> str:
    """解析 .engine/analysis/ 目录路径。"""
    # 测试可注入：环境变量 NOVEL_ENGINE_DIR 覆盖引擎根目录
    override = os.environ.get("NOVEL_ENGINE_DIR")
    if override:
        analysis_dir = Path(override) / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        (analysis_dir / "history").mkdir(parents=True, exist_ok=True)
        return str(analysis_dir)
    # handlers_analysis.py 在 shared/handlers/ 下，工具根目录在 ../../../
    current = Path(__file__).resolve().parent  # handlers/
    shared = current.parent                     # shared/
    opencode = shared.parent                    # .opencode/
    tool_root = opencode.parent                 # novel-create-hermes/
    analysis_dir = tool_root / ".engine" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "history").mkdir(parents=True, exist_ok=True)
    return str(analysis_dir)


def _current_filepath(analysis_dir: str) -> str:
    return os.path.join(analysis_dir, "clues_aggregated.md")


def _history_dir(analysis_dir: str) -> str:
    return os.path.join(analysis_dir, "history")


def _archive_current(analysis_dir: str) -> str | None:
    """若当前清单存在且非空，归档到 history/，返回归档文件名；否则返回 None。"""
    current = _current_filepath(analysis_dir)
    if not os.path.exists(current):
        return None
    with open(current, "r", encoding="utf-8") as f:
        old = f.read()
    if not old.strip():
        return None

    archive_name = f"clues_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.md"
    archive_path = os.path.join(_history_dir(analysis_dir), archive_name)
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(old)
    return archive_name


def handle_save_analysis(content: str = "") -> dict:
    """
    保存聚合分析改进清单（覆盖写当前版本，旧版自动归档到 history/）。

    Args:
        content: 改进清单全文（Markdown 格式）。为空则仅创建/初始化文件。

    Returns:
        dict: {"file": "保存路径", "updated_at": 时间戳, "archived": 归档文件名或 None}
    """
    analysis_dir = _resolve_engine_analysis_dir()
    filepath = _current_filepath(analysis_dir)

    # 内容未变化时跳过归档与写入，保持幂等（同一轮重复 save 不产生冗余归档）
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()
        if existing == content:
            return {
                "file": filepath,
                "updated_at": datetime.now().isoformat(),
                "archived": None,
                "unchanged": True,
            }

    archived = _archive_current(analysis_dir)

    timestamp = datetime.now()

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

    return {
        "file": filepath,
        "updated_at": timestamp.isoformat(),
        "archived": archived,
    }


def handle_read_analysis(version: str = "") -> dict:
    """
    读取聚合分析改进清单（当前或指定历史版本）。

    Args:
        version: 为空读取当前清单；否则读取 history/ 下对应文件名
                 （如 clues_20260731_054123.md）。

    Returns:
        dict: {"file": "路径", "content": 清单内容, "version": "current 或文件名"}
              文件不存在时 content 为空串。
    """
    analysis_dir = _resolve_engine_analysis_dir()

    if version:
        # 防目录穿越：只允许读取 history/ 内的 .md 文件
        if not re.match(r"^clues_\d{8}_\d{6}_\d{3}\.md$", version):
            return {"error": f"非法版本名: {version}（应为 clues_YYYYMMDD_HHMMSS_fff.md）"}
        filepath = os.path.join(_history_dir(analysis_dir), version)
        if not os.path.exists(filepath):
            return {"error": f"历史版本不存在: {version}"}
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"file": filepath, "content": content, "version": version}

    filepath = _current_filepath(analysis_dir)
    if not os.path.exists(filepath):
        return {"file": filepath, "content": "", "version": "current"}

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"file": filepath, "content": content, "version": "current"}


def handle_list_analysis() -> dict:
    """
    列出当前改进清单 + 全部历史版本。

    Returns:
        dict: {
            "current": {"file", "updated_at"} 或 None,
            "history": [{"file", "version", "size", "updated_at"}],
            "count": 历史版本数,
        }
    """
    analysis_dir = _resolve_engine_analysis_dir()
    current = _current_filepath(analysis_dir)

    current_info = None
    if os.path.exists(current):
        current_info = {
            "file": current,
            "version": "current",
            "size": os.path.getsize(current),
            "updated_at": datetime.fromtimestamp(os.path.getmtime(current)).isoformat(),
        }

    history = []
    hist_dir = _history_dir(analysis_dir)
    if os.path.isdir(hist_dir):
        for name in sorted(os.listdir(hist_dir)):
            if not re.match(r"^clues_\d{8}_\d{6}_\d{3}\.md$", name):
                continue
            path = os.path.join(hist_dir, name)
            history.append({
                "file": path,
                "version": name,
                "size": os.path.getsize(path),
                "updated_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
            })
        # 旧的在前（时间戳升序）
        history.reverse()

    return {
        "current": current_info,
        "history": history,
        "count": len(history),
    }
