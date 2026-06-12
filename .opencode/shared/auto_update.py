"""auto_update.py — 章节写后元数据维护

读取 chapters/.metas/ 标记，更新伏笔/时间线/角色统计/config/索引/摘要。

用法:
  python auto_update.py --project-root PATH --chapter chapters/第X章.txt
  python auto_update.py --project-root PATH  # 自动扫描 .metas/

示例:
  python auto_update.py --project-root novels/项目名 --chapter chapters/第1章.txt
"""

import argparse
import sys
from pathlib import Path

from _utils import find_project_root
from _tracking import update_foreshadowing, update_timeline, update_character_stats, update_config_progress, update_plot_threads
from _summary import extract_markers, persist_actual_summary


def _parse_events(raw_events: list[str]) -> list[dict]:
    """解析事件参数。支持格式：'描述' 或 '描述|时间'。"""
    result = []
    for e in raw_events:
        if "|" in e:
            desc, time_val = e.split("|", 1)
            result.append({"描述": desc.strip(), "时间": time_val.strip()})
        else:
            result.append({"描述": e.strip()})
    return result

try:
    from rebuild_project_index import rebuild_index
except ImportError:
    rebuild_index = None


def main():
    parser = argparse.ArgumentParser(description="章节写后元数据维护")
    parser.add_argument("--chapter", type=str, default=None,
                        help="章节文件路径。省略时自动扫描 .metas/ 目录。")
    parser.add_argument("--project-root", type=str, required=True, help="项目根目录")
    parser.add_argument("--foreshadowing", type=str, nargs="*", help="新增伏笔")
    parser.add_argument("--resolve-foreshadowing", type=str, nargs="*", help="已回收伏笔（模糊匹配）")
    parser.add_argument("--events", type=str, nargs="*", help="新增事件。格式：'描述' 或 '描述|故事时间'")
    parser.add_argument("--characters", type=str, nargs="*", help="出场角色名")
    parser.add_argument("--actual-summary", type=str, default=None, help="章节摘要")
    parser.add_argument("--summary-file", type=str, default=None, help="从文件读取摘要")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    if args.chapter:
        chapter_path = project_root / args.chapter
        if not chapter_path.is_file():
            print(f"错误: 章节文件不存在: {chapter_path}")
            sys.exit(1)
        chapters = [chapter_path]
    else:
        chapters_dir = project_root / "chapters"
        if not chapters_dir.is_dir():
            print("错误: chapters/ 目录不存在")
            sys.exit(1)
        chapters = []
        for f in sorted(chapters_dir.glob("*.txt")):
            if (chapters_dir / ".metas" / f.name).is_file():
                chapters.append(f)
        if not chapters:
            print("没有待处理的章节（chapters/.metas/ 为空）")
            sys.exit(0)
        print(f"发现 {len(chapters)} 个待处理章节")

    for cp in chapters:
        markers = extract_markers(cp)

        foreshadowing_data = None
        if args.foreshadowing:
            foreshadowing_data = [{"描述": f} for f in args.foreshadowing]
        elif markers.get("foreshadowing"):
            foreshadowing_data = [{"描述": f} for f in markers["foreshadowing"]]

        resolve_items = args.resolve_foreshadowing or markers.get("resolve_foreshadowing", [])
        # Merge CLI events with marker events
        events_data = None
        cli_events = _parse_events(args.events) if args.events else []
        marker_events = markers.get("timeline_events", [])
        merged = cli_events + marker_events
        if merged:
            events_data = merged
        char_list = args.characters or markers.get("characters")

        update_foreshadowing(cp, foreshadowing_data, resolve_items)
        update_timeline(cp, events_data)
        update_character_stats(cp, char_list)
        update_config_progress(cp)
        plot_result = update_plot_threads(cp, char_list)

        print(f"已更新元数据: {cp.name}")
        print("  - 伏笔.yaml ✓")
        print("  - 时间线.yaml ✓")
        print("  - 角色统计.yaml ✓")
        print("  - config.yaml ✓")
        if plot_result["updated"] > 0:
            print(f"  - 情节线进度 ✓ ({plot_result['updated']} 条)")
            for detail in plot_result["details"]:
                print(f"    {detail}")

        summary = args.actual_summary
        if not summary and args.summary_file:
            sf = Path(args.summary_file)
            if sf.is_file():
                summary = sf.read_text(encoding="utf-8").strip()
        if not summary:
            summary = markers.get("actual_summary")
        if summary:
            persist_actual_summary(find_project_root(cp), cp, summary)
            print("  - 章节摘要 ✓")

    if rebuild_index:
        try:
            rebuild_index(find_project_root(chapters[0]))
        except Exception as e:
            print(f"  [跳过] 项目索引更新失败: {e}")


if __name__ == "__main__":
    main()
