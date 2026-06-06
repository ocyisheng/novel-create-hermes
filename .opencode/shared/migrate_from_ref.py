#!/usr/bin/env python3
"""
migrate_from_ref.py — 从旧 $ref 系统迁移到三层契约结构

一次性迁移脚本，将旧版 $ref 格式的项目升级到 novel-context-service 的三层结构。

CLI:
  python migrate_from_ref.py --project NOVELS_ROOT/星辰
  python migrate_from_ref.py --dry-run --project NOVELS_ROOT/星辰

迁移内容:
  1. 扫描所有 *.yaml 文件，识别并替换 $ref 引用为内联结构化数据
  2. 为实体文件补充 _meta, 索引信息, 摘要 三层结构
  3. 为每实体生成 {entity_id}.summary.yaml 摘要文件
  4. 生成初始 project_index.yaml

依赖: Python 3, stdlib + PyYAML
"""

import sys
import os
import argparse
import shutil
from pathlib import Path
from datetime import datetime

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)


# ── Constants ──────────────────────────────────────────────────────────────

ENTITY_DIRECTORIES = {
    "character": "characters",
    "location": "worldbuilding",
    "plot_thread": "plot_threads",
    "chapter": "chapters",
}

# Directory names that contain entity files (for three-layer upgrade detection)
ENTITY_TYPE_DIR_MAP = {
    "characters": "character",
    "worldbuilding": "location",
    "情节线": "plot_thread",
    "分纲": "chapter",
    "outline": "outline_section",
}

BACKUP_SUFFIX = ".migrate_backup"


# ── Argument Parsing ───────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse and return CLI arguments."""
    parser = argparse.ArgumentParser(
        description="migrate_from_ref.py — 从旧 $ref 系统迁移到三层契约结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python migrate_from_ref.py --project NOVELS_ROOT/星辰\n"
            "  python migrate_from_ref.py --dry-run --project NOVELS_ROOT/星辰\n"
        ),
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="项目根目录路径 (如 NOVELS_ROOT/星辰)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="预览模式：只打印变更，不修改任何文件",
    )
    return parser.parse_args()


# ── Tree Traversal Helpers ─────────────────────────────────────────────────


def get_nested(data: dict, dot_path: str):
    """Traverse a dict by dot-separated keys and return the value or None."""
    keys = dot_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        if key not in current:
            return None
        current = current[key]
    return current


def set_nested(data: dict, dot_path: str, value) -> None:
    """Set a value at a dot-separated path, creating intermediate dicts."""
    keys = dot_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def detect_entity_type(file_path: Path, project_root: Path) -> str:
    """Detect entity type from directory name."""
    try:
        rel = file_path.relative_to(project_root)
        parent = rel.parent.name
        return ENTITY_TYPE_DIR_MAP.get(parent, "unknown")
    except ValueError:
        return "unknown"


def is_entity_file(file_path: Path, project_root: Path) -> bool:
    """Check if a YAML file lives in a known entity directory."""
    try:
        rel = file_path.relative_to(project_root)
        return rel.parent.name in ENTITY_TYPE_DIR_MAP
    except ValueError:
        return False


def is_generated_file(file_path: Path) -> bool:
    """Check if a file is auto-generated (summary, backup, etc)."""
    stem = file_path.stem
    if stem.endswith(".summary"):
        return True
    return False


def collect_yaml_files(project_root: Path) -> list[Path]:
    """Collect all .yaml and .yml files in the project.

    Skips hidden directories, __pycache__, .venv, and generated files.
    """
    files: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        for f in project_root.rglob(ext):
            # Skip generated / system directories
            parts = f.relative_to(project_root).parts
            skip_prefixes = {".", "__pycache__", ".venv", "node_modules"}
            if any(p.startswith(".") or p in skip_prefixes for p in parts):
                continue
            # Skip generated summary files
            if is_generated_file(f):
                continue
            files.append(f)
    return sorted(files)


# ── $ref Detection and Resolution ─────────────────────────────────────────


def find_refs(data, path="", refs=None):
    """Recursively find all ``{"$ref": "..."}`` patterns in YAML data.

    Returns a list of ``(parent_dict, ref_value, dot_path)`` tuples.
    """
    if refs is None:
        refs = []

    if isinstance(data, dict):
        if "$ref" in data:
            refs.append((data, data["$ref"], path))
        for k, v in data.items():
            child_path = f"{path}.{k}" if path else k
            find_refs(v, child_path, refs)

    elif isinstance(data, list):
        for i, item in enumerate(data):
            child_path = f"{path}[{i}]"
            find_refs(item, child_path, refs)

    return refs


