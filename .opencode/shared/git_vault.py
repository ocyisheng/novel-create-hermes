#!/usr/bin/env python3
"""
git_vault.py — 小说项目 Git 保护引擎

每个小说项目创建一个独立 git 仓库，在后处理链中自动提交变更。
git 失败时不阻塞调用者，变更缓存到 pending 目录下次补提。

用法:
  # CLI
  python git_vault.py init --project-root NOVELS_ROOT/项目名
  python git_vault.py commit --project-root NOVELS_ROOT/项目名 -m "write: 第3章" --stage P8
  python git_vault.py status --project-root NOVELS_ROOT/项目名
  python git_vault.py restore --project-root NOVELS_ROOT/项目名 --file chapters/第3章.txt
  python git_vault.py list-deleted --project-root NOVELS_ROOT/项目名 --count 5
  python git_vault.py log --project-root NOVELS_ROOT/项目名 --count 10

  # Python 导入
  from git_vault import GitVault
  result = GitVault.commit(project_root, "write: 第3章", stage="P8")
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── 常量 ──────────────────────────────────────────────────────────────────────

GITIGNORE_CONTENT = """\
# git_vault.py 自动管理
.venv/
venv/
__pycache__/
*.pyc
*.swp
*.swo
Thumbs.db

# 章节元数据（可由 rebuild 重新生成）
chapters/.metas/

# git_vault 内部标记
.git_vault_init

