"""
V2 CLI 工具 — 编排层 prompt 中调用的脚本入口。

常用命令：
    # 实体操作
    python .opencode/shared/v2_cli.py find-unit --path <PROJECT> --name <名称>
    python .opencode/shared/v2_cli.py get-unit --path <PROJECT> --id <ID>
    python .opencode/shared/v2_cli.py create-unit --path <PROJECT> --type <UnitType> --name <名称> --content <JSON>
    python .opencode/shared/v2_cli.py update-unit --path <PROJECT> --id <ID> [--file content.json | --content <JSON>] [--name <名称>] [--tags <标签>]
    python .opencode/shared/v2_cli.py list-units --path <PROJECT> --type <UnitType> [--limit N]

    # 关系查询（--rel-type 过滤，见 list-relation-types）
    python .opencode/shared/v2_cli.py get-neighbors --path <PROJECT> --id <ID> [--rel-type <TYPE>]

    # 关系操作
    python .opencode/shared/v2_cli.py add-relation --path <PROJECT> --source <ID> --target <ID> --type <TYPE>

    # 文档导出
    python .opencode/shared/v2_cli.py export-docs --path <PROJECT>
    python .opencode/shared/v2_cli.py export --path <PROJECT>

    # 统计与工具
    python .opencode/shared/v2_cli.py stats --path <PROJECT>
    python .opencode/shared/v2_cli.py list-relation-types
    python .opencode/shared/v2_cli.py batch-infer --path <PROJECT>

    # 可视化
    python .opencode/shared/v2_cli.py viz --path <PROJECT>                              # 全项目关系图
    python .opencode/shared/v2_cli.py viz --path <PROJECT> --character "韩致"           # 角色关系图
    python .opencode/shared/v2_cli.py viz --path <PROJECT> --timeline "韩致"            # 时间线
    python .opencode/shared/v2_cli.py viz --path <PROJECT> --output 图.html --open      # 自定义输出
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
        if args.verbose:
            print(f"内容:\n{u.content}")
        else:
            preview = u.content[:200].replace("\n", " ")
            print(f"内容: {preview}..." if len(u.content) > 200 else f"内容: {preview}")
            if len(u.content) > 200:
                print("（使用 --verbose 查看完整内容）")


def cmd_get_neighbors(args):
    from graph_schema import RelationType
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    rt = RelationType(args.rel_type) if args.rel_type else None
    neighbors = s.get_neighbors(args.id, relation_type=rt, max_depth=1)
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
    from relation_inferrer import RelationInferrer
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
    # 关系推断钩子：自动建立关联
    inferrer = RelationInferrer(s)
    created = inferrer.infer_on_create(u)
    s.flush()
    print(f"创建成功: {u.id}")
    if created:
        print(f"关系推断: 新增 {created} 条关联")


def cmd_update_unit(args):
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()

    content = None
    if args.file:
        import json
        with open(args.file, "r", encoding="utf-8-sig") as f:
            content = json.dumps(json.load(f), ensure_ascii=False)
    elif args.content:
        content = args.content

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None

    u = s.update_unit(
        unit_id=args.id,
        content=content,
        unit_name=args.name if args.name else None,
        tags=tags,
        actor=args.actor,
    )
    if not u:
        print("更新失败：叙事单元不存在")
        return

    s.flush()
    print(f"更新成功: {u.id}")
    print(f"  名称: {u.unit_name}")
    print(f"  版本: {u.version}")
    print(f"  标签: {', '.join(u.tags) if u.tags else '无'}")


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


def cmd_list_relation_types(args):
    from graph_schema import RelationType
    print("可用关系类型（--rel-type 参数值）:")
    print()
    for rt in RelationType:
        inv = rt.inverse
        inv_note = f" → 反向: {inv.value}" if inv != rt else "（对称）"
        print(f"  {rt.value:20s} {rt.name}{inv_note}")
    print()
    print("查询方向说明：")
    print("  get-neighbors 返回的是通过该关系类型连接到目标的所有单元")
    print("  如 --rel-type contains → 返回目标包含的下级")
    print("  如 --rel-type member_of → 返回声明属于目标的角色")


def cmd_list_units(args):
    from graph_schema import UnitType
    from graph_store import GraphStore
    import itertools
    s = GraphStore(args.path)
    s.initialize()
    t = args.type.upper() if args.type else ""
    ut = None
    if t and t != "ALL":
        ut = UnitType[t]
    limit = int(args.limit) if args.limit and int(args.limit) > 0 else None
    units = s.find_units(type=ut)
    if limit:
        units = itertools.islice(units, limit)
    for u in units:
        print(f"[{u.type.value}] {u.unit_name} [{u.status.value}]")


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


def cmd_batch_infer(args):
    """批量推断：扫描所有已有单元，自动建立关系"""
    from graph_store import GraphStore
    from relation_inferrer import RelationInferrer
    s = GraphStore(args.path)
    s.initialize()
    before = s.stats()["total_relations"]
    inferrer = RelationInferrer(s)

    def progress(i, total, created):
        print(f"  进度: {i}/{total} 单元, 已建 {created} 关系")

    print(f"开始批量推断 ({s.stats()['total_units']} 单元)...")
    total = inferrer.batch_infer_all(progress_callback=progress)

    after = s.stats()["total_relations"]
    print(f"\n批量推断完成:")
    print(f"  新建关系: {total}")
    print(f"  关系总计: {before} → {after}")


def cmd_export_docs(args):
    """导出结构化文档（Markdown）到 graph/export/"""
    from graph_store import GraphStore
    from projection_engine import ProjectionEngine
    s = GraphStore(args.path)
    s.initialize()
    p = ProjectionEngine(s, args.path)
    written = p.export_docs(output_dir=args.out)
    print(f"✅ 结构化文档已导出: {len(written)} 个文件")
    for w in written:
        print(f"   📄 {w}")
    print(f"\n   打开 index.md 开始浏览：")


def cmd_export(args):
    """导出 CHUNK 叙事单元为章节 TXT 文件"""
    from graph_schema import UnitType
    from graph_store import GraphStore
    from pathlib import Path
    s = GraphStore(args.path)
    s.initialize()
    chunks = s.find_units(type=UnitType.CHUNK)
    if not chunks:
        print("没有找到 CHUNK 类型的叙事单元")
        return
    out_dir = Path(args.out) if args.out else Path(args.path) / "chapters"
    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
    exported = 0
    for c in chunks:
        ch = c.belongs_to_chapter
        if ch:
            fname = f"第{ch}章.txt"
        else:
            fname = f"{c.unit_name}.txt"
        fpath = out_dir / fname
        fpath.write_text(c.content or "", encoding="utf-8")
        exported += 1
        print(f"  📄 {fpath.name}")
    print(f"\n导出完成: {exported} 个章节文件 → {out_dir}")


def cmd_viz(args):
    """生成可视化：全项目关系图 / 角色 Ego Network / 时间线"""
    from v2_graph_viz import V2GraphLoader, V2HTMLGenerator
    from pathlib import Path

    project_root = Path(args.path).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}")
        return

    # 读项目名
    project_name = project_root.name
    config_path = project_root / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if cfg and "项目名称" in cfg:
                project_name = cfg["项目名称"]
        except Exception:
            pass

    loader = V2GraphLoader(str(project_root))

    # 确定输出路径
    viz_dir = project_root / "graph" / "viz"
    if args.output:
        output_path = str(Path(args.output).resolve())
    else:
        viz_dir.mkdir(parents=True, exist_ok=True)
        if args.timeline:
            output_path = str(viz_dir / f"{args.timeline}_时间线.html")
        elif args.character:
            output_path = str(viz_dir / f"{args.character}_关系图.html")
        else:
            output_path = str(viz_dir / "全项目关系图.html")

    import webbrowser
    gen = V2HTMLGenerator(project_name)

    # 时间线模式
    if args.timeline:
        unit_id = loader.find_unit_id(args.timeline)
        if not unit_id:
            print(f"错误: 未找到单元: {args.timeline}")
            return
        data = loader.build_timeline(unit_id)
        if not data:
            print("错误: 无法生成时间线")
            return
        gen.generate_timeline(data, output_path)
        print(f"✅ 时间线已生成: {output_path}")
        print(f"   实体: {data['entity']['name']}")
        print(f"   事件: {len(data['events'])} 个")
        if args.open:
            webbrowser.open(output_path)
        return

    # 角色 Ego Network 模式
    if args.character:
        unit_id = loader.find_unit_id(args.character)
        if not unit_id:
            print(f"错误: 未找到角色/单元: {args.character}")
            return
        data = loader.build_character_network(unit_id)
        center_name = ""
        u = loader.store.get_unit(data.get("center_id", "")) if data.get("center_id") else None
        cname = u.unit_name if u else args.character
        graph_filename = Path(output_path).name
        gen.generate_graph(data, output_path)
        # 生成详情页
        detail_dir = viz_dir / "detail"
        gen.generate_detail_pages(data, str(detail_dir), graph_file=graph_filename)
        print(f"✅ 角色关系图已生成: {output_path}")
        print(f"   角色: {cname}")
        print(f"   节点: {len(data['nodes'])} 个, 关系: {len(data['edges'])} 条")
        if args.open:
            webbrowser.open(output_path)
        return

    # 默认：全项目图谱
    data = loader.build_full_graph()
    graph_filename = Path(output_path).name
    gen.generate_graph(data, output_path)
    # 生成详情页
    detail_dir = viz_dir / "detail"
    gen.generate_detail_pages(data, str(detail_dir), graph_file=graph_filename)
    print(f"✅ V2 关系图已生成: {output_path}")
    print(f"   节点: {len(data['nodes'])} 个, 关系: {len(data['edges'])} 条")
    stats = loader.store.stats()
    print(f"   V2 graph: {stats['total_units']} 叙事单元, {stats['total_relations']} 关系")
    if args.open:
        webbrowser.open(output_path)


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

    p = sub.add_parser("update-unit", help="更新叙事单元内容/名称/标签")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--content", default="", help="新内容（JSON 字符串，与 --file 二选一）")
    p.add_argument("--file", default="", help="从 JSON 文件读取新内容（优先于 --content）")
    p.add_argument("--name", default="", help="新名称")
    p.add_argument("--tags", default="", help="逗号分隔的标签列表")
    p.add_argument("--actor", default="script")

    p = sub.add_parser("get-unit", help="获取叙事单元详情")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--verbose", "-v", action="store_true", help="显示完整内容（默认截断前200字）")

    p = sub.add_parser("get-neighbors", help="查询关联关系（可按关系类型过滤）")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--rel-type", default="", help="关系类型（如 contains / has_member / located_at 等）")

    p = sub.add_parser("add-relation", help="建立关系")
    p.add_argument("--path", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--type", required=True, help="关系类型（participates_in/implements/references 等）")
    p.add_argument("--actor", default="script")

    p = sub.add_parser("list-relation-types", help="列出所有关系类型及用法")
    p.add_argument("--path", default="", help="（可选，仅用于上下文）")

    p = sub.add_parser("flush", help="持久化 graph 数据")
    p.add_argument("--path", required=True)

    p = sub.add_parser("build-workspace", help="构建工作空间上下文")
    p.add_argument("--path", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--level", default="warm", choices=["cold", "warm", "hot"])

    p = sub.add_parser("rebuild-projections", help="重建投影")
    p.add_argument("--path", required=True)
    p.add_argument("--mode", default="hybrid", choices=["in_place", "hybrid", "graph_only"])

    p = sub.add_parser("stats", help="graph 统计")
    p.add_argument("--path", required=True)

    p = sub.add_parser("list-units", help="列出叙事单元")
    p.add_argument("--path", required=True)
    p.add_argument("--type", default="", help="UnitType 名称（SCENE/CHARACTER_ARC 等）")
    p.add_argument("--limit", default="0", help="返回条数上限（0=全部）")

    p = sub.add_parser("recent-events", help="最近事件")
    p.add_argument("--path", required=True)
    p.add_argument("--limit", default="5")

    p = sub.add_parser("migrate", help="迁移项目到 V2")
    p.add_argument("--path", required=True)
    p.add_argument("--verify", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("batch-infer", help="批量推断：扫描所有单元自动建立关系")
    p.add_argument("--path", required=True)

    p = sub.add_parser("export-docs", help="导出结构化文档（Markdown）到 graph/export/")
    p.add_argument("--path", required=True)
    p.add_argument("--out", default="", help="输出目录（默认 graph/export/）")

    p = sub.add_parser("export", help="导出 CHUNK 单元为章节 TXT 文件")
    p.add_argument("--path", required=True)
    p.add_argument("--out", default="", help="输出目录（默认 chapters/）")

    p = sub.add_parser("viz", help="生成可视化：关系图 / 角色网络 / 时间线")
    p.add_argument("--path", "-p", required=True, help="项目根目录")
    p.add_argument("--character", "-c", default="", help="角色名称/ID：生成 Ego Network 关系图")
    p.add_argument("--timeline", "-t", default="", help="角色名称/ID：生成时间线")
    p.add_argument("--output", "-o", default="", help="输出 HTML 路径")
    p.add_argument("--open", action="store_true", help="生成后自动在浏览器打开")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "start-session": cmd_start_session,
        "find-unit": cmd_find_unit,
        "create-unit": cmd_create_unit,
        "update-unit": cmd_update_unit,
        "get-unit": cmd_get_unit,
        "get-neighbors": cmd_get_neighbors,
        "add-relation": cmd_add_relation,
        "flush": cmd_flush,
        "list-relation-types": cmd_list_relation_types,
        "build-workspace": cmd_build_workspace,
        "rebuild-projections": cmd_rebuild_projections,
        "stats": cmd_stats,
        "list-units": cmd_list_units,
        "recent-events": cmd_recent_events,
        "migrate": cmd_migrate,
        "batch-infer": cmd_batch_infer,
        "export-docs": cmd_export_docs,
        "export": cmd_export,
        "viz": cmd_viz,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
