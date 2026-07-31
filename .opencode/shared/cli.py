#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-create-hermes 统一 CLI 入口。

所有 argparse 集中在此，功能脚本中不再有 argparse 代码。
调用 handlers 模块中的纯业务函数，只做参数提取和输出格式化。

用法:
        python .opencode/shared/cli.py server --project-root <路径> --port 8766
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


# (viz 子命令已移除 — 改用 `server` 子命令启动 Web 端动态可视化)


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
    p = sub.add_parser("v2", help="V2 工具集（graph CRUD / search / session / deviation 等）")
    v2_sub = p.add_subparsers(dest="v2_command")

    # 自动注册 OPERATION_REGISTRY 中所有 graph/session/deviation/knowledge 操作
    from cli_gen import add_registry_commands
    add_registry_commands(v2_sub)

    # 手动覆盖：registry 未覆盖的命令
    sp = v2_sub.add_parser("rebuild-projections", help="重建投影")
    sp.add_argument("--path", required=True)
    sp.add_argument("--mode", default="hybrid", choices=["in_place", "hybrid", "graph_only"])

    sp = v2_sub.add_parser("report", help="项目报告（统计 + 一致性 + 偏差 + Gap）")
    sp.add_argument("--path", required=True)
    sp.add_argument("--with-deviations", action="store_true", help="包含偏差状态统计")

    return p


# ── v2 dispatch ──────────────────────────────────────────────────────────

