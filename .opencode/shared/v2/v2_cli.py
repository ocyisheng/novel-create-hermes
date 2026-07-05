"""
V2 CLI 工具 — 编排层 prompt 中调用的脚本入口。

常用命令：
    # 搜索与分析
    python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "天道宗"        # 关键词搜索
    python .opencode/shared/v2_cli.py search --path <PROJECT> --name "林昭"            # 按名称搜索（含邻居）
    python .opencode/shared/v2_cli.py search --path <PROJECT> --name "wr_c0585b9b"     # 按 ID 搜索（含邻居）
    python .opencode/shared/v2_cli.py search --path <PROJECT> --pattern "筑基.*期" --regex  # 正则搜索
    python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "剑" --scope SCENE  # 限定类型搜索
    python .opencode/shared/v2_cli.py check --path <PROJECT>                            # 一致性检查
    python .opencode/shared/v2_cli.py report --path <PROJECT>                           # 项目报告

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
    python .opencode/shared/v2_cli.py add-relation --path <PROJECT> --source <ID> --target <ID> --type <TYPE> --bidirectional
    python .opencode/shared/v2_cli.py fix-asymmetry --path <PROJECT>

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
    rtype = RelationType(args.type)
    rel = s.add_relation(args.source, args.target, rtype, actor=args.actor)
    if not rel:
        print("关系建立失败")
        return
    print(f"关系已建立: {rel.id}")
    # 双向模式：自动添加反向关系
    if getattr(args, "bidirectional", False):
        inv_type = rtype.inverse
        if inv_type != rtype:
            # 不同类型对（belongs_to ↔ contains 等）
            inv_rel = s.add_relation(args.target, args.source, inv_type, actor=args.actor)
        else:
            # 对称类型（references, allied_with 等）
            inv_rel = s.add_relation(args.target, args.source, rtype, actor=args.actor)
        if inv_rel:
            print(f"反向关系已建立: {inv_rel.id}")
    s.flush()


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


def cmd_fix_asymmetry(args):
    """扫描所有关系，补齐缺失的反向边。"""
    from graph_schema import RelationType
    from graph_store import GraphStore
    s = GraphStore(args.path)
    s.initialize()
    created = 0
    skipped = 0
    for rel in list(s._relations.values()):
        rtype = rel.relation_type
        inv_type = rtype.inverse
        if inv_type != rtype:
            rev_source, rev_target, rev_type = rel.target_id, rel.source_id, inv_type
        else:
            rev_source, rev_target, rev_type = rel.target_id, rel.source_id, rtype
        exists = any(
            r.source_id == rev_source and r.target_id == rev_target and r.relation_type == rev_type
            for r in s._relations.values()
        )
        if exists:
            skipped += 1
            continue
        r = s.add_relation(rev_source, rev_target, rev_type,
                           weight=rel.weight, description="auto-filled reverse",
                           actor="fix-asymmetry")
        if r:
            created += 1
    s.flush()
    print(f"检查了 {skipped + created} 条关系")
    print(f"补齐反向边: {created} 条新建, {skipped} 条已存在")


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


def cmd_search(args):
    """搜索叙事单元（关键词/正则/实体）"""
    from graph_store import GraphStore
    from search_engine import SearchEngine
    s = GraphStore(args.path)
    s.initialize()
    engine = SearchEngine(s)

    result = engine.search(
        keyword=args.keyword,
        pattern=args.pattern,
        name=args.name,
        scope=args.scope,
        regex=args.regex,
        case_sensitive=args.case_sensitive,
        max_results=args.limit,
    )
    print(engine.query_to_string(result))


def cmd_check(args):
    """一致性检查：输出供 LLM 分析的结构化数据"""
    from graph_store import GraphStore
    from search_engine import SearchEngine
    s = GraphStore(args.path)
    s.initialize()
    engine = SearchEngine(s)

    results = engine.check_consistency()
    if not results:
        print("一致性检查通过：未发现明显问题")
        return

    by_severity = {"error": [], "warning": [], "info": []}
    for r in results:
        by_severity.setdefault(r.severity, []).append(r)

    print(f"一致性检查结果 ({len(results)} 条):")
    print()
    for severity in ("error", "warning", "info"):
        items = by_severity.get(severity, [])
        if not items:
            continue
        label = {"error": "❌ 错误", "warning": "⚠️ 警告", "info": "ℹ️ 信息"}.get(severity, severity)
        print(f"  [{label}] ({len(items)} 条)")
        for r in items:
            print(f"    - [{r.rule_id}] {r.description}")
            if r.detail:
                for line in r.detail.split("\n"):
                    print(f"      {line}")
        print()


def cmd_report(args):
    """项目报告：统计 + gap 原始数据"""
    from graph_store import GraphStore
    from search_engine import SearchEngine
    from deviation_manager import DeviationManager
    s = GraphStore(args.path)
    s.initialize()

    # Graph 统计
    stats = s.stats()
    print("=" * 50)
    print("项目报告")
    print("=" * 50)
    print()
    print("【Graph 统计】")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 搜索引擎分析
    engine = SearchEngine(s)
    consistency = engine.check_consistency()
    print(f"\n【一致性检查】")
    if consistency:
        print(f"  共 {len(consistency)} 条:")
        by_sev = {}
        for r in consistency:
            by_sev.setdefault(r.severity, []).append(r)
        for sev in ("error", "warning", "info"):
            items = by_sev.get(sev, [])
            if items:
                print(f"    {sev}: {len(items)} 条")
    else:
        print("  未发现明显问题")

    # 偏差统计
    if args.with_deviations:
        mgr = DeviationManager(args.path)
        ds = mgr.stats()
        print(f"\n【偏差状态】")
        print(f"  全量扫描版本: v{ds['full_scan_version']}")
        print(f"  总偏差数: {ds['total']}")
        if ds['by_status']:
            print(f"  按状态: {ds['by_status']}")
        if ds['by_severity']:
            print(f"  按严重程度: {ds['by_severity']}")

    # Gap 分析
    print(f"\n【Gap 分析】")
    engine = SearchEngine(s)
    all_units = {u.type.value: [] for u in s._units.values()}
    for u in s._units.values():
        all_units.setdefault(u.type.value, []).append(u)

    for utype, units in sorted(all_units.items()):
        if not units:
            continue
        with_relations = 0
        for u in units:
            if s.get_relations(u.id):
                with_relations += 1
        total = len(units)
        active = sum(1 for u in units if u.status.value != "archived")
        pct = round(with_relations / total * 100) if total > 0 else 0
        print(f"  {utype:20s}: {total:3d} 个 ({active} 活跃), "
              f"{with_relations:3d} 个有关联 ({pct}%)")

    print(f"\n{'=' * 50}")


def cmd_viz(args):
    """生成可视化：全项目关系图 / 角色 Ego Network / 时间线"""
    # 委托给 v2_graph_viz.main()，避免重复维护两份相同逻辑
    import sys as _sys
    from pathlib import Path as _Path

    viz_argv = [
        "v2_graph_viz.py",
        "--project-root", str(_Path(args.path).resolve()),
    ]
    if args.character:
        viz_argv.extend(["--character", args.character])
    if args.timeline:
        viz_argv.extend(["--timeline", args.timeline])
    if args.output:
        viz_argv.extend(["--output", args.output])
    if args.open:
        viz_argv.append("--open")
    if getattr(args, 'incremental', False):
        viz_argv.append("--incremental")
    if getattr(args, 'force', False):
        viz_argv.append("--force")

    from v2_graph_viz import main as _viz_main
    _sys.argv = viz_argv
    _viz_main()


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

    p = sub.add_parser("add-relation", help="建立关系（支持 --bidirectional 自动补反向）")
    p.add_argument("--path", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--type", required=True, help="关系类型（participates_in/implements/references 等）")
    p.add_argument("--actor", default="script")
    p.add_argument("--bidirectional", action="store_true", help="同时添加反向关系")

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

    p = sub.add_parser("fix-asymmetry", help="补齐所有对称关系类型的缺失反向边")
    p.add_argument("--path", required=True)

    p = sub.add_parser("batch-infer", help="批量推断：扫描所有单元自动建立关系")
    p.add_argument("--path", required=True)

    p = sub.add_parser("export-docs", help="导出结构化文档（Markdown）到 graph/export/")
    p.add_argument("--path", required=True)
    p.add_argument("--out", default="", help="输出目录（默认 graph/export/）")

    p = sub.add_parser("export", help="导出 CHUNK 单元为章节 TXT 文件")
    p.add_argument("--path", required=True)
    p.add_argument("--out", default="", help="输出目录（默认 chapters/）")

    p = sub.add_parser("search", help="搜索叙事单元")
    p.add_argument("--path", required=True)
    p.add_argument("--keyword", default="", help="关键词搜索")
    p.add_argument("--pattern", default="", help="正则搜索（与 --keyword 互斥）")
    p.add_argument("--name", default="", help="实体搜索（按名称或ID，与 --keyword/--pattern 互斥）")
    p.add_argument("--scope", nargs="*", default=None, help="过滤单元类型（如 SCENE CHARACTER_ARC）")
    p.add_argument("--regex", action="store_true", help="启用正则模式")
    p.add_argument("--case-sensitive", dest="case_sensitive", action="store_true", help="区分大小写")
    p.add_argument("--limit", type=int, default=20, help="最大返回条数")

    p = sub.add_parser("check", help="一致性检查")
    p.add_argument("--path", required=True)

    p = sub.add_parser("report", help="项目报告（统计 + gap 原始数据）")
    p.add_argument("--path", required=True)
    p.add_argument("--with-deviations", action="store_true", help="包含偏差状态统计")

    p = sub.add_parser("viz", help="生成可视化：关系图 / 角色网络 / 时间线")
    p.add_argument("--path", "-p", required=True, help="项目根目录")
    p.add_argument("--character", "-c", default="", help="角色名称/ID：生成 Ego Network 关系图")
    p.add_argument("--timeline", "-t", default="", help="角色名称/ID：生成时间线")
    p.add_argument("--output", "-o", default="", help="输出 HTML 路径")
    p.add_argument("--open", action="store_true", help="生成后自动在浏览器打开")
    p.add_argument("--incremental", action="store_true",
                   help="增量模式：只重新生成有变化的页面（基于 unit.version）")
    p.add_argument("--force", action="store_true",
                   help="强制全量重建（忽略 --incremental）")

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
        "fix-asymmetry": cmd_fix_asymmetry,
        "batch-infer": cmd_batch_infer,
        "export-docs": cmd_export_docs,
        "export": cmd_export,
        "search": cmd_search,
        "check": cmd_check,
        "report": cmd_report,
        "viz": cmd_viz,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
