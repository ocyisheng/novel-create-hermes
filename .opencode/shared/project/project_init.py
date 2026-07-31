#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_init.py — 项目管理（兼容桥接层）

管理小说项目的创建、导入、状态查看、续写、切换和删除。

业务逻辑已迁移至 handlers/handlers_project.py。
cli.py 直接调用 handlers，不再经过本模块。
本模块仅保留旧符号（NOVELS_ROOT / project_path / run_project_command 等）
作为向后兼容桥，内部委托给 handlers，避免双实现漂移。

依赖: Python 3.8+
"""

from __future__ import annotations

import os
import sys

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


# ── 目录配置 ──────────────────────────────────────────────────────────────

def find_novels_root() -> str:
    """从多个候选位置发现 NOVELS_ROOT"""
    env = os.environ.get("NOVELS_ROOT")
    if env and os.path.isdir(env):
        return env
    # CWD 下的 novels/
    cwd_novels = os.path.join(os.getcwd(), "novels")
    if os.path.isdir(cwd_novels):
        return cwd_novels
    # 工具根目录下的 novels/
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    tool_novels = os.path.join(tool_root, "novels")
    if os.path.isdir(tool_novels):
        return tool_novels
    return cwd_novels


NOVELS_ROOT = find_novels_root()


# ── 工具函数（兼容桥，委托 handlers）─────────────────────────────────────

def project_path(name: str) -> str:
    return os.path.join(NOVELS_ROOT, name)


def project_exists(name: str) -> bool:
    return os.path.isdir(project_path(name)) and os.path.isfile(
        os.path.join(project_path(name), "config.yaml")
    )


def load_config(name: str) -> dict:
    from handlers.handlers_project import _load_config
    return _load_config(name)


def save_config(name: str, config: dict):
    from handlers.handlers_project import _save_config
    _save_config(name, config)


def get_context_path(project_name: str) -> str:
    """获取 novel-context.md 中对应项目的持久化上下文路径"""
    return os.path.join(NOVELS_ROOT, project_name, ".context", "novel-context.md")


def global_context_path() -> str:
    """获取当前 novel-context.md 路径（工具根目录下的全局上下文）"""
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(tool_root, ".context", "novel-context.md")


# ── 程序化调度入口（无 argparse 依赖，委托 handlers）─────────────────────

def run_project_command(command: str, **kwargs):
    """运行项目管理命令。

    供 novel_tool.py 等程序化调用，不依赖 argparse。
    业务逻辑委托给 handlers/handlers_project.py。

    Args:
        command: 子命令名 (new/import/status/resume/switch/delete)
        **kwargs: 对应命令的参数
    """
    from handlers.handlers_project import (
        handle_project_new,
        handle_project_import,
        handle_project_status,
        handle_project_resume,
        handle_project_switch,
        handle_project_delete,
    )
    dispatch = {
        "new": handle_project_new,
        "import": handle_project_import,
        "status": handle_project_status,
        "resume": handle_project_resume,
        "switch": handle_project_switch,
        "delete": handle_project_delete,
    }
    fn = dispatch.get(command)
    if not fn:
        return {"error": f"未知命令 {command}"}
    # 旧 argparse 参数名与 handler 签名差异：source → source_path
    if command == "import" and "source" in kwargs and "source_path" not in kwargs:
        kwargs["source_path"] = kwargs.pop("source")
    return fn(**kwargs)
