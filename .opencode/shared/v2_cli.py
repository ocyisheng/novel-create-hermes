"""
V2 CLI 工具 — 编排层 prompt 中调用的脚本入口。

用法：
    python .opencode/shared/v2_cli.py find-unit --path <PROJECT> --name <名称>
    python .opencode/shared/v2_cli.py rebuild-projections --path <PROJECT>
    python .opencode/shared/v2_cli.py stats --path <PROJECT>
    python .opencode/shared/v2_cli.py list-units --path <PROJECT> --type <UnitType>
    python .opencode/shared/v2_cli.py recent-events --path <PROJECT>
"""

import sys
import os
import argparse

V2_DIR = os.path.join(os.path.dirname(__file__), "v2")
sys.path.insert(0, V2_DIR)


def cmd_find_unit(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    u = s.get_unit_by_name(args.name)
    print(u.id if u else "NOT_FOUND")


def cmd_rebuild_projections(args):
    from graph_store import GraphStore
    from projection_engine import ProjectionEngine
    s = GraphStore(args.path)
    s.initialize()
    p = ProjectionEngine(s, args.path, output_mode=args.mode)
    p.rebuild_all()
    print("投影已重建")


def cmd_stats(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    for k, v in s.stats().items():
        print(f"{k}: {v}")


def cmd_list_units(args):
    from graph_schema import UnitType
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    ut = UnitType[args.type.upper()] if args.type else None
    for u in s.find_units(type=ut):
        print(f"{u.unit_name} [{u.status.value}]")


def cmd_recent_events(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    for e in s._events[-int(args.limit):]:
        print(f"[{e.timestamp:%H:%M}] {e.actor}: {e.event_type.value}")


def cmd_migrate(args):
    from migrate import main as migrate_main
    sys.argv = ["migrate.py", "--project-root", args.path]
    if args.verify:
        sys.argv.append("--verify")
    if args.report:
        sys.argv.append("--report")
    if args.dry_run:
        sys.argv.append("--dry-run")
    migrate_main()


def main():
    parser = argparse.ArgumentParser(description="V2 CLI 工具")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("find-unit", help="按名称查找叙事单元ID")
    p.add_argument("--path", required=True)
    p.add_argument("--name", required=True)

    p = sub.add_parser("rebuild-projections", help="重建投影")
    p.add_argument("--path", required=True)
    p.add_argument("--mode", default="hybrid", choices=["in_place", "hybrid"])

    p = sub.add_parser("stats", help="graph 统计")
    p.add_argument("--path", required=True)

    p = sub.add_parser("list-units", help="列出叙事单元")
    p.add_argument("--path", required=True)
    p.add_argument("--type", default="", help="UnitType 名称（SCENE/CHARACTER_ARC 等）")

    p = sub.add_parser("recent-events", help="最近事件")
    p.add_argument("--path", required=True)
    p.add_argument("--limit", default="5")

    p = sub.add_parser("migrate", help="迁移项目到 V2")
    p.add_argument("--path", required=True)
    p.add_argument("--verify", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "find-unit": cmd_find_unit,
        "rebuild-projections": cmd_rebuild_projections,
        "stats": cmd_stats,
        "list-units": cmd_list_units,
        "recent-events": cmd_recent_events,
        "migrate": cmd_migrate,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
