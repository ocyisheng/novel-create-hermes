#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
checkpoint_service.py — novel-checkpoint-service 公共 API 门面

本文件是所有外部代码访问检查点服务的唯一入口。
直接 import rule_loader / 访问内部模块不被支持。

CLI 用法（Agent 层）:
    python checkpoint_service.py check <检查点名> <等级>   查询检查点决策
    python checkpoint_service.py list                      列出所有检查点
    python checkpoint_service.py reload                    重载规则
    python checkpoint_service.py self-check                自检

Python API（脚本层）:
    from checkpoint_service import (
        check_pause,           # 查询检查点决策
        is_pause,              # 便捷布尔判断
        get_checkpoints,       # 获取所有检查点名称
        get_checkpoint_rule,   # 获取特定检查点规则
        reload_rules,          # 从文件重载规则
        self_check,            # 自检
    )
"""

import argparse
import json
import sys
import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger("checkpoint_service")


# ===========================================================================
# 内部实现
# ===========================================================================

def _find_skill_root() -> Path:
    """定位本技能根目录（scripts/ 的父目录）。"""
    return Path(__file__).parent.parent


def _find_project_root(start: Optional[Path] = None) -> Optional[Path]:
    """
    从当前目录向上查找项目根目录（含 config.yaml 的目录）。
    """
    search_dir = start or Path.cwd()
    for parent in [search_dir] + list(search_dir.parents):
        if (parent / "config.yaml").exists():
            return parent
    return None


def _load_yaml(path: Path) -> dict:
    """安全加载 YAML 文件，失败时返回空 dict。"""
    import yaml
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"加载 YAML 失败 {path}: {e}")
        return {}


# ===========================================================================
# 规则加载
# ===========================================================================

_BUILTIN_RULES: dict = {}                # 内置规则缓存
_PROJECT_RULES_CACHE: dict = {}          # 项目覆盖规则缓存，按 project_root 分键
_CACHED_DEFAULT: str = "continue"        # 默认决策
_LAST_PROJECT_ROOT: Optional[str] = None  # 上次查询的项目根目录


def _load_builtin() -> dict:
    """加载内置默认规则。"""
    rules_path = _find_skill_root() / "scripts" / "default_rules.yaml"
    if not rules_path.exists():
        return {}
    data = _load_yaml(rules_path)
    _CACHED_DEFAULT = data.get("default", "continue")
    return data.get("checkpoints", {})


def _load_project_overrides(project_root: Optional[Path] = None) -> dict:
    """加载项目 config.yaml 中的 checkpoint_rules 覆盖。"""
    if project_root is None:
        project_root = _find_project_root()
    if project_root is None:
        return {}

    config_path = project_root / "config.yaml"
    if not config_path.exists():
        return {}

    data = _load_yaml(config_path)
    return data.get("checkpoint_rules", {})


def _get_effective_rules(project_root: Optional[Path] = None) -> Tuple[dict, str]:
    """
    获取合并后的有效规则。
    返回 (rules_dict, default_decision)。
    项目规则覆盖内置规则中同名的检查点。
    缓存按 project_root 分键，确保多项目切换时规则正确。

    Args:
        project_root: 项目根目录。省略时自动查找。
    """
    global _BUILTIN_RULES, _PROJECT_RULES_CACHE, _CACHED_DEFAULT, _LAST_PROJECT_ROOT

    if not _BUILTIN_RULES:
        _BUILTIN_RULES = _load_builtin()

    # Resolve project_root to a canonical key for cache lookup
    resolved_root = project_root.resolve() if project_root else _find_project_root()
    cache_key = str(resolved_root) if resolved_root else "__no_project__"

    # Reload project overrides when project root changes
    if cache_key not in _PROJECT_RULES_CACHE or _LAST_PROJECT_ROOT != cache_key:
        _PROJECT_RULES_CACHE[cache_key] = _load_project_overrides(resolved_root)
        _LAST_PROJECT_ROOT = cache_key

    project_rules = _PROJECT_RULES_CACHE.get(cache_key, {})

    # 合并：项目规则覆盖内置规则
    merged = dict(_BUILTIN_RULES)
    merged.update(project_rules)
    return merged, _CACHED_DEFAULT


def reload_rules(project_root: Optional[Path] = None) -> None:
    """
    重新从文件加载规则（热重载）。

    Args:
        project_root: 项目根目录。省略时自动查找。
    """
    global _BUILTIN_RULES, _PROJECT_RULES_CACHE, _CACHED_DEFAULT

    _BUILTIN_RULES = _load_builtin()
    # Clear project rules cache on reload so they are re-read from disk
    _PROJECT_RULES_CACHE.clear()

    rules_count = len(_BUILTIN_RULES)
    overrides_count = len(_PROJECT_RULES)
    logger.info(f"规则已重载: {rules_count} 内置, {overrides_count} 项目覆盖")


# ===========================================================================
# 公共 API
# ===========================================================================

# ── Hard-guarded checkpoints (not overridable by project config) ───
_HARD_PAUSE_CHECKPOINTS = {"writing_after_outline"}


def check_pause(point_name: str, intervention_level: str, project_root: Optional[Path] = None) -> str:
    """
    根据检查点和干预等级返回暂停决策。

    Args:
        point_name: 检查点名称（如 "writing_after_outline"）
        intervention_level: 干预等级（high/medium/low）
        project_root: 项目根目录。省略时自动查找。

    Returns:
        "pause" / "continue" / "auto_fix"
    """
    # Hard guard: certain checkpoints always pause, regardless of project config
    if point_name in _HARD_PAUSE_CHECKPOINTS:
        return "pause"

    rules, default = _get_effective_rules(project_root)
    if point_name not in rules:
        return default
    return rules[point_name].get(intervention_level, default)


def is_pause(point_name: str, intervention_level: str) -> bool:
    """
    便捷函数：是否需要暂停？

    Args:
        point_name: 检查点名称
        intervention_level: 干预等级

    Returns:
        True 表示需要暂停，False 表示继续
    """
    return check_pause(point_name, intervention_level) == "pause"


def get_checkpoints() -> List[str]:
    """返回所有已注册的检查点名称（有序）。"""
    rules, _ = _get_effective_rules()
    return list(rules.keys())


def get_checkpoint_rule(point_name: str) -> Optional[dict]:
    """返回特定检查点的规则字典，不存在时返回 None。"""
    rules, _ = _get_effective_rules()
    return rules.get(point_name)


def self_check() -> List[dict]:
    """
    运行环境自检。
    返回检查项列表，每项含 name / status / detail。
    """
    results = []

    # 检查 Python 版本
    py_ok = sys.version_info >= (3, 8)
    results.append({
        "name": "Python 版本",
        "status": "pass" if py_ok else "fail",
        "detail": sys.version if py_ok else f"需要 Python 3.8+, 当前 {sys.version_info.major}.{sys.version_info.minor}",
    })

    # 检查 PyYAML
    try:
        import yaml
        results.append({"name": "PyYAML", "status": "pass", "detail": yaml.__version__})
    except ImportError:
        results.append({"name": "PyYAML", "status": "fail", "detail": "未安装, 运行 novel-env-setup 安装"})

    # 检查内置规则文件
    rules_path = _find_skill_root() / "scripts" / "default_rules.yaml"
    if rules_path.exists():
        results.append({"name": "内置规则文件", "status": "pass", "detail": str(rules_path)})
    else:
        results.append({"name": "内置规则文件", "status": "fail", "detail": f"不存在: {rules_path}"})

    # 检查规则加载
    try:
        rules, default = _get_effective_rules()
        results.append({
            "name": "规则加载",
            "status": "pass",
            "detail": f"{len(rules)} 个检查点, 默认决策: {default}",
        })
    except Exception as e:
        results.append({"name": "规则加载", "status": "fail", "detail": str(e)})

    return results


# ===========================================================================
# CLI 入口
# ===========================================================================

def _cli_check(args: argparse.Namespace) -> None:
    """CLI: 查询检查点决策。"""
    project_root = Path(args.project_root) if args.project_root else None
    decision = check_pause(args.checkpoint, args.level, project_root)
    result = {
        "checkpoint": args.checkpoint,
        "level": args.level,
        "decision": decision,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cli_list(args: argparse.Namespace) -> None:
    """CLI: 列出所有检查点。"""
    rules, default = _get_effective_rules()
    print(f"默认决策: {default}")
    print(f"检查点数量: {len(rules)}")
    print()
    for name in sorted(rules.keys()):
        rule = rules[name]
        levels = ", ".join(f"{k}={v}" for k, v in sorted(rule.items()))
        print(f"  {name}")
        print(f"    {levels}")


def _cli_reload(args: argparse.Namespace) -> None:
    """CLI: 重载规则。"""
    project_root = Path(args.project_root) if args.project_root else None
    reload_rules(project_root)

    rules_count = len(get_checkpoints())
    print(json.dumps({
        "status": "ok",
        "message": f"规则已重载, {rules_count} 个检查点可用",
    }, ensure_ascii=False, indent=2))


def _cli_self_check(args: argparse.Namespace) -> None:
    """CLI: 自检。"""
    results = self_check()
    all_pass = all(r["status"] == "pass" for r in results)
    print(json.dumps({
        "status": "pass" if all_pass else "fail",
        "checks": results,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="novel-checkpoint-service — YAML 规则检查点服务",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # check
    p_check = subparsers.add_parser("check", help="查询检查点决策")
    p_check.add_argument("checkpoint", help="检查点名称")
    p_check.add_argument("level", choices=["high", "medium", "low"], help="干预等级")
    p_check.add_argument("--project-root", "-r", help="项目根目录路径（可选）")
    p_check.set_defaults(func=_cli_check)

    # list
    p_list = subparsers.add_parser("list", help="列出所有检查点")
    p_list.set_defaults(func=_cli_list)

    # reload
    p_reload = subparsers.add_parser("reload", help="重载规则")
    p_reload.add_argument("--project-root", "-r", help="项目根目录路径（可选）")
    p_reload.set_defaults(func=_cli_reload)

    # self-check
    p_self = subparsers.add_parser("self-check", help="环境自检")
    p_self.set_defaults(func=_cli_self_check)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
