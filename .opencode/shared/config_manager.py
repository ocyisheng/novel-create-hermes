#!/usr/bin/env python3
"""
config_manager.py — 安全读写 config.yaml 字段，支持 dot notation 嵌套访问。

Usage:
    python config_manager.py get <field> --project-root PATH
    python config_manager.py set <field> <value> --project-root PATH

Examples:
    python config_manager.py get 当前阶段 --project-root NOVELS_ROOT/项目名
    python config_manager.py get 创作进度.当前章节 --project-root NOVELS_ROOT/项目名
    python config_manager.py set 当前阶段 章节写作 --project-root NOVELS_ROOT/项目名
"""

import sys
from pathlib import Path
import yaml


def load_config(project_root: Path) -> dict:
    config_path = project_root / "config.yaml"
    if not config_path.is_file():
        print(f"Error: config.yaml not found at {project_root}", file=sys.stderr)
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(project_root: Path, data: dict) -> None:
    config_path = project_root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        bak = config_path.with_suffix(".yaml.bak")
        if bak.exists():
            bak.unlink()
        config_path.rename(bak)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _get_nested(data: dict, dot_path: str):
    keys = dot_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_nested(data: dict, dot_path: str, value):
    keys = dot_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def main():
    import argparse
    parser = argparse.ArgumentParser(description="config.yaml 字段读写（支持嵌套 dot notation）")
    sub = parser.add_subparsers(dest="command")

    p_get = sub.add_parser("get", help="读取字段")
    p_get.add_argument("field", help="字段名（如 当前阶段, 创作进度.当前章节）")
    p_get.add_argument("--project-root", required=True, help="项目根目录")

    p_set = sub.add_parser("set", help="写入字段")
    p_set.add_argument("field", help="字段名")
    p_set.add_argument("value", help="新值")
    p_set.add_argument("--project-root", required=True, help="项目根目录")

    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    data = load_config(project_root)

    if args.command == "get":
        val = _get_nested(data, args.field)
        if val is None:
            print(f"Warning: field '{args.field}' not found in config.yaml", file=sys.stderr)
            sys.exit(1)
        print(val)
    elif args.command == "set":
        old = _get_nested(data, args.field)
        _set_nested(data, args.field, args.value)
        save_config(project_root, data)
        print(f"已更新 {args.field}: {old} → {args.value}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
