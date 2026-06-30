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
    from _utils import load_yaml, save_yaml, extract_chapter_number, get_nested
except ImportError:
    import importlib.util
    _utils_path = Path(__file__).parent / "_utils.py"
    spec = importlib.util.spec_from_file_location("_utils", _utils_path)
    _utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_utils)
    load_yaml = _utils.load_yaml
    save_yaml = _utils.save_yaml
    extract_chapter_number = _utils.extract_chapter_number
    get_nested = _utils.get_nested


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


# ── 对比预期 vs 实际 ─────────────────────────────────────────────────────────

def _load_plot_thread_rhythms(project_root: Path) -> list[dict]:
    """从所有情节线文件加载 角色参与.出场节奏。"""
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    if not index:
        return []

    plot_threads = index.get("plot_threads", {})
    rhythms = []

    for entry in plot_threads.values():
        fp = entry.get("file_path") if isinstance(entry, dict) else None
        if not fp:
            continue
        thread_path = project_root / fp
        if not thread_path.is_file():
            continue
        data = load_yaml(thread_path)
        if not data:
            continue
        r = get_nested(data, "完整档案.角色参与.出场节奏")
        if r:
            rhythms.extend(r)

    return rhythms


def compare_appearance_plan(project_root: Path, stats: dict) -> list[dict]:
    """对比角色出场规划（情节线.出场节奏）与实际出场数据。

    stats: rebuild_character_stats 生成的聚合数据（角色→章节列表）

    Returns:
        偏差列表，每项含 type / char / msg
    """
    rhythms = _load_plot_thread_rhythms(project_root)
    if not rhythms:
        return []

    aggregation = stats.get("角色登场聚合", {}) if "角色登场聚合" in stats else stats
    # 支持直接传聚合 dict 或原始输出
    if not aggregation:
        return []

    deviations = []
    actual_chapters = {}  # char_name → set of chapters
    for char_name, info in aggregation.items():
        if isinstance(info, dict):
            chs = info.get("chapters", [])
            actual_chapters[char_name] = set(chs)

    for rhythm in rhythms:
        char_name = rhythm.get("角色", "")
        if not char_name:
            continue

        first = rhythm.get("首次出场", 0) or 0
        key_chapters = rhythm.get("关键章节", []) or []
        blackout = rhythm.get("不活跃区间", []) or []
        density = rhythm.get("出场密度", "正常")

        actual = actual_chapters.get(char_name, set())
        max_written = max(actual) if actual else 0

        # 1. 关键章节缺失
        for kc in key_chapters:
            if kc not in actual:
                deviations.append({
                    "type": "missing_key_chapter",
                    "char": char_name,
                    "msg": f"关键章节第{kc}章未出场" + (f"（已写至第{max_written}章）" if max_written >= kc else ""),
                })

        # 2. 不活跃区间违规
        for interval in blackout:
            if isinstance(interval, str) and "-" in interval:
                parts = interval.split("-")
                if len(parts) == 2:
                    try:
                        start, end = int(parts[0]), int(parts[1])
                        violations = [c for c in actual if start <= c <= end]
                        for v in violations:
                            deviations.append({
                                "type": "blackout_violation",
                                "char": char_name,
                                "msg": f"不应在第{v}章出场（规划不活跃区间 {interval}）",
                            })
                    except ValueError:
                        pass

        # 3. 首次出场前提前出现
        if first and actual:
            earliest = min(actual)
            if earliest < first:
                deviations.append({
                    "type": "early_bird",
                    "char": char_name,
                    "msg": f"首次出场章节{earliest}早于规划第{first}章",
                })

        # 4. 出场密度异常（可选预警）
        if density == "密集" and actual:
            max_gap = 0
            sorted_chs = sorted(actual)
            for i in range(1, len(sorted_chs)):
                gap = sorted_chs[i] - sorted_chs[i - 1]
                if gap > max_gap:
                    max_gap = gap
            if max_gap > 15:
                deviations.append({
                    "type": "density_warning",
                    "char": char_name,
                    "msg": f"出场密度异常（密集），最长间隔{max_gap}章",
                })
        elif density == "稀疏" and actual:
            total = len(actual)
            avg_gap = max_written / total if total > 0 else 0
            if avg_gap < 3:
                deviations.append({
                    "type": "density_warning",
                    "char": char_name,
                    "msg": f"出场密度异常（稀疏），共{total}次平均每{avg_gap:.0f}章出场",
                })

    return deviations


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_character_stats.py — 从章节元数据重建角色出场统计",
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", "-n", action="store_true", help="仅预览，不写入文件")
    parser.add_argument("--compare", "-c", action="store_true", help="对比出场规划 vs 实际偏差")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    stats = rebuild_character_stats(project_root, dry_run=args.dry_run)

    if args.compare and stats:
        agg = {}
        # 加载聚合数据（如果 rebuild 没有写入，尝试读已有文件）
        agg_path = project_root / "outline" / "追踪" / "角色登场聚合.yaml"
        if agg_path.is_file():
            agg_data = load_yaml(agg_path)
            if agg_data:
                agg = agg_data.get("角色登场聚合", {})
        if not agg:
            # fallback: 从 stats 自己算
            agg = {}
            for char_name in set(r["角色"] for r in stats.get("出场", [])):
                chapters = sorted(set(
                    r["章节"] for r in stats["出场"] if r["角色"] == char_name
                ))
                agg[char_name] = {"chapters": chapters, "total": len(chapters)}

        deviations = compare_appearance_plan(project_root, agg)
        if deviations:
            print(f"\n⚠️  出场偏差报告（共 {len(deviations)} 项）")
            print("-" * 40)
            for d in deviations:
                tag = {"missing_key_chapter": "缺失", "blackout_violation": "违规",
                       "early_bird": "提前", "density_warning": "密度"}[d["type"]]
                print(f"  [{tag}] {d['char']}: {d['msg']}")
        else:
            print("\n✅ 出场规划与实际一致，无偏差")


if __name__ == "__main__":
    main()
