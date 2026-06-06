#!/usr/bin/env python3
"""Novel Style Manager — 风格文件维护脚本。

对标: rebuild_project_index.py（维护 project_index.yaml）、auto_update.py（维护 config.yaml + 追踪数据）

5 个子命令:
  register   — 注册风格到 styles/index.yaml
  validate   — 验证 style.yaml 结构（7维度齐全 + ≤30行 + 合法YAML）
activate   — 设置 config.yaml 活跃风格
deactivate — 清除 config.yaml 活跃风格
  list       — 列出 styles/index.yaml 中所有风格名
  builtin    — 管理内建风格（list / copy）
"""

import argparse
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required but not installed.", file=sys.stderr)
    sys.exit(1)


REQUIRED_DIMENSIONS = [
    "narrative_tone",
    "sentence_structure",
    "pacing",
    "dialogue_style",
    "vocabulary_register",
    "rhetorical_features",
    "forbidden_patterns",
]


def register_style(project_root: Path, style_name: str, style_file: str) -> None:
    index_file = project_root / "styles" / "index.yaml"

    data = {"styles": []}
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {"styles": []}

    if any(s.get("name") == style_name for s in data.get("styles", [])):
        print(f"Error: style '{style_name}' already registered.", file=sys.stderr)
        sys.exit(1)

    data.setdefault("styles", []).append({"name": style_name, "file": style_file})

    with open(index_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def validate_style(file_path: Path) -> None:
    errors = []

    if not file_path.exists():
        errors.append(f"file not found: {file_path}")

    if not errors:
        try:
            content = file_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                errors.append("top-level is not a dict")
        except yaml.YAMLError as e:
            print(f"invalid YAML: {e}", file=sys.stderr)
            sys.exit(1)

    if not errors:
        for key in ("style_name", "description", "dimensions"):
            if key not in data:
                errors.append(f"missing top-level key: '{key}'")

    if not errors and "dimensions" in data:
        for dim in REQUIRED_DIMENSIONS:
            if dim not in data["dimensions"]:
                errors.append(f"dimensions missing: '{dim}'")
            else:
                dim_val = data["dimensions"][dim]
                if dim_val is None or (isinstance(dim_val, dict) and not any(v for v in dim_val.values() if v)):
                    errors.append(f"'{dim}' is empty")

    if not errors:
        line_count = content.count("\n") + 1
        if line_count > 30:
            errors.append(f"line count {line_count} exceeds limit 30")
        # category is recommended, warn if missing
        if not data.get("category"):
            print(f"warning: missing recommended field 'category'", file=sys.stderr)

    if errors:
        print(f"validate failed: {'; '.join(errors)}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"validate passed: {data.get('style_name', 'unknown')}")


def _update_style_field(config_path: Path, value: str) -> None:
    """通过 YAML 安全读写更新 活跃风格 字段。"""
    if not config_path.exists():
        print(f"Error: config.yaml not found at {config_path}", file=sys.stderr)
        sys.exit(1)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    data["活跃风格"] = value
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def deactivate_style(project_root: Path) -> None:
    _update_style_field(project_root / "config.yaml", "")


BUILTIN_DIR = Path(__file__).parent.parent / "builtin"


def activate_style(project_root: Path, style_name: str) -> None:
    local = project_root / "styles" / f"{style_name}.yaml"
    builtin = BUILTIN_DIR / f"{style_name}.yaml"
    if not local.exists() and not builtin.exists():
        print(f"Error: style '{style_name}' not found in project or builtin", file=sys.stderr)
        sys.exit(1)
    _update_style_field(project_root / "config.yaml", style_name)


def list_styles(project_root: Path, include_builtin: bool = False) -> None:
    index_file = project_root / "styles" / "index.yaml"
    if index_file.exists():
        data = yaml.safe_load(index_file.read_text(encoding="utf-8")) or {}
        for s in data.get("styles", []):
            print(s.get("name", ""))
    if include_builtin:
        for f in sorted(BUILTIN_DIR.glob("*.yaml")):
            print(f.stem + " [内置]")


def builtin_handler(args) -> None:
    """Handle the 'builtin' subcommand (list / copy)."""
    if args.builtin_action == "list":
        builtin_files = sorted(BUILTIN_DIR.glob("*.yaml"))
        if not builtin_files:
            print("(no builtin styles found)")
            return
        for f in builtin_files:
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                desc = data.get("description", "") if isinstance(data, dict) else ""
            except Exception:
                desc = ""
            print(f"  {f.stem}" + (f"  — {desc}" if desc else ""))
    elif args.builtin_action == "copy":
        project_root = Path(args.project_root)
        style_name = args.name
        source = BUILTIN_DIR / f"{style_name}.yaml"
        if not source.exists():
            print(f"Error: builtin style '{style_name}' not found", file=sys.stderr)
            sys.exit(1)
        dest_dir = project_root / "styles"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{style_name}.yaml"
        if dest.exists():
            print(f"Error: '{style_name}.yaml' already exists in project styles/", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(source, dest)
        print(f"Copied '{style_name}' to {dest}")
    else:
        print("Usage: builtin {list|copy}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Novel Style Manager")
    sp = parser.add_subparsers(dest="command")

    p = sp.add_parser("register", help="Register a style in styles/index.yaml")
    p.add_argument("--project-root", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--file", required=True)

    p = sp.add_parser("validate", help="Validate a style.yaml file")
    p.add_argument("--file", required=True)

    p = sp.add_parser("activate", help="Set 活跃风格 in config.yaml")
    p.add_argument("--project-root", required=True)
    p.add_argument("--name", required=True)

    p = sp.add_parser("deactivate", help="Clear 活跃风格 in config.yaml")
    p.add_argument("--project-root", required=True)

    p = sp.add_parser("list", help="List available styles")
    p.add_argument("--project-root", required=True)
    p.add_argument("--include-builtin", action="store_true", help="Include built-in styles")

    p = sp.add_parser("builtin", help="Manage built-in styles")
    bp = p.add_subparsers(dest="builtin_action")
    bl = bp.add_parser("list", help="List built-in styles")
    bc = bp.add_parser("copy", help="Copy a built-in style to project")
    bc.add_argument("--project-root", required=True)
    bc.add_argument("--name", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "register":
        register_style(Path(args.project_root), args.name, args.file)
    elif args.command == "validate":
        validate_style(Path(args.file))
    elif args.command == "activate":
        activate_style(Path(args.project_root), args.name)
    elif args.command == "deactivate":
        deactivate_style(Path(args.project_root))
    elif args.command == "list":
        list_styles(Path(args.project_root), getattr(args, "include_builtin", False))
    elif args.command == "builtin":
        builtin_handler(args)


if __name__ == "__main__":
    main()
