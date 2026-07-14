"""
叙事单元 content 字段的 JSON Schema 定义 + 验证。

每种 UnitType 的普适字段（Universal Fields）在此定义。
流派适配字段（Genre-Adaptive Fields）不由 schema 约束，
由 render_utils 的值类型推断标准表处理。

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

# 每个 schema 只定义普适字段（Universal Fields）—
# 所有该类型的单元都必须/应该包含的字段。
# 流派适配字段（如仙侠的"修为"、都市的"职业"）不由 schema 约束。

SCENE_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["开篇","推进","冲突","转折","展示","过渡","收束"]},
    "POV角色": {"type": str, "required": True},
    "地点": {"type": str, "required": True},
    "时间": {"type": str, "required": False},
    "一句话概要": {"type": str, "required": True},
    "出场角色": {"type": list, "required": False},
    "关联情节线": {"type": list, "required": False},
}

CHARACTER_ARC_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["主角","重要配角","反派","关键配角","群像","功能性角色"]},
    "性格": {"type": dict, "required": True, "fields": {
        "核心特质": {"type": [str, list]},  # 可 string 或 string[]，render_utils 统一按 tagcloud 渲染
        "优点": {"type": list},
        "缺点": {"type": list},
    }},
    "背景": {"type": dict, "required": False},
    "目标与冲突": {"type": dict, "required": False},
    "角色弧线": {"type": dict, "required": True, "fields": {
        "起始状态": {"type": str},
        "最终状态": {"type": str},
    }},
    # 能力设定、关系网络 等为流派适配字段，不在此定义
}

PLOT_THREAD_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["主线","支线","暗线","感情线","成长线","世界观线"]},
    "冲突核心": {"type": str, "required": True},
    "关键事件": {"type": list, "required": False, "item_fields": {
        "章节": {"type": int},
        "事件": {"type": str},
    }},
    "终局设计": {"type": str, "required": False},
    # 伏笔清单、角色参与 等为流派适配字段，不在此定义
}

WORLD_RULE_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["世界观总览","规则","力量体系","势力","地点","历史","文化","经济体系","政治体系","社会阶层","纪年事件"]},
    "二级类型": {"type": str, "required": False, "description": "子类型的细化分类"},
    "描述": {"type": str, "required": False, "description": "核心描述，自由文本"},
}

NOTE_SCHEMA = {
    "子类型": {"type": str, "required": False, "options": ["灵感","笔记"]},
    # 自由文本，结构不限
}

STRUCTURE_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["总纲","部大纲","篇大纲","卷大纲","章纲"]},
    "结构模式": {"type": str, "required": True, "options": ["沙漏","长链","螺旋","环状","多线交织"]},
    "本章功能": {"type": str, "required": False, "description": "章纲专用：本章在全书的叙事定位"},
    "场景规划摘要": {"type": str, "required": False, "description": "章纲专用：场景意图草稿，写作中可任意偏离"},
    "备注": {"type": str, "required": False},
}

NARRATIVE_VOICE_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["第一人称","第三人称限制","第三人称全知","第二人称","多视角交替"]},
    "腔调谱系": {"type": str, "required": True, "description": "踩谁的影子？自觉继承或走出谱系"},
    "功能定位": {"type": str, "required": True, "options": ["催眠","警醒","复调"]},
    "叙事视角": {"type": str, "required": True, "options": ["全知","部分全知","戏剧性手法","多视角"]},
    "视角切换规则": {"type": str, "required": False},
    "信息分配策略": {"type": str, "required": False, "options": ["常规","抵抗","挑衅"]},
    "笔记传统启用": {"type": bool, "required": False},
}

CHUNK_SCHEMA = {
    "子类型": {"type": str, "required": True, "options": ["v1","v2","v3"]},
    "章节号": {"type": int, "required": False},
    "章节名": {"type": str, "required": False},
    "正文路径": {"type": str, "required": False},
    "正文分片": {"type": dict, "required": False},
    "字数": {"type": int, "required": False},
}

THEMATIC_MOTIF_SCHEMA = {
    "子类型": {"type": str, "required": False, "options": ["贯穿性","局部性","装饰性"]},
    "意象": {"type": str, "required": True, "description": "核心象征元素"},
    "象征意义": {"type": str, "required": True, "description": "该意象承载的多层含义"},
    "变奏方式": {"type": str, "required": False, "description": "意象如何重复并变化"},
    "出现章节": {"type": list, "required": False},
    "相关角色": {"type": list, "required": False},
}

# ── Schema 注册表 ────────────────────────────────────────────────────────

SCHEMA_REGISTRY: Dict[UnitType, dict] = {
    UnitType.SCENE: SCENE_SCHEMA,
    UnitType.CHARACTER_ARC: CHARACTER_ARC_SCHEMA,
    UnitType.PLOT_THREAD: PLOT_THREAD_SCHEMA,
    UnitType.WORLD_RULE: WORLD_RULE_SCHEMA,
    UnitType.NOTE: NOTE_SCHEMA,
    UnitType.CHUNK: CHUNK_SCHEMA,
    UnitType.STRUCTURE: STRUCTURE_SCHEMA,
    UnitType.NARRATIVE_VOICE: NARRATIVE_VOICE_SCHEMA,
    UnitType.THEMATIC_MOTIF: THEMATIC_MOTIF_SCHEMA,
}


# ── 子类型注册表（Subtype Registry）────────────────────────────────────────

# 定义每个 UnitType 的二次分类字段及消费方需要的信息。
# 所有消费方（render_utils / v2_graph_viz / 筛选层级）统一走此注册表，
# 新增子类型只需在此加一行。

@dataclass
class SubtypeConfig:
    field: str
    alt_fields: list = field(default_factory=list)
    required: bool = False
    options: list = field(default_factory=list)
    value_labels: Dict[str, str] = field(default_factory=dict)
    value_colors: Dict[str, str] = field(default_factory=dict)
    behaviors: Dict[str, dict] = field(default_factory=dict)


SUBTYPE_REGISTRY: Dict[UnitType, SubtypeConfig] = {
    UnitType.WORLD_RULE: SubtypeConfig(
        field="子类型",
        alt_fields=["实体子类型"],
        required=True,
        options=["世界观总览","规则","力量体系","势力","地点","历史","文化","经济体系","政治体系","社会阶层","纪年事件"],
        value_labels={"location": "地点", "faction": "势力", "rule": "规则", "power_system": "力量体系", "chronicle_event": "纪年事件"},
        value_colors={
            "地点": {"bg": "rgba(0,176,240,0.2)", "text": "#5BD"},
            "势力": {"bg": "rgba(237,125,49,0.2)", "text": "#ED7D31"},
            "纪年事件": {"bg": "rgba(180,167,214,0.2)", "text": "#8E7CC3"},
        },
        behaviors={
            "纪年事件": {"type": "timeline_event", "time_field": "时间", "event_field": "事件"},
        },
    ),
    UnitType.NOTE: SubtypeConfig(
        field="子类型",
        alt_fields=["note_type"],
        required=False,
        options=["灵感", "笔记"],
    ),
    UnitType.SCENE: SubtypeConfig(
        field="子类型",
        required=True,
        options=["开篇","推进","冲突","转折","展示","过渡","收束"],
    ),
    UnitType.STRUCTURE: SubtypeConfig(
        field="子类型",
        required=True,
        options=["总纲","部大纲","篇大纲","卷大纲","章纲"],
    ),
    UnitType.CHARACTER_ARC: SubtypeConfig(
        field="子类型",
        required=True,
        options=["主角","重要配角","反派","关键配角","群像","功能性角色"],
    ),
    UnitType.PLOT_THREAD: SubtypeConfig(
        field="子类型",
        required=True,
        options=["主线","支线","暗线","感情线","成长线","世界观线"],
    ),
    UnitType.CHUNK: SubtypeConfig(
        field="子类型",
        required=True,
        options=["v1","v2","v3"],
    ),
    UnitType.THEMATIC_MOTIF: SubtypeConfig(
        field="子类型",
        required=False,
        options=["贯穿性","局部性","装饰性"],
    ),
    UnitType.NARRATIVE_VOICE: SubtypeConfig(
        field="子类型",
        required=True,
        options=["第一人称","第三人称限制","第三人称全知","第二人称","多视角交替"],
    ),
}


def get_subtype_info(unit_type: UnitType) -> Optional[SubtypeConfig]:
    return SUBTYPE_REGISTRY.get(unit_type)


def get_subtype_field_names() -> set:
    return {info.field for info in SUBTYPE_REGISTRY.values()}


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
            # 非 JSON 内容（如旧格式 CHUNK 纯文本）跳过验证
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
