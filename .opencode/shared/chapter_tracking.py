"""chapter_tracking.py — 章节写后追踪数据维护

读取 chapters/.metas/ 标记，增量更新伏笔/时间线/角色统计/情节线进度/摘要。

职责边界：本脚本只维护 outline/追踪/ 下的追踪数据。项目索引（project_index.yaml）
由各创作阶段的 post-processing 链负责（P2/P3/P5/P7/P13），或通过 --rebuild-index 手动触发。

用法:
  # 增量更新（默认 — 仅追踪数据）
  python chapter_tracking.py --project-root PATH --chapter chapters/第X章.txt
  python chapter_tracking.py --project-root PATH  # 自动扫描 .metas/

  # 全量重建（追踪数据）
  python chapter_tracking.py --project-root PATH --rebuild-foreshadowing
  python chapter_tracking.py --project-root PATH --rebuild-timeline
  python chapter_tracking.py --project-root PATH --rebuild-plot-progress
  python chapter_tracking.py --project-root PATH --rebuild-summaries
  python chapter_tracking.py --project-root PATH --rebuild-all

  # 全量重建（索引，独立触发）
  python chapter_tracking.py --project-root PATH --rebuild-index

示例:
  python chapter_tracking.py --project-root novels/项目名 --chapter chapters/第1章.txt
  python chapter_tracking.py --project-root novels/项目名 --rebuild-all
"""

import argparse
import sys
from pathlib import Path

from _utils import find_project_root
from _tracking import (
    update_foreshadowing, update_timeline, update_character_stats,
    update_plot_threads, update_chapter_summary, update_worldbuilding_usage,
)
from _summary import extract_markers


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

try:
    from rebuild_character_stats import rebuild_character_stats
except ImportError:
    rebuild_character_stats = None

try:
    from rebuild_foreshadowing import rebuild_foreshadowing
except ImportError:
    rebuild_foreshadowing = None

try:
    from rebuild_worldbuilding_mapping import rebuild_worldbuilding_mapping
except ImportError:
    rebuild_worldbuilding_mapping = None

try:
    from rebuild_timeline import rebuild_timeline
except ImportError:
    rebuild_timeline = None

try:
    from rebuild_plot_progress import rebuild_plot_progress
except ImportError:
    rebuild_plot_progress = None

try:
    from rebuild_chapter_summaries import rebuild_chapter_summaries
except ImportError:
    rebuild_chapter_summaries = None


