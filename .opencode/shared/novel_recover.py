#!/usr/bin/env python3
"""
novel_recover.py — 小说项目恢复工具

包装 git_vault.py，面向编排层和用户提供文件恢复入口。

用法:
  # 列出最近被删除的文件
  python novel_recover.py list-deleted --project-root NOVELS_ROOT/项目名

  # 恢复指定文件（自动查找最后存在的版本）
  python novel_recover.py restore --project-root NOVELS_ROOT/项目名 --file chapters/第5章.txt

  # 恢复指定文件的某个历史版本
  python novel_recover.py restore --project-root NOVELS_ROOT/项目名 \\
      --file characters/韩致.yaml --revision HEAD~3

  # 查看仓库健康状态
  python novel_recover.py status --project-root NOVELS_ROOT/项目名

  # 查看提交历史
  python novel_recover.py log --project-root NOVELS_ROOT/项目名 --count 10

  # 回退到历史版本（软重置，保留工作区文件）
  python novel_recover.py reset --project-root NOVELS_ROOT/项目名 --revision <hash>
"""

import argparse
import sys
from pathlib import Path

try:
    from git_vault import GitVault
except ImportError:
    print("错误: 需要 git_vault.py，请检查 .opencode/shared/ 目录", file=sys.stderr)
    sys.exit(1)


def _find_project_root(path: Path) -> Path | None:
    """从给定路径向上查找项目根。"""
    if (path / "config.yaml").is_file():
        return path.resolve()
    for parent in path.parents:
        if (parent / "config.yaml").is_file():
            return parent.resolve()
    return None


def cmd_list_deleted(project_root: Path, args) -> int:
    """列出指定数量的被删除文件。"""
    entries = GitVault.list_deleted(project_root, count=args.count)
    if not entries:
        print("ℹ git 历史中未找到被删除的文件记录。")
        print("  注意：git 保护从启用之日开始记录，之前的操作不在历史中。")
        return 0

    total_files = sum(len(e["files"]) for e in entries)
    print(f"找到 {total_files} 个被删除的文件（来自 {len(entries)} 次提交）：")
    print()

    for entry in entries:
        if not entry["files"]:
            continue
        print(f"提交: {entry['commit'][:12]}  {entry['date']}")
        print(f"  信息: {entry['message']}")
        for f in entry["files"]:
            print(f"  ✂  {f}")
        print()

    print("恢复方法: novel_recover.py restore --file <路径>")
    return 0


def cmd_restore(project_root: Path, args) -> int:
    """恢复文件。"""
    result = GitVault.restore(
        project_root, args.file,
        revision=args.revision
    )
    if result["ok"]:
        print(f"✅ 已恢复: {result['file']}")
        if result["revision"] != "HEAD":
            print(f"   来自版本: {result['revision']}")
        print(f"   路径: {(project_root / result['file']).resolve()}")
        return 0
    else:
        print(f"❌ 恢复失败: {result['error']}", file=sys.stderr)
        print()
        print("可能的原因：")
        print("  1. 文件从未被 git 追踪（新建后从未提交就被删了）")
        print("  2. 文件名拼写错误")
        print("  3. 该项目的 git 仓库尚未初始化")
        print()
        print("建议：")
        print("  - 用 list-deleted 查看可恢复的文件列表")
        print("  - 用 status 查看仓库状态")
        return 1


def cmd_status(project_root: Path, args) -> int:
    """显示仓库健康状态。"""
    s = GitVault.status(project_root)

    if not s["initialized"]:
        print("❌ git 仓库未初始化")
        print()
        print("该项目尚未启用 git 保护。初始化后，未来的操作会自动记录版本历史。")
        return 1

    print(f"📂 项目: {project_root.name}")
    print(f"   路径: {project_root.resolve()}")
    print()

    # 仓库健康
    print(f"仓库状态: ✅ 已初始化")
    if s["last_commit"]:
        lc = s["last_commit"]
        print(f"提交总数: {s['commits_count']}")
        print(f"最新提交: {lc['message']}")
        print(f"   时间: {lc['date']}")
        print(f"   哈希: {lc['hash']}")
    print()

    # 工作树状态
    if s["clean"]:
        print("工作树: ✅ 干净（无未提交变更）")
    else:
        if s["staged"]:
            print(f"已暂存: {len(s['staged'])} 个文件")
            for f in s["staged"][:10]:
                print(f"  + {f}")
            if len(s["staged"]) > 10:
                print(f"  ... 还有 {len(s['staged']) - 10} 个")
        if s["modified"]:
            print(f"未暂存的修改: {len(s['modified'])} 个文件")
            for f in s["modified"][:10]:
                print(f"  M {f}")
            if len(s["modified"]) > 10:
                print(f"  ... 还有 {len(s['modified']) - 10} 个")
            print()
            print("建议：运行 novel_recover.py save 提交当前变更")
        if s["untracked"]:
            print(f"未跟踪: {len(s['untracked'])} 个文件（不会影响恢复）")

    return 0