def _run_v2(args):
    """直接调 handlers，不再经过 v2_cli.py。自动 dispatch + override 表。"""
    import json as _json

    def _err_exit(result):
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)

    cmd = args.v2_command

    # ── override 表：特殊输出格式的命令 ──
    from handlers import (
        handle_get_unit, handle_stats, handle_search, handle_check_consistency,
        handle_list_relation_types, handle_find_unit, handle_list_units,
        handle_recent_events, handle_get_neighbors, handle_create_unit,
        handle_update_unit, handle_add_relation, handle_flush,
        handle_fix_asymmetry, handle_batch_infer, handle_export_docs,
        handle_export_chunks, handle_find_descendants, handle_find_ancestors,
        handle_rebuild_structure_path, handle_migrate_structure_to_edges,
        handle_purge_archived, handle_session_start,
        handle_session_build_workspace,
    )

    OVERRIDES = {}
    # 短名称 → 自动生成的全名称映射
    CMD_ALIASES = {
        "get-unit": "graph-get-unit", "stats": "graph-stats",
        "search": "graph-search", "check": "graph-check",
        "list-relation-types": "graph-list-relation-types",
        "find-unit": "graph-find-unit", "create-unit": "graph-create-unit",
        "update-unit": "graph-update-unit", "add-relation": "graph-add-relation",
        "flush": "graph-flush", "build-workspace": "session-build-workspace",
        "start-session": "session-start", "list-units": "graph-list-units",
        "recent-events": "graph-recent-events", "get-neighbors": "graph-get-neighbors",
        "fix-asymmetry": "graph-fix-asymmetry", "batch-infer": "graph-batch-infer",
        "export-docs": "graph-export-docs", "export": "graph-export-chunks",
        "find-descendants": "graph-find-descendants",
        "find-ancestors": "graph-find-ancestors",
        "rebuild-structure-path": "graph-rebuild-structure-path",
        "migrate-structure": "graph-migrate-structure-to-edges",
        "purge-archived": "graph-purge-archived",
    }

    def _register(name):
        def decorator(fn):
            OVERRIDES[name] = fn
            return fn
        return decorator

    @_register("get-unit")
    def _get_unit():
        result = handle_get_unit(project_root=args.path, id=args.id)
        _err_exit(result)
        u = result.get("unit")
        if not u:
            print("NOT_FOUND")
            return
        print(f"名称: {u['name']}")
        print(f"类型: {u['type']}")
        print(f"状态: {u['status']}")
        print(f"确信度: {u.get('confidence', '')}")
        print(f"标签: {', '.join(u.get('tags', [])) or '无'}")
        ch = f"第{u.get('chapter', '')}章" if u.get('chapter') else "无"
        print(f"章节: {ch}")
        content = u.get('content', '')
        if content:
            if getattr(args, 'verbose', False):
                print(f"内容:\n{content}")
            else:
                preview = content[:200].replace("\n", " ")
                print(f"内容: {preview}..." if len(content) > 200 else f"内容: {preview}")
                if len(content) > 200:
                    print("（使用 --verbose 查看完整内容）")

    @_register("stats")
    def _stats():
        result = handle_stats(project_root=args.path)
        _err_exit(result)
        for k, v in result.items():
            print(f"{k}: {v}")

    @_register("search")
    def _search():
        result = handle_search(
            project_root=args.path, keyword=getattr(args, 'keyword', ''),
            pattern=getattr(args, 'pattern', ''), name=getattr(args, 'name', ''),
            scope=getattr(args, 'scope', None), regex=getattr(args, 'regex', False),
            case_sensitive=getattr(args, 'case_sensitive', False),
            limit=getattr(args, 'limit', 20),
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

    @_register("check")
    def _check():
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
                limit = getattr(args, 'limit', 0)
                if limit > 0 and shown >= limit:
                    break
            if limit > 0 and shown >= limit:
                break

    @_register("list-relation-types")
    def _list_relation_types():
        result = handle_list_relation_types()
        print("可用关系类型（--rel-type 参数值）:")
        print()
        for rt in result.get("relation_types", []):
            inv_note = f" → 反向: {rt['inverse']}" if rt['inverse'] != rt['value'] else "（对称）"
            print(f"  {rt['value']:20s} {rt['name']}{inv_note}")
        print()
        print("查询方向说明：")
        print("  get-neighbors 返回的是通过该关系类型连接到目标的所有单元")

    @_register("find-unit")
    def _find_unit():
        result = handle_find_unit(project_root=args.path, name=args.name)
        _err_exit(result)
        print(result.get("id") or "NOT_FOUND")

    @_register("create-unit")
    def _create_unit():
        result = handle_create_unit(
            project_root=args.path, unit_type=args.unit_type, name=args.name,
            content=getattr(args, 'content', None) or getattr(args, 'data', None),
            file_path=getattr(args, 'file', None) or None,
            tags=getattr(args, 'tags', None) or None,
            chapter=int(getattr(args, 'chapter', 0)) if getattr(args, 'chapter', None) else None,
            actor=getattr(args, 'actor', 'script'),
        )
        _err_exit(result)
        print(f"创建成功: {result['id']}")
        if result.get('relations_created'):
            print(f"关系推断: 新增 {result['relations_created']} 条关联")
        if result.get('schema_errors'):
            for se in result['schema_errors']:
                print(f"  ⚠️  {se}")

    @_register("update-unit")
    def _update_unit():
        result = handle_update_unit(
            project_root=args.path, id=args.id,
            content=getattr(args, 'content', None) or None,
            file_path=getattr(args, 'file', None) or None,
            name=getattr(args, 'name', None) or None,
            tags=getattr(args, 'tags', None) or None,
            actor=getattr(args, 'actor', 'script'),
        )
        _err_exit(result)
        print(f"更新成功: {result['id']}")
        print(f"  名称: {result.get('name', '')}")
        print(f"  版本: {result.get('version', '')}")
        print(f"  标签: {', '.join(result.get('tags', [])) or '无'}")

    @_register("add-relation")
    def _add_relation():
        result = handle_add_relation(
            project_root=args.path, source=args.source,
            target=args.target, rel_type=args.rel_type,
            bidirectional=getattr(args, 'bidirectional', False),
            actor=getattr(args, 'actor', 'script'),
        )
        _err_exit(result)
        print(f"关系已建立: {result.get('id', '')}")
        if result.get('inverse_id'):
            print(f"反向关系已建立: {result['inverse_id']}")

    @_register("flush")
    def _flush():
        result = handle_flush(project_root=args.path)
        _err_exit(result)
        print("graph 已持久化")

    @_register("build-workspace")
    def _build_workspace():
        result = handle_session_build_workspace(
            project_root=args.path, id=args.id,
            level=getattr(args, 'level', 'warm'),
        )
        _err_exit(result)
        print(result.get("context", ""))

    @_register("start-session")
    def _start_session():
        result = handle_session_start(
            project_root=args.path, focus_type=args.focus_type, id=args.id,
        )
        _err_exit(result)
        print(f"SESSION={result['session_id']}")

    @_register("list-units")
    def _list_units():
        result = handle_list_units(
            project_root=args.path,
            unit_type=getattr(args, 'unit_type', ''),
            limit=int(getattr(args, 'limit', 0)) if getattr(args, 'limit', '0') and int(getattr(args, 'limit', '0')) > 0 else 0,
        )
        _err_exit(result)
        for u in result.get("units", []):
            print(f"[{u['type']}] {u['name']} [{u['status']}]")

    @_register("recent-events")
    def _recent_events():
        limit = int(getattr(args, 'limit', 5)) if getattr(args, 'limit', None) else 5
        result = handle_recent_events(project_root=args.path, limit=limit)
        _err_exit(result)
        for e in result.get("events", []):
            print(f"[{e['timestamp']}] {e['actor']}: {e['event_type']}")

    @_register("get-neighbors")
    def _get_neighbors():
        result = handle_get_neighbors(
            project_root=args.path, id=args.id,
            rel_type=getattr(args, 'rel_type', ''),
            limit=getattr(args, 'limit', 0),
        )
        _err_exit(result)
        for n in result.get("neighbors", []):
            print(f"{n['type']}: {n['name']} ({n['id']})")

    @_register("fix-asymmetry")
    def _fix_asymmetry():
        result = handle_fix_asymmetry(project_root=args.path)
        _err_exit(result)
        total = result.get("created", 0) + result.get("skipped", 0)
        print(f"检查了 {total} 条关系")
        print(f"补齐反向边: {result.get('created', 0)} 条新建, {result.get('skipped', 0)} 条已存在")

    @_register("batch-infer")
    def _batch_infer():
        result = handle_batch_infer(project_root=args.path)
        _err_exit(result)
        print(f"批量推断完成:")
        print(f"  新建关系: {result.get('new_relations', 0)}")
        print(f"  关系总计: {result.get('total_before', 0)} → {result.get('total_after', 0)}")

    @_register("export-docs")
    def _export_docs():
        result = handle_export_docs(
            project_root=args.path, out=getattr(args, 'out', ''),
        )
        _err_exit(result)
        files = result.get("files", [])
        print(f"✅ 结构化文档已导出: {len(files)} 个文件")
        for w in files:
            print(f"   📄 {w}")

    @_register("export")
    def _export():
        result = handle_export_chunks(
            project_root=args.path, out=getattr(args, 'out', ''),
        )
        _err_exit(result)
        files = result.get("files", [])
        print(f"导出完成: {len(files)} 个章节文件")

    @_register("find-descendants")
    def _find_descendants():
        result = handle_find_descendants(
            project_root=args.path, id=args.id,
            max_depth=getattr(args, 'max_depth', 10),
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

    @_register("find-ancestors")
    def _find_ancestors():
        result = handle_find_ancestors(project_root=args.path, id=args.id)
        _err_exit(result)
        ancestors = result.get("ancestors", [])
        if not ancestors:
            print("未找到祖先单元")
            return
        print(f"找到 {len(ancestors)} 个祖先单元:")
        for u in ancestors:
            print(f"  • {u['type']}: {u['name']} ({u['id']})")

    @_register("rebuild-structure-path")
    def _rebuild_structure_path():
        result = handle_rebuild_structure_path(project_root=args.path, id=args.id)
        _err_exit(result)
        path = result.get("structure_path", [])
        if not path:
            print("未重建出结构路径")
            return
        print(f"结构路径 ({len(path)} 级):")
        for item in path:
            print(f"  [{item.get('level', '?')}] {item.get('id', '')}")

    @_register("migrate-structure")
    def _migrate_structure():
        result = handle_migrate_structure_to_edges(project_root=args.path)
        _err_exit(result)
        print(f"迁移完成:")
        print(f"  新建边: {result.get('edges_created', 0)}")
        print(f"  已存在: {result.get('edges_skipped', 0)}")
        print(f"  错误:   {result.get('errors', 0)}")
        if result.get("details"):
            for d in result["details"][:10]:
                print(f"  • {d}")

    @_register("purge-archived")
    def _purge_archived():
        result = handle_purge_archived(
            project_root=args.path, ids=getattr(args, 'ids', ''),
            actor=getattr(args, 'actor', 'script'),
        )
        _err_exit(result)
        print(f"✅ {result['message']}")
        if result.get("unit_ids"):
            print(f"  已删除单元 ({result['purged']} 个):")
            for uid in result["unit_ids"]:
                print(f"    • {uid}")

    @_register("rebuild-projections")
    def _rebuild_projections():
        from projection_engine import ProjectionEngine
        from graph_store import GraphStore
        store = GraphStore(args.path)
        store.initialize()
        p = ProjectionEngine(store, args.path, output_mode=args.mode)
        p.rebuild_all()
        print("投影已重建")

    @_register("report")
    def _report():
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

        if getattr(args, 'with_deviations', False):
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

    # ── 路由 ──
    # 1) 精确匹配 override 表
    if cmd in OVERRIDES:
        OVERRIDES[cmd]()
        return

    # 2) 别名匹配（短名称 → 自动生成的全名称，如 get-unit → graph-get-unit）
    if cmd in CMD_ALIASES and CMD_ALIASES[cmd] in OVERRIDES:
        OVERRIDES[CMD_ALIASES[cmd]]()
        return

    # 3) 未在 override 表中的 → 自动 dispatch（输出 JSON）
    _auto_dispatch_v2(args)


def _command_to_operation(cmd_name: str) -> str:
    """CLI 子命令名 → novel-tool 操作名。"""
    idx = cmd_name.find("-")
    if idx == -1:
        return cmd_name
    return cmd_name[:idx] + "." + cmd_name[idx + 1:].replace("-", "_")


def _auto_dispatch_v2(args):
    """自动 dispatch 到 OPERATION_REGISTRY 并输出 JSON。"""
    import json as _json
    from handlers import OPERATION_REGISTRY, run_operation

    cmd = args.v2_command
    op_name = _command_to_operation(cmd)
    entry = OPERATION_REGISTRY.get(op_name)
    if not entry:
        print(f"未知 v2 命令: {cmd}")
        sys.exit(1)

    params = {}
    if "project_root" in entry["params"]:
        params["project_root"] = args.path
    for pname in entry["params"]:
        if pname == "project_root":
            continue
        val = getattr(args, pname.replace("-", "_"), None)
        if val is not None and val != "":
            params[pname] = val

    result = run_operation(op_name, **params)
    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)
    print(_json.dumps(result, ensure_ascii=False, indent=2))


# ── server ────────────────────────────────────────────────────────────

def _build_server_parser(sub):
    p = sub.add_parser("server", help="启动本地 Web 服务（FastAPI + 前端 SPA）")
    p.add_argument("--project-root", "-p", required=True, help="项目根目录")
    p.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    p.add_argument("--port", type=int, default=8766, help="监听端口（默认 8766）")
    return p


def _run_server(args):
    from handlers import handle_server_start
    result = handle_server_start(
        project_root=args.project_root,
        host=args.host,
        port=args.port,
    )
    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)


