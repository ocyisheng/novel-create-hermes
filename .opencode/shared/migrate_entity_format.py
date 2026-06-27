#!/usr/bin/env python3
"""
migrate_entity_format.py — 实体 YAML 三层格式迁移工具

将旧格式（扁平字段）的实体文件自动转换为标准三层结构：
  _meta + 索引信息.* + 摘要.* + 完整档案.*

检测规则：缺少 _meta / 索引信息 / 摘要 / 完整档案 中任何一个即视为旧格式。
跳过 _index.yaml、角色统计.yaml 等非实体文件。

用法:
    python migrate_entity_format.py --project-root NOVELS_ROOT/项目名
    python migrate_entity_format.py --project-root NOVELS_ROOT/项目名 --dry-run
    python migrate_entity_format.py --project-root NOVELS_ROOT/项目名 --backup-dir /tmp/backup
    python migrate_entity_format.py --project-root NOVELS_ROOT/项目名 --type characters

安全措施:
    - 跳过已是三层结构的文件（幂等）
    - --dry-run 模式预览不改动
    - 默认创建 .bak 备份
"""

import argparse
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


# ── 实体类型 → 目录映射 ──────────────────────────────────────────────────────

ENTITY_DIRS = {
    "characters": {
        "glob": "*.yaml",
        "skip": ["角色统计.yaml"],
        "entity_type": "character",
        "index_fields": ["实体ID", "名称", "角色类型", "状态", "势力归属", "种族", "境界"],
        "abstract_fields": ["一句话描述", "核心特质", "当前目标", "关键关系", "简介", "描述"],
    },
    "worldbuilding": {
        "glob": "*.yaml",
        "skip": [],
        "entity_type": "worldbuilding",
        "index_fields": ["实体ID", "名称", "实体子类型", "状态", "所属势力", "位置"],
        "abstract_fields": ["一句话描述", "核心特质", "简介", "描述", "概述"],
    },
    "outline/情节线": {
        "glob": "*.yaml",
        "skip": ["主索引.yaml", "_index.yaml"],
        "entity_type": "plot_thread",
        "index_fields": ["实体ID", "名称", "类型", "状态", "起始章节", "情节线类型"],
        "abstract_fields": ["一句话描述", "当前境况", "核心特质", "当前目标", "关联角色"],
    },
    "outline/分纲": {
        "glob": "卷*/*.yaml",
        "skip": ["_index.yaml"],
        "entity_type": "chapter_outline",
        "index_fields": ["实体ID", "名称", "章节号", "状态", "所属卷"],
        "abstract_fields": ["一句话描述", "出场角色", "核心情节点", "简介", "摘要"],
    },
}


KNOWN_INDEX_KEYS = set()
for cfg in ENTITY_DIRS.values():
    KNOWN_INDEX_KEYS.update(cfg["index_fields"])

KNOWN_ABSTRACT_KEYS = set()
for cfg in ENTITY_DIRS.values():
    KNOWN_ABSTRACT_KEYS.update(cfg["abstract_fields"])

# 一些旧格式中可能出现的键，不应该放入完整档案（已被结构化为索引/摘要）
RESERVED_META_KEYS = {"_meta"}
RESERVED_INDEX_KEYS = KNOWN_INDEX_KEYS | {"创建时间", "创建于"}
RESERVED_ABSTRACT_KEYS = KNOWN_ABSTRACT_KEYS


# ── 检测 ──────────────────────────────────────────────────────────────────────

def _is_three_layer(data: dict) -> bool:
    """检查 dict 是否已采用标准三层结构。"""
    if not isinstance(data, dict):
        return False
    return all(k in data for k in ("_meta", "索引信息", "摘要", "完整档案"))


def _is_skippable(filename: str, skip_list: list[str]) -> bool:
    """检查文件名是否在跳过列表中。"""
    for pattern in skip_list:
        if filename == pattern:
            return True
    return False


# ── 转换 ──────────────────────────────────────────────────────────────────────

def _infer_entity_id(data: dict, name_hint: str) -> str:
    """从旧格式中推断实体 ID。"""
    for key in ("实体ID", "实体id", "entity_id", "slug"):
        val = data.get(key)
        if val and isinstance(val, str):
            return val.strip()
    # fallback: use 名称 or filename
    name = data.get("名称") or name_hint
    if isinstance(name, str):
        return name.strip()
    return name_hint


