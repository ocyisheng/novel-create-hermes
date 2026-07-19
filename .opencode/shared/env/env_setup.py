#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
env_setup.py — 环境验证与修复

支持多小说项目共享 .venv。
.venv 自动发现顺序：CWD → CWD父目录 → 向上回溯 → 工具根目录。
也可用 --root 显式指定工具根目录。

本模块职责（作为纯函数库，由 cli.py 和 novel_tool.py 调用）：
1. 验证 .venv 是否存在且可用
2. 验证核心依赖是否已安装
3. 自动修复缺失依赖
4. 输出环境状态报告

用法:
    python .opencode/shared/cli.py env [--fix] [--force] [--root <路径>]

CLI 入口已移至 cli.py。
"""

import os
import sys
import platform
import subprocess
from pathlib import Path


# ===========================================================================
# 配置
# ===========================================================================

# .venv 位于小说项目的父目录，多个小说项目共享
# 例: novels/.venv  (novels/小说1, novels/小说2 共用)
SKILL_DIR = Path(__file__).resolve().parent.parent  # novel-env-setup
_TOOL_ROOT = SKILL_DIR.parent.parent.parent  # novel-create-hermes 工具根目录

# 自动发现 .venv：按优先级搜索
def _discover_venv() -> Path:
    """从当前目录开始向上搜索 .venv"""
    cwd = Path.cwd().resolve()

    # 优先级 1: CWD 本身
    if (cwd / ".venv").exists():
        return cwd / ".venv"

    # 优先级 2: CWD 的父目录（当 CWD 是小说项目子目录时）
    if cwd.parent and (cwd.parent / ".venv").exists():
        return cwd.parent / ".venv"

    # 优先级 3: CWD 向上回溯 3 层（兼容嵌套较深的情况）
    for parent in cwd.parents:
        if (parent / ".venv").exists():
            return parent / ".venv"

    # 优先级 4: 工具根目录（向后兼容）
    return _TOOL_ROOT / ".venv"

VENV_DIR = _discover_venv()
REQUIREMENTS = SKILL_DIR / "scripts" / "requirements.txt"

MIN_PYTHON = (3, 8)


# ===========================================================================
# 环境检测
# ===========================================================================

def check_python_version() -> tuple:
    """检查当前 Python 版本是否满足要求。返回 (是否满足, 版本字符串)。"""
    major, minor = sys.version_info[:2]
    micro = sys.version_info[2]
    version_str = f"{major}.{minor}.{micro}"
    return (major, minor) >= MIN_PYTHON, version_str


def check_venv_exists() -> bool:
    """检查虚拟环境目录是否存在。"""
    if platform.system() == "Windows":
        return (VENV_DIR / "Scripts" / "python.exe").exists()
    else:
        return (VENV_DIR / "bin" / "python3").exists()


def get_venv_python() -> Path:
    """获取虚拟环境中的 Python 可执行文件路径。"""
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    else:
        return VENV_DIR / "bin" / "python3"


def check_dependencies(venv_python: Path) -> tuple:
    """检查核心依赖是否已安装。返回 (是否全部安装, 缺失列表)。"""
    required = [("PyYAML", "yaml")]
    missing = []

    for name, import_name in required:
        try:
            result = subprocess.run(
                [str(venv_python), "-c", f"import {import_name}; print({import_name}.__version__)"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                missing.append(name)
        except Exception:
            missing.append(name)

    return len(missing) == 0, missing


# ===========================================================================
# 环境修复
# ===========================================================================

def fix_dependencies(venv_python: Path) -> bool:
    """在虚拟环境中安装缺失的依赖。"""
    if not REQUIREMENTS.exists():
        print(f"  ❌ requirements.txt 不存在: {REQUIREMENTS}")
        return False

    print(f"\n  正在安装依赖...")
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"  ❌ 依赖安装失败: {result.stderr}")
            return False
        print(f"  ✅ 依赖已安装")
        return True
    except subprocess.TimeoutExpired:
        print("  ❌ 依赖安装超时")
        return False
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False


def force_recreate_venv() -> bool:
    """强制重建虚拟环境。"""
    import shutil

    print(f"\n[强制模式] 删除旧环境...")
    if VENV_DIR.exists():
        try:
            shutil.rmtree(VENV_DIR)
            print(f"  ✅ 已删除: {VENV_DIR}")
        except Exception as e:
            print(f"  ❌ 删除失败: {e}")
            return False

    # 获取系统 Python 命令
    python_cmd = "python" if platform.system() == "Windows" else "python3"
    print(f"\n[1/2] 创建虚拟环境...")
    try:
        result = subprocess.run(
            [python_cmd, "-m", "venv", str(VENV_DIR)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"  ❌ 虚拟环境创建失败: {result.stderr}")
            return False
        print(f"  ✅ 虚拟环境已创建")
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return False

    venv_python = get_venv_python()
    print(f"\n[2/2] 安装依赖...")
    return fix_dependencies(venv_python)


# ===========================================================================
# 状态报告
# ===========================================================================

def print_status() -> int:
    """打印环境状态报告。返回 0=就绪, 1=未就绪。"""
    print("\n" + "=" * 50)
    print("环境状态报告")
    print("=" * 50)
    print(f"  小说项目根目录: {VENV_DIR.parent}")
    print(f"  虚拟环境位置:   {VENV_DIR}")
    print()

    # Python 版本
    version_ok, version_str = check_python_version()
    status = "✅" if version_ok else "❌"
    print(f"  {status} Python: {version_str} {'(满足 >= 3.8)' if version_ok else '(需要 >= 3.8)'}")

    # 虚拟环境
    venv_exists = check_venv_exists()
    status = "✅" if venv_exists else "❌"
    print(f"  {status} 虚拟环境: {VENV_DIR}")

    # 依赖
    if venv_exists:
        venv_python = get_venv_python()
        deps_ok, missing = check_dependencies(venv_python)
    else:
        deps_ok = False
        missing = ["所有依赖"]

    status = "✅" if deps_ok else "❌"
    missing_str = ", ".join(missing) if missing else "无"
    print(f"  {status} 依赖: {'全部已安装' if deps_ok else f'缺失: {missing_str}'}")

    print("=" * 50)

    if version_ok and venv_exists and deps_ok:
        print("\n✅ 环境已就绪！")
        print(f"\n激活命令:")
        if platform.system() == "Windows":
            print(f"  call {VENV_DIR}\\Scripts\\activate")
        else:
            print(f"  source {VENV_DIR}/bin/activate")
        print(f"\n下一步: 执行小说项目操作")
        return 0
    else:
        print("\n⚠️  环境未就绪")
        if not venv_exists:
            print(f"\n修复方法:")
            print(f"  cd 到小说项目的根目录（即小说1、小说2所在目录）")
            print(f"  然后运行: .opencode\\skills\\novel-env-setup\\scripts\\setup_env.bat")
        elif not deps_ok:
            print(f"\n修复方法:")
            print(f"  python {Path(__file__).resolve().relative_to(Path.cwd())} --fix")
        return 1


# ===========================================================================
# 程序化入口（无 argparse 依赖）
# ===========================================================================

def run_env_setup(
    fix: bool = False,
    force: bool = False,
    root: str = "",
) -> int:
    """运行环境验证与修复。

    供 novel_tool.py 等程序化调用，不依赖 argparse。

    Args:
        fix: 自动修复缺失依赖
        force: 强制重建 .venv
        root: 工具根目录（覆盖 .venv 路径）

    Returns:
        0 = 就绪, 1 = 未就绪
    """
    global VENV_DIR

    if root:
        root_path = Path(root).resolve()
        VENV_DIR = root_path / ".venv"
        print(f"📂 使用指定根目录: {root_path}")

    print("=" * 50)
    print("novel-create-hermes 环境验证")
    print("=" * 50)

    version_ok, version_str = check_python_version()
    if not version_ok:
        print(f"\n❌ Python 版本 {version_str} 不满足要求（需要 >= 3.8）")
        print("   请升级 Python 版本")
        return 1

    print(f"✅ Python {version_str}")

    if force:
        if force_recreate_venv():
            print("\n✅ 环境已重建")
            return print_status()
        return 1

    exit_code = print_status()

    if exit_code != 0 and fix:
        if check_venv_exists():
            venv_python = get_venv_python()
            if fix_dependencies(venv_python):
                print("\n✅ 环境已修复")
                return print_status()
        else:
            print("\n❌ .venv 不存在，无法自动修复")
            venv_parent = VENV_DIR.parent
            print(f"   请在小说项目根目录创建 .venv：")
            print(f"   cd {venv_parent}")
            print(f"   .opencode\\skills\\novel-env-setup\\scripts\\setup_env.bat")

    return exit_code