# ── analyze ────────────────────────────────────────────────────────

def _build_analyze_parser(sub):
    p = sub.add_parser("analyze", help="使用数据分析与优化建议")
    p.add_argument("--project-root", "-p", required=True, help="项目根目录")
    p.add_argument("--mode", choices=["quick", "full"], default="full",
                    help="分析模式: quick=仅统计, full=含详细分析")
    p.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p.add_argument("--output", "-o", default="", help="输出到文件")
    return p


def _run_analyze(args):
    from v2.usage_analyzer import collect_usage_data, format_report
    import json

    report = collect_usage_data(args.project_root)
    if "error" in report:
        print(f"❌ {report['error']}")
        sys.exit(1)

    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    else:
        output = format_report(report, verbose=(args.mode == "full"))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 报告已写入: {args.output}")
    else:
        print(output)


# ── 主入口 ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="novel-create-hermes 统一 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="domain")

    _build_migrate_parser(sub)
    _build_project_parser(sub)
    _build_env_parser(sub)
    _build_v2_parser(sub)
    _build_server_parser(sub)
    _build_analyze_parser(sub)

    args = parser.parse_args()

    if not args.domain:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "migrate": _run_migrate,
        "project": _run_project,
        "env": _run_env,
        "v2": _run_v2,
        "server": _run_server,
        "analyze": _run_analyze,
    }

    dispatch[args.domain](args)


if __name__ == "__main__":
    main()
