#!/usr/bin/env python3
"""
rebuild_foreshadowing.py — 从分纲+章节元数据重建伏笔。

全量重建模式，对应的增量更新函数在 _tracking.py（update_foreshadowing）。

用法：
    python rebuild_foreshadowing.py --project-root NOVELS_ROOT/项目名
    python rebuild_foreshadowing.py --project-root NOVELS_ROOT/项目名 --dry-run

数据源：outline/分纲/*.yaml + chapters/.metas/*.txt
输出：  outline/追踪/伏笔.yaml

格式（扁平列表）：
    伏笔:
      - 编号: "F001"
        描述: "主角身世之谜"
        章节: 1
        状态: "待回收"
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


def _extract_foreshadowing_from_meta(meta_path: Path) -> list[dict]:
    """从章节元数据中提取伏笔列表。"""
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
        # 新伏笔
        new_foreshadowing = data.get("foreshadowing", [])
        if isinstance(new_foreshadowing, list):
            for item in new_foreshadowing:
                if isinstance(item, str):
                    result.append({"描述": item, "状态": "待回收"})
                elif isinstance(item, dict):
                    if "状态" not in item:
                        item["状态"] = "待回收"
                    result.append(item)

        # 回收伏笔
        resolved = data.get("resolve_foreshadowing", [])
        if isinstance(resolved, list):
            for item in resolved:
                if isinstance(item, str):
                    result.append({"描述": item, "状态": "已回收"})
                elif isinstance(item, dict):
                    item["状态"] = "已回收"
                    result.append(item)

        return result

    # 尝试从文本格式提取
    # 新伏笔
    match = re.search(r"【新伏笔】\s*\n(.*?)(?=\n【|$)", content, re.DOTALL)
    if match:
        for line in match.group(1).strip().split("\n"):
            line = line.strip()
            if line:
                result.append({"描述": line, "状态": "待回收"})

    # 回收伏笔
    match = re.search(r"【回收伏笔】\s*\n(.*?)(?=\n【|$)", content, re.DOTALL)
    if match:
        for line in match.group(1).strip().split("\n"):
            line = line.strip()
            if line:
                result.append({"描述": line, "状态": "已回收"})

    return result


def _extract_foreshadowing_from_outline(outline_path: Path) -> list[dict]:
    """从分纲文件中提取伏笔列表。"""
    data = load_yaml(outline_path)
    if not data:
        return []

    result = []

    # 分纲中的伏笔清单
    foreshadowing = data.get("伏笔清单", {})
    if isinstance(foreshadowing, dict):
        # 计划伏笔
        planned = foreshadowing.get("计划伏笔", [])
        if isinstance(planned, list):
            for item in planned:
                if isinstance(item, dict):
                    item.setdefault("状态", "待回收")
                    result.append(item)

        # 计划回收
        to_resolve = foreshadowing.get("计划回收", [])
        if isinstance(to_resolve, list):
            for item in to_resolve:
                if isinstance(item, dict):
                    item.setdefault("状态", "待回收")
                    result.append(item)

    return result


def rebuild_foreshadowing(project_root: Path, dry_run: bool = False) -> dict:
    """从分纲+章节元数据重建伏笔。

    Returns:
        生成的完整数据结构
    """
    project_root = project_root.resolve()
    outline_dir = project_root / "outline"
    fengang_dir = outline_dir / "分纲"
    meta_dir = project_root / "chapters" / ".metas"
    foreshadowing_path = outline_dir / "追踪" / "伏笔.yaml"

    # 1. 扫描分纲文件
    records = []
    if fengang_dir.is_dir():
        for f in sorted(fengang_dir.glob("*.yaml")):
            chapter_num = extract_chapter_number(f.name)
            if chapter_num == 0:
                continue

            items = _extract_foreshadowing_from_outline(f)
            for item in items:
                item["章节"] = chapter_num
                records.append(item)

    # 2. 扫描章节元数据（覆盖分纲中的数据）
    if meta_dir.is_dir():
        for meta_file in sorted(meta_dir.glob("*.txt")):
            chapter_num = extract_chapter_number(meta_file.name)
            if chapter_num == 0:
                continue

            items = _extract_foreshadowing_from_meta(meta_file)
            for item in items:
                item["章节"] = chapter_num
                records.append(item)

    if not records:
        print("⚠️  未找到任何伏笔记录")
        return {}

    # 3. 去重（按描述去重，保留最新的）
    seen = {}
    for record in records:
        desc = record.get("描述", "")
        if desc:
            seen[desc] = record
    records = list(seen.values())

    # 4. 按章节排序
    records.sort(key=lambda r: (r.get("章节", 0), r.get("描述", "")))

    # 5. 构建输出
    output = {"伏笔": records, "版本": "1.0"}

    # 6. 统计信息
    unique_descs = set(r.get("描述", "") for r in records)
    max_chapter = max(r.get("章节", 0) for r in records) if records else 0
    pending = sum(1 for r in records if r.get("状态") == "待回收")
    resolved = sum(1 for r in records if r.get("状态") == "已回收")

    # 7. 构建伏笔回收完整性报告
    overdues = []
    by_chapter = defaultdict(lambda: {"设": 0, "回收": 0})
    for record in records:
        chapter = record.get("章节", 0)
        status = record.get("状态", "")
        if status == "待回收":
            by_chapter[chapter]["设"] += 1
        elif status == "已回收":
            by_chapter[chapter]["回收"] += 1

    # 检测逾期伏笔（有预期回收章节，但当前进度超过该章节）
    for record in records:
        expected_chapter = record.get("预期回收章节", 0)
        if expected_chapter and expected_chapter < max_chapter:
            if record.get("状态") == "待回收":
                overdues.append({
                    "编号": record.get("编号", ""),
                    "名称": record.get("描述", "")[:30],
                    "计划回收章节": expected_chapter,
                    "当前章节": max_chapter,
                    "状态": "逾期",
                })

    quality_report = {
        "统计": {
            "总伏笔数": len(records),
            "已设置": len(records) - resolved,
            "已回收": resolved,
            "待回收": pending,
            "逾期未回收": len(overdues),
        },
        "逾期伏笔": overdues,
        "按章节统计": {
            f"第{k}章": v for k, v in sorted(by_chapter.items())
        },
    }

    quality_path = project_root / "quality" / "伏笔回收完整性.yaml"

    # 8. 写入文件
    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {len(records)} 条记录，{len(unique_descs)} 个唯一伏笔，最高章节: {max_chapter}")
        print(f"  待回收: {pending}, 已回收: {resolved}, 逾期: {len(overdues)}")
        for record in records[:10]:
            print(f"  第{record.get('章节', '?')}章: {record.get('描述', '?')[:30]}...")
        if len(records) > 10:
            print(f"  ... 还有 {len(records) - 10} 条")
        if overdues:
            print(f"\n⚠️  逾期伏笔 {len(overdues)} 个:")
            for od in overdues[:5]:
                print(f"  {od['编号']}: 计划第{od['计划回收章节']}章, 当前第{od['当前章节']}章")
        return output

    save_yaml(foreshadowing_path, output)
    print(f"📝 伏笔重建完成: {len(records)} 条记录，{len(unique_descs)} 个唯一伏笔")
    print(f"   待回收: {pending}, 已回收: {resolved}, 逾期: {len(overdues)}")

    save_yaml(quality_path, quality_report)
    print(f"📝 伏笔回收完整性报告: {quality_path}")
    print(f"   总伏笔: {len(records)}, 已回收: {resolved}, 逾期未回收: {len(overdues)}")

    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_foreshadowing.py — 从分纲+章节元数据重建伏笔",
    )
    parser.add_argument("--project-root", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    rebuild_foreshadowing(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
