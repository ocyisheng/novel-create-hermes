#!/usr/bin/env python3
"""
rebuild_plot_progress.py — 从情节线文件重建进度。

用法：
    python rebuild_plot_progress.py --project-root NOVELS_ROOT/项目名
    python rebuild_plot_progress.py --project-root NOVELS_ROOT/项目名 --dry-run

数据源：outline/情节线/*.yaml（主线+支线）
输出：  outline/追踪/情节线进度.yaml

格式（扁平列表）：
    进度:
      - 情节线: "main_plot"
        章节: 1
        时间: "2024-01-01T00:00:00"
"""

import argparse
import sys
from datetime import datetime
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


def rebuild_plot_progress(project_root: Path, dry_run: bool = False) -> dict:
    """从情节线文件重建进度。

    Returns:
        生成的完整数据结构
    """
    project_root = project_root.resolve()
    plot_dir = project_root / "outline" / "情节线"
    progress_path = project_root / "outline" / "追踪" / "情节线进度.yaml"

    if not plot_dir.is_dir():
        print(f"⚠️  情节线目录不存在: {plot_dir}")
        return {}

    # 1. 扫描所有情节线文件
    records = []
    now = datetime.now().isoformat()

    for plot_file in sorted(plot_dir.glob("*.yaml")):
        if plot_file.name == "主索引.yaml":
            continue

        data = load_yaml(plot_file)
        if not data:
            continue

        entity_id = data.get("索引信息", {}).get("实体ID", plot_file.stem)
        plot_name = data.get("索引信息", {}).get("名称", plot_file.stem)

        # 从情节线的伏笔清单中提取已埋设的伏笔
        full_archive = data.get("完整档案", {})
        foreshadowing = full_archive.get("伏笔清单", {})

        # 计划伏笔 → 已埋设
        planned = foreshadowing.get("计划伏笔", [])
        if isinstance(planned, list):
            for item in planned:
                if isinstance(item, dict):
                    f_num = item.get("编号", "")
                    f_desc = item.get("描述", "")
                    if f_num or f_desc:
                        records.append({
                            "情节线": entity_id,
                            "伏笔编号": f_num,
                            "描述": f_desc,
                            "状态": "已埋设",
                            "时间": now,
                        })

        # 计划回收 → 待回收
        to_resolve = foreshadowing.get("计划回收", [])
        if isinstance(to_resolve, list):
            for item in to_resolve:
                if isinstance(item, dict):
                    f_num = item.get("编号", "")
                    f_desc = item.get("描述", "")
                    if f_num or f_desc:
                        records.append({
                            "情节线": entity_id,
                            "伏笔编号": f_num,
                            "描述": f_desc,
                            "状态": "待回收",
                            "时间": now,
                        })

    if not records:
        print("⚠️  未找到任何情节线进度记录")
        return {}

    # 2. 按情节线排序
    records.sort(key=lambda r: (r.get("情节线", ""), r.get("伏笔编号", "")))

    # 3. 构建输出
    output = {"进度": records}

    # 4. 统计信息
    unique_plots = set(r.get("情节线", "") for r in records)
    pending = sum(1 for r in records if r.get("状态") == "待回收")
    buried = sum(1 for r in records if r.get("状态") == "已埋设")

    # 5. 写入文件
    if dry_run:
        print("=== DRY RUN ===")
        print(f"扫描到 {len(records)} 条记录，涉及 {len(unique_plots)} 条情节线")
        print(f"  已埋设: {buried}, 待回收: {pending}")
        for record in records[:10]:
            print(f"  {record.get('情节线', '?')}: {record.get('伏笔编号', '?')} - {record.get('描述', '?')[:30]}")
        if len(records) > 10:
            print(f"  ... 还有 {len(records) - 10} 条")
        return output

    save_yaml(progress_path, output)
    print(f"📝 情节线进度重建完成: {len(records)} 条记录，涉及 {len(unique_plots)} 条情节线")
    print(f"   已埋设: {buried}, 待回收: {pending}")
    print(f"   写入: {progress_path}")
    return output


def main():
    parser = argparse.ArgumentParser(
        description="rebuild_plot_progress.py — 从情节线文件重建进度",
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
