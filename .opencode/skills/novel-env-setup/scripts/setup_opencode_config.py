#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_opencode_config.py — 创建/更新 OhMyOpenAgent 插件配置

在环境初始化后自动调用，确保 novel 创作所需的 category 路由配置已就绪。
追加模式：读取已有配置 → 追加/更新 categories → 写回，不会丢失其他字段。
"""

import argparse
import json
import shutil
import sys
from pathlib import Path


def create_parser() -> argparse.ArgumentParser:
    """创建参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="setup_opencode_config.py",
        description="创建/更新 OhMyOpenAgent 插件配置，确保 novel 创作所需的 category 路由已就绪。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python setup_opencode_config.py              # 创建/更新配置
  python setup_opencode_config.py --dry-run     # 预览，不修改
  python setup_opencode_config.py --force       # 跳过读取失败警告，直接覆盖

说明:
  追加模式：读取已有配置 → 追加/更新 novel-write/novel-review/novel-ideate 类别 → 写回
  不会丢失其他已有的非 novel 类别配置。"""
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览合并结果，不修改文件"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过读取失败警告，直接覆盖写入"
    )
    return parser

# ===========================================================================
# novel 创作 category 配置
# ===========================================================================

NOVEL_CATEGORIES = {
    "novel-write": {
        "model": "opencode/deepseek-v4-flash-free",
        "fallback_models": [
            "opencode/big-pickle",
            "opencode/nemotron-3-super-free",
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-v4-pro",
        ],
    },
    "novel-review": {
        "model": "opencode/deepseek-v4-flash-free",
        "fallback_models": [
            "opencode/nemotron-3-super-free",
            "opencode/big-pickle",
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-v4-pro",
        ],
    },
    "novel-ideate": {
        "model": "opencode/big-pickle",
        "fallback_models": [
            "opencode/deepseek-v4-flash-free",
            "opencode/mimo-v2.5-free",
            "deepseek/deepseek-v4-flash",
        ],
    }
}


def get_config_path() -> Path:
    """返回 oh-my-openagent.json 的完整路径（跨平台）。"""
    return Path.home() / ".config" / "opencode" / "oh-my-openagent.json"


# ===========================================================================
# 读取
# ===========================================================================

def load_config(path: Path) -> dict:
    """读取已有配置，不存在则返回空字典。

    字节序（BOM）自动识别：优先 utf-8-sig（Windows PowerShell 输出带 BOM），
    若解析失败再尝试纯 utf-8。

    返回:
        (success: bool, data: dict)
        success=False 表示文件存在但解析失败。
    """
    if not path.is_file():
        return True, {}

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            raw = path.read_text(encoding=encoding).strip()
            if not raw:
                return True, {}
            data = json.loads(raw)
            if isinstance(data, dict):
                return True, data
            return False, {}
        except (json.JSONDecodeError, OSError):
            continue

    return False, {}


# ===========================================================================
# 合并（追加模式）
# ===========================================================================

def merge_categories(config: dict) -> dict:
    """将 novel categories 追加到配置中。

    - 保留现有 ``categories`` 中不属于 NOVEL_CATEGORIES 的项
    - NOVEL_CATEGORIES 中的 key 强制覆盖（保证路由配置正确）
    - 其他顶级 key 完全保留
    """
    existing_cats = config.get("categories")
    if not isinstance(existing_cats, dict):
        existing_cats = {}

    # 分离：保留的非 novel + 追加的 novel
    non_novel_cats = {k: v for k, v in existing_cats.items() if k not in NOVEL_CATEGORIES}
    config["categories"] = {**non_novel_cats, **NOVEL_CATEGORIES}

    return config


# ===========================================================================
# 写回 + 备份
# ===========================================================================

def write_config(config: dict, path: Path, backup: bool = True) -> None:
    """将配置写入 JSON 文件。写前做备份。

    参数:
        backup: 若 True 且原文件存在，先复制为 .bak。
    """
    if backup and path.is_file():
        bak = path.with_suffix(".json.bak")
        shutil.copy2(path, bak)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ===========================================================================
# 统计
# ===========================================================================

def calc_stats(config: dict) -> dict:
    """返回合并后的统计信息。"""
    cats = config.get("categories", {})
    novel_cat_count = len(NOVEL_CATEGORIES)
    total_cat_count = len(cats)
    non_novel_cat_count = total_cat_count - novel_cat_count
    other_key_count = len(config) - 1  # 减去 categories
    return {
        "novel_cats": novel_cat_count,
        "non_novel_cats": max(0, non_novel_cat_count),
        "other_keys": max(0, other_key_count),
    }


# ===========================================================================
# CLI
# ===========================================================================

def main() -> int:
    parser = create_parser()
    args = parser.parse_args()
    dry_run = args.dry_run
    force = args.force

    config_path = get_config_path()

    print(f"配置文件: {config_path}")

    # ── 读取 ────────────────────────────────────────────────────
    ok, existing = load_config(config_path)

    if not ok:
        msg = (
            f"⚠️  读取失败: {config_path} 存在但 JSON 格式无效。\n"
            f"   手动修复或删除后重试"
        )
        if not force:
            print(msg)
            return 1
        print(f"⚠️  读取失败（--force 忽略，将覆盖写入）")
        existing = {}

    # ── 预览 ────────────────────────────────────────────────────
    if dry_run:
        if ok and config_path.is_file():
            print(f"\n当前配置:\n{config_path.read_text(encoding='utf-8-sig')}")
        else:
            print("\n当前配置: 文件不存在")

        merged = merge_categories(dict(existing))
        print(f"合并后:\n{json.dumps(merged, ensure_ascii=False, indent=2)}")

        stats = calc_stats(merged)
        print(f"\n统计: {stats['novel_cats']} novel 类别"
              f" + {stats['non_novel_cats']} 非 novel 类别"
              f" + {stats['other_keys']} 其他配置项")
        print("(dry-run，未修改文件)")
        return 0

    # ── 合并 ────────────────────────────────────────────────────
    merged = merge_categories(dict(existing))

    # ── 写回 ────────────────────────────────────────────────────
    write_config(merged, config_path)

    # ── 报告 ────────────────────────────────────────────────────
    stats = calc_stats(merged)
    is_new = not (ok and existing)

    if is_new:
        print(f"✅ 已创建 ({stats['novel_cats']} novel 类别)")
    else:
        print(f"✅ 已更新"
              f" (保留 {stats['non_novel_cats']} 非 novel 类别"
              f" + {stats['other_keys']} 其他配置项)")

    print(f"📄 {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
