"""entity_schema.py — 实体字段 Schema 定义

为 novel-entity-editor 技能提供各实体类型的可编辑字段定义。
用于：
  1. AI 判断哪些字段可以安全修改
  2. entity_diff.py 的 diff 范围过滤
  3. 编辑后的验证（确保必填字段不被删除）

用法:
    from entity_schema import get_schema, get_editable_fields
    schema = get_schema("character")
    editable = get_editable_fields("character")
"""

from typing import Any

# ── Schema 定义 ──────────────────────────────────────────────────────────────

# 每个实体类型定义了：
#   editable:    可编辑字段路径列表（点号路径）
#   protected:   禁止编辑的系统字段
#   required:    编辑后必须保留的必填字段
#   auto_fields: 由脚本自动维护的字段（编辑时忽略）

SCHEMAS: dict[str, dict[str, Any]] = {
    "character": {
        "description": "角色档案 (characters/{角色名}.yaml)",
        "editable": [
            "索引信息.角色类型",
            "索引信息.势力",
            "索引信息.状态",
            "摘要.一句话描述",
            "摘要.当前境况",
            "摘要.核心特质",
            "摘要.当前目标",
            "摘要.关键关系",
            "完整档案.基本信息.性别",
            "完整档案.基本信息.年龄",
            "完整档案.基本信息.身份",
            "完整档案.基本信息.外貌.身高",
            "完整档案.基本信息.外貌.体型",
            "完整档案.基本信息.外貌.特征",
            "完整档案.基本信息.外貌.习惯动作",
            "完整档案.基本信息.外貌.服饰风格",
            "完整档案.性格.核心特质",
            "完整档案.性格.优点",
            "完整档案.性格.缺点",
            "完整档案.性格.价值观",
            "完整档案.性格.口头禅",
            "完整档案.性格.语气风格",
            "完整档案.背景.出身",
            "完整档案.背景.成长经历",
            "完整档案.背景.关键事件",
            "完整档案.背景.心理创伤",
            "完整档案.背景.动机根源",
            "完整档案.目标与冲突.公开目标",
            "完整档案.目标与冲突.隐藏目标",
            "完整档案.目标与冲突.内心渴望",
            "完整档案.目标与冲突.核心恐惧",
            "完整档案.目标与冲突.主要障碍",
            "完整档案.能力设定.技能专长",
            "完整档案.能力设定.天生才能",
            "完整档案.能力设定.能力限制",
            "完整档案.能力设定.成长潜力",
            "完整档案.关系网络.家人",
            "完整档案.关系网络.师门",
            "完整档案.关系网络.朋友",
            "完整档案.关系网络.敌人",
            "完整档案.关系网络.恋人",
            "完整档案.关系网络.其他关系",
            "完整档案.角色弧线.起始状态",
            "完整档案.角色弧线.成长阶段",
            "完整档案.角色弧线.关键转变",
            "完整档案.角色弧线.最终状态",
            "完整档案.角色弧线.弧线完整性",
            "完整档案.与主线关系.主线参与度",
            "完整档案.与主线关系.对主线影响",
            "完整档案.与主线关系.主线对其影响",
            "完整档案.创作笔记.注意事项",
            "完整档案.创作笔记.避免踩坑",
            "完整档案.创作笔记.扩展建议",
        ],
        "protected": [
            "_meta.entity_type",
            "_meta.schema_version",
            "_meta.created_at",
        ],
        "required": [
            "索引信息.实体ID",
            "索引信息.名称",
            "索引信息.角色类型",
            "索引信息.状态",
            "摘要.一句话描述",
        ],
        "auto_fields": [
            "_meta.updated_at",
            "索引信息.首次出场章节",
        ],
    },
    "worldbuilding": {
        "description": "世界观实体 (worldbuilding/{实体ID}.yaml)",
        "editable": [
            "索引信息.名称",
            "索引信息.实体子类型",
            "索引信息.状态",
            "摘要.一句话描述",
            "摘要.关键词",
            "完整档案.世界名称",
            "完整档案.时代背景",
            "完整档案.核心设定",
            "完整档案.物理法则",
            "完整档案.禁忌与限制",
            "完整档案.因果规律",
            "完整档案.体系名称",
            "完整档案.等级划分",
            "完整档案.力量来源",
            "完整档案.势力名称",
            "完整档案.领袖",
            "完整档案.性质",
            "完整档案.核心目标",
            "完整档案.势力平衡",
            "完整档案.地点名称",
            "完整档案.区域描述",
            "完整档案.气候",
            "完整档案.交通要道",
            "完整档案.危险区域",
            "完整档案.纪元划分",
            "完整档案.重大事件",
            "完整档案.种族或民族",
            "完整档案.宗教与信仰",
            "完整档案.社会结构",
            "完整档案.风俗习惯",
            "完整档案.注意事项",
            "完整档案.扩展建议",
        ],
        "protected": [
            "_meta.entity_type",
            "_meta.schema_version",
            "_meta.created_at",
        ],
        "required": [
            "索引信息.实体ID",
            "索引信息.名称",
            "索引信息.实体子类型",
            "摘要.一句话描述",
        ],
        "auto_fields": [
            "_meta.updated_at",
        ],
    },
    "plot_thread": {
        "description": "情节线 (outline/情节线/{主线|支线_名称}.yaml)",
        "editable": [
            "索引信息.名称",
            "索引信息.类型",
            "索引信息.状态",
            "摘要.一句话描述",
            "摘要.当前境况",
            "摘要.核心特质",
            "摘要.当前目标",
            "摘要.关键关系",
            "摘要.当前区间",
            "摘要.区间情节点",
            "摘要.关联角色",
            "完整档案.描述",
            "完整档案.类型",
            "完整档案.冲突核心",
            "完整档案.关键事件",
            "完整档案.关联支线",
            "完整档案.终局设计",
            "完整档案.伏笔清单.已埋伏笔",
            "完整档案.伏笔清单.待回收伏笔",
            "完整档案.角色参与.涉及角色",
            "完整档案.角色参与.角色推动作用",
            "完整档案.创作笔记.注意事项",
            "完整档案.创作笔记.节奏提示",
        ],
        "protected": [
            "_meta.entity_type",
            "_meta.schema_version",
            "_meta.created_at",
        ],
        "required": [
            "索引信息.实体ID",
            "索引信息.名称",
            "索引信息.类型",
            "摘要.一句话描述",
        ],
        "auto_fields": [
            "_meta.updated_at",
            "索引信息.起始章节",
        ],
    },
    "outline_synopsis": {
        "description": "总纲 (outline/总纲.yaml) — 元文档，无三层结构",
        "editable": [
            "项目名称",
            "类型",
            "目标字数",
            "预计章节数",
            "目标读者",
            "核心概念.一句话概述",
            "核心概念.核心卖点",
            "核心概念.主题关键词",
            "核心概念.主题.核心",
            "核心概念.主题.呈现",
            "人物与世界.主角与世界的关系",
            "人物与世界.主角的特殊性",
            "人物与世界.世界规则对主角的约束",
            "人物与世界.主角打破/利用世界规则的方式",
            "人物与世界.初始境况",
            "故事结构.结构类型",
            "故事结构.幕",
            "分卷",
            "节奏.前期基调",
            "节奏.中期基调",
            "节奏.后期基调",
            "节奏.章节分布",
            "结局类型",
            "结局设计",
        ],
        "protected": [],
        "required": [
            "项目名称",
            "类型",
            "核心概念.一句话概述",
        ],
        "auto_fields": [],
    },
    "volume": {
        "description": "分卷大纲 (outline/分卷/卷{N}_{名称}.yaml) — 元文档",
        "editable": [
            "卷信息.卷名",
            "卷信息.章节范围",
            "卷信息.时间跨度",
            "卷信息.核心冲突",
            "叙事任务",
            "主角状态.起点",
            "主角状态.终点",
            "主角状态.年龄",
            "微弧分割",
            "POV分布",
            "间奏章节",
            "关键事件清单",
            "角色发展",
            "本卷节奏.整体基调",
            "本卷节奏.情感曲线",
            "卷末钩子",
        ],
        "protected": [
            "卷信息.卷号",
        ],
        "required": [
            "卷信息.卷号",
            "卷信息.卷名",
            "卷信息.核心冲突",
        ],
        "auto_fields": [],
    },
    "chapter_outline": {
        "description": "分纲 (outline/分纲/卷{卷号}/第{N}章.yaml)",
        "editable": [
            "索引信息.名称",
            "索引信息.状态",
            "摘要.一句话描述",
            "摘要.当前境况",
            "摘要.核心特质",
            "摘要.当前目标",
            "摘要.关键关系",
            "摘要.出场角色",
            "摘要.核心情节点",
            "摘要.关键转折",
            "完整档案.基本信息.章节名",
            "完整档案.基本信息.类型",
            "完整档案.基本信息.字数目标",
            "完整档案.结构规划.开篇.方式",
            "完整档案.结构规划.开篇.上章衔接",
            "完整档案.结构规划.发展.核心冲突",
            "完整档案.结构规划.发展.推进",
            "完整档案.结构规划.转折.事件",
            "完整档案.结构规划.收尾.结果",
            "完整档案.结构规划.收尾.下章铺垫",
            "完整档案.情节点",
            "完整档案.出场角色",
            "完整档案.伏笔处理.回收伏笔",
            "完整档案.伏笔处理.新设伏笔",
            "完整档案.伏笔处理.延续伏笔",
            "完整档案.时间线事件",
            "完整档案.涉及地点",
            "完整档案.情感节奏.情感基调",
            "完整档案.情感节奏.高潮点",
            "完整档案.世界观补充",
            "完整档案.写作笔记.注意事项",
        ],
        "protected": [
            "_meta.entity_type",
            "_meta.schema_version",
            "_meta.created_at",
        ],
        "required": [
            "索引信息.实体ID",
            "索引信息.名称",
            "索引信息.章节号",
            "摘要.一句话描述",
        ],
        "auto_fields": [
            "_meta.updated_at",
            "索引信息.字数",
            "完整档案.基本信息.实际字数",
        ],
    },
}


