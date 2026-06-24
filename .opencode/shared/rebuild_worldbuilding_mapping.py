#!/usr/bin/env python3
"""
rebuild_worldbuilding_mapping.py — 从分纲全量重建世界构建→章节映射。

新建脚本，填补现有追踪体系的一个空白：
分纲模板已有「涉及地点」字段，但无人将其提取为结构化追踪数据。

扫描分纲 + 世界构建文件，输出每章涉及的世界构建实体（力量体系/势力/地点/规则/文化/技术等）。

数据源：outline/分纲/**/*.yaml + worldbuilding/*.yaml + project_index.yaml
输出：  outline/追踪/世界构建章节映射.yaml

格式：
    worldbuilding_usage:
      力量体系_名称:
        chapters: [1, 3, 5]
        first_chapter: 1
        last_chapter: 5
        usage_count: 3
      势力格局_名称:
        chapters: [2, 4, 7, 10]
        first_chapter: 2
        last_chapter: 10
        usage_count: 4

用法：
    python rebuild_worldbuilding_mapping.py --project-root NOVELS_ROOT/项目名
    python rebuild_worldbuilding_mapping.py --project-root NOVELS_ROOT/项目名 --dry-run
"""

import argparse
import re
import sys
from collections import defaultdict
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


def load_worldbuilding_index(project_root: Path) -> dict[str, str]:
    """从 project_index.yaml 加载世界构建实体列表。

    Returns:
        {实体名称: 文件名路径}
    """
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    wb = index.get("worldbuilding", {})
    result = {}
    for entity_id, entry in wb.items():
        name = entry.get("name", entity_id)
        file_path = entry.get("file_path", "")
        result[name] = file_path
    return result


def extract_locations_from_fengang(fengang_path: Path) -> list[str]:
    """从分纲文件提取涉及地点。

    检查位置：
      1. 完整档案.涉及地点（主字段）
      2. 完整档案.场域规划[].涉及角色（如果场域名包含地点）
      3. 完整档案.世界观补充[].内容描述（提取地点关键词）
    """
    data = load_yaml(fengang_path)
    if not data:
        return []

    locations = []
    full = data.get("完整档案", {})

    # 1. 涉及地点字段
    locs = full.get("涉及地点", [])
    if isinstance(locs, list):
        for loc in locs:
            if isinstance(loc, str) and loc:
                locations.append(loc)

    # 2. 场域规划中的场域名（可能包含地点信息）
    scene_plan = full.get("场域规划", [])
    if isinstance(scene_plan, list):
        for scene in scene_plan:
            if isinstance(scene, dict):
                # 场域中的环境要素
                atmosphere = scene.get("氛围", {})
                env_elements = atmosphere.get("环境要素", [])
                if isinstance(env_elements, list):
                    for elem in env_elements:
                        if isinstance(elem, str) and elem and elem not in locations:
                            locations.append(elem)

    # 3. 世界观补充
    supplements = full.get("世界观补充", [])
    if isinstance(supplements, list):
        for item in supplements:
            if isinstance(item, dict):
                elem_type = item.get("元素类型", "")
                content = item.get("内容描述", "")
                if elem_type in ("地点", "势力", "规则", "文化", "技术") and content:
                    locations.append(content)

    return locations


