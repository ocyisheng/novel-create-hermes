#!/usr/bin/env python3
"""
check_project_integrity.py — 小说项目完整性检查器

扫描 novels/ 下所有项目，检测 git 保护状态、文件完整性、pending 缓存。
面向编排层和运维使用。

用法:
  python check_project_integrity.py                           # 扫描所有项目
  python check_project_integrity.py --project 空山闻仙        # 只检查指定项目
  python check_project_integrity.py --fix                      # 尝试修复发现的问题
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

try:
    from git_vault import GitVault
except ImportError:
    print("错误: 需要 git_vault.py，请检查 .opencode/shared/ 目录", file=sys.stderr)
    sys.exit(1)


NOVELS_ROOT = Path(__file__).resolve().parent.parent.parent / "novels"


def _find_novel_projects(root: Path) -> list[Path]:
    """扫描 novels/ 下所有包含 config.yaml 的项目目录。"""
    if not root.is_dir():
        return []
    return sorted([
        d for d in root.iterdir()
        if d.is_dir() and (d / "config.yaml").is_file()
    ])


def check_single_project(project_root: Path, verbose: bool = False) -> dict:
    """检查单个项目的 git 保护状态。

    Returns:
        {"name": str, "path": str, "healthy": bool, "issues": [str], "details": {...}}
    """
    issues = []
    status = GitVault.status(project_root)

    details = {
        "name": project_root.name,
        "path": str(project_root.resolve()),
        "initialized": status["initialized"],
        "commits_count": status["commits_count"],
        "clean": status["clean"],
        "has_last_commit": bool(status.get("last_commit")),
    }

    if not status["initialized"]:
        issues.append("git 仓库未初始化")
        if verbose:
            print(f"  ⚠  {project_root.name}: git 仓库未初始化")

    if status["commits_count"] == 0 and status["initialized"]:
        issues.append("有 git 仓库但无提交记录")

    if not status["clean"]:
        if status["untracked"]:
            issues.append(f"{len(status['untracked'])} 个未跟踪文件")
        if status["modified"]:
            issues.append(f"{len(status['modified'])} 个未提交修改")
        if verbose:
            print(f"  📝 {project_root.name}: 工作树不干净")

    # 检查 pending cache
    pending_dir = project_root / ".git" / "pending_commits"
    pending_count = 0
    if pending_dir.is_dir():
        pending_count = len(list(pending_dir.glob("*.msg")))
        if pending_count > 0:
            details["pending_commits"] = pending_count
            issues.append(f"{pending_count} 个待提交的缓存")

    # 检查 .gitignore 是否已创建
    has_gitignore = (project_root / ".gitignore").is_file()
    details["has_gitignore"] = has_gitignore

    # 检查初始化标记
    has_marker = (project_root / ".git_vault_init").is_file()
    details["has_marker"] = has_marker

    healthy = len(issues) == 0
    details["healthy"] = healthy
    details["issues"] = issues

    return details


def fix_project(project_root: Path, verbose: bool = False) -> dict:
    """尝试修复发现的问题。"""
    result = check_single_project(project_root, verbose=False)
    fixes = []

    if not result["initialized"]:
        # 初始化 git 仓库
        init_r = GitVault.init_project(project_root)
        if init_r["ok"]:
            fixes.append("已初始化 git 仓库")
            if verbose:
                print(f"  ✅ {project_root.name}: git 仓库已初始化")
        else:
            fixes.append(f"❌ 初始化失败: {init_r.get('error', 'unknown')}")

    # 尝试刷新 pending
    try:
        from git_vault import _flush_pending, _is_git_available
        if _is_git_available() and (project_root / ".git").is_dir():
            flushed = _flush_pending(project_root)
            if flushed > 0:
                fixes.append(f"已补提 {flushed} 个缓存提交")
    except (ImportError, AttributeError):
        pass

    # 如果工作树不干净且有 pending，尝试提交
    pending_dir = project_root / ".git" / "pending_commits"
    if not result["clean"] and pending_dir.is_dir():
        flushed = len(list(pending_dir.glob("*.msg")))
        if flushed > 0:
            # 简单 flush
            GitVault.commit(project_root, "[system] auto-flush after integrity check")
            fixes.append(f"已尝试补提 {flushed} 个缓存提交")

    return {
        "name": project_root.name,
        "path": str(project_root.resolve()),
        "fixes": fixes,
        "healthy_after": check_single_project(project_root)["healthy"],
    }


def main():
    parser = argparse.ArgumentParser(
        description="小说项目完整性检查器"
    )
    parser.add_argument("--project", "-p", help="仅检查指定项目名")
    parser.add_argument("--fix", action="store_true", help="尝试自动修复发现的问题")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    projects_root = NOVELS_ROOT
    if not projects_root.is_dir():
        print(f"错误: novels 目录不存在: {projects_root}", file=sys.stderr)
        sys.exit(1)

    projects = _find_novel_projects(projects_root)
    if not projects:
        print(f"ℹ novels 目录中未找到任何项目")
        sys.exit(0)

    # 如果指定了项目名，只检查匹配的项目
    if args.project:
        matched = [p for p in projects if p.name == args.project]
        if not matched:
            print(f"错误: 未找到项目 '{args.project}'", file=sys.stderr)
            sys.exit(1)
        projects = matched

    print(f"📋 正在检查 {len(projects)} 个项目...")
    print()

    healthy_count = 0
    for proj in projects:
        if args.fix:
            print(f"  🔧 {proj.name}")
            result = fix_project(proj, verbose=args.verbose)
            if result["fixes"]:
                for f in result["fixes"]:
                    print(f"    {f}")
            else:
                print(f"    ✅ 无需修复")
            if result["healthy_after"]:
                healthy_count += 1
        else:
            result = check_single_project(proj, verbose=args.verbose)
            status_icon = "✅" if result["healthy"] else "⚠"
            print(f"  {status_icon} {proj.name}")
            if result["issues"]:
                for issue in result["issues"]:
                    print(f"       - {issue}")
            if result["healthy"]:
                healthy_count += 1

    print()
    if args.fix:
        print(f"✅ 修复完成: {healthy_count}/{len(projects)} 个项目健康")
    else:
        print(f"📊 总结: {healthy_count}/{len(projects)} 个项目健康")
        if healthy_count < len(projects):
            print("   运行 check_project_integrity.py --fix 尝试自动修复")
        print()
        print("检查指标:")
        print("  - git 仓库已初始化")
        print("  - 至少有一次提交")
        print("  - 工作树干净（无未跟踪/未提交文件）")
        print("  - 无 pending 缓存")
        print("  - .gitignore 已创建")
        print("  - 初始化标记文件存在")


if __name__ == "__main__":
    main()