def _infer_name(data: dict, name_hint: str) -> str:
    """从旧格式中推断名称。"""
    for key in ("名称", "name", "标题", "姓名", "角色名"):
        val = data.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return name_hint


def _extract_index_data(data: dict, cfg: dict, name_hint: str) -> dict:
    """从扁平数据中提取索引信息字段。"""
    index_data = {}
    for field in cfg["index_fields"]:
        if field == "实体ID":
            continue  # handled separately
        val = data.get(field)
        if val is not None:
            index_data[field] = val

    # Ensure 实体ID
    if "实体ID" not in index_data:
        index_data["实体ID"] = _infer_entity_id(data, name_hint)
    # Ensure 名称
    if "名称" not in index_data:
        index_data["名称"] = _infer_name(data, name_hint)
    # Ensure 状态
    if "状态" not in index_data:
        index_data["状态"] = "active"

    return index_data


def _extract_abstract_data(data: dict, cfg: dict) -> dict:
    """从扁平数据中提取摘要字段。"""
    abstract_data = {}
    for field in cfg["abstract_fields"]:
        val = data.get(field)
        if val is not None:
            abstract_data[field] = val
    return abstract_data


def _build_complete_archive(data: dict, cfg: dict) -> dict:
    """将未被结构化的剩余字段放入完整档案。"""
    consumed = set()
    consumed.add("_meta")
    for field in cfg["index_fields"]:
        consumed.add(field)
    for field in cfg["abstract_fields"]:
        consumed.add(field)

    archive = {}
    for key, val in data.items():
        if key not in consumed:
            archive[key] = val
    return archive


def convert_entity(data: dict, entity_type: str, name_hint: str = "",
                    now: str = "") -> dict | None:
    """将旧格式 dict 转换为三层结构。已是三层结构则返回 None。"""
    if _is_three_layer(data):
        return None

    if not now:
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Find matching config
    cfg = None
    for ek, ec in ENTITY_DIRS.items():
        if ec["entity_type"] == entity_type:
            cfg = ec
            break
    if not cfg:
        # Fallback config
        cfg = {
            "entity_type": entity_type,
            "index_fields": ["实体ID", "名称", "状态"],
            "abstract_fields": ["一句话描述", "简介"],
        }

    # Build three layers
    index_data = _extract_index_data(data, cfg, name_hint)
    abstract_data = _extract_abstract_data(data, cfg)
    archive = _build_complete_archive(data, cfg)

    new_data = {
        "_meta": {
            "entity_type": cfg.get("entity_type", entity_type),
            "schema_version": "3.0",
            "created_at": now,
            "updated_at": now,
        },
        "索引信息": index_data,
        "摘要": abstract_data,
        "完整档案": archive,
    }

    return new_data