# 缓存目录
.git/pending_commits/
"""

INIT_MARKER = ".git_vault_init"
PENDING_DIR_NAME = ".git/pending_commits"
GIT_TIMEOUT = 30  # git 命令超时秒数


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    """执行 git 命令，cwd 固定在项目目录。"""
    cmd = ["git"] + list(args)
    try:
        return subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except FileNotFoundError:
        # git 未安装
        return subprocess.CompletedProcess(
            args=cmd, returncode=127,
            stdout="", stderr="git: command not found"
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=cmd, returncode=124,
            stdout="", stderr="git: timeout"
        )


def _is_git_available() -> bool:
    """检查系统是否安装了 git。"""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


from _utils import find_project_root_or_none as _find_project_root


# ── Pending commit 缓存 ──────────────────────────────────────────────────────

def _pending_dir(project_root: Path) -> Path:
    return project_root / PENDING_DIR_NAME


def _cache_pending(project_root: Path, message: str) -> None:
    """git 失败时将提交缓存到 pending 目录。"""
    pdir = _pending_dir(project_root)
    pdir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    cache_file = pdir / f"{timestamp}.msg"
    try:
        cache_file.write_text(message, encoding="utf-8")
    except OSError:
        pass


def _flush_pending(project_root: Path) -> int:
    """尝试提交所有缓存的 pending commit。返回成功提交数。"""
    pdir = _pending_dir(project_root)
    if not pdir.is_dir():
        return 0
    flushed = 0
    try:
        for cache_file in sorted(pdir.iterdir()):
            if cache_file.suffix != ".msg":
                continue
            message = cache_file.read_text(encoding="utf-8").strip()
            if not message:
                cache_file.unlink()
                continue
            # add + commit
            r1 = _git(project_root, "add", "-A")
            if r1.returncode != 0:
                break
            r2 = _git(project_root, "commit", "-m", message)
            if r2.returncode != 0:
                break
            cache_file.unlink()
            flushed += 1
    except OSError:
        pass
    return flushed


# ── GitVault 核心类 ──────────────────────────────────────────────────────────

class GitVault:
    """小说项目 git 保护引擎。每个项目独立仓库。"""

    @staticmethod
    def init_project(project_root: Path) -> dict:
        """初始化 git 仓库并做首次提交。幂等。

        Args:
            project_root: 项目根目录（包含 config.yaml 的目录）

        Returns:
            {"ok": bool, "repo": str, "lines": [str], "error": str}
        """
        project_root = project_root.resolve()
        lines = []
        error = None

        if not project_root.is_dir():
            return {"ok": False, "repo": "", "lines": [], "error": f"目录不存在: {project_root}"}

        git_dir = project_root / ".git"

        # 已初始化 → 跳过
        if git_dir.is_dir():
            lines.append("🔒 git 仓库已存在")

            # 尝试 flush pending
            flushed = _flush_pending(project_root)
            if flushed > 0:
                lines.append(f"  ↻ 补提 {flushed} 个缓存提交")

            return {"ok": True, "repo": str(git_dir), "lines": lines, "error": None}

        if not _is_git_available():
            return {"ok": False, "repo": "", "lines": [], "error": "git 未安装或不可用"}

        # git init
        result = _git(project_root, "init")
        if result.returncode != 0:
            error = f"git init 失败: {result.stderr.strip()[:200]}"
            return {"ok": False, "repo": "", "lines": lines, "error": error}

        lines.append(f"🔒 git 仓库已初始化: {git_dir}")

        # 写入 .gitignore（不覆盖用户已有的）
        gitignore_path = project_root / ".gitignore"
        if not gitignore_path.exists():
            try:
                gitignore_path.write_text(GITIGNORE_CONTENT, encoding="utf-8")
                lines.append("  📄 .gitignore 已创建")
            except OSError as e:
                lines.append(f"  ⚠ .gitignore 写入失败: {e}")

        # 写入初始化标记文件
        marker_path = project_root / INIT_MARKER
        if not marker_path.exists():
            try:
                marker_path.write_text(
                    f"# GitVault init: {project_root.name}\n"
                    f"# 初始化时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
                    encoding="utf-8"
                )
            except OSError:
                pass

        # 首次提交
        project_name = project_root.name
        r_add = _git(project_root, "add", "-A")
        if r_add.returncode == 0:
            r_commit = _git(project_root, "commit", "-m", f"[system] init: {project_name}")
            if r_commit.returncode == 0:
                lines.append(f"  📝 初始提交: [system] init: {project_name}")
            else:
                lines.append(f"  ⚠ 首次提交失败（项目文件将在后续操作中自动提交）")
        else:
            lines.append(f"  ⚠ git add 失败（项目文件将在后续操作中自动提交）")

        return {"ok": True, "repo": str(git_dir), "lines": lines, "error": None}

    @staticmethod
    def commit(project_root: Path, message: str, *,
               stage: Optional[str] = None,
               files: Optional[list[str]] = None) -> dict:
        """自动 add + commit。git 失败时缓存到 pending。

        Args:
            project_root: 项目根目录
            message: 提交信息主体
            stage: 阶段标记（P8, P13, system, config 等）
            files: 限定文件列表（None = 全部变更）

        Returns:
            {"ok": bool, "hash": str, "message": str, "error": str, "saved": bool}
        """
        project_root = project_root.resolve()
        full_message = f"[{stage}] {message}" if stage else message

        if not _is_git_available():
            _cache_pending(project_root, full_message)
            return {
                "ok": False, "hash": "", "message": full_message,
                "error": "git 不可用，已缓存",
                "saved": True,
            }

        # 确保仓库已初始化
        git_dir = project_root / ".git"
        if not git_dir.is_dir():
            init_result = GitVault.init_project(project_root)
            if not init_result["ok"] and init_result["error"]:
                _cache_pending(project_root, full_message)
                return {
                    "ok": False, "hash": "", "message": full_message,
                    "error": f"init 失败: {init_result['error']}，已缓存",
                    "saved": True,
                }

        # 先 flush pending
        _flush_pending(project_root)

        # git add
        if files:
            for f in files:
                fpath = project_root / f
                if fpath.exists():
                    _git(project_root, "add", "--", f)
                else:
                    # 文件已被删除，用 add --all 处理
                    _git(project_root, "add", "-A", "--", f)
        else:
            _git(project_root, "add", "-A")

        # 检查是否有变更需要提交
        status_result = _git(project_root, "status", "--porcelain")
        if status_result.returncode != 0 or not status_result.stdout.strip():
            # 无变更，直接返回成功
            return {
                "ok": True, "hash": "", "message": full_message,
                "error": None, "saved": False,
            }

        # git commit
        commit_result = _git(project_root, "commit", "-m", full_message)
        if commit_result.returncode != 0:
            # commit 失败（可能 git config 缺失等），缓存
            _cache_pending(project_root, full_message)
            return {
                "ok": False, "hash": "", "message": full_message,
                "error": f"commit 失败: {commit_result.stderr.strip()[:200]}，已缓存",
                "saved": True,
            }

        # 提取 hash
        hash_result = _git(project_root, "rev-parse", "--short", "HEAD")
        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else ""

        return {
            "ok": True,
            "hash": commit_hash,
            "message": full_message,
            "error": None,
            "saved": True,
        }

    @staticmethod
    def restore(project_root: Path, file_path: str, *,
                revision: Optional[str] = None) -> dict:
        """从 git 恢复文件到工作区。

        Args:
            project_root: 项目根目录
            file_path: 相对于项目根的文件路径
            revision: git revision。None 时自动查找文件存在的最近版本。

        Returns:
            {"ok": bool, "file": str, "revision": str, "error": str}
        """
        project_root = project_root.resolve()
        git_dir = project_root / ".git"

        if not git_dir.is_dir():
            return {"ok": False, "file": file_path, "revision": str(revision),
                    "error": "git 仓库未初始化"}

        # 如果未指定 revision，先检查 HEAD 是否有此文件
        if revision is None:
            check = _git(project_root, "show", "HEAD:{}".format(file_path))
            if check.returncode != 0:
                # HEAD 没有此文件 → 查找文件存在的最近提交
                log_r = _git(project_root, "log", "--diff-filter=D",
                             "--format=%H", "-1", "--", file_path)
                if log_r.returncode == 0 and log_r.stdout.strip():
                    # 文件被删的提交 → 恢复父版本
                    revision = "{}^".format(log_r.stdout.strip()[:40])
                else:
                    # 尝试在所有历史中找
                    log_r2 = _git(project_root, "log", "--format=%H",
                                  "-1", "--", file_path)
                    if log_r2.returncode == 0 and log_r2.stdout.strip():
                        revision = log_r2.stdout.strip()[:40]
                    else:
                        return {"ok": False, "file": file_path,
                                "revision": "N/A",
                                "error": "git 历史中未找到此文件"}
            else:
                revision = "HEAD"

        result = _git(project_root, "checkout", revision, "--", file_path)
        if result.returncode != 0:
            return {"ok": False, "file": file_path, "revision": revision,
                    "error": "恢复失败: {}".format(result.stderr.strip()[:200])}

        return {"ok": True, "file": file_path, "revision": revision, "error": None}

    @staticmethod
    def list_deleted(project_root: Path, count: int = 10) -> list[dict]:
        """列出最近 N 次提交中被删除的文件。

        Returns:
            [{"commit": str, "message": str, "date": str, "files": [str]}, ...]
        """
        project_root = project_root.resolve()
        git_dir = project_root / ".git"

        if not git_dir.is_dir():
            return []

        # 用 --diff-filter=D 找出删除文件的提交
        format_str = "--pretty=format:%H|%s|%ai"
        result = _git(
            project_root, "log", format_str, "--diff-filter=D",
            "--name-only", f"-{count}"
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        entries = []
        current = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line and len(line.split("|")) == 3:
                # 新提交开始
                if current:
                    entries.append(current)
                parts = line.split("|")
                current = {"commit": parts[0], "message": parts[1],
                           "date": parts[2], "files": []}
            elif current:
                current["files"].append(line)

        if current:
            entries.append(current)

        return entries

    @staticmethod
    def status(project_root: Path) -> dict:
        """获取仓库状态摘要。

        Returns:
            {"ok": bool, "repo": str, "initialized": bool,
             "clean": bool, "untracked": [str], "modified": [str],
             "staged": [str], "last_commit": dict, "commits_count": int,
             "error": str}
        """
        project_root = project_root.resolve()
        result = {
            "ok": True,
            "repo": str(project_root),
            "initialized": False,
            "clean": True,
            "untracked": [],
            "modified": [],
            "staged": [],
            "last_commit": {},
            "commits_count": 0,
            "error": None,
        }

        git_dir = project_root / ".git"
        if not git_dir.is_dir():
            result["ok"] = False
            result["error"] = "git 仓库未初始化"
            return result

        result["initialized"] = True

        if not _is_git_available():
            result["ok"] = False
            result["error"] = "git 不可用"
            return result

        # 检查工作树状态
        status_r = _git(project_root, "status", "--porcelain")
        if status_r.returncode == 0 and status_r.stdout.strip():
            result["clean"] = False
            for line in status_r.stdout.splitlines():
                line = line.rstrip()
                if len(line) < 3:
                    continue
                status_code = line[:2].strip()
                file_path = line[3:]
                if status_code == "??":
                    result["untracked"].append(file_path)
                elif status_code in ("M", "A", "D"):
                    result["staged"].append(file_path)
                elif status_code in (" M", " D", "??"):
                    # 工作区修改（未暂存）
                    result["modified"].append(file_path)

        # 最后一次提交
        log_r = _git(project_root, "log", "-1",
                     "--pretty=format:%H|%s|%ai")
        if log_r.returncode == 0 and log_r.stdout.strip():
            parts = log_r.stdout.strip().split("|")
            if len(parts) == 3:
                result["last_commit"] = {
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                }

        # 提交总数
        count_r = _git(project_root, "rev-list", "--count", "HEAD")
        if count_r.returncode == 0 and count_r.stdout.strip():
            try:
                result["commits_count"] = int(count_r.stdout.strip())
            except ValueError:
                pass

        return result

    @staticmethod
    def reset_to(project_root: Path, revision: str) -> dict:
        """软重置到指定提交（保留工作区文件）。

        Args:
            project_root: 项目根目录
            revision: git revision（hash 或 HEAD~N）

        Returns:
            {"ok": bool, "revision": str, "error": str}
        """
        project_root = project_root.resolve()
        git_dir = project_root / ".git"

        if not git_dir.is_dir():
            return {"ok": False, "revision": revision,
                    "error": "git 仓库未初始化"}

        # 先确保工作树干净（避免 reset 后丢失未提交变更）
        status_r = _git(project_root, "status", "--porcelain")
        if status_r.returncode == 0 and status_r.stdout.strip():
            # 有未提交变更 → 自动提交一个 WIP 快照
            _git(project_root, "add", "-A")
            _git(project_root, "commit", "-m",
                 f"[system] auto-snapshot before reset to {revision}")

        result = _git(project_root, "reset", "--soft", revision)
        if result.returncode != 0:
            return {"ok": False, "revision": revision,
                    "error": f"reset 失败: {result.stderr.strip()[:200]}"}

        return {"ok": True, "revision": revision, "error": None}

    @staticmethod
    def log(project_root: Path, count: int = 10,
            since: Optional[str] = None) -> list[dict]:
        """查看提交历史。

        Args:
            project_root: 项目根目录
            count: 返回的提交数
            since: 起始时间（ISO 格式，如 "2026-06-28"）

        Returns:
            [{"hash": str, "message": str, "date": str, "author": str}, ...]
        """
        project_root = project_root.resolve()
        git_dir = project_root / ".git"

        if not git_dir.is_dir():
            return []

        format_str = "--pretty=format:%h|%s|%ai|%an"
        cmd_args = ["log", format_str]
        if since:
            cmd_args.extend(["--since", since])
        cmd_args.append(f"-{count}")

        result = _git(project_root, *cmd_args)
        if result.returncode != 0 or not result.stdout.strip():
            return []

        entries = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) == 4:
                entries.append({
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                    "author": parts[3],
                })
        return entries


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="小说项目 Git 保护引擎"
    )
    parser.add_argument(
        "--project-root", "-p",
        help="项目根目录。省略时从 CWD 自动检测。"
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="初始化 git 仓库")
    p_init.add_argument("--project-root", "-p")

    # commit
    p_commit = sub.add_parser("commit", help="提交变更")
    p_commit.add_argument("--project-root", "-p")
    p_commit.add_argument("-m", "--message", required=True, help="提交信息")
    p_commit.add_argument("--stage", help="阶段标记（P8, P13, system, config 等）")
    p_commit.add_argument("--files", nargs="*", help="要提交的文件列表")

    # status
    p_status = sub.add_parser("status", help="查看仓库状态")
    p_status.add_argument("--project-root", "-p")

    # restore
    p_restore = sub.add_parser("restore", help="恢复文件")
    p_restore.add_argument("--project-root", "-p")
    p_restore.add_argument("--file", required=True, help="相对于项目根的文件路径")
    p_restore.add_argument("--revision", default=None, help="git revision（默认自动查找）")

    # list-deleted
    p_ld = sub.add_parser("list-deleted", help="列出已删除的文件")
    p_ld.add_argument("--project-root", "-p")
    p_ld.add_argument("--count", type=int, default=10, help="搜索深度")

    # reset
    p_reset = sub.add_parser("reset", help="软重置到指定提交")
    p_reset.add_argument("--project-root", "-p")
    p_reset.add_argument("--revision", required=True, help="目标 revision")

    # log
    p_log = sub.add_parser("log", help="查看提交历史")
    p_log.add_argument("--project-root", "-p")
    p_log.add_argument("--count", type=int, default=10)
    p_log.add_argument("--since", help="起始时间（如 2026-06-28）")

    args = parser.parse_args()

    # 确定项目根
    project_root = None
    if args.project_root:
        project_root = Path(args.project_root)
    elif hasattr(args, "project_root") and getattr(args, "project_root", None):
        project_root = Path(getattr(args, "project_root"))
    else:
        detected = _find_project_root(Path.cwd())
        if detected:
            project_root = detected
        else:
            print("错误: 无法检测项目根，请用 --project-root 指定", file=sys.stderr)
            sys.exit(1)

    if not project_root.is_dir():
        print(f"错误: 目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    if args.command == "init":
        result = GitVault.init_project(project_root)
        for line in result.get("lines", []):
            print(line)
        if result.get("error"):
            print(f"⚠ {result['error']}", file=sys.stderr)
        if not result["ok"]:
            sys.exit(1)

    elif args.command == "commit":
        result = GitVault.commit(
            project_root, args.message,
            stage=args.stage, files=args.files
        )
        if result["saved"] and result["hash"]:
            print(f"✅ {result['hash']} {result['message']}")
        elif result["saved"] and not result["hash"]:
            print(f"📦 {result['message']}（已缓存）")
        else:
            print(f"ℹ 无变更需要提交")
        if result.get("error"):
            print(f"⚠ {result['error']}", file=sys.stderr)

    elif args.command == "status":
        s = GitVault.status(project_root)
        if not s["initialized"]:
            print("ℹ git 仓库未初始化")
            print(f"   运行: python git_vault.py init -p {project_root}")
            sys.exit(0)

        print(f"📂 项目: {project_root.name}")
        print(f"   路径: {project_root}")
        if s["last_commit"]:
            lc = s["last_commit"]
            print(f"   最新提交: {lc['message']} ({lc['date']})")
        print(f"   提交数: {s['commits_count']}")

        if s["clean"]:
            print(f"   工作树: ✅ 干净")
        else:
            if s["untracked"]:
                print(f"   未跟踪: {len(s['untracked'])} 个文件")
                for f in s["untracked"][:10]:
                    print(f"     ?? {f}")
            if s["modified"]:
                print(f"   已修改（工作区）: {len(s['modified'])} 个文件")
                for f in s["modified"][:10]:
                    print(f"     M  {f}")
            if s["staged"]:
                print(f"   已暂存: {len(s['staged'])} 个文件")
                for f in s["staged"][:10]:
                    print(f"     + {f}")

    elif args.command == "restore":
        result = GitVault.restore(
            project_root, args.file, revision=args.revision
        )
        if result["ok"]:
            print(f"✅ 已恢复: {result['file']} (revision: {result['revision']})")
        else:
            print(f"❌ {result['error']}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list-deleted":
        entries = GitVault.list_deleted(project_root, count=args.count)
        if not entries:
            print("ℹ 未找到已删除的文件记录")
            sys.exit(0)

        for entry in entries:
            print(f"\n{entry['commit']}  {entry['date']}")  # noqa: E701
            print(f"    {entry['message']}")
            for f in entry["files"]:
                print(f"    ✂  {f}")

    elif args.command == "reset":
        result = GitVault.reset_to(project_root, args.revision)
        if result["ok"]:
            print(f"✅ 已重置到 {result['revision']}（工作区文件保留）")
        else:
            print(f"❌ {result['error']}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "log":
        kwargs = {"count": args.count}
        if args.since:
            kwargs["since"] = args.since
        entries = GitVault.log(project_root, **kwargs)
        if not entries:
            print("ℹ 无提交记录")
            sys.exit(0)

        print(f"提交历史 ({len(entries)}):")
        print("-" * 60)
        for entry in entries:
            print(f"{entry['hash']}  {entry['date']}")
            print(f"    {entry['message']}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
