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
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


# ── Output formatting helpers ───────────────────────────────────────────────

def _fmt_dt() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _get_nested(data: dict, dot_path: str):
    """Traverse a dict by dot-separated keys."""
    keys = dot_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _load_yaml_safe(path: Path) -> dict | None:
    """Load YAML, return None on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ── Entity scanning config ────────────────────────────────────────────────────

ENTITY_SCAN_CONFIG = {
    "characters": {
        "dir": "characters",
        "glob": "*.yaml",
        "skip": [],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "type": "索引信息.角色类型",
            "first_chapter": "索引信息.首次出场章节",
        },
    },
    "worldbuilding": {
        "dir": "worldbuilding",
        "glob": "*.yaml",
        "skip": [],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "subtype": "索引信息.实体子类型",
        },
    },
    "plot_threads": {
        "dir": "outline/情节线",
        "glob": "*.yaml",
        "skip": ["主索引.yaml"],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "first_chapter": "索引信息.起始章节",
            # current_chapter 改为从 追踪/情节线进度.yaml 读取
            "start_time": "索引信息.起始时间",
            "end_time": "索引信息.结束时间",
        },
    },
    "chapters": {
        "dir": "outline/分纲",
        "glob": "**/*.yaml",
        "skip": [],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "chapter_num": "索引信息.章节号",
        },
    },
}


def _scan_entity_section(project_root: Path, config: dict, now: str) -> tuple[dict, int]:
    """按配置扫描一类实体，返回 (entries, count)。"""
    entries = {}
    scan_dir = project_root / config["dir"]
    if not scan_dir.is_dir():
        return entries, 0

    for fpath in sorted(scan_dir.rglob(config["glob"])):
        if fpath.name in config.get("skip", []):
            continue
        data = _load_yaml_safe(fpath)
        if data is None:
            continue

        entity_id = _get_nested(data, config["id_path"])
        if not entity_id:
            continue

        entry = {
            "file_path": str(fpath.relative_to(project_root)),
            "updated_at": now,
        }
        for key, dot_path in config["fields"].items():
            entry[key] = _get_nested(data, dot_path) or ""
        for key, dot_path in config.get("extra", {}).items():
            val = _get_nested(data, dot_path)
            if val is not None:
                entry[key] = val

        entries[entity_id] = entry

    return entries, len(entries)


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

    now = _fmt_dt()

    # Read project name from config.yaml
    project_name = project_root.name
    config_path = project_root / "config.yaml"
    config = _load_yaml_safe(config_path)
    if config:
        for key in ("项目名称", "project_name", "name"):
            val = config.get(key)
            if val and isinstance(val, str):
                project_name = val
                break

    # Scan all entity types via config
    scan_results = {}
    entity_counts = {}
    for section_name, scan_config in ENTITY_SCAN_CONFIG.items():
        entries, count = _scan_entity_section(project_root, scan_config, now)
        scan_results[section_name] = entries
        entity_counts[section_name] = count

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
