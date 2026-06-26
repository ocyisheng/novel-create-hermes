#!/usr/bin/env python3
"""
config_manager.py — 安全读写 config.yaml 字段，支持 dot notation 嵌套访问。
                    含阶段验证（支持 P-1.5 pre_style 阶段）。

阶段模型（v3.1.0）：
  主阶段: P-3 → P-2 → P-1 → P0 → P1 → P-1.5(可选) → P2 → P3 → P4 → P4.5 → P5 → P6 → P7 → P8 → P9 → P10 → P11 → P12 → P13 → P14 → P15
  活跃子阶段（P2 支持）: [角色, 世界观, 总纲, 情节, ...]

Usage:
    python config_manager.py get <field> --project-root PATH
    python config_manager.py set <field> <value> --project-root PATH
    python config_manager.py validate-stage <stage>   # 验证阶段名称是否合法

Examples:
    python config_manager.py get 当前阶段 --project-root NOVELS_ROOT/项目名
    python config_manager.py get 创作进度.当前章节 --project-root NOVELS_ROOT/项目名
    python config_manager.py set 当前阶段 章节写作 --project-root NOVELS_ROOT/项目名
    python config_manager.py validate-stage pre_style --project-root NOVELS_ROOT/项目名
"""

import sys
from pathlib import Path
import yaml

# ── 合法阶段列表（v3.1.0） ──────────────────────────────────────────────────
VALID_STAGES = [
    "pre_setup",           # P-3 需求发现
    "project_setup",       # P-2 项目操作
    "env_setup",           # P-1 环境初始化
    "knowledge_base",      # P0 知识库
    "ideation",            # P1 创意构思
    "pre_style",           # P-1.5 风格提取（可选，在P1之后）
    "world_building",      # P2 世界观建设
    "characters",          # P3 角色创建
    "synopsis",            # P4 总纲撰写
    "narrative_strategy",  # P4.5 叙事策略
    "plot",                # P5 情节构建
    "volume_outline",      # P6 分卷大纲
    "chapter_outline",     # P7 分纲构建
    "chapter_writing",     # P8 章节写作
    "quality_check",       # P9 质量检测
    "style_verify",        # P10 风格验证
    "export",              # P11 导出
    "chapter_edit",        # P12 章节编辑
    "entity_edit",         # P13 实体编辑
    "search_analysis",     # P14 搜索分析
    "other",               # P15 其他
]

# 阶段映射：中文名 → 英文ID（用于 validate-stage 兼容）
STAGE_ALIASES = {
    "需求发现": "pre_setup",
    "项目操作": "project_setup",
    "环境初始化": "env_setup",
    "知识库": "knowledge_base",
    "创意构思": "ideation",
    "风格提取": "pre_style",
    "世界观建设": "world_building",
    "角色创建": "characters",
    "总纲撰写": "synopsis",
    "叙事策略": "narrative_strategy",
    "情节构建": "plot",
    "分卷大纲": "volume_outline",
    "分纲构建": "chapter_outline",
    "章节写作": "chapter_writing",
    "质量检测": "quality_check",
    "风格验证": "style_verify",
    "导出": "export",
    "章节编辑": "chapter_edit",
    "实体编辑": "entity_edit",
    "搜索分析": "search_analysis",
    "其他": "other",
}


def load_config(project_root: Path) -> dict:
    config_path = project_root / "config.yaml"
    if not config_path.is_file():
        print(f"Error: config.yaml not found at {project_root}", file=sys.stderr)
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(project_root: Path, data: dict) -> None:
    config_path = project_root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        bak = config_path.with_suffix(".yaml.bak")
        if bak.exists():
            bak.unlink()
        config_path.rename(bak)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def _get_nested(data: dict, dot_path: str):
    keys = dot_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_nested(data: dict, dot_path: str, value):
    keys = dot_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def main():
    import argparse
    parser = argparse.ArgumentParser(description="config.yaml 字段读写（支持嵌套 dot notation）")
    sub = parser.add_subparsers(dest="command")

    p_get = sub.add_parser("get", help="读取字段")
    p_get.add_argument("field", help="字段名（如 当前阶段, 创作进度.当前章节）")
    p_get.add_argument("--project-root", required=True, help="项目根目录")

    p_set = sub.add_parser("set", help="写入字段")
    p_set.add_argument("field", help="字段名")
    p_set.add_argument("value", help="新值")
    p_set.add_argument("--project-root", required=True, help="项目根目录")

    p_validate = sub.add_parser("validate-stage", help="验证阶段名称是否合法")
    p_validate.add_argument("stage", help="阶段名（中文或英文ID）")
    p_validate.add_argument("--project-root", required=True, help="项目根目录")

    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    data = load_config(project_root)

    if args.command == "get":
        val = _get_nested(data, args.field)
        if val is None:
            print(f"Warning: field '{args.field}' not found in config.yaml", file=sys.stderr)
            sys.exit(1)
        print(val)
    elif args.command == "validate-stage":
        stage = args.stage
        # Try exact match in valid stages
        if stage in VALID_STAGES:
            print(f"✅ 合法阶段: {stage}")
            return
        # Try alias lookup
        if stage in STAGE_ALIASES:
            mapped = STAGE_ALIASES[stage]
            print(f"✅ 合法阶段: {stage} → {mapped}")
            return
        # Try fuzzy match
        for valid in VALID_STAGES:
            if stage.lower() in valid.lower() or valid.lower() in stage.lower():
                print(f"❓ 未精确匹配，您是否想用: {valid}？")
                print(f"   合法阶段列表: {', '.join(VALID_STAGES)}")
                sys.exit(1)
        print(f"❌ 非法阶段: {stage}")
        print(f"   合法阶段列表: {', '.join(VALID_STAGES)}")
        sys.exit(1)
    elif args.command == "set":
        old = _get_nested(data, args.field)
        _set_nested(data, args.field, args.value)
        save_config(project_root, data)
        print(f"已更新 {args.field}: {old} → {args.value}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
