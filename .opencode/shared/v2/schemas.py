"""
叙事单元 content 字段的 JSON Schema 定义 + 验证。

每种 UnitType 的 content 字段有预期的 JSON 结构。
脚本在写入时自动校验必填字段和类型，不需要 LLM 记忆结构规范。

使用方式：
    from schemas import validate_content
    errors = validate_content(UnitType.SCENE, content_dict)
    if errors:
        raise ValueError(f"字段不完整: {errors}")
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

from graph_schema import UnitType


# ── Schema 定义 ───────────────────────────────────────────────────────────

# 每个 schema 是一个字典，描述 content 中期望的 JSON 结构：
# {
#     "必填字段": {"type": str, "description": "..."},
#     "可选字段": {"type": list, "required": False, ...},
# }

SCENE_SCHEMA = {
    "章节类型": {"type": str, "required": True, "options": ["推进","过渡","高潮","结局","转折","收尾"]},
    "字数目标": {"type": int, "required": False},
    "结构规划": {"type": dict, "required": True, "fields": {
        "开篇": {"type": dict, "fields": {"方式": {"type": str}, "上章衔接": {"type": str}}},
        "发展": {"type": dict, "fields": {"核心冲突": {"type": str}, "推进": {"type": str}}},
        "转折": {"type": dict, "fields": {"事件": {"type": str}}},
        "收尾": {"type": dict, "fields": {"结果": {"type": str}, "下章铺垫": {"type": str}}},
    }},
    "场域规划": {"type": list, "required": False, "item_fields": {
        "场域名": {"type": str},
        "POV角色": {"type": str},
        "持续时间": {"type": int},
        "功能": {"type": str},
        "进入方式": {"type": str},
        "退出方式": {"type": str},
    }},
    "张力曲线": {"type": dict, "required": False, "fields": {
        "开场": {"type": int}, "章节高潮": {"type": int}, "结尾": {"type": int},
    }},
    "关联情节线": {"type": list, "required": False},
    "出场角色": {"type": list, "required": False},
    "伏笔处理": {"type": dict, "required": False},
}

CHARACTER_ARC_SCHEMA = {
    "角色类型": {"type": str, "required": True, "options": ["主角","反派","导师","盟友","对手","次要角色"]},
    "性格": {"type": dict, "required": True, "fields": {
        "核心特质": {"type": str},
        "优点": {"type": list},
        "缺点": {"type": list},
    }},
    "背景": {"type": dict, "required": False},
    "目标与冲突": {"type": dict, "required": False},
    "能力设定": {"type": dict, "required": False},
    "关系网络": {"type": list, "required": False, "item_fields": {
        "角色": {"type": str},
        "标签": {"type": list},
        "强度": {"type": [int, float]},
    }},
    "角色弧线": {"type": dict, "required": True, "fields": {
        "起始状态": {"type": str},
        "最终状态": {"type": str},
    }},
}

PLOT_THREAD_SCHEMA = {
    "类型": {"type": str, "required": True, "options": ["主线","支线","角色弧"]},
    "冲突核心": {"type": str, "required": True},
    "关键事件": {"type": list, "required": False, "item_fields": {
        "章节": {"type": int},
        "事件": {"type": str},
    }},
    "伏笔清单": {"type": dict, "required": False},
    "角色参与": {"type": dict, "required": False},
    "终局设计": {"type": str, "required": False},
}

WORLD_RULE_SCHEMA = {
    "实体子类型": {"type": str, "required": True, "options": [
        "world_overview","rule","power_system","faction","location",
        "history","culture","economic_system","political_system","social_hierarchy"
    ]},
    "核心设定": {"type": str, "required": True},
    # 子类型特定字段——按子类型有不同的必填结构
}

NOTE_SCHEMA = {
    "note_type": {"type": str, "required": False, "options": ["总纲","叙事策略","灵感","笔记"]},
    # 自由文本，结构不限
}

CHUNK_SCHEMA = {
    "章节号": {"type": int, "required": True},
    "正文": {"type": str, "required": True},
    "字数": {"type": int, "required": False},
}

# ── Schema 注册表 ────────────────────────────────────────────────────────

SCHEMA_REGISTRY: Dict[UnitType, dict] = {
    UnitType.SCENE: SCENE_SCHEMA,
    UnitType.CHARACTER_ARC: CHARACTER_ARC_SCHEMA,
    UnitType.PLOT_THREAD: PLOT_THREAD_SCHEMA,
    UnitType.WORLD_RULE: WORLD_RULE_SCHEMA,
    UnitType.NOTE: NOTE_SCHEMA,
    UnitType.CHUNK: CHUNK_SCHEMA,
    UnitType.THEMATIC_MOTIF: {},
}


# ── 验证函数 ──────────────────────────────────────────────────────────────

def validate_content(unit_type: UnitType, content: Any) -> List[str]:
    """
    验证 content 是否符合该类型的 Schema。
    
    返回错误信息列表（空列表表示验证通过）。
    content 可以是 dict（已解析 JSON）或 str（原始 JSON/文本）。
    """
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            # 纯文本内容（如 CHUNK 的章节正文）不验证
            return []
    
    if not isinstance(content, dict):
        return []
    
    schema = SCHEMA_REGISTRY.get(unit_type, {})
    if not schema:
        return []
    
    errors = []
    
    for field_name, rules in schema.items():
        if rules.get("required", False):
            if field_name not in content or content[field_name] is None:
                errors.append(f"缺少必填字段: {field_name}")
                continue
        
        if field_name not in content:
            continue
        
        value = content[field_name]
        expected_type = rules.get("type")
        
        if expected_type and value is not None:
            if isinstance(expected_type, list):
                type_ok = any(_check_type(value, t) for t in expected_type)
            else:
                type_ok = _check_type(value, expected_type)
            
            if not type_ok:
                errors.append(
                    f"字段 '{field_name}' 类型错误: 期望 {_type_name(expected_type)}, 实际 {type(value).__name__}"
                )
        
        # 检查枚举选项
        options = rules.get("options", [])
        if options and value not in options and isinstance(value, str):
            errors.append(f"字段 '{field_name}' 值 '{value}' 不在允许范围内: {options}")
        
        # 递归检查嵌套 dict
        nested_fields = rules.get("fields", {})
        if nested_fields and isinstance(value, dict):
            sub_errors = _validate_dict_fields(value, nested_fields, field_name)
            errors.extend(sub_errors)
        
        # 检查列表项
        item_fields = rules.get("item_fields", {})
        if item_fields and isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    sub_errors = _validate_dict_fields(item, item_fields, f"{field_name}[{i}]")
                    errors.extend(sub_errors)
    
    return errors


def _check_type(value: Any, expected: type) -> bool:
    if expected == str:
        return isinstance(value, str)
    elif expected == int:
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected == float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == list:
        return isinstance(value, list)
    elif expected == dict:
        return isinstance(value, dict)
    elif expected == bool:
        return isinstance(value, bool)
    return True


def _type_name(t: Any) -> str:
    if isinstance(t, list):
        return "/".join(_type_name(x) for x in t)
    return t.__name__


def _validate_dict_fields(data: dict, fields: dict, prefix: str) -> List[str]:
    errors = []
    for field_name, rules in fields.items():
        full_name = f"{prefix}.{field_name}"
        if rules.get("required", False) and (field_name not in data or data[field_name] is None):
            errors.append(f"缺少必填字段: {full_name}")
            continue
        if field_name not in data:
            continue
        expected_type = rules.get("type")
        value = data[field_name]
        if expected_type and value is not None:
            if not _check_type(value, expected_type):
                errors.append(f"字段 '{full_name}' 类型错误")
        # 递归
        nested = rules.get("fields", {})
        if nested and isinstance(value, dict):
            errors.extend(_validate_dict_fields(value, nested, full_name))
    return errors


# ── 便捷构造器 ────────────────────────────────────────────────────────────

def default_content(unit_type: UnitType) -> str:
    """返回该类型的默认 content JSON（仅含必填字段的空值）"""
    schema = SCHEMA_REGISTRY.get(unit_type, {})
    defaults = {}
    for field, rules in schema.items():
        if rules.get("required", False):
            t = rules.get("type")
            if t == str:
                defaults[field] = ""
            elif t == int:
                defaults[field] = 0
            elif t == list:
                defaults[field] = []
            elif t == dict:
                defaults[field] = {}
            else:
                defaults[field] = None
    return json.dumps(defaults, ensure_ascii=False)


# ── Schema 自检 ──────────────────────────────────────────────────────────

def schema_info(unit_type: UnitType) -> List[str]:
    """返回该类型的 Schema 摘要（供 LLM 参考注入 prompt）"""
    schema = SCHEMA_REGISTRY.get(unit_type, {})
    lines = [f"content JSON 字段要求 ({unit_type.value}):"]
    for field, rules in schema.items():
        req = "必填" if rules.get("required") else "可选"
        t = _type_name(rules.get("type", "any"))
        opts = f" 选项: {rules['options']}" if rules.get("options") else ""
        lines.append(f"  - {field} ({t}, {req}){opts}")
    return lines
