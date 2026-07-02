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


def cmd_get_unit(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    u = s.get_unit(args.id)
    if not u:
        print("NOT_FOUND")
        return
    print(f"名称: {u.unit_name}")
    print(f"类型: {u.type.value}")
    print(f"状态: {u.status.value}")
    print(f"确信度: {u.confidence}")
    print(f"标签: {', '.join(u.tags) if u.tags else '无'}")
    ch = f"第{u.belongs_to_chapter}章" if u.belongs_to_chapter else "无"
    print(f"章节: {ch}")
    if u.content:
        preview = u.content[:200].replace("\n", " ")
        print(f"内容: {preview}..." if len(u.content) > 200 else f"内容: {preview}")


def cmd_get_neighbors(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    neighbors = s.get_neighbors(args.id, max_depth=1)
    for nid in neighbors.get(1, set()):
        n = s.get_unit(nid)
        if n:
            print(f"{n.type.value}: {n.unit_name} ({nid})")


def cmd_add_relation(args):
    from graph_schema import RelationType
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    rel = s.add_relation(args.source, args.target, RelationType(args.type), actor=args.actor)
    if rel:
        s.flush()
        print(f"关系已建立: {rel.id}")
    else:
        print("关系建立失败")


def cmd_start_session(args):
    from graph_schema import UnitType
    from session import SessionManager
    mgr = SessionManager(args.path)
    mgr.load_user_state()
    if mgr.active_session:
        s = mgr.resume_session()
    else:
        s = mgr.start_session(focus_type=UnitType[args.type.upper()], focus_unit_id=args.id)
    mgr.save_user_state()
    print(f"SESSION={s.id}")


def cmd_create_unit(args):
    from graph_schema import UnitType
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    u = s.create_unit(
        type=UnitType[args.type.upper()],
        unit_name=args.name,
        content=args.content,
        tags=tags,
        belongs_to_chapter=int(args.chapter) if args.chapter else None,
        actor=args.actor,
    )
    s.flush()
    print(f"创建成功: {u.id}")


def cmd_flush(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    s.flush()
    print("graph 已持久化")


def cmd_build_workspace(args):
    from graph_store import GraphStore
    from workspace import WorkspaceBuilder
    s = GraphStore(args.path)
    s.initialize()
    b = WorkspaceBuilder(s)
    ws = b.build(args.id, preheat_level=args.level)
    print(ws.to_prompt_block(args.level))


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

    p = sub.add_parser("start-session", help="启动/恢复创作会话")
    p.add_argument("--path", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--id", required=True)

    p = sub.add_parser("find-unit", help="按名称查找叙事单元ID")
    p.add_argument("--path", required=True)
    p.add_argument("--name", required=True)

    p = sub.add_parser("create-unit", help="创建新叙事单元")
    p.add_argument("--path", required=True)
    p.add_argument("--type", required=True, help="SCENE / CHARACTER_ARC / PLOT_THREAD 等")
    p.add_argument("--name", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--tags", default="", help="逗号分隔的标签列表")
    p.add_argument("--chapter", default="", help="所属章节号")
    p.add_argument("--actor", default="script")

    p = sub.add_parser("get-unit", help="获取叙事单元详情")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)

    p = sub.add_parser("get-neighbors", help="查询关联关系")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)

    p = sub.add_parser("add-relation", help="建立关系")
    p.add_argument("--path", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--type", required=True, help="关系类型（participates_in/implements/references 等）")
    p.add_argument("--actor", default="script")

    p = sub.add_parser("flush", help="持久化 graph 数据")
    p.add_argument("--path", required=True)

    p = sub.add_parser("build-workspace", help="构建工作空间上下文")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--level", default="warm", choices=["cold", "warm", "hot"])

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
        "start-session": cmd_start_session,
        "find-unit": cmd_find_unit,
        "create-unit": cmd_create_unit,
        "get-unit": cmd_get_unit,
        "get-neighbors": cmd_get_neighbors,
        "add-relation": cmd_add_relation,
        "flush": cmd_flush,
        "build-workspace": cmd_build_workspace,
        "rebuild-projections": cmd_rebuild_projections,
        "stats": cmd_stats,
        "list-units": cmd_list_units,
        "recent-events": cmd_recent_events,
        "migrate": cmd_migrate,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
