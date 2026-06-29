#!/usr/bin/env python3
"""
rebuild_project_index.py — 扫描 filesystem 重建 project_index.yaml

幂等脚本，可从零扫描项目目录下的实体文件重建索引。
支持 CLI 调用和 Python 导入两种模式。

CLI:
  python rebuild_project_index.py --project-root NOVELS_ROOT/项目名
  python rebuild_project_index.py --project-root NOVELS_ROOT/项目名 --dry-run

导入:
  from rebuild_project_index import rebuild_index
  index_data = rebuild_index(project_root)
  rebuild_index(project_root, dry_run=True)

扫描范围:
  - characters/*.yaml           → characters 段
  - worldbuilding/*.yaml        → worldbuilding 段
  - outline/情节线/*.yaml       → plot_threads 段
  - outline/分纲/卷*/*.yaml     → chapters 段
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


# ── 共享导入 ──────────────────────────────────────────────────────────────────

from _utils import fmt_dt, get_nested, load_yaml_safe
from _config import ENTITY_SCAN_CONFIG


def _scan_entity_section(project_root: Path, config: dict, now: str) -> tuple[dict, int, list]:
    """按配置扫描一类实体，返回 (entries, count, warnings)。"""
    entries = {}
    warnings = []
    scan_dir = project_root / config["dir"]
    if not scan_dir.is_dir():
        return entries, 0, warnings

    for fpath in sorted(scan_dir.rglob(config["glob"])):
        if fpath.name in config.get("skip", []):
            continue
        data = load_yaml_safe(fpath)
        if data is None:
            warnings.append({
                "file": str(fpath.relative_to(project_root)),
                "issue": "YAML 解析失败，无法索引",
            })
            continue

        entity_id = get_nested(data, config["id_path"])
        if not entity_id:
            warnings.append({
                "file": str(fpath.relative_to(project_root)),
                "issue": f"缺少必填字段 '{config['id_path']}'，无法索引",
            })
            continue

        entry = {
            "file_path": str(fpath.relative_to(project_root)),
            "updated_at": now,
        }
        for key, dot_path in config["fields"].items():
            entry[key] = get_nested(data, dot_path) or ""
        for key, dot_path in config.get("extra", {}).items():
            val = get_nested(data, dot_path)
            if val is not None:
                entry[key] = val

        entries[entity_id] = entry

    return entries, len(entries), warnings


# ── Public API ──────────────────────────────────────────────────────────────

def rebuild_index(project_root: Path, dry_run: bool = False) -> dict:
    """扫描项目目录下的所有实体文件，重建 project_index.yaml。

    Args:
        project_root: 项目根目录（包含 config.yaml 的目录）
        dry_run: True 时仅打印结果，不写文件

    Returns:
        完整的 project_index.yaml 数据结构（dict）

    Raises:
        FileNotFoundError: 项目根目录不存在
    """
    project_root = project_root.resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(f"项目根目录不存在: {project_root}")

    now = fmt_dt()

    # Read project name from config.yaml
    project_name = project_root.name
    config_path = project_root / "config.yaml"
    config = load_yaml_safe(config_path)
    if config:
        for key in ("项目名称", "project_name", "name"):
            val = config.get(key)
            if val and isinstance(val, str):
                project_name = val
                break

    # Scan all entity types via config
    scan_results = {}
    entity_counts = {}
    all_warnings = []
    for section_name, scan_config in ENTITY_SCAN_CONFIG.items():
        entries, count, warnings = _scan_entity_section(project_root, scan_config, now)
        scan_results[section_name] = entries
        entity_counts[section_name] = count
        for w in warnings:
            all_warnings.append(f"  ⚠ [{section_name}] {w['file']}: {w['issue']}")

    # Build full index
    index_data = {
        "_meta": {
            "generated_by": "shared/rebuild_project_index.py",
            "created_at": now,
            "last_updated": now,
            "project_name": project_name,
            "entity_counts": entity_counts,
        },
        **scan_results,
    }

    if dry_run:
        print(f"[DRY RUN] 项目: {project_name}")
        for name, count in entity_counts.items():
            print(f"  {name}: {count}")
        print(f"  索引文件: {project_root / 'project_index.yaml'} (未写入)")
        return index_data

    # Write index file
    index_path = project_root / "project_index.yaml"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing
    if index_path.exists():
        bak_path = index_path.with_suffix(".yaml.bak")
        if bak_path.exists():
            bak_path.unlink()
        index_path.rename(bak_path)

    with open(index_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(index_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"[OK] 项目索引已重建: {index_path}")
    print(f"  角色: {entity_counts['characters']} | 世界观: {entity_counts['worldbuilding']} | 情节线: {entity_counts['plot_threads']} | 章节: {entity_counts['chapters']}")

    if all_warnings:
        print(f"  ⚠ 扫描警告 ({len(all_warnings)}):")
        for w in all_warnings:
            print(w)

    # git 自动提交（非 dry-run 时）
    if not dry_run:
        try:
            from git_vault import GitVault
            GitVault.commit(project_root, "rebuild: project_index", stage="system")
        except ImportError:
            pass
        except Exception:
            pass

    return index_data


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="扫描 filesystem 重建项目索引 project_index.yaml"
    )
    parser.add_argument(
        "--project-root", "-p",
        required=True,
        help="项目根目录（包含 config.yaml 的目录）",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="仅预览，不写入文件",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    try:
        rebuild_index(project_root, dry_run=args.dry_run)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
