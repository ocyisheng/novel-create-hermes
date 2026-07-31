"""
handlers_analysis.py — 聚合分析改进清单持久化（版本化归档 + 来源元数据）。

用户说"分析优化线索"/"综合分析"时，编排层聚合历史总结产出改进清单，
通过 analysis.save 写入 .engine/analysis/clues_aggregated.md（引擎级存储）。

存储结构（引擎级，跨项目）：
  .engine/analysis/clues_aggregated.md        — 当前改进清单（Markdown，原子写）
  .engine/analysis/history/clues_YYYYMMDD_HHMMSS.md — 历史版本归档（每次 save 前自动归档旧版）

文件格式（JSON front-matter + Markdown 正文，与 summary 存储格式一致）：
  ---
  {"sources": ["凡人之诡影重重_2026-07-27_025440.summary.md"], "aggregated_at": "...", "total_summaries": 1}
  ---
  ## 优化线索聚合分析
  ...正文...

操作：
  analysis.save    content={清单} [sources={["file1", ...]}]  覆盖写当前清单，旧版自动归档
  analysis.read    [version={文件名}]  读取当前或指定历史版本（返回剥离 front-matter 的 content + sources 元数据）
  analysis.list    列出当前 + 全部历史版本

注意：清单是聚合分析的产物，由编排层通过命令写入/覆盖，代码层不直接读写
（区别于 subagents/summaries 的追加写模式）。
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
_ARCHIVE_RE = re.compile(r"^clues_\d{8}_\d{6}_\d{3}\.md$")


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


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    """
    解析 front-matter，返回 (meta_dict, 正文)。

    优先按 JSON 解析（与 summary 存储格式一致）；失败时回退 YAML
    （兼容早期 YAML 版本文件）；两者都失败或无 front-matter 时返回 ({}, 原文)。
    """
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    fm_text = m.group(1).strip()
    # JSON 优先
    try:
        meta = json.loads(fm_text)
        if isinstance(meta, dict):
            return meta, raw[m.end():]
    except json.JSONDecodeError:
        pass
    # YAML 回退（兼容旧格式）
    try:
        import yaml
        meta = yaml.safe_load(fm_text) or {}
    except Exception:
        return {}, raw
    if not isinstance(meta, dict):
        return {}, raw
    return meta, raw[m.end():]


def _normalize_sources(sources) -> list[str]:
    """将 sources 归一化为文件名列表（接受 list、JSON 数组字符串、逗号分隔字符串）。"""
    if sources is None:
        return []
    if isinstance(sources, str):
        s = sources.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                import json
                parsed = json.loads(s)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return [x.strip() for x in parsed if isinstance(x, str) and x.strip()]
        return [x.strip() for x in s.split(",") if x.strip()]
    if isinstance(sources, (list, tuple)):
        return [x.strip() for x in sources if isinstance(x, str) and x.strip()]
    return []


def _render_document(content: str, sources: list[str], timestamp: datetime) -> str:
    """渲染 front-matter + 正文（JSON front-matter，与 summary 存储格式一致）。sources 为空时不写。"""
    if not sources:
        return content
    meta = {
        "sources": sources,
        "aggregated_at": timestamp.isoformat(),
        "total_summaries": len(sources),
    }
    front = "---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n"
    return front + content


def handle_save_analysis(content: str = "", sources=None) -> dict:
    """
    保存聚合分析改进清单（覆盖写当前版本，旧版自动归档到 history/）。

    Args:
        content: 改进清单全文（Markdown 格式）。为空则仅创建/初始化文件。
        sources: 来源 summary 文件名列表（证据链）。支持 list、JSON 数组字符串、
                 逗号分隔字符串。非空时写入文件头 YAML front-matter。

    Returns:
        dict: {"file", "updated_at", "archived", "total_summaries"}
    """
    analysis_dir = _resolve_engine_analysis_dir()
    filepath = _current_filepath(analysis_dir)

    sources_list = _normalize_sources(sources)
    timestamp = datetime.now()

    # 空内容时写入带时间戳的初始化头，避免空文件
    if not content or not content.strip():
        content = f"<!-- 改进清单已初始化: {timestamp.isoformat()} -->\n"

    # 幂等判断：比较正文 + sources（忽略 aggregated_at 时间戳，它每次生成都不同）
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            existing = f.read()
        existing_meta, existing_body = _split_frontmatter(existing)
        same_sources = _normalize_sources(existing_meta.get("sources")) == sources_list
        if existing_body == content and same_sources:
            return {
                "file": filepath,
                "updated_at": timestamp.isoformat(),
                "archived": None,
                "total_summaries": len(sources_list),
                "unchanged": True,
            }

    new_doc = _render_document(content, sources_list, timestamp)
    archived = _archive_current(analysis_dir)

    # 原子写：先写临时文件再替换，避免中断导致清单损坏
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(new_doc)
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return {
        "file": filepath,
        "updated_at": timestamp.isoformat(),
        "archived": archived,
        "total_summaries": len(sources_list),
    }


def handle_read_analysis(version: str = "") -> dict:
    """
    读取聚合分析改进清单（当前或指定历史版本）。

    Args:
        version: 为空读取当前清单；否则读取 history/ 下对应文件名
                 （如 clues_20260731_054123_000.md）。

    Returns:
        dict: {"file", "content": 正文（剥离 front-matter）, "version",
               "sources": 来源文件名列表, "aggregated_at", "total_summaries"}
              文件不存在时 content 为空串。
    """
    analysis_dir = _resolve_engine_analysis_dir()

    if version:
        # 防目录穿越：只允许读取 history/ 内的 .md 文件
        if not _ARCHIVE_RE.match(version):
            return {"error": f"非法版本名: {version}（应为 clues_YYYYMMDD_HHMMSS_fff.md）"}
        filepath = os.path.join(_history_dir(analysis_dir), version)
        if not os.path.exists(filepath):
            return {"error": f"历史版本不存在: {version}"}
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
        meta, body = _split_frontmatter(raw)
        return {
            "file": filepath,
            "content": body,
            "version": version,
            "sources": meta.get("sources", []),
            "aggregated_at": meta.get("aggregated_at", ""),
            "total_summaries": meta.get("total_summaries", 0),
        }

    filepath = _current_filepath(analysis_dir)
    if not os.path.exists(filepath):
        return {
            "file": filepath,
            "content": "",
            "version": "current",
            "sources": [],
            "aggregated_at": "",
            "total_summaries": 0,
        }

    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()
    meta, body = _split_frontmatter(raw)
    return {
        "file": filepath,
        "content": body,
        "version": "current",
        "sources": meta.get("sources", []),
        "aggregated_at": meta.get("aggregated_at", ""),
        "total_summaries": meta.get("total_summaries", 0),
    }


def handle_list_analysis() -> dict:
    """
    列出当前改进清单 + 全部历史版本。

    Returns:
        dict: {
            "current": {"file", "version", "size", "updated_at", "sources", "total_summaries"} 或 None,
            "history": [{"file", "version", "size", "updated_at", "sources", "total_summaries"}],
            "count": 历史版本数,
        }
    """
    analysis_dir = _resolve_engine_analysis_dir()
    current = _current_filepath(analysis_dir)

    def _entry_meta(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        meta, _body = _split_frontmatter(raw)
        return {
            "sources": meta.get("sources", []),
            "total_summaries": meta.get("total_summaries", 0),
        }

    current_info = None
    if os.path.exists(current):
        meta = _entry_meta(current)
        current_info = {
            "file": current,
            "version": "current",
            "size": os.path.getsize(current),
            "updated_at": datetime.fromtimestamp(os.path.getmtime(current)).isoformat(),
            "sources": meta["sources"],
            "total_summaries": meta["total_summaries"],
        }

    history = []
    hist_dir = _history_dir(analysis_dir)
    if os.path.isdir(hist_dir):
        for name in sorted(os.listdir(hist_dir)):
            if not _ARCHIVE_RE.match(name):
                continue
            path = os.path.join(hist_dir, name)
            meta = _entry_meta(path)
            history.append({
                "file": path,
                "version": name,
                "size": os.path.getsize(path),
                "updated_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
                "sources": meta["sources"],
                "total_summaries": meta["total_summaries"],
            })
        # 旧的在前（时间戳升序）
        history.reverse()

    return {
        "current": current_info,
        "history": history,
        "count": len(history),
    }
