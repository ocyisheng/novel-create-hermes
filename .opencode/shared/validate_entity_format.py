#!/usr/bin/env python3
"""
validate_entity_format.py — 实体 YAML 格式校验

扫描项目下所有实体文件，对照 rebuild_project_index.py 中定义的 ENTITY_SCAN_CONFIG
检查必填字段是否存在。不匹配的文件输出详细报告。

用法:
    python validate_entity_format.py --project-root NOVELS_ROOT/项目名
    python validate_entity_format.py --project-root NOVELS_ROOT/项目名 --verbose
    python validate_entity_format.py --project-root NOVELS_ROOT/项目名 --fix-warnings

输出:
    YAML 格式报告到 stdout
    退出码: 0=全部通过, 1=有格式问题

与后处理链集成:
    fix_yaml_indent.py → validate_entity_format.py → rebuild_project_index.py
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)

# 从重建索引脚本导入配置（单一事实源）
sys.path.insert(0, str(Path(__file__).parent))
from rebuild_project_index import ENTITY_SCAN_CONFIG, _get_nested, _load_yaml_safe


def validate_entity_format(project_root: Path, verbose: bool = False) -> dict:
    """扫描项目下所有实体 YAML，校验格式是否符合规范。

    Returns:
        dict: {
            "status": "passed" | "failed",
            "summary": {"checked": N, "passed": N, "failed": N, "warnings": N},
            "results": [
                {"file": "...", "section": "...", "status": "passed"|"failed",
                 "issues": ["..."]}
            ]
        }
    """
    results = []
    total_checked = 0
    total_passed = 0
    total_failed = 0
    total_warnings = 0

    for section_name, config in ENTITY_SCAN_CONFIG.items():
        scan_dir = project_root / config["dir"]
        if not scan_dir.is_dir():
            if verbose:
                results.append({
                    "section": section_name,
                    "status": "skipped",
                    "message": f"目录不存在: {config['dir']}",
                })
            continue

        for fpath in sorted(scan_dir.rglob(config["glob"])):
            if fpath.name in config.get("skip", []):
                continue

            total_checked += 1
            issues = []
            warnings = []

            data = _load_yaml_safe(fpath)
            if data is None:
                issues.append("YAML 解析失败：文件无法读取或格式错误")
                results.append({
                    "file": str(fpath.relative_to(project_root)),
                    "section": section_name,
                    "status": "failed",
                    "issues": issues,
                })
                total_failed += 1
                continue

            # 1. 检查 _meta 段（所有索引实体应有）
            meta = data.get("_meta")
            if section_name in ("characters", "worldbuilding", "plot_threads", "chapters"):
                if not isinstance(meta, dict):
                    issues.append("缺少 _meta 段（应为 mapping）")
                else:
                    if not meta.get("entity_type"):
                        warnings.append("_meta.entity_type 为空或缺失（建议填写）")
                    if not meta.get("schema_version"):
                        warnings.append("_meta.schema_version 为空或缺失（建议填写）")

            # 2. 检查 id_path 指定的必填字段
            id_path = config["id_path"]
            id_val = _get_nested(data, id_path)
            if not id_val:
                issues.append(f"缺少必填字段: {id_path}（当前值为空，该字段作为实体唯一标识）")

            # 3. 检查 fields 中定义的所有字段
            for field_key, dot_path in config["fields"].items():
                val = _get_nested(data, dot_path)
                if not val:
                    issues.append(f"缺少必填字段: {dot_path}（字段用途: {field_key}）")

            # 4. 可选检查: extra 字段（非必填，仅 warning）
            for field_key, dot_path in config.get("extra", {}).items():
                val = _get_nested(data, dot_path)
                if val is None:
                    warnings.append(f"可选字段缺失: {dot_path}（字段: {field_key}）")

            if issues:
                results.append({
                    "file": str(fpath.relative_to(project_root)),
                    "section": section_name,
                    "status": "failed",
                    "issues": issues,
                })
                total_failed += 1
            else:
                record = {
                    "file": str(fpath.relative_to(project_root)),
                    "section": section_name,
                    "status": "passed",
                    "issues": [],
                }
                if warnings:
                    record["warnings"] = warnings
                    total_warnings += len(warnings)
                results.append(record)
                total_passed += 1

    summary = {
        "checked": total_checked,
        "passed": total_passed,
        "failed": total_failed,
        "warnings": total_warnings,
    }

    return {
        "status": "passed" if total_failed == 0 else "failed",
        "summary": summary,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="实体 YAML 格式校验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python validate_entity_format.py --project-root novels/空山闻仙
  python validate_entity_format.py --project-root novels/空山闻仙 --verbose
  python validate_entity_format.py --project-root novels/空山闻仙 --fix-warnings
        """,
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示跳过的目录信息")
    parser.add_argument("--fix-warnings", action="store_true",
                        help="将 warnings 降级为 errors（严格模式）")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    report = validate_entity_format(project_root, verbose=args.verbose)

    # 输出 YAML 报告
    yaml.safe_dump(report, sys.stdout, default_flow_style=False,
                   sort_keys=False, allow_unicode=True)

    # 退出码
    if report["status"] == "failed":
        sys.exit(1)
    if args.fix_warnings and report["summary"]["warnings"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
