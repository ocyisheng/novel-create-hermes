"""元数据标记提取与摘要处理

从 chapters/.metas/ 目录读取章节元数据，提取伏笔、角色、摘要等信息，
并将摘要内联到分纲 YAML 文件中。
"""

import re
from pathlib import Path

from _utils import load_yaml, save_yaml, extract_chapter_number


def extract_markers(chapter_path: Path) -> dict:
    """从章节元数据目录 .metas/ 读取标记。

    查找 chapters/.metas/{章节名}.txt，不存在则降级扫描章节文件末尾。
    支持的标记：【本章摘要】【新伏笔】【回收伏笔】【出场角色】
    """
    meta_path = chapter_path.parent / ".metas" / chapter_path.name
    text = None
    if meta_path.is_file():
        try:
            text = meta_path.read_text(encoding="utf-8")
        except Exception:
            pass

    if text is None:
        try:
            text = chapter_path.read_text(encoding="utf-8")
        except Exception:
            return {}

    result = {}

    m = re.search(r'【本章摘要】\s*\n(.*?)(?=\n【|$)', text, re.DOTALL)
    if m:
        result["actual_summary"] = m.group(1).strip().replace("\n", " ")[:200]

    m = re.search(r'【新伏笔】\s*\n(.*?)(?=\n【|$)', text, re.DOTALL)
    if m:
        items = [line.strip() for line in m.group(1).strip().split("\n") if line.strip()]
        if items:
            result["foreshadowing"] = items

    m = re.search(r'【回收伏笔】\s*\n(.*?)(?=\n【|$)', text, re.DOTALL)
    if m:
        items = [line.strip() for line in m.group(1).strip().split("\n") if line.strip()]
        if items:
            result["resolve_foreshadowing"] = items

    m = re.search(r'【出场角色】\s*\n(.*?)(?=\n【|$)', text, re.DOTALL)
    if m:
        names = [n.strip() for n in m.group(1).strip().split(",") if n.strip()]
        if names:
            result["characters"] = names

    m = re.search(r'【时间线事件】\s*\n(.*?)(?=\n【|$)', text, re.DOTALL)
    if m:
        events = []
        for line in m.group(1).strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                desc, time_val = line.split("|", 1)
                events.append({"描述": desc.strip(), "时间": time_val.strip()})
            else:
                events.append({"描述": line})
        if events:
            result["timeline_events"] = events

    return result


def persist_actual_summary(project_root: Path, chapter_path: Path, actual_summary: str) -> bool:
    """将章节摘要内联到分纲文件的 `摘要.本章摘要` 字段。"""
    if not actual_summary or not actual_summary.strip():
        return False

    chapter_num = extract_chapter_number(chapter_path)
    if not chapter_num:
        return False

    fg_root = project_root / "outline" / "分纲"
    if not fg_root.is_dir():
        return False

    target_name = f"第{chapter_num}章.yaml"
    matches = list(fg_root.rglob(target_name))
    if not matches:
        print(f"  警告: 未找到分纲文件 {target_name}")
        return False

    outline_path = matches[0]
    data = load_yaml(outline_path)

    if not isinstance(data, dict):
        return False

    summary_section = data.setdefault("摘要", {})
    if not isinstance(summary_section, dict):
        return False

    summary_section["本章摘要"] = actual_summary.strip()
    save_yaml(outline_path, data)

    print(f"  -> 章节摘要已内联到 {outline_path.relative_to(project_root)}")
    return True
