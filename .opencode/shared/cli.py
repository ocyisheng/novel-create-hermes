#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel-create-hermes 统一 CLI 入口。

把所有命令路由到对应的子 CLI。避免 Agent prompt 中维护多个入口路径。
所有文档只引用此一个入口。

用法:
    python .opencode/shared/cli.py v2 <command> [--path <PROJECT>] [args...]
    python .opencode/shared/cli.py project <command> [args...]
    python .opencode/shared/cli.py env [--fix|--force] [--root <PATH>]

领域:
    v2        V2 叙事单元操作（原 v2/v2_cli.py）
              search / check / report / create-unit / add-relation / viz ...
    project   项目管理（原 project/project_init.py）
              new / import / status / resume / switch / delete
    env       环境管理（原 env/env_setup.py）
              默认检查 / --fix 修复 / --force 重建

示例:
    python .opencode/shared/cli.py v2 search --path novels/龙渊 --keyword "天道宗"
    python .opencode/shared/cli.py v2 viz --path novels/龙渊 --open
    python .opencode/shared/cli.py project new "龙渊" "玄幻" --v2
    python .opencode/shared/cli.py project status "龙渊"
    python .opencode/shared/cli.py env --fix
"""

import sys
import os

# 确保 shared/ 在 sys.path 中，使子模块可被正确导入
_SHARED_DIR = os.path.dirname(os.path.abspath(__file__))
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    domain = sys.argv[1]
    # 移除前两个参数（cli.py <domain>），把剩余参数传给子 CLI
    rest_args = [sys.argv[0]] + sys.argv[2:]  # 保留 argv[0] 作为程序名

    dispatch = {
        "v2": _route_v2,
        "project": _route_project,
        "env": _route_env,
    }

    router = dispatch.get(domain)
    if not router:
        print(f"未知领域: {domain}")
        print("可用领域: v2, project, env")
        print(__doc__)
        sys.exit(1)

    router(rest_args)


def _route_v2(args: list):
    """路由到 v2/v2_cli.py"""
    v2_dir = os.path.join(_SHARED_DIR, "v2")
    if v2_dir not in sys.path:
        sys.path.insert(0, v2_dir)
    sys.argv = args
    from v2_cli import main as v2_main
    v2_main()


def _route_project(args: list):
    """路由到 project/project_init.py"""
    project_dir = os.path.join(_SHARED_DIR, "project")
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    sys.argv = args
    from project_init import main as project_main
    project_main()


def _route_env(args: list):
    """路由到 env/env_setup.py"""
    env_dir = os.path.join(_SHARED_DIR, "env")
    if env_dir not in sys.path:
        sys.path.insert(0, env_dir)
    sys.argv = args
    from env_setup import main as env_main
    env_main()


if __name__ == "__main__":
    main()