def cmd_log(project_root: Path, args) -> int:
    """查看提交历史。"""
    kwargs = {"count": args.count}
    if args.since:
        kwargs["since"] = args.since

    entries = GitVault.log(project_root, **kwargs)
    if not entries:
        print("ℹ 无提交记录。")
        if args.since:
            print(f"   条件: since={args.since}")
        print("  可能是仓库尚未初始化或没有提交。")
        return 0

    # 按日期分组显示
    current_date = ""
    print(f"提交历史（最近 {len(entries)} 次）:")
    print("=" * 60)
    for entry in entries:
        date_short = entry["date"][:10] if len(entry["date"]) >= 10 else entry["date"]
        if date_short != current_date:
            print(f"\n--- {date_short} ---")
            current_date = date_short
        print(f"{entry['hash']}  {entry['message']}")
    print()

    # 恢复指引
    print("恢复指引:")
    print("  查看被删文件: list-deleted")
    print("  恢复文件:     restore --file <路径> --revision <哈希>")
    print("  回退到某版本: reset --revision <哈希>")

    return 0


def cmd_reset(project_root: Path, args) -> int:
    """软重置到指定版本。"""
    result = GitVault.reset_to(project_root, args.revision)
    if result["ok"]:
        print(f"✅ 已重置到 {result['revision']}")
        print()
        print("这是软重置（--soft），工作区文件未变。")
        print("如果需要丢弃工作区变更：")
        print("  git -C <项目目录> restore .")
        print()
        print("如果确认新状态正确，运行：")
        print("  novel_recover.py save")
        return 0
    else:
        print(f"❌ 重置失败: {result['error']}", file=sys.stderr)
        return 1


def cmd_save(project_root: Path, args) -> int:
    """手动提交当前所有变更。"""
    result = GitVault.commit(
        project_root, "manual snapshot",
        stage="system"
    )
    if result["saved"] and result["hash"]:
        print(f"✅ {result['hash']} {result['message']}")
        return 0
    elif result["saved"] and not result["hash"]:
        print(f"📦 已缓存提交（git 不可用时排队）")
        return 0
    else:
        print(f"ℹ 无变更需要提交")
        return 0


def _build_parser():
    """构建参数解析器。注意：--project-root 必须在子命令前定义。"""
    parser = argparse.ArgumentParser(
        description="小说项目恢复工具"
    )
    parser.add_argument("--project-root", "-p",
                        help="项目根目录。省略时从 CWD 自动检测。")
    subparsers = parser.add_subparsers(dest="command")

    # list-deleted
    p_ld = subparsers.add_parser("list-deleted", help="列出被删除的文件")
    p_ld.add_argument("--count", type=int, default=10, help="搜索深度")

    # restore
    p_rs = subparsers.add_parser("restore", help="恢复文件")
    p_rs.add_argument("--file", required=True, help="相对于项目根的文件路径")
    p_rs.add_argument("--revision", default=None, help="git revision（默认自动查找）")

    # status
    subparsers.add_parser("status", help="查看仓库健康状态")

    # log
    p_log = subparsers.add_parser("log", help="查看提交历史")
    p_log.add_argument("--count", type=int, default=10)
    p_log.add_argument("--since", help="起始时间（如 2026-06-28）")

    # reset
    p_rs2 = subparsers.add_parser("reset", help="软重置到指定版本（保留工作区）")
    p_rs2.add_argument("--revision", required=True, help="目标 revision")

    # save
    subparsers.add_parser("save", help="手动提交当前所有变更")

    return parser


def _resolve_project_root(parser, argv) -> tuple:
    """
    先解析 --project-root（使用 parse_known_args），
    再解析子命令和其余参数，解决 argparse 子命令在前时可选参数被忽略的问题。
    """
    # 第一阶段：只提取 --project-root，无视子命令位置
    # 先建一个只有 --project-root 的 parser
    root_parser = argparse.ArgumentParser(add_help=False)
    root_parser.add_argument("--project-root", "-p")
    root_parser.add_argument("--help", "-h", action="store_true")
    known, remaining = root_parser.parse_known_args(argv)

    project_root = None
    if known.project_root:
        project_root = Path(known.project_root)
    else:
        detected = _find_project_root(Path.cwd())
        if detected:
            project_root = detected

    if known.help or "-h" in argv or "--help" in argv:
        parser.print_help()
        sys.exit(0)

    # 第二阶段：用完整 parser 解析子命令（但 --project-root 可能已被提取，需从 remaining 中去掉它）
    # 把 --project-root 从 remaining 中去掉，避免子命令 parser 报错
    clean_argv = []
    skip_next = False
    for i, arg in enumerate(remaining):
        if skip_next:
            skip_next = False
            continue
        if arg in ("--project-root", "-p"):
            skip_next = True  # 跳过值
            continue
        if arg.startswith("--project-root=") or arg.startswith("-p="):
            continue  # 跳过 --project-root=value 形式
        clean_argv.append(arg)

    return project_root, parser.parse_args(clean_argv)


def main():
    parser = _build_parser()
    project_root, args = _resolve_project_root(parser, sys.argv[1:])

    if not project_root or not project_root.is_dir():
        print("错误: 无法检测项目根，请用 --project-root 指定", file=sys.stderr)
        sys.exit(1)

    # 路由
    cmd_map = {
        "list-deleted": cmd_list_deleted,
        "restore": cmd_restore,
        "status": cmd_status,
        "log": cmd_log,
        "reset": cmd_reset,
        "save": cmd_save,
    }

    if args.command in cmd_map:
        sys.exit(cmd_map[args.command](project_root, args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
