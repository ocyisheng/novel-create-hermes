"""
handlers_analysis.py — 聚合分析改进清单持久化（版本化文件 + 索引 + 修复状态跟踪）。

用户说"分析优化线索"/"综合分析"时，编排层聚合历史总结产出改进清单，
通过 analysis.save 写入 .engine/analysis/clues_YYYYMMDD_HHMMSS_fff.md（引擎级存储）。

存储结构（引擎级，跨项目，对齐 summaries/subagents 的 index.json 模式）：
  .engine/analysis/index.json                       — 索引：每轮清单一条 entry（含线索清单 + 修复状态）
  .engine/analysis/clues_YYYYMMDD_HHMMSS_fff.md     — 每轮改进清单（版本化文件名，直接落在根目录）
  .engine/analysis/history/                         — 旧版归档目录（仅兼容读取遗留数据，新 save 不再写入）
  .engine/analysis/clues_aggregated.md              — 旧版"当前清单"（仅兼容读取，新 save 不再写入）

文件格式（JSON front-matter + Markdown 正文，与 summary 存储格式一致）：
  ---
  {"sources": ["凡人之诡影重重_2026-07-27_025440.summary.md"], "aggregated_at": "...", "total_summaries": 1}
  ---
  ## 优化线索聚合分析
  ...正文...

index.json entry 结构：
  {
    "file": "clues_20260803_175908_353.md",   # 清单文件名
    "location": "root",                        # 存储位置：root=根目录 / history=旧归档 / legacy=旧当前文件
    "timestamp": "2026-08-03T17:59:08+08:00",  # 保存时间
    "project": "凡人之诡影重重",               # 项目名（从 sources 推断或显式传入）
    "sources": ["..."],                        # 来源 summary 文件名（证据链）
    "total_summaries": 8,
    "clues": ["[workflow] 编排层·创建/拆分前查重", ...],   # 从正文提取的线索标识
    "resolved": [                              # 已修复的线索
      {"clue": "...", "resolved_at": "...", "note": "..."}
    ]
  }

操作：
  analysis.save    content={清单} [sources={["file1", ...]}] [project={项目名}]
                   生成新版本化清单文件 + 自动登记 index.json（含线索提取）
  analysis.resolve file={清单文件名} clue={线索标识} [note={修复说明}]
                   标记某清单中某条线索为已修复（默认作用于最新清单）
  analysis.read    [version={文件名}]  读取最新或指定版本（返回 content + sources + resolved 状态）
  analysis.list    列出全部版本（含各自线索与修复状态）

核心价值：新一轮聚合前调用 analysis.list 即可获取已 resolve 线索集合，
编排层据此跳过/标注已修复线索，避免重复报告已优化过的问题。
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
_ARCHIVE_RE = re.compile(r"^clues_\d{8}_\d{6}_\d{3}\.md$")
# 从清单正文提取线索标识：**[类型] 组件**（B.3 输出格式）
_CLUE_KEY_RE = re.compile(r"\*\*(\[[^\]]+\]\s*[^*]+?)\*\*")


def _resolve_engine_analysis_dir() -> str:
    """解析 .engine/analysis/ 目录路径。"""
    # 测试可注入：环境变量 NOVEL_ENGINE_DIR 覆盖引擎根目录
    override = os.environ.get("NOVEL_ENGINE_DIR")
    if override:
        analysis_dir = Path(override) / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        return str(analysis_dir)
    # handlers_analysis.py 在 shared/handlers/ 下，工具根目录在 ../../../
    current = Path(__file__).resolve().parent  # handlers/
    shared = current.parent                     # shared/
    opencode = shared.parent                    # .opencode/
    tool_root = opencode.parent                 # novel-create-hermes/
    analysis_dir = tool_root / ".engine" / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    return str(analysis_dir)


def _index_path(analysis_dir: str) -> str:
    return os.path.join(analysis_dir, "index.json")


def _history_dir(analysis_dir: str) -> str:
    return os.path.join(analysis_dir, "history")


def _versioned_filename(timestamp: datetime) -> str:
    """生成版本化清单文件名（毫秒级防同秒冲突）。"""
    return f"clues_{timestamp.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.md"


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


def _render_document(content: str, sources: list[str], timestamp: datetime, project: str = "") -> str:
    """渲染 front-matter + 正文（JSON front-matter，与 summary 存储格式一致）。sources 为空时不写。"""
    if not sources:
        return content
    meta = {
        "sources": sources,
        "aggregated_at": timestamp.isoformat(),
        "total_summaries": len(sources),
    }
    if project:
        meta["project"] = project
    front = "---\n" + json.dumps(meta, ensure_ascii=False) + "\n---\n"
    return front + content


def _extract_clue_keys(content: str) -> list[str]:
    """从清单正文提取线索标识（**[类型] 组件**），去重保序。"""
    keys = []
    for m in _CLUE_KEY_RE.finditer(content or ""):
        key = m.group(1).strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def _infer_project(sources: list[str], explicit: str = "") -> str:
    """项目名：显式传入优先；否则从 sources 文件名前缀推断（{project}_{ts}.summary.md）。"""
    if explicit:
        return explicit
    for s in sources:
        name = s.rsplit("/", 1)[-1]
        # 兼容两种时间戳格式：20260727_025440（旧）与 2026-07-27_025440（新）
        m = re.match(r"^(.+?)_(?:\d{8}|\d{4}-\d{2}-\d{2})_\d{6}", name)
        if m:
            return m.group(1)
    return ""


def _load_index(analysis_dir: str) -> dict:
    """读取 index.json；缺失/损坏时自动扫描现有文件重建索引（兼容旧数据）。"""
    path = _index_path(analysis_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                return data
        except Exception:
            pass
    return _rebuild_index(analysis_dir)


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


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _entry_from_file(name: str, path: str, location: str) -> dict:
    """从清单文件构建 index entry（解析 front-matter + 提取线索）。"""
    raw = _read_file(path)
    meta, body = _split_frontmatter(raw)
    sources = _normalize_sources(meta.get("sources"))
    return {
        "file": name,
        "location": location,
        "timestamp": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
        "project": meta.get("project", "") or _infer_project(sources),
        "sources": sources,
        "total_summaries": meta.get("total_summaries", len(sources)),
        "clues": _extract_clue_keys(body),
        "resolved": [],
    }


def _rebuild_index(analysis_dir: str) -> dict:
    """
    扫描现有文件自动重建索引（首次使用新版时迁移旧数据）。

    覆盖三类文件：
      1. 根目录 clues_*.md —— 新版版本化清单
      2. history/clues_*.md —— 旧版归档
      3. clues_aggregated.md —— 旧版"当前清单"
    """
    entries: list[dict] = []
    seen: set[str] = set()

    # 1. 根目录版本化文件
    if os.path.isdir(analysis_dir):
        for name in sorted(os.listdir(analysis_dir)):
            if not _ARCHIVE_RE.match(name):
                continue
            path = os.path.join(analysis_dir, name)
            entries.append(_entry_from_file(name, path, "root"))
            seen.add(name)

    # 2. history/ 旧归档（排除已在根目录登记的）
    hist = _history_dir(analysis_dir)
    if os.path.isdir(hist):
        for name in sorted(os.listdir(hist)):
            if not _ARCHIVE_RE.match(name) or name in seen:
                continue
            entries.append(_entry_from_file(name, os.path.join(hist, name), "history"))
            seen.add(name)

    # 3. 旧版当前清单 clues_aggregated.md
    legacy = os.path.join(analysis_dir, "clues_aggregated.md")
    if os.path.exists(legacy) and "clues_aggregated.md" not in seen:
        entries.append(_entry_from_file("clues_aggregated.md", legacy, "legacy"))
        seen.add("clues_aggregated.md")

    # 时间升序（新清单在后 = 最新）
    entries.sort(key=lambda e: e.get("timestamp") or "")
    index = {"entries": entries, "total": len(entries)}
    _atomic_write_json(_index_path(analysis_dir), index)
    return index


def _locate_entry_file(analysis_dir: str, entry: dict) -> str:
    """根据 entry 的 location 定位清单文件的绝对路径。"""
    location = entry.get("location", "root")
    if location == "history":
        return os.path.join(_history_dir(analysis_dir), entry["file"])
    if location == "legacy":
        return os.path.join(analysis_dir, "clues_aggregated.md")
    return os.path.join(analysis_dir, entry["file"])


def handle_save_analysis(content: str = "", sources=None, project: str = "") -> dict:
    """
    保存聚合分析改进清单（每次生成新版本化文件，自动登记 index.json）。

    Args:
        content: 改进清单全文（Markdown 格式）。为空则仅创建/初始化文件。
        sources: 来源 summary 文件名列表（证据链）。支持 list、JSON 数组字符串、
                 逗号分隔字符串。非空时写入文件头 JSON front-matter。
        project: 项目名（可选；缺省从 sources 文件名推断）。

    Returns:
        dict: {"file", "filepath", "updated_at", "total_summaries", "clues", "total"}
    """
    analysis_dir = _resolve_engine_analysis_dir()
    sources_list = _normalize_sources(sources)
    timestamp = datetime.now()

    # 空内容时写入带时间戳的初始化头，避免空文件
    if not content or not content.strip():
        content = f"<!-- 改进清单已初始化: {timestamp.isoformat()} -->\n"

    index = _load_index(analysis_dir)

    # 幂等判断：与最新 entry 的正文 + sources 比较（忽略 aggregated_at 时间戳）
    if index["entries"]:
        latest = index["entries"][-1]
        latest_path = _locate_entry_file(analysis_dir, latest)
        if os.path.exists(latest_path):
            latest_raw = _read_file(latest_path)
            latest_meta, latest_body = _split_frontmatter(latest_raw)
            same_sources = _normalize_sources(latest_meta.get("sources")) == sources_list
            if latest_body == content and same_sources:
                return {
                    "file": latest["file"],
                    "filepath": latest_path,
                    "updated_at": timestamp.isoformat(),
                    "total_summaries": len(sources_list),
                    "clues": latest.get("clues", []),
                    "total": index["total"],
                    "unchanged": True,
                }

    # 生成版本化文件名并写入
    filename = _versioned_filename(timestamp)
    filepath = os.path.join(analysis_dir, filename)
    project_name = _infer_project(sources_list, project)
    new_doc = _render_document(content, sources_list, timestamp, project_name)

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

    # 登记 index.json
    entry = _entry_from_file(filename, filepath, "root")
    index["entries"].append(entry)
    index["total"] = len(index["entries"])
    _atomic_write_json(_index_path(analysis_dir), index)

    return {
        "file": filename,
        "filepath": filepath,
        "updated_at": timestamp.isoformat(),
        "total_summaries": len(sources_list),
        "clues": entry["clues"],
        "total": index["total"],
    }


def handle_resolve_analysis(file: str = "", clue: str = "", note: str = "") -> dict:
    """
    标记某清单中的某条线索为已修复（默认作用于最新清单）。

    Args:
        file: 清单文件名（如 clues_20260803_175908_353.md）；为空则作用于最新清单
        clue: 线索标识（如 [workflow] 编排层·创建/拆分前查重）。支持精确匹配
              与包含匹配；未命中清单线索列表时按原样记录（宽容模式）。
        note: 修复说明（可选）

    Returns:
        dict: {"file", "clue", "resolved": [...], "matched": bool}
    """
    if not clue:
        return {"error": "缺少 clue 参数（要标记为已修复的线索标识）"}

    analysis_dir = _resolve_engine_analysis_dir()
    index = _load_index(analysis_dir)

    if not index["entries"]:
        return {"error": "尚无改进清单，请先 analysis.save"}

    # 定位 entry
    if file:
        entry = next((e for e in index["entries"] if e["file"] == file), None)
        if not entry:
            return {"error": f"清单不存在: {file}（可用 analysis.list 查看）"}
    else:
        entry = index["entries"][-1]

    # 线索匹配：先精确，再包含
    clue_keys = entry.get("clues", [])
    matched = None
    if clue in clue_keys:
        matched = clue
    else:
        for k in clue_keys:
            if clue in k or k in clue:
                matched = k
                break

    resolved_list = entry.setdefault("resolved", [])
    target = matched or clue
    existing = next((r for r in resolved_list if r.get("clue") == target), None)
    if existing:
        existing["resolved_at"] = datetime.now().isoformat()
        if note:
            existing["note"] = note
    else:
        resolved_list.append({
            "clue": target,
            "resolved_at": datetime.now().isoformat(),
            "note": note or "",
        })

    _atomic_write_json(_index_path(analysis_dir), index)
    return {
        "file": entry["file"],
        "clue": target,
        "matched": matched is not None,
        "resolved": resolved_list,
        "total": index["total"],
    }


def handle_read_analysis(version: str = "", file: str = "") -> dict:
    """
    读取聚合分析改进清单（默认最新版本，可指定版本）。

    Args:
        version: 清单文件名（如 clues_20260731_054123_000.md）；"current" 或缺省读最新
        file: 与 version 等价（兼容不同参数名）

    Returns:
        dict: {"file", "content": 正文（剥离 front-matter）, "sources", "aggregated_at",
               "total_summaries", "clues", "resolved", "project"}
              文件不存在时 content 为空串。
    """
    analysis_dir = _resolve_engine_analysis_dir()
    index = _load_index(analysis_dir)
    version = file or version

    # 定位 entry：指定文件名 → 精确匹配；"current"/空 → 最新
    entry = None
    if version and version != "current":
        entry = next((e for e in index["entries"] if e["file"] == version), None)

    if entry is None:
        if version and version != "current":
            # 兼容旧数据：文件存在但未登记（如 history 遗留）
            if _ARCHIVE_RE.match(version):
                hist_path = os.path.join(_history_dir(analysis_dir), version)
                root_path = os.path.join(analysis_dir, version)
                if os.path.exists(hist_path):
                    entry = _entry_from_file(version, hist_path, "history")
                elif os.path.exists(root_path):
                    entry = _entry_from_file(version, root_path, "root")
            elif version == "clues_aggregated.md":
                legacy = os.path.join(analysis_dir, "clues_aggregated.md")
                if os.path.exists(legacy):
                    entry = _entry_from_file(version, legacy, "legacy")
        elif index["entries"]:
            entry = index["entries"][-1]

    if entry is None:
        return {
            "file": version or "current",
            "content": "",
            "version": version or "current",
            "sources": [],
            "aggregated_at": "",
            "total_summaries": 0,
            "clues": [],
            "resolved": [],
            "project": "",
        }

    filepath = _locate_entry_file(analysis_dir, entry)
    if not os.path.exists(filepath):
        return {
            "file": entry["file"],
            "content": "",
            "version": entry["file"],
            "sources": entry.get("sources", []),
            "aggregated_at": "",
            "total_summaries": entry.get("total_summaries", 0),
            "clues": entry.get("clues", []),
            "resolved": entry.get("resolved", []),
            "project": entry.get("project", ""),
        }

    raw = _read_file(filepath)
    meta, body = _split_frontmatter(raw)
    return {
        "file": entry["file"],
        "filepath": filepath,
        "content": body,
        "version": entry["file"],
        "sources": entry.get("sources", meta.get("sources", [])),
        "aggregated_at": meta.get("aggregated_at", ""),
        "total_summaries": entry.get("total_summaries", meta.get("total_summaries", 0)),
        "clues": entry.get("clues", []),
        "resolved": entry.get("resolved", []),
        "project": entry.get("project", meta.get("project", "")),
    }


def handle_list_analysis() -> dict:
    """
    列出全部改进清单版本（含各自线索与修复状态）。

    Returns:
        dict: {
            "entries": [{"file", "location", "timestamp", "project", "sources",
                         "total_summaries", "clues", "resolved"}],
            "total": 版本数,
            "resolved_count": 已修复线索总数,
        }
    """
    analysis_dir = _resolve_engine_analysis_dir()
    index = _load_index(analysis_dir)
    entries = index.get("entries", [])

    # 修复状态汇总（供新一轮聚合快速读取已 resolve 线索）
    resolved_count = sum(len(e.get("resolved", [])) for e in entries)
    return {
        "entries": entries,
        "total": len(entries),
        "resolved_count": resolved_count,
    }
