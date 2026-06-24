#!/usr/bin/env python3
"""
rebuild_plot_progress.py — 从分纲+情节线文件重建情节线进度（全量重建）。

全量重建模式，对应的增量更新函数在 _tracking.py（update_plot_threads）。

修复说明 (2026-06-23):
  旧版从情节线的「伏笔清单」读取规划数据，输出 {情节线, 伏笔编号, 状态}，
  与 update_plot_threads() 的增量产出 {情节线, 章节, 时间} 格式不一致。
  新版改为与增量函数一致的逻辑：
    数据源：outline/分纲/**/第{N}章.yaml + outline/情节线/*.yaml
    逻辑：扫描每章出场角色 → 与每条情节线的涉及角色做交集判断
    若分纲有关联情节线字段 → 优先使用（精确匹配）
    若无 → fallback 到角色交集匹配（与增量更新一致）
  输出：{情节线, 章节, 时间}（扁平列表，格式与 update_plot_threads 相同）
  新增输出：outline/追踪/情节线活跃章节聚合.yaml（实体→章节列表字典）

用法：
    python rebuild_plot_progress.py --project-root NOVELS_ROOT/项目名
    python rebuild_plot_progress.py --project-root NOVELS_ROOT/项目名 --dry-run

数据源：outline/分纲/**/*.yaml + outline/情节线/*.yaml
输出：  outline/追踪/情节线进度.yaml
        outline/追踪/情节线活跃章节聚合.yaml
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
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


def _extract_characters_from_fengang(fengang_path: Path) -> list[str]:
    """从分纲文件提取出场角色名列表。"""
    data = load_yaml(fengang_path)
    if not data:
        return []

    chars = []

    # 先尝试 完整档案.出场角色
    full = data.get("完整档案", {})
    role_list = full.get("出场角色", [])
    if isinstance(role_list, list):
        for item in role_list:
            if isinstance(item, dict):
                name = item.get("角色名", "")
                if name:
                    chars.append(name)
            elif isinstance(item, str):
                chars.append(item)

    # 也检查 摘要.出场角色
    summary = data.get("摘要", {})
    summary_chars = summary.get("出场角色", [])
    if isinstance(summary_chars, list):
        for item in summary_chars:
            if isinstance(item, str) and item not in chars:
                chars.append(item)

    return chars


def _get_plot_entity_id(plot_file: Path, data: dict) -> str:
    """从情节线文件中提取实体ID。"""
    return data.get("索引信息", {}).get("实体ID", plot_file.stem)


def _get_plot_involved_characters(data: dict) -> set:
    """提取一条情节线的涉及角色集合。"""
    involved = set()

    full = data.get("完整档案", {})
    role_participation = full.get("角色参与", {})
    char_list = role_participation.get("涉及角色", [])
    if isinstance(char_list, list):
        involved.update(char_list)

    summary = data.get("摘要", {})
    summary_chars = summary.get("关联角色", [])
    if isinstance(summary_chars, list):
        involved.update(summary_chars)

    return involved


def _load_plot_threads(project_root: Path) -> dict:
    """加载所有情节线文件（主线+支线）。

    Returns:
        {entity_id: {"data": dict, "path": Path, "name": str, "characters": set}}
    """
    plot_dir = project_root / "outline" / "情节线"
    threads = {}

    if not plot_dir.is_dir():
        return threads

    for plot_file in sorted(plot_dir.glob("*.yaml")):
        if plot_file.name == "主索引.yaml":
            continue

        data = load_yaml(plot_file)
        if not data:
            continue

        entity_id = _get_plot_entity_id(plot_file, data)
        name = data.get("索引信息", {}).get("名称", plot_file.stem)
        characters = _get_plot_involved_characters(data)

        threads[entity_id] = {
            "data": data,
            "path": plot_file,
            "name": name,
            "characters": characters,
        }

    return threads


def _get_direct_plot_links(fengang_path: Path) -> list[str]:
    """从分纲文件的 关联情节线 字段提取直接引用的情节线ID。"""
    data = load_yaml(fengang_path)
    if not data:
        return []
    full = data.get("完整档案", {})
    links = full.get("关联情节线", [])
    if isinstance(links, list):
        return [l for l in links if l]
    return []


def rebuild_plot_progress(project_root: Path, dry_run: bool = False) -> dict:
    """从分纲+情节线文件重建情节线进度。

    Returns:
        生成的完整数据结构（包含进度+聚合）
    """
    project_root = project_root.resolve()
    fengang_dir = project_root / "outline" / "分纲"
    progress_path = project_root / "outline" / "追踪" / "情节线进度.yaml"
    agg_path = project_root / "outline" / "追踪" / "情节线活跃章节聚合.yaml"

    if not fengang_dir.is_dir():
        print(f"⚠️  分纲目录不存在: {fengang_dir}")
        return {}

    # 1. 加载所有情节线
    threads = _load_plot_threads(project_root)
    if not threads:
        print("⚠️  未找到任何情节线文件")
        return {}

    # 2. 扫描分纲，建立章节→情节线映射
    chapter_plot_map = defaultdict(set)  # chapter_num → {entity_id}
    now = datetime.now().isoformat()
    records = []
    main_entity = None

    # 找出主线实体ID（主线特殊处理：始终关联）
    for eid, info in threads.items():
        if info["path"].name == "主线.yaml":
            main_entity = eid
            break

    for fengang_file in sorted(fengang_dir.rglob("*.yaml")):
        chapter_num = extract_chapter_number(fengang_file.name)
        if chapter_num == 0:
            continue

        # 2a. 优先使用 关联情节线 字段（精确匹配）
        direct_links = _get_direct_plot_links(fengang_file)
        if direct_links:
            for link in direct_links:
                if link in threads:
                    chapter_plot_map[chapter_num].add(link)
            # 即使有 direct_links，主线仍自动关联
            if main_entity:
                chapter_plot_map[chapter_num].add(main_entity)
            continue

        # 2b. 无直接链接 → fallback 到角色匹配
        chapter_chars = set(_extract_characters_from_fengang(fengang_file))

        for eid, info in threads.items():
            # 主线：始终关联
            if eid == main_entity:
                chapter_plot_map[chapter_num].add(eid)
                continue

            # 支线：角色交集判断
            if chapter_chars and info["characters"] and (chapter_chars & info["characters"]):
                chapter_plot_map[chapter_num].add(eid)

    # 3. 生成扁平进度记录
    for chapter_num in sorted(chapter_plot_map.keys()):
        for eid in sorted(chapter_plot_map[chapter_num]):
            records.append({
                "情节线": eid,
                "章节": chapter_num,
                "时间": now,
            })

    if not records:
        print("⚠️  未找到任何情节线进度记录")
        return {}

    # 4. 按情节线+章节排序
    records.sort(key=lambda r: (r.get("情节线", ""), r.get("章节", 0)))

    output = {"进度": records}

    # 5. 构建聚合数据
    aggregation = {}
    for eid, info in threads.items():
        chapters = sorted(
            r["章节"] for r in records if r["情节线"] == eid
        )
        if chapters:
            aggregation[eid] = {
                "chapters": chapters,
                "active_count": len(chapters),
            }

    # 6. 统计
    unique_plots = set(r.get("情节线", "") for r in records)
    total_chapters = len(set(r.get("章节", 0) for r in records))

    # 7. 写入文件
    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {len(records)} 条进度记录，涉及 {len(unique_plots)} 条情节线，{total_chapters} 章")
        for eid in sorted(aggregation.keys()):
            name = threads.get(eid, {}).get("name", eid)
            chap_list = aggregation[eid]["chapters"]
            print(f"  {name} ({eid}): 活跃 {len(chap_list)} 章 → {chap_list}")
        return output

    # 写入进度文件
    save_yaml(progress_path, output)
    print(f"📝 情节线进度重建完成: {len(records)} 条记录，{len(unique_plots)} 条情节线，{total_chapters} 章")
    print(f"   写入: {progress_path}")

    # 写入聚合文件
    agg_output = {"活跃章节聚合": aggregation}
    save_yaml(agg_path, agg_output)
    print(f"📝 情节线活跃章节聚合重建完成: {len(aggregation)} 条情节线")
    print(f"   写入: {agg_path}")

    for eid in sorted(aggregation.keys()):
        name = threads.get(eid, {}).get("name", eid)
        chap_list = aggregation[eid]["chapters"]
        print(f"  {name}: 活跃 {len(chap_list)} 章")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_plot_progress.py — 从分纲+情节线文件重建进度（角色匹配逻辑）",
    )
    parser.add_argument("--project-root", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    rebuild_plot_progress(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
