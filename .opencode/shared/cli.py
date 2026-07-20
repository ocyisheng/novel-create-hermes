#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-create-hermes 统一 CLI 入口。

所有 argparse 集中在此，功能脚本中不再有 argparse 代码。
调用 handlers 模块中的纯业务函数，只做参数提取和输出格式化。

用法:
    python .opencode/shared/cli.py viz --project-root <路径> [选项]
    python .opencode/shared/cli.py migrate --project-root <路径> [选项]
    python .opencode/shared/cli.py project <command> [参数]
    python .opencode/shared/cli.py env [--fix|--force] [--root <路径>]
    python .opencode/shared/cli.py v2 <command> [--path <PROJECT>] [args...]
"""

import sys
import os
import argparse

_SHARED_DIR = os.path.dirname(os.path.abspath(__file__))
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)


# ── viz ────────────────────────────────────────────────────────────

def _build_viz_parser(sub):
    p = sub.add_parser("viz", help="生成叙事单元网络可视化")
    p.add_argument("--project-root", "-p", required=True, help="项目根目录")
    p.add_argument("--output", "-o", default="", help="输出 HTML 路径")
    p.add_argument("--character", "-c", default="", help="角色名称/ID：生成 Ego Network")
    p.add_argument("--timeline", "-t", default="", help="角色名称/ID：生成时间线")
    p.add_argument("--list-units", action="store_true", help="列出所有叙事单元")
    p.add_argument("--open", action="store_true", help="生成后自动在浏览器打开")
    p.add_argument("--incremental", action="store_true", help="增量模式")
    p.add_argument("--force", action="store_true", help="强制全量重建")
    return p


def _run_viz(args):
    from handlers import handle_viz
    result = handle_viz(
        project_root=args.project_root,
        output=args.output,
        character=args.character,
        timeline=args.timeline,
        list_units=args.list_units,
        open_browser=args.open,
        incremental=args.incremental,
        force=args.force,
    )
    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)
    print("✅ 可视化已生成")


# ── migrate ─────────────────────────────────────────────────────────

def _build_migrate_parser(sub):
    p = sub.add_parser("migrate", help="V1→V2 迁移")
    p.add_argument("--project-root", required=True, help="项目根目录绝对路径")
    p.add_argument("--dry-run", action="store_true", help="只扫描不写入")
    p.add_argument("--verify", action="store_true", help="迁移后执行验证")
    p.add_argument("--report", action="store_true", help="生成迁移报告")
    p.add_argument("--list-projects", action="store_true", help="列出可迁移的项目")
    p.add_argument("--novels-root", default="", help="NOVELS_ROOT 路径（用于 --list-projects）")
    p.add_argument("--normalize", action="store_true", help="统一 graph/nodes.jsonl 中子类型字段")
    return p


def _run_migrate(args):
    from v2.migrate import run_migration, find_projects, normalize_subtype_fields

    if args.list_projects:
        base = args.novels_root or os.path.join(os.getcwd(), "novels")
        projects = find_projects(base)
        if projects:
            print(f"发现 {len(projects)} 个项目:")
            for p in projects:
                print(f"  {os.path.join(base, p)}")
        else:
            print(f"在 {base} 下未找到项目（没有 config.yaml 的目录）")
        return

    if args.normalize:
        if not args.project_root:
            print("错误: --normalize 需要 --project-root")
            sys.exit(1)
        stats = normalize_subtype_fields(args.project_root, dry_run=args.dry_run)
        print(f"扫描节点: {stats.get('nodes_scanned', 0)}")
        print(f"修复节点: {stats.get('nodes_fixed', 0)}")
        if "by_type" in stats:
            for t, n in sorted(stats["by_type"].items()):
                print(f"  {t}: {n}")
        if "error" in stats:
            print(f"❌ {stats['error']}")
        elif stats.get("nodes_fixed", 0) == 0:
            print("✅ 无需迁移")
        elif not args.dry_run:
            print("✅ 迁移完成（备份: nodes.jsonl.bak）")
        return

    run_migration(
        project_root=args.project_root,
        dry_run=args.dry_run,
        verify=args.verify,
        report=args.report,
    )


# ── project ─────────────────────────────────────────────────────────

def _build_project_parser(sub):
    p = sub.add_parser("project", help="项目管理")
    p_sub = p.add_subparsers(dest="command")

    pn = p_sub.add_parser("new", help="新建小说项目")
    pn.add_argument("name", help="项目名称")
    pn.add_argument("genre", help="项目类型（玄幻/仙侠/都市/悬疑/科幻...）")
    pn.add_argument("--volumes", type=int, default=3, help="卷数（默认 3）")
    pn.add_argument("--acts", type=int, default=3, help="幕数（默认 3）")
    pn.add_argument("--structure", default="三幕", help="结构类型名称（默认 三幕）")
    pn.add_argument("--v2", action="store_true", help="创建 V2 原生项目")

    pi = p_sub.add_parser("import", help="导入已有小说")
    pi.add_argument("source", help="源路径")
    pi.add_argument("name", help="项目名称")
    pi.add_argument("--volumes", type=int, default=3, help="卷数（默认 3）")

    ps = p_sub.add_parser("status", help="查看项目状态")
    ps.add_argument("name", help="项目名称")
    ps.add_argument("--phase", default="", help="更新阶段标识")

    pr = p_sub.add_parser("resume", help="续写项目")
    pr.add_argument("name", help="项目名称")

    pw = p_sub.add_parser("switch", help="切换项目")
    pw.add_argument("name", help="目标项目名称")
    pw.add_argument("--dry-run", action="store_true", help="仅预览，不修改")
    pw.add_argument("--skip-sync", action="store_true", help="跳过索引同步")
    pw.add_argument("--no-verify", action="store_true", help="跳过验证")

    pd = p_sub.add_parser("delete", help="删除项目")
    pd.add_argument("name", help="项目名称")
    pd.add_argument("--force", action="store_true", help="跳过确认")

    return p


def _run_project(args):
    if not args.command:
        print("错误: project 需要子命令 (new/import/status/resume/switch/delete)")
        sys.exit(1)

    from handlers import (
        handle_project_new, handle_project_import, handle_project_status,
        handle_project_resume, handle_project_switch, handle_project_delete,
    )

    if args.command == "new":
        result = handle_project_new(
            name=args.name, genre=args.genre,
            v2=args.v2, volumes=args.volumes,
            acts=args.acts, structure=args.structure,
        )
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        if result.get("v2"):
            print(f"✅ V2 项目「{args.name}」创建完成！")
            print(f"   路径: {result['path']}")
            if result.get("graph_initialized"):
                print(f"   graph/: nodes.jsonl + edges.jsonl + events.olog 已就绪")
            print()
            print(f"   开始创作：直接告诉 novel-writer Agent 即可")
        else:
            print(f"✅ 项目「{args.name}」创建完成！")
            print(f"   路径: {result['path']}")
            print(f"   类型: {args.genre}")
            print(f"   结构: {args.volumes}卷/{args.acts}幕 ({args.structure})")
            print(f"   章节: {result.get('chapters', 0)} 章")

    elif args.command == "import":
        result = handle_project_import(name=args.name, source_path=args.source)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        print(f"✅ 导入完成！项目「{args.name}」")
        print(f"   路径: {result['path']}")
        if not result.get("has_graph"):
            print()
            print(f"💡 建议执行 V2 迁移以获得完整功能：")
            print(f"   python .opencode/shared/cli.py migrate "
                  f"--project-root \"{result['path']}\" --verify --report")
            print(f"   python .opencode/shared/cli.py v2 batch-infer "
                  f"--path \"{result['path']}\"")

    elif args.command == "status":
        result = handle_project_status(name=args.name, phase=args.phase)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        config = result.get("config", {})
        print(f"━━━ 项目状态: {args.name} ━━━")
        print(f"类型: {config.get('项目类型', '未设置')}")
        print(f"活跃风格: {config.get('活跃风格', '未设置')}")
        print(f"当前状态: {config.get('当前状态', '未设置')}")
        print(f"预期结构: {config.get('预期结构', '未设置')}")
        prog = config.get("写作进度", {})
        print(f"写作进度: 第{prog.get('当前卷', 0)}卷 第{prog.get('当前章', 0)}章")
        goals = config.get("创作目标", {})
        print(f"目标章节: {goals.get('目标章节数', 0)}")
        print(f"目标字数: {goals.get('目标字数', 0)}")
        if result.get("is_v2"):
            stats = result.get("stats", {})
            print(f"架构: V2（叙事单元网络）")
            print(f"叙事单元: {stats.get('total_units', '?')}")
            if stats.get('by_type'):
                for typ, count in sorted(stats['by_type'].items()):
                    print(f"  {typ}: {count}")
            print(f"关系: {stats.get('total_relations', '?')}")
        else:
            print(f"架构: V1（YAML 文件）")

    elif args.command == "resume":
        result = handle_project_resume(name=args.name)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        print(f"✅ 项目「{args.name}」已刷新，可以继续创作")

    elif args.command == "switch":
        result = handle_project_switch(
            name=args.name, dry_run=getattr(args, "dry_run", False)
        )
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        if result.get("dry_run"):
            print(f"🔍 [Dry Run] 将切换到项目: {args.name}")
        else:
            print(f"✅ 已切换到项目「{args.name}」")
            print(f"   路径: {result['path']}")
            print(f"   类型: {result.get('genre', '未知')}")
        if result.get("has_graph"):
            print(f"   V2: ✅ 已迁移（graph 就绪）")
        else:
            print(f"   V2: ⬜ 未迁移（可执行 V2 迁移）")

    elif args.command == "delete":
        result = handle_project_delete(name=args.name, force=args.force)
        if "error" in result:
            if result.get("needs_force"):
                print(f"⚠️  确认删除项目「{args.name}」?")
                print(f"   此操作不可恢复！")
                print(f"   使用 --force 跳过确认")
                sys.exit(0)
            print(f"❌ {result['error']}")
            sys.exit(1)
        print(f"✅ 项目「{args.name}」已删除")


# ── env ─────────────────────────────────────────────────────────────

def _build_env_parser(sub):
    p = sub.add_parser("env", help="环境验证与修复")
    p.add_argument("--fix", action="store_true", help="自动修复缺失依赖")
    p.add_argument("--force", action="store_true", help="强制重建 .venv")
    p.add_argument("--root", type=str, default="",
                   help="工具根目录（.venv 所在位置）")
    return p


def _run_env(args):
    from handlers import handle_env_check, handle_env_fix, handle_env_force

    if args.force:
        result = handle_env_force()
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        print(f"✅ .venv 已重建: {result.get('venv_path')}")
        return

    if args.fix:
        result = handle_env_fix()
        if result.get("ok"):
            print("✅ 依赖安装完成")
        else:
            print(f"❌ 依赖安装失败: {result.get('stderr', '')}")
            sys.exit(1)
        return

    result = handle_env_check()
    print(f"Python: {result['python_version']} "
          f"{'✅' if result['python_ok'] else '❌ 需 >= 3.8'}")
    print(f".venv:   {'✅' if result['venv_exists'] else '❌ 不存在'}")
    if result['venv_exists']:
        print(f"  路径: {result['venv_path']}")
    if result.get('deps_ok'):
        print(f"依赖:    ✅ 已安装")
    elif result.get('missing_deps'):
        print(f"依赖:    ⚠️ 缺失: {', '.join(result['missing_deps'])}")


# ── v2 工具集（argparse + 输出格式化，业务逻辑在 handlers 中）────────────

def _build_v2_parser(sub):
    p = sub.add_parser("v2", help="V2 工具集（search/check/report/create-unit/viz/stats 等）")
    v2_sub = p.add_subparsers(dest="v2_command")

    sp = v2_sub.add_parser("start-session", help="启动/恢复创作会话")
    sp.add_argument("--path", required=True)
    sp.add_argument("--focus-type", required=True)
    sp.add_argument("--id", required=True)

    sp = v2_sub.add_parser("find-unit", help="按名称查找叙事单元ID")
    sp.add_argument("--path", required=True)
    sp.add_argument("--name", required=True)

    sp = v2_sub.add_parser("create-unit", help="创建新叙事单元")
    sp.add_argument("--path", required=True)
    sp.add_argument("--unit-type", required=True, help="SCENE / CHARACTER_ARC / PLOT_THREAD 等")
    sp.add_argument("--name", required=True)
    sp.add_argument("--content", default="", help="内容（JSON 字符串，与 --file 二选一）")
    sp.add_argument("--data", default="", help="同 --content（别名）")
    sp.add_argument("--file", default="", help="从 JSON 文件读取内容（优先于 --content/--data）")
    sp.add_argument("--tags", default="", help="逗号分隔的标签列表")
    sp.add_argument("--chapter", default="", help="所属章节号")
    sp.add_argument("--actor", default="script")

    sp = v2_sub.add_parser("update-unit", help="更新叙事单元内容/名称/标签")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)
    sp.add_argument("--content", default="", help="新内容（JSON 字符串，与 --file 二选一）")
    sp.add_argument("--data", default="", help="同 --content（别名）")
    sp.add_argument("--file", default="", help="从 JSON 文件读取新内容（优先于 --content/--data）")
    sp.add_argument("--name", default="", help="新名称")
    sp.add_argument("--tags", default="", help="逗号分隔的标签列表")
    sp.add_argument("--actor", default="script")

    sp = v2_sub.add_parser("get-unit", help="获取叙事单元详情")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)
    sp.add_argument("--verbose", "-v", action="store_true", help="显示完整内容（默认截断前200字）")

    sp = v2_sub.add_parser("get-neighbors", help="查询关联关系（可按关系类型过滤）")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)
    sp.add_argument("--rel-type", default="", help="关系类型（如 contains/has_member/located_at）")
    sp.add_argument("--limit", type=int, default=0, help="最大返回数量（0=不限）")

    sp = v2_sub.add_parser("add-relation", help="建立关系（支持 --bidirectional 自动补反向）")
    sp.add_argument("--path", required=True)
    sp.add_argument("--source", required=True)
    sp.add_argument("--target", required=True)
    sp.add_argument("--rel-type", required=True, help="关系类型（participates_in/implements/references 等）")
    sp.add_argument("--actor", default="script")
    sp.add_argument("--bidirectional", action="store_true", help="同时添加反向关系")

    sp = v2_sub.add_parser("list-relation-types", help="列出所有关系类型及用法")

    sp = v2_sub.add_parser("flush", help="持久化 graph 数据")
    sp.add_argument("--path", required=True)

    sp = v2_sub.add_parser("build-workspace", help="构建工作空间上下文")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)
    sp.add_argument("--level", default="warm", choices=["cold", "warm", "hot"])

    sp = v2_sub.add_parser("rebuild-projections", help="重建投影")
    sp.add_argument("--path", required=True)
    sp.add_argument("--mode", default="hybrid", choices=["in_place", "hybrid", "graph_only"])

    sp = v2_sub.add_parser("stats", help="graph 统计")
    sp.add_argument("--path", required=True)

    sp = v2_sub.add_parser("list-units", help="列出叙事单元")
    sp.add_argument("--path", required=True)
    sp.add_argument("--unit-type", default="", help="UnitType 名称（SCENE/CHARACTER_ARC 等）")
    sp.add_argument("--limit", default="0", help="返回条数上限（0=全部）")

    sp = v2_sub.add_parser("recent-events", help="最近事件")
    sp.add_argument("--path", required=True)
    sp.add_argument("--limit", default="5")

    sp = v2_sub.add_parser("fix-asymmetry", help="补齐所有对称关系类型的缺失反向边")
    sp.add_argument("--path", required=True)

    sp = v2_sub.add_parser("batch-infer", help="批量推断：扫描所有单元自动建立关系")
    sp.add_argument("--path", required=True)

    sp = v2_sub.add_parser("export-docs", help="导出结构化文档（Markdown）到 graph/export/")
    sp.add_argument("--path", required=True)
    sp.add_argument("--out", default="", help="输出目录（默认 graph/export/）")

    sp = v2_sub.add_parser("export", help="导出 CHUNK 单元为章节 TXT 文件")
    sp.add_argument("--path", required=True)
    sp.add_argument("--out", default="", help="输出目录（默认 chapters/）")

    sp = v2_sub.add_parser("search", help="搜索叙事单元")
    sp.add_argument("--path", required=True)
    sp.add_argument("--keyword", default="", help="关键词搜索")
    sp.add_argument("--pattern", default="", help="正则搜索（与 --keyword 互斥）")
    sp.add_argument("--name", default="", help="实体搜索（按名称或ID，与 --keyword/--pattern 互斥）")
    sp.add_argument("--scope", nargs="*", default=None, help="过滤单元类型（如 SCENE CHARACTER_ARC）")
    sp.add_argument("--regex", action="store_true", help="启用正则模式")
    sp.add_argument("--case-sensitive", dest="case_sensitive", action="store_true", help="区分大小写")
    sp.add_argument("--limit", type=int, default=20, help="最大返回条数")

    sp = v2_sub.add_parser("check", help="一致性检查")
    sp.add_argument("--path", required=True)
    sp.add_argument("--limit", type=int, default=0, help="最大显示条数（0=全部）")

    sp = v2_sub.add_parser("report", help="项目报告（统计 + gap 原始数据）")
    sp.add_argument("--path", required=True)
    sp.add_argument("--with-deviations", action="store_true", help="包含偏差状态统计")

    sp = v2_sub.add_parser("read-knowledge", help="查询知识库（book-knowledge）")
    sp.add_argument("--path", required=True, help="项目根目录（含 knowledge/）")
    sp.add_argument("--slug", required=True, help="知识库 slug（如 fanren-xiuxian）")
    sp.add_argument("--topic", required=True, help="搜索主题（支持正则，如 宗门|势力|门派）")

    sp = v2_sub.add_parser("viz", help="生成可视化：关系图 / 角色网络 / 时间线")
    sp.add_argument("--path", "-p", required=True, help="项目根目录")
    sp.add_argument("--character", "-c", default="", help="角色名称/ID：生成 Ego Network")
    sp.add_argument("--timeline", "-t", default="", help="角色名称/ID：生成时间线")
    sp.add_argument("--output", "-o", default="", help="输出 HTML 路径")
    sp.add_argument("--open", action="store_true", help="生成后自动在浏览器打开")
    sp.add_argument("--incremental", action="store_true", help="增量模式")
    sp.add_argument("--force", action="store_true", help="强制全量重建")

    sp = v2_sub.add_parser("find-descendants", help="递归查找所有后代（CONTAINS）")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)
    sp.add_argument("--max-depth", type=int, default=10, help="递归深度（默认 10）")

    sp = v2_sub.add_parser("find-ancestors", help="递归查找所有祖先（CONTAINS）")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)

    sp = v2_sub.add_parser("rebuild-structure-path", help="从 CONTAINS 关系重建结构路径")
    sp.add_argument("--path", required=True)
    sp.add_argument("--id", required=True)

    sp = v2_sub.add_parser("migrate-structure", help="将结构路径字段迁移为 CONTAINS 边")
    sp.add_argument("--path", required=True)

    sp = v2_sub.add_parser("purge-archived", help="物理删除所有已归档(archived)的叙事单元及其关联边")
    sp.add_argument("--path", required=True)
    sp.add_argument("--ids", default="", help="逗号分隔的单元 ID 列表；为空则删除全部 archived 单元")
    sp.add_argument("--actor", default="script")

    return p


# ── v2 dispatch ──────────────────────────────────────────────────────────

def _run_v2(args):
    """直接调 handlers，不再经过 v2_cli.py。"""
    from handlers import (
        handle_get_unit, handle_find_unit, handle_create_unit, handle_update_unit,
        handle_get_neighbors, handle_search, handle_check_consistency,
        handle_list_units, handle_list_relation_types, handle_stats,
        handle_recent_events, handle_flush, handle_add_relation,
        handle_fix_asymmetry, handle_batch_infer, handle_export_docs,
        handle_export_chunks, handle_viz, handle_find_descendants,
        handle_find_ancestors, handle_rebuild_structure_path,
        handle_migrate_structure_to_edges, handle_session_start,
        handle_session_build_workspace, handle_purge_archived,
    )

    def _err_exit(result, msg="操作失败"):
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)

    cmd = args.v2_command

    # Phase 2 fallback: 未在手动 if/elif 中注册的操作尝试自动 dispatch
    from cli_gen import dispatch_registry_command
    if cmd and dispatch_registry_command(args):
        return

    if cmd == "start-session":
        result = handle_session_start(project_root=args.path, focus_type=args.focus_type, id=args.id)
        _err_exit(result)
        print(f"SESSION={result['session_id']}")

    elif cmd == "find-unit":
        result = handle_find_unit(project_root=args.path, name=args.name)
        _err_exit(result)
        print(result.get("id") or "NOT_FOUND")

    elif cmd == "create-unit":
        result = handle_create_unit(
            project_root=args.path, unit_type=args.unit_type, name=args.name,
            content=args.content or args.data or None,
            file_path=args.file or None,
            tags=args.tags or None,
            chapter=int(args.chapter) if args.chapter else None,
            actor=args.actor,
        )
        _err_exit(result)
        print(f"创建成功: {result['id']}")
        if result.get('relations_created'):
            print(f"关系推断: 新增 {result['relations_created']} 条关联")
        if result.get('schema_errors'):
            for se in result['schema_errors']:
                print(f"  ⚠️  {se}")

    elif cmd == "update-unit":
        result = handle_update_unit(
            project_root=args.path, id=args.id,
            content=args.content or None, file_path=args.file or None,
            name=args.name or None, tags=args.tags or None,
            actor=args.actor,
        )
        _err_exit(result)
        print(f"更新成功: {result['id']}")
        print(f"  名称: {result.get('name', '')}")
        print(f"  版本: {result.get('version', '')}")
        print(f"  标签: {', '.join(result.get('tags', [])) or '无'}")

    elif cmd == "get-unit":
        result = handle_get_unit(project_root=args.path, id=args.id)
        _err_exit(result)
        u = result.get("unit")
        if not u:
            print("NOT_FOUND")
            return
        from graph_schema import get_unit_chapter
        store = __import__('graph_store', fromlist=['GraphStore'])
        print(f"名称: {u['name']}")
        print(f"类型: {u['type']}")
        print(f"状态: {u['status']}")
        print(f"确信度: {u.get('confidence', '')}")
        print(f"标签: {', '.join(u.get('tags', [])) or '无'}")
        ch = f"第{u.get('chapter', '')}章" if u.get('chapter') else "无"
        print(f"章节: {ch}")
        content = u.get('content', '')
        if content:
            if args.verbose:
                print(f"内容:\n{content}")
            else:
                preview = content[:200].replace("\n", " ")
                print(f"内容: {preview}..." if len(content) > 200 else f"内容: {preview}")
                if len(content) > 200:
                    print("（使用 --verbose 查看完整内容）")

    elif cmd == "get-neighbors":
        result = handle_get_neighbors(
            project_root=args.path, id=args.id,
            rel_type=args.rel_type, limit=args.limit,
        )
        _err_exit(result)
        for n in result.get("neighbors", []):
            print(f"{n['type']}: {n['name']} ({n['id']})")

    elif cmd == "add-relation":
        result = handle_add_relation(
            project_root=args.path, source=args.source,
            target=args.target, rel_type=args.rel_type,
            bidirectional=args.bidirectional, actor=args.actor,
        )
        _err_exit(result)
        print(f"关系已建立: {result.get('id', '')}")
        if result.get('inverse_id'):
            print(f"反向关系已建立: {result['inverse_id']}")

    elif cmd == "list-relation-types":
        result = handle_list_relation_types()
        print("可用关系类型（--rel-type 参数值）:")
        print()
        for rt in result.get("relation_types", []):
            inv_note = f" → 反向: {rt['inverse']}" if rt['inverse'] != rt['value'] else "（对称）"
            print(f"  {rt['value']:20s} {rt['name']}{inv_note}")
        print()
        print("查询方向说明：")
        print("  get-neighbors 返回的是通过该关系类型连接到目标的所有单元")

    elif cmd == "flush":
        result = handle_flush(project_root=args.path)
        _err_exit(result)
        print("graph 已持久化")

    elif cmd == "build-workspace":
        result = handle_session_build_workspace(
            project_root=args.path, id=args.id, level=args.level,
        )
        _err_exit(result)
        print(result.get("context", ""))

    elif cmd == "rebuild-projections":
        from projection_engine import ProjectionEngine
        from graph_store import GraphStore
        store = GraphStore(args.path)
        store.initialize()
        p = ProjectionEngine(store, args.path, output_mode=args.mode)
        p.rebuild_all()
        print("投影已重建")

    elif cmd == "stats":
        result = handle_stats(project_root=args.path)
        _err_exit(result)
        for k, v in result.items():
            print(f"{k}: {v}")

    elif cmd == "list-units":
        from graph_schema import UnitType
        result = handle_list_units(
            project_root=args.path, unit_type=args.unit_type,
            limit=int(args.limit) if args.limit and int(args.limit) > 0 else 0,
        )
        _err_exit(result)
        for u in result.get("units", []):
            print(f"[{u['type']}] {u['name']} [{u['status']}]")

    elif cmd == "recent-events":
        limit = int(args.limit) if args.limit else 5
        result = handle_recent_events(project_root=args.path, limit=limit)
        _err_exit(result)
        for e in result.get("events", []):
            print(f"[{e['timestamp']}] {e['actor']}: {e['event_type']}")

    elif cmd == "fix-asymmetry":
        result = handle_fix_asymmetry(project_root=args.path)
        _err_exit(result)
        total = result.get("created", 0) + result.get("skipped", 0)
        print(f"检查了 {total} 条关系")
        print(f"补齐反向边: {result.get('created', 0)} 条新建, {result.get('skipped', 0)} 条已存在")

    elif cmd == "batch-infer":
        result = handle_batch_infer(project_root=args.path)
        _err_exit(result)
        before = result.get("total_before", 0)
        after = result.get("total_after", 0)
        print(f"批量推断完成:")
        print(f"  新建关系: {result.get('new_relations', 0)}")
        print(f"  关系总计: {before} → {after}")

    elif cmd == "export-docs":
        result = handle_export_docs(project_root=args.path, out=args.out)
        _err_exit(result)
        files = result.get("files", [])
        print(f"✅ 结构化文档已导出: {len(files)} 个文件")
        for w in files:
            print(f"   📄 {w}")

    elif cmd == "export":
        result = handle_export_chunks(project_root=args.path, out=args.out)
        _err_exit(result)
        files = result.get("files", [])
        print(f"导出完成: {len(files)} 个章节文件")

    elif cmd == "search":
        result = handle_search(
            project_root=args.path, keyword=args.keyword,
            pattern=args.pattern, name=args.name,
            scope=args.scope, regex=args.regex,
            case_sensitive=args.case_sensitive, limit=args.limit,
        )
        _err_exit(result)
        total = result.get("total", 0)
        time_ms = result.get("time_ms", 0)
        print(f"找到 {total} 条结果 ({time_ms}ms)")
        for r in result.get("results", []):
            preview = r.get("content_preview", "")[:80].replace("\n", " ")
            print(f"  [{r['unit_type']}] {r['unit_name']} ({r['unit_id']})")
            if preview:
                print(f"    {preview}")

    elif cmd == "check":
        result = handle_check_consistency(project_root=args.path)
        _err_exit(result)
        findings = result.get("findings", [])
        if not findings:
            print("一致性检查通过：未发现明显问题")
            return
        by_severity = {"error": [], "warning": [], "info": []}
        for r in findings:
            by_severity.setdefault(r.get("severity"), []).append(r)
        print(f"一致性检查结果 ({len(findings)} 条):")
        shown = 0
        for severity in ("error", "warning", "info"):
            items = by_severity.get(severity, [])
            if not items:
                continue
            label = {"error": "❌ 错误", "warning": "⚠️ 警告", "info": "ℹ️ 信息"}.get(severity, severity)
            print(f"  [{label}] ({len(items)} 条)")
            for r in items:
                print(f"    - [{r['rule_id']}] {r.get('description', '')}")
                if r.get('detail'):
                    for line in r['detail'].split("\n"):
                        print(f"      {line}")
                shown += 1
                if args.limit > 0 and shown >= args.limit:
                    break
            if args.limit > 0 and shown >= args.limit:
                break

    elif cmd == "report":
        result = handle_stats(project_root=args.path)
        _err_exit(result)
        print("=" * 50)
        print("项目报告")
        print("=" * 50)
        print()
        print("【Graph 统计】")
        for k, v in result.items():
            print(f"  {k}: {v}")

        check_result = handle_check_consistency(project_root=args.path)
        findings = check_result.get("findings", [])
        print(f"\n【一致性检查】")
        if findings:
            print(f"  共 {len(findings)} 条:")
            by_sev = {}
            for r in findings:
                by_sev.setdefault(r.get("severity"), []).append(r)
            for sev in ("error", "warning", "info"):
                items = by_sev.get(sev, [])
                if items:
                    print(f"    {sev}: {len(items)} 条")
        else:
            print("  未发现明显问题")

        if args.with_deviations:
            from handlers import handle_deviation_stats
            ds = handle_deviation_stats(project_root=args.path)
            print(f"\n【偏差状态】")
            print(f"  全量扫描版本: v{ds.get('full_scan_version', 0)}")
            print(f"  总偏差数: {ds.get('total', 0)}")
            if ds.get('by_status'):
                print(f"  按状态: {ds['by_status']}")
            if ds.get('by_severity'):
                print(f"  按严重程度: {ds['by_severity']}")

        print(f"\n【Gap 分析】")
        from graph_schema import UnitType
        from graph_store import GraphStore
        store = GraphStore(args.path)
        store.initialize()
        all_units = {}
        for u in store._units.values():
            all_units.setdefault(u.type.value, []).append(u)
        for utype, units in sorted(all_units.items()):
            if not units:
                continue
            with_relations = 0
            for u in units:
                if store.get_relations(u.id):
                    with_relations += 1
            total = len(units)
            active = sum(1 for u in units if u.status.value != "archived")
            pct = round(with_relations / total * 100) if total > 0 else 0
            print(f"  {utype:20s}: {total:3d} 个 ({active} 活跃), "
                  f"{with_relations:3d} 个有关联 ({pct}%)")
        print(f"\n{'=' * 50}")

    elif cmd == "read-knowledge":
        from handlers import handle_knowledge_read
        result = handle_knowledge_read(
            project_root=args.path, slug=args.slug, topic=args.topic,
        )
        _err_exit(result)
        slug = result.get("slug", "")
        title = result.get("title", slug)
        author = result.get("author", "")
        chapter_count = result.get("chapter_count", "?")
        print(f"## Reference: {slug}")
        print(f"### Source")
        print(f"{title} — {author} ({chapter_count} chapters)")
        print()
        content = result.get("content", "")
        if content:
            print(content)

    elif cmd == "viz":
        result = handle_viz(
            project_root=args.path, character=args.character,
            timeline=args.timeline, output=args.output,
            open_browser=args.open, incremental=args.incremental,
            force=args.force,
        )
        _err_exit(result)
        print("✅ 可视化已生成")

    elif cmd == "find-descendants":
        result = handle_find_descendants(
            project_root=args.path, id=args.id, max_depth=args.max_depth,
        )
        _err_exit(result)
        descendants = result.get("descendants", [])
        if not descendants:
            print("未找到后代单元")
            return
        print(f"找到 {len(descendants)} 个后代单元:")
        for u in descendants:
            ch = f" [第{u.get('chapter')}章]" if u.get("chapter") else ""
            print(f"  • {u['type']}: {u['name']} ({u['id']}){ch}")

    elif cmd == "find-ancestors":
        result = handle_find_ancestors(project_root=args.path, id=args.id)
        _err_exit(result)
        ancestors = result.get("ancestors", [])
        if not ancestors:
            print("未找到祖先单元")
            return
        print(f"找到 {len(ancestors)} 个祖先单元:")
        for u in ancestors:
            print(f"  • {u['type']}: {u['name']} ({u['id']})")

    elif cmd == "rebuild-structure-path":
        result = handle_rebuild_structure_path(project_root=args.path, id=args.id)
        _err_exit(result)
        path = result.get("structure_path", [])
        if not path:
            print("未重建出结构路径")
            return
        print(f"结构路径 ({len(path)} 级):")
        for item in path:
            print(f"  [{item.get('level', '?')}] {item.get('id', '')}")

    elif cmd == "migrate-structure":
        result = handle_migrate_structure_to_edges(project_root=args.path)
        _err_exit(result)
        print(f"迁移完成:")
        print(f"  新建边: {result.get('edges_created', 0)}")
        print(f"  已存在: {result.get('edges_skipped', 0)}")
        print(f"  错误:   {result.get('errors', 0)}")
        if result.get("details"):
            for d in result["details"][:10]:
                print(f"  • {d}")

    elif cmd == "purge-archived":
        result = handle_purge_archived(
            project_root=args.path, ids=args.ids, actor=args.actor,
        )
        _err_exit(result)
        print(f"✅ {result['message']}")
        if result.get("unit_ids"):
            print(f"  已删除单元 ({result['purged']} 个):")
            for uid in result["unit_ids"]:
                print(f"    • {uid}")

    else:
        print(f"未知 v2 命令: {cmd}")
        sys.exit(1)


# ── 主入口 ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="novel-create-hermes 统一 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="domain")

    _build_viz_parser(sub)
    _build_migrate_parser(sub)
    _build_project_parser(sub)
    _build_env_parser(sub)
    _build_v2_parser(sub)

    args = parser.parse_args()

    if not args.domain:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "viz": _run_viz,
        "migrate": _run_migrate,
        "project": _run_project,
        "env": _run_env,
        "v2": _run_v2,
    }

    dispatch[args.domain](args)


if __name__ == "__main__":
    main()