def extract_worldbuilding_entities_from_outline(
    fengang_path: Path,
    wb_index: dict[str, str],
) -> list[str]:
    """从分纲中匹配世界构建实体。

    匹配规则：
      1. 涉及地点 字段中的文本与 wb_index 中的实体名称做部分匹配
      2. 世界观补充 字段中的元素类型+内容做匹配

    Returns:
        匹配到的世界构建实体ID列表（如 "力量体系_灵气"）
    """
    data = load_yaml(fengang_path)
    if not data:
        return []

    matched = []
    full = data.get("完整档案", {})

    # 收集分纲中的所有文本线索
    search_texts = []

    locs = full.get("涉及地点", [])
    if isinstance(locs, list):
        search_texts.extend([str(l) for l in locs if l])

    supplements = full.get("世界观补充", [])
    if isinstance(supplements, list):
        for item in supplements:
            if isinstance(item, dict):
                content = item.get("内容描述", "")
                if content:
                    search_texts.append(content)

    scene_plan = full.get("场域规划", [])
    if isinstance(scene_plan, list):
        for scene in scene_plan:
            if isinstance(scene, dict):
                scene_name = scene.get("场域名", "")
                if scene_name:
                    search_texts.append(scene_name)
                atmosphere = scene.get("氛围", {})
                env_elems = atmosphere.get("环境要素", [])
                if isinstance(env_elems, list):
                    search_texts.extend([str(e) for e in env_elems if e])

    # 对每个世界构建实体，检查分纲文本是否提及
    for wb_name in wb_index:
        for text in search_texts:
            # 部分匹配：实体名称中的关键词出现在分纲文本中
            wb_keywords = re.split(r"[\s_\-]", wb_name)
            wb_keywords = [w for w in wb_keywords if len(w) >= 2]
            if not wb_keywords:
                continue

            match_count = sum(1 for kw in wb_keywords if kw in text)
            # 至少匹配 50% 的关键词
            if match_count >= max(1, len(wb_keywords) // 2):
                if wb_name not in matched:
                    matched.append(wb_name)
                break

    return matched


def rebuild_worldbuilding_mapping(project_root: Path, dry_run: bool = False) -> dict:
    """从分纲全量重建世界构建→章节映射。

    Returns:
        生成的完整数据结构
    """
    project_root = project_root.resolve()
    fengang_dir = project_root / "outline" / "分纲"
    output_path = project_root / "outline" / "追踪" / "世界构建章节映射.yaml"

    if not fengang_dir.is_dir():
        print(f"⚠️  分纲目录不存在: {fengang_dir}")
        return {}

    # 加载世界构建索引
    wb_index = load_worldbuilding_index(project_root)

    # 实体→章节映射
    entity_chapters = defaultdict(set)  # entity_name → {chapter_num}

    # 扫描分纲
    for fengang_file in sorted(fengang_dir.rglob("*.yaml")):
        chapter_num = extract_chapter_number(fengang_file.name)
        if chapter_num == 0:
            continue

        # 方法1：通过 keyword 匹配世界构建实体
        if wb_index:
            entities = extract_worldbuilding_entities_from_outline(fengang_file, wb_index)
            for entity in entities:
                entity_chapters[entity].add(chapter_num)

        # 方法2：直接读取涉及地点（即使没有索引也记录）
        locs = extract_locations_from_fengang(fengang_file)
        for loc in locs:
            key = f"地点_{loc}"
            entity_chapters[key].add(chapter_num)

    if not entity_chapters:
        print("⚠️  未找到任何世界构建→章节映射")
        return {}

    # 构建输出
    usage = {}
    for entity_name, chapters_set in sorted(entity_chapters.items()):
        chapters = sorted(chapters_set)
        usage[entity_name] = {
            "chapters": chapters,
            "first_chapter": chapters[0],
            "last_chapter": chapters[-1],
            "usage_count": len(chapters),
        }

    output = {"worldbuilding_usage": usage}

    # 统计
    total_entities = len(usage)
    total_chapters = len(set(
        c for v in usage.values() for c in v["chapters"]
    ))

    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {total_entities} 个世界构建实体，涉及 {total_chapters} 章")
        for entity_name, info in list(usage.items())[:15]:
            print(f"  {entity_name}: 出场 {info['usage_count']} 次，章节 {info['chapters']}")
        if len(usage) > 15:
            print(f"  ... 还有 {len(usage) - 15} 个实体")
        return output

    save_yaml(output_path, output)
    print(f"📝 世界构建章节映射重建完成: {total_entities} 个实体，{total_chapters} 章")
    print(f"   写入: {output_path}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_worldbuilding_mapping.py — 从分纲重建世界构建→章节映射",
    )
    parser.add_argument("--project-root", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    rebuild_worldbuilding_mapping(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