# ── 公开接口 ─────────────────────────────────────────────────────────────────

def get_schema(entity_type: str) -> dict[str, Any] | None:
    """获取指定实体类型的完整 schema"""
    return SCHEMAS.get(entity_type)


def get_editable_fields(entity_type: str) -> list[str]:
    """获取可编辑字段路径列表"""
    schema = SCHEMAS.get(entity_type)
    return schema["editable"] if schema else []


def get_protected_fields(entity_type: str) -> list[str]:
    """获取受保护字段路径列表（禁止编辑）"""
    schema = SCHEMAS.get(entity_type)
    return schema["protected"] if schema else []


def get_required_fields(entity_type: str) -> list[str]:
    """获取必填字段路径列表（编辑后不能删除）"""
    schema = SCHEMAS.get(entity_type)
    return schema["required"] if schema else []


def get_auto_fields(entity_type: str) -> list[str]:
    """获取自动维护字段路径列表（编辑时需忽略）"""
    schema = SCHEMAS.get(entity_type)
    return schema["auto_fields"] if schema else []


def detect_entity_type(file_path: str) -> str | None:
    """根据文件路径和内容自动检测实体类型

    Args:
        file_path: 实体文件路径（相对于项目根目录或绝对路径）

    Returns:
        实体类型名称，无法识别时返回 None
    """
    from pathlib import Path

    path = Path(file_path)
    path_str = path.as_posix()

    # 按路径模式匹配
    if "characters/" in path_str and path.suffix == ".yaml":
        return "character"
    if "worldbuilding/" in path_str and path.suffix == ".yaml":
        return "worldbuilding"
    if "outline/情节线/" in path_str:
        return "plot_thread"
    if path.name == "总纲.yaml":
        return "outline_synopsis"
    if "outline/分卷/" in path_str and "第" in path.name:
        return "chapter_outline"
    if "outline/分卷/" in path_str:
        return "volume"

    # 尝试从 YAML 内容检测
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        entity_type = data.get("_meta", {}).get("entity_type", "")
        if entity_type in SCHEMAS:
            return entity_type
    except Exception:
        pass

    return None