def _scan_entity_files(project_root: Path, entity_type: str | None = None
                       ) -> list[tuple[Path, str]]:
    """扫描项目目录，返回 (文件路径, entity_type) 列表。"""
    files = []
    for dir_rel, cfg in ENTITY_DIRS.items():
        if entity_type and cfg["entity_type"] != entity_type:
            continue
        scan_dir = project_root / dir_rel
        if not scan_dir.is_dir():
            continue
        for fpath in sorted(scan_dir.rglob(cfg["glob"])):
            if _is_skippable(fpath.name, cfg["skip"]):
                continue
            files.append((fpath, cfg["entity_type"]))
    return files


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="实体 YAML 三层格式迁移工具"
    )
    parser.add_argument(
        "--project-root", "-p",
        required=True,
        help="项目根目录（包含 config.yaml 的目录）",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="仅预览，不改动文件",
    )
    parser.add_argument(
        "--backup-dir",
        default="",
        help="备份目录（默认在文件同目录创建 .bak）",
    )
    parser.add_argument(
        "--type", "-t",
        dest="entity_type",
        choices=["character", "worldbuilding", "plot_thread", "chapter_outline"],
        default=None,
        help="只迁移指定类型（默认全部）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出每步转换细节",
    )

    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Scan files
    files = _scan_entity_files(project_root, args.entity_type)
    if not files:
        print(f"[EMPTY] 未找到实体文件: {project_root}")
        sys.exit(0)

    # Process
    converted = 0
    skipped = 0
    errors = 0
    results = []

    for fpath, etype in files:
        name_hint = fpath.stem

        # Read
        try:
            with open(fpath, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            errors += 1
            results.append({
                "file": str(fpath.relative_to(project_root)),
                "status": "error",
                "detail": f"YAML 读取失败: {e}",
            })
            if args.verbose:
                print(f"  ❌ {fpath.relative_to(project_root)}: YAML 读取失败 — {e}")
            continue

        if not isinstance(data, dict):
            skipped += 1
            results.append({
                "file": str(fpath.relative_to(project_root)),
                "status": "skipped",
                "detail": "非 dict 根结构，跳过",
            })
            continue

        # Convert
        new_data = convert_entity(data, etype, name_hint, now)
        if new_data is None:
            skipped += 1
            results.append({
                "file": str(fpath.relative_to(project_root)),
                "status": "skipped",
                "detail": "已是三层结构",
            })
            if args.verbose:
                print(f"  ⏭ {fpath.relative_to(project_root)}: 已是三层格式")
            continue

        # Preview
        rel_path = fpath.relative_to(project_root)
        if args.dry_run:
            converted += 1
            results.append({
                "file": str(rel_path),
                "status": "dry-run",
                "detail": "可迁移",
            })
            if args.verbose:
                print(f"  📋 {rel_path}: 可迁移（dry-run）")
                print(f"      索引信息: {list(new_data.get('索引信息', {}).keys())}")
                print(f"      摘要: {list(new_data.get('摘要', {}).keys())}")
                print(f"      完整档案: {list(new_data.get('完整档案', {}).keys())}")
            continue

        # Write
        try:
            # Backup
            if args.backup_dir:
                bak_dir = Path(args.backup_dir)
                bak_dir.mkdir(parents=True, exist_ok=True)
                bak_path = bak_dir / f"{rel_path}.bak"
                bak_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fpath, bak_path)
            else:
                bak_path = fpath.with_suffix(".yaml.bak")
                if not bak_path.exists():
                    shutil.copy2(fpath, bak_path)

            # Write converted
            with open(fpath, "w", encoding="utf-8") as f:
                yaml.safe_dump(new_data, f, default_flow_style=False,
                               sort_keys=False, allow_unicode=True)

            converted += 1
            results.append({
                "file": str(rel_path),
                "status": "converted",
                "detail": f"图层数: {sum(1 for k in ('_meta', '索引信息', '摘要', '完整档案') if k in new_data)}/4",
            })
            if args.verbose:
                print(f"  ✅ {rel_path}: 已转换")
                print(f"      索引信息: {list(new_data.get('索引信息', {}).keys())}")
                print(f"      摘要: {list(new_data.get('摘要', {}).keys())}")
                print(f"      完整档案: {list(new_data.get('完整档案', {}).keys())}")

        except Exception as e:
            errors += 1
            results.append({
                "file": str(rel_path),
                "status": "error",
                "detail": f"写入失败: {e}",
            })
            if args.verbose:
                print(f"  ❌ {rel_path}: 写入失败 — {e}")

    # Summary
    print()
    mode = "DRY-RUN" if args.dry_run else "MIGRATION"
    verb = "would convert" if args.dry_run else "converted"
    print(f"[{mode}] Summary for: {project_root}")
    print(f"  总文件: {len(files)}")
    print(f"  ✅ {verb}: {converted}")
    print(f"  ⏭ 跳过（已是标准格式）: {skipped}")
    print(f"  ❌ 错误: {errors}")

    if results:
        print(f"\n  详细报告:")
        for r in results:
            status_icon = {"converted": "✅", "dry-run": "📋", "skipped": "⏭", "error": "❌"}.get(r["status"], "❓")
            print(f"    {status_icon} [{r['status']}] {r['file']}: {r['detail']}")

    # Exit code
    if errors > 0:
        sys.exit(1)

    # Rebuild index hint
    if converted > 0 and not args.dry_run:
        print(f"\n  💡 提示: 运行以下命令重建索引:")
        print(f"     python .opencode/shared/rebuild_project_index.py --project-root {project_root}")


if __name__ == "__main__":
    main()