def resolve_ref_path(ref_value: str, project_root: Path) -> Path | None:
    """Resolve ``$ref`` value (e.g. ``@characters/linmo.yaml``) to absolute path.

    Handles anchor syntax (``#anchor``) by stripping it.
    Returns ``None`` if the value doesn't use the ``@`` prefix.
    """
    if not ref_value.startswith("@"):
        return None
    rel = ref_value[1:]  # strip @
    # Strip anchor fragment, e.g. "#伏笔001"
    if "#" in rel:
        rel = rel.split("#")[0]
    return (project_root / rel).resolve()


# ── Inline Data Extraction ────────────────────────────────────────────────


def extract_inline_fields(
    target_data: dict, target_path: Path, project_root: Path
) -> dict:
    """Extract key identification fields from a referenced entity file.

    Returns a dict suitable for inlining at the ``$ref`` site.
    """
    entity_type = detect_entity_type(target_path, project_root)

    # Try three-layer structure first
    index_info = get_nested(target_data, "索引信息") or {}
    summary_info = get_nested(target_data, "摘要") or {}

    try:
        rel_source = str(target_path.relative_to(project_root).as_posix())
    except ValueError:
        rel_source = target_path.name

    inline = {
        "实体ID": index_info.get("实体ID") or target_data.get("实体ID") or target_path.stem,
        "名称": index_info.get("名称") or target_data.get("名称") or target_data.get("姓名") or "",
        "类型": entity_type,
        "来源文件": rel_source,
    }

    if summary_info:
        if summary_info.get("一句话描述"):
            inline["一句话描述"] = summary_info["一句话描述"]
        if summary_info.get("当前境况"):
            inline["当前境况"] = summary_info["当前境况"]

    return inline


# ── Three-Layer Upgrade ────────────────────────────────────────────────────


def upgrade_to_three_layers(
    data: dict, file_path: Path, project_root: Path
) -> tuple[dict, list[str]]:
    """Add ``_meta``, ``索引信息``, ``摘要`` to entity data if missing.

    Returns ``(modified_data, change_descriptions)``.
    """
    changes: list[str] = []
    entity_type = detect_entity_type(file_path, project_root)

    # ── 1. _meta ────────────────────────────────────────────────────────
    if "_meta" not in data or not isinstance(data["_meta"], dict):
        data["_meta"] = {
            "entity_type": entity_type,
            "schema_version": "3.0",
        }
        changes.append(f"添加 _meta (entity_type={entity_type})")
    else:
        meta = data["_meta"]
        if "entity_type" not in meta:
            meta["entity_type"] = entity_type
            changes.append(f"设置 _meta.entity_type={entity_type}")
        if not meta.get("schema_version"):
            meta["schema_version"] = "3.0"
            changes.append("设置 _meta.schema_version=3.0")
        elif str(meta.get("schema_version", "")).startswith("1."):
            meta["schema_version"] = "3.0"
            changes.append("更新 _meta.schema_version 至 3.0")

    # ── 2. 索引信息 ────────────────────────────────────────────────────
    if "索引信息" not in data or not isinstance(data["索引信息"], dict):
        entity_id = (
            data.get("实体ID")
            or data.get("id")
            or file_path.stem
        )
        name = data.get("名称") or data.get("姓名") or data.get("name") or ""
        status = data.get("状态") or data.get("status") or "active"
        first_ch = data.get("首次出场章节") or data.get("first_chapter") or 0
        curr_ch = data.get("当前章节位置") or data.get("current_chapter") or 0

        data["索引信息"] = {
            "实体ID": entity_id,
            "名称": name,
            "角色类型": data.get("角色类型") or "",
            "状态": status,
            "首次出场章节": int(first_ch) if isinstance(first_ch, (int, float, str)) and str(first_ch).isdigit() else 0,
            "当前章节位置": int(curr_ch) if isinstance(curr_ch, (int, float, str)) and str(curr_ch).isdigit() else 0,
        }
        changes.append(f"添加 索引信息 (实体ID={entity_id})")

    # ── 3. 摘要 ─────────────────────────────────────────────────────────
    if "摘要" not in data or not isinstance(data["摘要"], dict):
        one_line = (
            data.get("一句话描述")
            or data.get("简介")
            or data.get("description")
            or ""
        )
        core_traits = data.get("核心特质") or data.get("core_traits") or []
        current_goal = data.get("当前目标") or data.get("current_goal") or ""

        data["摘要"] = {
            "一句话描述": one_line if isinstance(one_line, str) else str(one_line),
            "当前境况": data.get("当前境况") or "",
            "核心特质": core_traits if isinstance(core_traits, list) else [],
            "当前目标": current_goal if isinstance(current_goal, str) else str(current_goal),
            "关键关系": data.get("关键关系") or [],
        }
        changes.append("添加 摘要")

    return data, changes