def list_supported_types() -> list[dict[str, str]]:
    """列出所有支持的实体类型"""
    return [
        {
            "type": key,
            "description": val["description"],
            "editable_count": len(val["editable"]),
        }
        for key, val in SCHEMAS.items()
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="entity_schema.py",
        description="实体字段 Schema 查询",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python entity_schema.py list                           # 列出所有实体类型
  python entity_schema.py fields --type character        # 查看角色可编辑字段
  python entity_schema.py fields --type worldbuilding    # 查看世界观可编辑字段
  python entity_schema.py detect --file characters/张三.yaml  # 检测文件实体类型

支持的实体类型:
  character       — 角色档案 (53 个可编辑字段)
  worldbuilding   — 世界观实体 (32 个可编辑字段)
  plot_thread     — 情节线 (23 个可编辑字段)
  outline_synopsis — 总纲 (24 个可编辑字段)
  volume          — 分卷大纲 (16 个可编辑字段)
  chapter_outline — 分纲 (31 个可编辑字段)"""
    )
    parser.add_argument("action", choices=["list", "fields", "detect"],
                        help="list=列出类型, fields=查询可编辑字段, detect=检测文件类型")
    parser.add_argument("--type", help="实体类型 (fields 时需要)")
    parser.add_argument("--file", help="文件路径 (detect 时需要)")
    args = parser.parse_args()

    if args.action == "list":
        for entry in list_supported_types():
            print(f"{entry['type']:25s} {entry['editable_count']:3d} 个可编辑字段  —  {entry['description']}")

    elif args.action == "fields":
        if not args.type:
            print("错误: --type 是必填参数")
            exit(1)
        schema = get_schema(args.type)
        if not schema:
            print(f"错误: 未知实体类型 '{args.type}'")
            exit(1)
        print(f"实体类型: {args.type}")
        print(f"描述: {schema['description']}")
        print(f"\n可编辑字段 ({len(schema['editable'])}):")
        for f in schema["editable"]:
            print(f"  ✓ {f}")
        print(f"\n受保护字段 ({len(schema['protected'])}):")
        for f in schema["protected"]:
            print(f"  ✗ {f}")
        print(f"\n必填字段 ({len(schema['required'])}):")
        for f in schema["required"]:
            print(f"  ★ {f}")
        print(f"\n自动字段 ({len(schema['auto_fields'])}):")
        for f in schema["auto_fields"]:
            print(f"  ⚡ {f}")

    elif args.action == "detect":
        if not args.file:
            print("错误: --file 是必填参数")
            exit(1)
        etype = detect_entity_type(args.file)
        if etype:
            schema = get_schema(etype)
            print(f"检测结果: {etype}")
            print(f"描述: {schema['description']}")
        else:
            print(f"无法识别实体类型: {args.file}")
