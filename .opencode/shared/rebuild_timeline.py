#!/usr/bin/env python3
"""
rebuild_timeline.py — 从分纲+章节元数据重建时间线。

全量重建模式，对应的增量更新函数在 _tracking.py（update_timeline）。

用法：
    python rebuild_timeline.py --project-root NOVELS_ROOT/项目名
    python rebuild_timeline.py --project-root NOVELS_ROOT/项目名 --dry-run

数据源：outline/分纲/*.yaml + chapters/.metas/*.txt
输出：  outline/追踪/时间线.yaml

格式（扁平列表）：
    事件:
      - 描述: "主角进入宗门"
        章节: 1
        时间: "Day 1"
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from _utils import load_yaml, save_yaml, extract_chapter_number
except ImportError:
    import importlib.util
    _utils_path = Path(__file__).parent / "_utils.py"
    spec = importlib.util.spec_from_file_location("_utils", _utils_path)
    _utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_utils)
    load_yaml = _utils.load_yaml
    save_yaml = _utils.save_yaml
    extract_chapter_number = _utils.extract_chapter_number


def _extract_events_from_meta(meta_path: Path) -> list[dict]:
    """从章节元数据中提取时间线事件。"""
    if not meta_path.is_file():
        return []

    try:
        content = meta_path.read_text(encoding="utf-8")
    except Exception:
        return []

    result = []

    # 尝试从 YAML 格式提取
    data = load_yaml(meta_path)
    if data and isinstance(data, dict):
        events = data.get("timeline_events", [])
        if isinstance(events, list):
            for item in events:
                if isinstance(item, str):
                    result.append({"描述": item})
                elif isinstance(item, dict):
                    result.append(item)
            return result

    # 尝试从文本格式提取
    match = re.search(r"【时间线事件】\s*\n(.*?)(?=\n【|$)", content, re.DOTALL)
    if match:
        for line in match.group(1).strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                desc, time_val = line.split("|", 1)
                result.append({"描述": desc.strip(), "时间": time_val.strip()})
            else:
                result.append({"描述": line})

    return result


def _extract_events_from_outline(outline_path: Path) -> list[dict]:
    """从分纲文件中提取时间线事件。"""
    data = load_yaml(outline_path)
    if not data:
        return []

    result = []

    # 分纲中的时间线
    timeline = data.get("时间线", [])
    if isinstance(timeline, list):
        for item in timeline:
            if isinstance(item, str):
                result.append({"描述": item})
            elif isinstance(item, dict):
                result.append(item)

    # 也检查故事时间
    story_time = data.get("摘要", {}).get("故事时间", "")
    if story_time:
        result.append({"描述": "本章时间点", "时间": story_time})

    return result


def rebuild_timeline(project_root: Path, dry_run: bool = False) -> dict:
    """从分纲+章节元数据重建时间线。

    Returns:
        生成的完整数据结构
    """
    project_root = project_root.resolve()
    outline_dir = project_root / "outline"
    fengang_dir = outline_dir / "分纲"
    meta_dir = project_root / "chapters" / ".metas"
    timeline_path = outline_dir / "追踪" / "时间线.yaml"

    # 1. 扫描分纲文件
    records = []
    if fengang_dir.is_dir():
        for f in sorted(fengang_dir.glob("*.yaml")):
            chapter_num = extract_chapter_number(f.name)
            if chapter_num == 0:
                continue

            items = _extract_events_from_outline(f)
            for item in items:
                item["章节"] = chapter_num
                records.append(item)

    # 2. 扫描章节元数据（覆盖分纲中的数据）
    if meta_dir.is_dir():
        for meta_file in sorted(meta_dir.glob("*.txt")):
            chapter_num = _extract_chapter_number(meta_file.name)
            if chapter_num == 0:
                continue

            items = _extract_events_from_meta(meta_file)
            for item in items:
                item["章节"] = chapter_num
                records.append(item)

    if not records:
        print("⚠️  未找到任何时间线事件")
        return {}

    # 3. 按章节排序
    records.sort(key=lambda r: (r.get("章节", 0), r.get("描述", "")))

    # 4. 构建输出
    output = {"事件": records, "版本": "1.0"}

    # 5. 统计信息
    unique_descs = set(r.get("描述", "") for r in records)
    max_chapter = max(r.get("章节", 0) for r in records) if records else 0
    with_time = sum(1 for r in records if r.get("时间"))

    # 6. 写入文件
    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {len(records)} 条事件，{len(unique_descs)} 个唯一描述，最高章节: {max_chapter}")
        print(f"  有时间标记: {with_time}")
        for record in records[:10]:
            time_str = f" [{record.get('时间', '')}]" if record.get('时间') else ""
            print(f"  第{record.get('章节', '?')}章: {record.get('描述', '?')[:30]}{time_str}")
        if len(records) > 10:
            print(f"  ... 还有 {len(records) - 10} 条")
        return output

    save_yaml(timeline_path, output)
    print(f"📝 时间线重建完成: {len(records)} 条事件，{len(unique_descs)} 个唯一描述")
    print(f"   有时间标记: {with_time}")
    print(f"   写入: {timeline_path}")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_timeline.py — 从分纲+章节元数据重建时间线",
    )
    parser.add_argument("--project-root", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    rebuild_timeline(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
