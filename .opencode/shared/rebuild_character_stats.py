#!/usr/bin/env python3
"""
rebuild_character_stats.py — 从章节元数据重建角色出场统计。

全量重建模式，对应的增量更新函数在 _tracking.py（update_character_stats）。

用法：
    python rebuild_character_stats.py --project-root NOVELS_ROOT/项目名
    python rebuild_character_stats.py --project-root NOVELS_ROOT/项目名 --dry-run

数据源：chapters/.metas/*.txt（章节元数据中的 characters 标记）
输出：  outline/追踪/角色统计.yaml

格式（扁平列表）：
    出场:
      - 角色: "张小凡"
        章节: 1
        状态: "重伤"
      - 角色: "林雨薇"
        章节: 1
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


def _extract_characters_from_meta(meta_path: Path) -> list[dict]:
    """从章节元数据中提取出场角色列表（包含状态信息）。"""
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
        chars = data.get("characters", [])
        if isinstance(chars, list):
            # 支持简单列表或带状态的列表
            for item in chars:
                if isinstance(item, str):
                    result.append({"角色": item})
                elif isinstance(item, dict):
                    result.append(item)
            return result

    # 尝试从文本格式提取：characters: [角色1, 角色2]
    match = re.search(r"characters:\s*\[(.*?)\]", content)
    if match:
        chars_str = match.group(1)
        for c in chars_str.split(","):
            c = c.strip().strip('"').strip("'")
            if c:
                result.append({"角色": c})
        return result

    return []


def rebuild_character_stats(project_root: Path, dry_run: bool = False) -> dict:
    """从章节元数据重建角色出场统计。

    Returns:
        生成的完整数据结构
    """
    project_root = project_root.resolve()
    chapters_dir = project_root / "chapters"
    meta_dir = chapters_dir / ".metas"
    stats_path = project_root / "outline" / "追踪" / "角色统计.yaml"

    if not meta_dir.is_dir():
        print(f"❌ 章节元数据目录不存在: {meta_dir}", file=sys.stderr)
        return {}

    # 1. 扫描所有章节元数据
    records = []
    for meta_file in sorted(meta_dir.glob("*.txt")):
        chapter_num = extract_chapter_number(meta_file.name)
        if chapter_num == 0:
            continue

        characters = _extract_characters_from_meta(meta_file)
        for char_info in characters:
            record = {
                "角色": char_info.get("角色", ""),
                "章节": chapter_num,
            }
            # 添加状态字段（如果有）
            if "状态" in char_info:
                record["状态"] = char_info["状态"]
            records.append(record)

    if not records:
        print("⚠️  未找到任何角色出场记录")
        return {}

    # 2. 按章节排序
    records.sort(key=lambda r: (r["章节"], r["角色"]))

    # 3. 构建输出
    output = {"出场": records}

    # 4. 统计信息
    unique_chars = set(r["角色"] for r in records)
    max_chapter = max(r["章节"] for r in records) if records else 0

    # 5. 构建聚合数据（角色→章节列表字典）
    aggregation = {}
    for char_name in sorted(unique_chars):
        char_records = [r for r in records if r["角色"] == char_name]
        chapters = sorted(set(r["章节"] for r in char_records))
        # 获取最新状态（最后出场时的状态）
        latest_status = None
        for r in reversed(char_records):
            if "状态" in r:
                latest_status = r["状态"]
                break
        entry = {
            "chapters": chapters,
            "total": len(chapters),
        }
        if latest_status:
            entry["status"] = latest_status
        aggregation[char_name] = entry

    # 6. 写入主文件
    agg_path = project_root / "outline" / "追踪" / "角色登场聚合.yaml"
    agg_output = {"角色登场聚合": aggregation}

    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {len(records)} 条记录，涉及 {len(unique_chars)} 个角色，最高章节: {max_chapter}")
        for char in sorted(unique_chars):
            chap_list = aggregation[char]["chapters"]
            print(f"  {char}: 出场 {len(chap_list)} 次，章节 {chap_list}")
        return output

    save_yaml(stats_path, output)
    print(f"📝 角色统计重建完成: {len(records)} 条记录，{len(unique_chars)} 个角色")
    print(f"   写入: {stats_path}")

    save_yaml(agg_path, agg_output)
    print(f"📝 角色登场聚合重建完成: {len(aggregation)} 个角色")
    print(f"   写入: {agg_path}")

    for char in sorted(unique_chars):
        chap_list = aggregation[char]["chapters"]
        print(f"  {char}: 出场 {len(chap_list)} 次，章节 {chap_list}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_character_stats.py — 从章节元数据重建角色出场统计",
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", "-n", action="store_true", help="仅预览，不写入文件")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    rebuild_character_stats(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
