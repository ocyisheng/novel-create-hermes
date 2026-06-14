#!/usr/bin/env python3
"""
rebuild_chapter_summaries.py — 从章节元数据重建摘要。

用法：
    python rebuild_chapter_summaries.py --project-root NOVELS_ROOT/项目名
    python rebuild_chapter_summaries.py --project-root NOVELS_ROOT/项目名 --dry-run

数据源：chapters/.metas/*.txt（章节元数据中的 actual_summary 标记）
输出：  outline/追踪/章节摘要.yaml

格式（扁平列表）：
    摘要:
      - 章节: 1
        摘要: "本章讲述了..."
"""

import argparse
import re
import sys
from pathlib import Path

try:
    from _utils import load_yaml, save_yaml
except ImportError:
    import importlib.util
    _utils_path = Path(__file__).parent / "_utils.py"
    spec = importlib.util.spec_from_file_location("_utils", _utils_path)
    _utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_utils)
    load_yaml = _utils.load_yaml
    save_yaml = _utils.save_yaml


def _extract_chapter_number(filename: str) -> int:
    """从文件名提取章节号。"""
    match = re.search(r"第(\d+)章", filename)
    if match:
        return int(match.group(1))
    return 0


def _extract_summary_from_meta(meta_path: Path) -> str:
    """从章节元数据中提取摘要。"""
    if not meta_path.is_file():
        return ""

    try:
        content = meta_path.read_text(encoding="utf-8")
    except Exception:
        return ""

    # 尝试从 YAML 格式提取
    data = load_yaml(meta_path)
    if data and isinstance(data, dict):
        summary = data.get("actual_summary", "")
        if summary:
            return summary.strip()

    # 尝试从文本格式提取
    match = re.search(r"【本章摘要】\s*\n(.*?)(?=\n【|$)", content, re.DOTALL)
    if match:
        return match.group(1).strip().replace("\n", " ")[:200]

    return ""


def rebuild_chapter_summaries(project_root: Path, dry_run: bool = False) -> dict:
    """从章节元数据重建摘要。

    Returns:
        生成的完整数据结构
    """
    project_root = project_root.resolve()
    meta_dir = project_root / "chapters" / ".metas"
    summary_path = project_root / "outline" / "追踪" / "章节摘要.yaml"

    if not meta_dir.is_dir():
        print(f"⚠️  章节元数据目录不存在: {meta_dir}")
        return {}

    # 1. 扫描所有章节元数据
    records = []
    for meta_file in sorted(meta_dir.glob("*.txt")):
        chapter_num = _extract_chapter_number(meta_file.name)
        if chapter_num == 0:
            continue

        summary = _extract_summary_from_meta(meta_file)
        if summary:
            records.append({
                "章节": chapter_num,
                "摘要": summary,
            })

    if not records:
        print("⚠️  未找到任何章节摘要")
        return {}

    # 2. 按章节排序
    records.sort(key=lambda r: r.get("章节", 0))

    # 3. 构建输出
    output = {"摘要": records}

    # 4. 统计信息
    max_chapter = max(r.get("章节", 0) for r in records) if records else 0
    avg_length = sum(len(r.get("摘要", "")) for r in records) / len(records) if records else 0

    # 5. 写入文件
    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {len(records)} 条摘要，最高章节: {max_chapter}")
        print(f"  平均长度: {avg_length:.0f} 字符")
        for record in records[:5]:
            print(f"  第{record.get('章节', '?')}章: {record.get('摘要', '?')[:50]}...")
        if len(records) > 5:
            print(f"  ... 还有 {len(records) - 5} 条")
        return output

    save_yaml(summary_path, output)
    print(f"📝 章节摘要重建完成: {len(records)} 条摘要")
    print(f"   平均长度: {avg_length:.0f} 字符")
    print(f"   写入: {summary_path}")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_chapter_summaries.py — 从章节元数据重建摘要",
    )
    parser.add_argument("--project-root", required=True, help="项目根目录路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    rebuild_chapter_summaries(project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