def main():
    parser = argparse.ArgumentParser(description="章节写后元数据维护")
    parser.add_argument("--chapter", "-c", type=str, default=None,
                        help="章节文件路径。省略时自动扫描 .metas/ 目录。")
    parser.add_argument("--project-root", "-p", type=str, required=True, help="项目根目录")
    parser.add_argument("--foreshadowing", type=str, nargs="*", help="新增伏笔")
    parser.add_argument("--resolve-foreshadowing", type=str, nargs="*", help="已回收伏笔（模糊匹配）")
    parser.add_argument("--events", type=str, nargs="*", help="新增事件。格式：'描述' 或 '描述|故事时间'")
    parser.add_argument("--characters", type=str, nargs="*", help="出场角色名")
    parser.add_argument("--actual-summary", type=str, default=None, help="章节摘要")
    parser.add_argument("--summary-file", type=str, default=None, help="从文件读取摘要")
    parser.add_argument("--rebuild-stats", action="store_true",
                        help="重建角色统计（从实体文件同步，替代增量更新）")
    parser.add_argument("--rebuild-foreshadowing", action="store_true",
                        help="重建伏笔（从分纲+章节元数据）")
    parser.add_argument("--rebuild-timeline", action="store_true",
                        help="重建时间线（从分纲+章节元数据）")
    parser.add_argument("--rebuild-plot-progress", action="store_true",
                        help="重建情节线进度（从分纲角色匹配）")
    parser.add_argument("--rebuild-worldbuilding", action="store_true",
                        help="重建世界构建章节映射（从分纲+project_index）")
    parser.add_argument("--rebuild-summaries", action="store_true",
                        help="重建章节摘要（从章节元数据）")
    parser.add_argument("--rebuild-all", action="store_true",
                        help="重建所有追踪文件")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="重建项目索引 project_index.yaml（从实体 YAML 全量扫描）")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="仅预览，不写入文件（仅重建模式）")
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
        plot_result = update_plot_threads(cp, char_list)
        wb_result = update_worldbuilding_usage(cp)

        print(f"已更新元数据: {cp.name}")
        print("  - 伏笔.yaml ✓")
        print("  - 时间线.yaml ✓")
        print("  - 角色统计.yaml ✓")
        if plot_result["updated"] > 0:
            print(f"  - 情节线进度 ✓ ({plot_result['updated']} 条)")
            for detail in plot_result["details"]:
                print(f"    {detail}")
        if wb_result["updated"] > 0:
            print(f"  - 世界构建章节映射 ✓ ({wb_result['updated']} 个实体)")

        # 重建角色统计（从实体文件同步）
        if args.rebuild_stats and rebuild_character_stats is not None:
            try:
                rebuild_character_stats(find_project_root(cp))
                print("  - 角色统计.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 角色统计重建失败: {e}")

        summary = args.actual_summary
        if not summary and args.summary_file:
            sf = Path(args.summary_file)
            if sf.is_file():
                summary = sf.read_text(encoding="utf-8").strip()
        if not summary:
            summary = markers.get("actual_summary")
        if summary:
            update_chapter_summary(find_project_root(cp), cp, summary)
            print("  - 章节摘要 ✓")

    # 处理重建参数
    if args.rebuild_all or args.rebuild_worldbuilding:
        if rebuild_worldbuilding_mapping is not None:
            try:
                rebuild_worldbuilding_mapping(project_root, dry_run=args.dry_run)
                print("  - 世界构建章节映射.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 世界构建映射重建失败: {e}")
        else:
            print("  [跳过] rebuild_worldbuilding_mapping.py 未找到")

    if args.rebuild_all or args.rebuild_foreshadowing:
        if rebuild_foreshadowing is not None:
            try:
                rebuild_foreshadowing(project_root, dry_run=args.dry_run)
                print("  - 伏笔.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 伏笔重建失败: {e}")
        else:
            print("  [跳过] rebuild_foreshadowing.py 未找到")

    if args.rebuild_all or args.rebuild_timeline:
        if rebuild_timeline is not None:
            try:
                rebuild_timeline(project_root, dry_run=args.dry_run)
                print("  - 时间线.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 时间线重建失败: {e}")
        else:
            print("  [跳过] rebuild_timeline.py 未找到")

    if args.rebuild_all or args.rebuild_plot_progress:
        if rebuild_plot_progress is not None:
            try:
                rebuild_plot_progress(project_root, dry_run=args.dry_run)
                print("  - 情节线进度.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 情节线进度重建失败: {e}")
        else:
            print("  [跳过] rebuild_plot_progress.py 未找到")

    if args.rebuild_all or args.rebuild_summaries:
        if rebuild_chapter_summaries is not None:
            try:
                rebuild_chapter_summaries(project_root, dry_run=args.dry_run)
                print("  - 章节摘要.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 章节摘要重建失败: {e}")
        else:
            print("  [跳过] rebuild_chapter_summaries.py 未找到")

    if args.rebuild_index or args.rebuild_all:
        if rebuild_index is not None:
            try:
                rebuild_index(project_root, dry_run=args.dry_run)
                print("  - project_index.yaml (rebuild) ✓")
            except (OSError, RuntimeError) as e:
                print(f"  [跳过] 项目索引重建失败: {e}")
        else:
            print("  [跳过] rebuild_project_index.py 未找到")


if __name__ == "__main__":
    main()