# ── Summary File Generation ────────────────────────────────────────────────


def generate_summary_file(
    entity_data: dict, entity_id: str, entity_path: Path
) -> Path:
    """Write ``{entity_id}.summary.yaml`` alongside the entity file.

    Returns the absolute path of the written summary file.
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    name = get_nested(entity_data, "索引信息.名称") or entity_id
    summary = get_nested(entity_data, "摘要") or {}

    raw_relations = summary.get("关键关系", [])
    relations_output = []
    for rel in raw_relations:
        if isinstance(rel, dict):
            relations_output.append({
                "角色": rel.get("角色", ""),
                "关系": rel.get("关系", rel.get("关系类型", "")),
                "状态": rel.get("状态", rel.get("关系状态", "")),
            })
        elif isinstance(rel, str):
            relations_output.append({"角色": rel, "关系": "", "状态": ""})

    summary_data = {
        "_meta": {
            "generated_by": "novel-context-service/migrate_from_ref.py",
            "source_entity": entity_id,
            "updated_at": now,
        },
        "实体ID": entity_id,
        "名称": name,
        "一句话描述": summary.get("一句话描述", ""),
        "当前境况": summary.get("当前境况", ""),
        "核心特质": summary.get("核心特质", []),
        "当前目标": summary.get("当前目标", ""),
        "关键关系": relations_output,
    }

    summary_dir = entity_path.parent / ".summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{entity_id}.yaml"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# {name} 摘要 — 由 migrate_from_ref.py 自动生成\n")
        yaml.safe_dump(
            summary_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return summary_path.resolve()


# ── Project Index Building ─────────────────────────────────────────────────


def build_project_index(
    project_root: Path,
    entity_files_info: list[tuple[Path, dict, str]],
) -> Path:
    """Build ``project_index.yaml`` from migrated entity data.

    Returns the path of the written index file.
    """
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    project_name = _get_project_name(project_root)

    index_data = {
        "_meta": {
            "generated_by": "novel-context-service/migrate_from_ref.py",
            "created_at": now,
            "last_updated": now,
            "project_name": project_name,
            "entity_counts": {
                "characters": 0,
                "worldbuilding": 0,
                "plot_threads": 0,
                "chapters": 0,
            },
        },
        "characters": {},
        "worldbuilding": {},
        "plot_threads": {},
        "chapters": {},
    }

    for file_path, entity_data, entity_id in entity_files_info:
        entity_type = (
            get_nested(entity_data, "_meta.entity_type")
            or detect_entity_type(file_path, project_root)
        )
        section = ENTITY_DIRECTORIES.get(entity_type, "worldbuilding")
        # Guard against unknown types creating garbage sections
        if section not in index_data:
            section = "worldbuilding"

        index_info = get_nested(entity_data, "索引信息") or {}
        summary_info = get_nested(entity_data, "摘要") or {}

        role_type = index_info.get("角色类型") or index_info.get("实体类型") or ""

        index_data[section][entity_id] = {
            "name": index_info.get("名称", ""),
            "type": role_type,
            "status": index_info.get("状态", "active"),
            "first_chapter": index_info.get("首次出场章节", 0),
            "current_chapter": index_info.get("当前章节位置", 0),
            "one_line": summary_info.get("一句话描述", ""),
            "updated_at": now,
        }
        index_data["_meta"]["entity_counts"][section] = len(index_data[section])

    index_path = project_root / "project_index.yaml"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("# 项目索引 — 由 migrate_from_ref.py 自动生成\n")
        yaml.safe_dump(
            index_data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return index_path


def _get_project_name(project_root: Path) -> str:
    """Read project_name from config.yaml or fall back to directory name."""
    config_path = project_root / "config.yaml"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            if isinstance(cfg, dict):
                for key in ("项目名称", "project_name", "name", "title"):
                    val = cfg.get(key)
                    if val and isinstance(val, str):
                        return val
        except Exception:
            pass
    return project_root.name


# ── Safe Write (with backup) ───────────────────────────────────────────────


def safe_write_yaml(file_path: Path, data: dict) -> None:
    """Write YAML data to file, creating a .migrate_backup of the original."""
    if file_path.exists():
        backup_path = file_path.with_suffix(BACKUP_SUFFIX + file_path.suffix)
        shutil.copy2(file_path, backup_path)

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


# ── Main Migration Orchestrator ────────────────────────────────────────────


def migrate_project(project_root: Path, dry_run: bool = False) -> dict:
    """Execute the full migration on a project.

    Returns a dict with the migration statistics.
    """
    label = "🔍 [DRY RUN] " if dry_run else ""
    print(f"{label}迁移项目: {project_root}")
    print()

    warnings: list[str] = []
    yaml_files = collect_yaml_files(project_root)
    print(f"找到 {len(yaml_files)} 个 YAML 文件")
    print()

    # ── Step 1-4: Scan & replace $ref references ────────────────────────

    ref_replacements: list[dict] = []
    files_to_rewrite: list[tuple[Path, dict]] = []

    for yf in yaml_files:
        try:
            with open(yf, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            msg = str(e)
            if hasattr(e, "problem_mark") and e.problem_mark:
                line = e.problem_mark.line + 1
                msg = f"第 {line} 行: {e.problem}"
            warnings.append(f"YAML 解析错误 {yf.name}: {msg}")
            continue
        except (OSError, IOError) as e:
            warnings.append(f"读取失败 {yf.name}: {e}")
            continue

        if not isinstance(data, dict):
            continue

        refs = find_refs(data)
        if not refs:
            continue

        any_changed = False
        for parent_dict, ref_value, ctx_path in refs:
            target_path = resolve_ref_path(ref_value, project_root)
            if target_path is None:
                warnings.append(
                    f"无效 $ref 格式 '{ref_value}' 在 {yf.relative_to(project_root)}"
                )
                continue
            if not target_path.is_file():
                warnings.append(
                    f"引用目标不存在 '{ref_value}' 在 {yf.relative_to(project_root)}"
                )
                continue

            # Read referenced file
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    target_data = yaml.safe_load(f)
            except Exception as e:
                warnings.append(
                    f"无法读取引用目标 {target_path.name}: {e}"
                )
                continue

            if not isinstance(target_data, dict):
                warnings.append(
                    f"引用目标 {target_path.name} 不是字典格式，跳过"
                )
                continue

            # Extract inline fields
            inline_fields = extract_inline_fields(
                target_data, target_path, project_root
            )

            # Record the replacement
            try:
                rel_yf = yf.relative_to(project_root)
                rel_target = target_path.relative_to(project_root)
            except ValueError:
                rel_yf = yf
                rel_target = target_path

            ref_replacements.append({
                "file": rel_yf,
                "path": ctx_path,
                "ref_value": ref_value,
                "target": rel_target,
                "inline": inline_fields,
            })

            # Perform replacement
            parent_dict.pop("$ref", None)
            parent_dict.update(inline_fields)
            any_changed = True

        if any_changed:
            files_to_rewrite.append((yf, data))

    # Write modified files (with $ref replacements)
    for yf, data in files_to_rewrite:
        if not dry_run:
            safe_write_yaml(yf, data)

    # Print $ref report
    if ref_replacements:
        _print_section_header(f"$ref 引用替换 ({len(ref_replacements)} 处)")
        for r in ref_replacements:
            inline = r["inline"]
            print(f"  📄 {r['file']}")
            print(f"     路径: {r['path']}")
            print(f"     原引用: {r['ref_value']} → {r['target']}")
            name = inline.get("名称") or inline.get("实体ID", "?")
            print(f"     替换为: {name}")
            print()
    else:
        print("未发现 $ref 引用")
        print()

    # ── Step 5: Upgrade entity files to three-layer structure ──────────

    upgraded_entities: list[tuple[Path, list[str], dict]] = []
    entity_files_info: list[tuple[Path, dict, str]] = []

    for yf in yaml_files:
        # Skip non-entity files
        if not is_entity_file(yf, project_root):
            # Still collect entity info for index building if already three-layer
            try:
                with open(yf, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    has_three = (
                        "_meta" in data and isinstance(data["_meta"], dict)
                        and "索引信息" in data and isinstance(data["索引信息"], dict)
                        and "摘要" in data and isinstance(data["摘要"], dict)
                    )
                    if has_three:
                        eid = get_nested(data, "索引信息.实体ID") or yf.stem
                        entity_files_info.append((yf, data, eid))
            except Exception:
                pass
            continue

        # Read entity data
        try:
            with open(yf, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        # Check if already has three-layer structure
        has_full = (
            "_meta" in data and isinstance(data["_meta"], dict)
            and "索引信息" in data and isinstance(data["索引信息"], dict)
            and "摘要" in data and isinstance(data["摘要"], dict)
        )

        if has_full:
            eid = get_nested(data, "索引信息.实体ID") or yf.stem
            entity_files_info.append((yf, data, eid))
            continue

        # Upgrade
        modified, changes = upgrade_to_three_layers(data, yf, project_root)

        if changes:
            try:
                rel_yf = yf.relative_to(project_root)
            except ValueError:
                rel_yf = yf

            upgraded_entities.append((rel_yf, changes, modified))
            eid = get_nested(modified, "索引信息.实体ID") or yf.stem
            entity_files_info.append((yf, modified, eid))

            if not dry_run:
                safe_write_yaml(yf, modified)

    if upgraded_entities:
        _print_section_header(
            f"三层结构补充 ({len(upgraded_entities)} 个实体)"
        )
        for rel_yf, changes, _ in upgraded_entities:
            print(f"  📄 {rel_yf}")
            for c in changes:
                print(f"     ✓ {c}")
            print()
    else:
        print("所有实体文件已具备三层结构")
        print()

    # ── Step 5b: Generate summary files (.summary/{id}.yaml) ──────────

    summary_count = 0
    for yf, entity_data, entity_id in entity_files_info:
        summary_path = yf.parent / ".summary" / f"{entity_id}.yaml"
        if summary_path.is_file():
            continue
        if not dry_run:
            generate_summary_file(entity_data, entity_id, yf)
        summary_count += 1

    if summary_count > 0:
        print(f"将生成 {summary_count} 个摘要文件 (.summary/{{id}}.yaml)")
        print()

    # ── Step 6: Build project_index.yaml ───────────────────────────────

    index_path = project_root / "project_index.yaml"
    if not dry_run:
        build_project_index(project_root, entity_files_info)

    # ── Summary Report ─────────────────────────────────────────────────

    _print_section_header("迁移摘要" if not dry_run else "DRY RUN 摘要")

    stats = {
        "yaml_files": len(yaml_files),
        "ref_replacements": len(ref_replacements),
        "upgraded_entities": len(upgraded_entities),
        "summary_files": summary_count,
        "files_modified": len(files_to_rewrite) + len(upgraded_entities),
    }

    print(f"  YAML 文件数:      {stats['yaml_files']}")
    print(f"  $ref 替换:        {stats['ref_replacements']}")
    print(f"  三层结构补充:     {stats['upgraded_entities']} 个实体")
    print(f"  摘要文件生成:     {stats['summary_files']} 个")
    print(f"  需修改文件数:     {stats['files_modified']}")
    print(f"  项目索引:         {'project_index.yaml' if not dry_run else '(未写入)'}")

    if warnings:
        print()
        _print_section_header("警告")
        for w in warnings:
            print(f"  ⚠️  {w}")

    print()
    if dry_run:
        print("🟡 DRY RUN 模式：文件未被修改。移除 --dry-run 执行实际迁移。")
    else:
        print("✅ 迁移完成。请验证 project_index.yaml 内容和各实体文件。")

    return stats


def _print_section_header(title: str) -> None:
    """Print a section header with underline."""
    print(title)
    print("─" * 60)


# ── Entry Point ────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()

    if not project_root.is_dir():
        print(f"Error: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    try:
        migrate_project(project_root, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n迁移被用户中断", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: 迁移失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
