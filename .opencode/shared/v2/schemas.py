"""
schemas.py — 叙事单元 content JSON Schema 工具层（门面）。

不再持有独立字段定义。所有元数据从 TypeRegistry（YAML unit_types/*.yaml）读取。
保留为门面层以兼容现有调用方。

消费方：
  - GraphStore.create/update: validate_content()
  - WorkspaceBuilder.build: schema_info()
  - Web UI get_schema_fields API
  - render_utils / graph_viz: get_subtype_info()

历史：
  - v1: 独立维护 SCHEMA_REGISTRY + SUBTYPE_REGISTRY
  - v2: 降级为 TypeRegistry 门面，YAML 成为唯一事实来源
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from graph_schema import UnitType
from type_registry import TypeRegistry


def _get_registry() -> TypeRegistry:
    """获取全局 TypeRegistry 单例。"""
    return TypeRegistry.get_global()


def _type_name(type_name: str) -> str:
    """将类型标识转为可读名称（兼容 render_utils 等调用方）。"""
    return type_name


# ── 验证函数 ──────────────────────────────────────────────────────────────


def validate_content(unit_type: UnitType, content: Any) -> List[str]:
    """
    验证 content 是否符合该类型的 Schema。

    通过 TypeRegistry.validate_content() 实现，YAML 是唯一来源。
    返回错误信息列表（空列表表示验证通过）。
    content 可以是 dict（已解析 JSON）或 str（原始 JSON/文本）。
    """
    type_name = unit_type.value if hasattr(unit_type, "value") else str(unit_type)
    return _get_registry().validate_content(type_name, content)


# ── Schema 查询 ────────────────────────────────────────────────────────────


def schema_info(unit_type: UnitType) -> List[str]:
    """返回该类型的 Schema 摘要（供 LLM 参考注入 prompt）。"""
    type_name = unit_type.value if hasattr(unit_type, "value") else str(unit_type)
    return _get_registry().schema_info(type_name)


def default_content(unit_type: UnitType) -> str:
    """返回该类型的默认 content JSON（仅含必填字段的空值）。"""
    type_name = unit_type.value if hasattr(unit_type, "value") else str(unit_type)
    return _get_registry().default_content(type_name)


def get_schema(unit_type: UnitType) -> Dict[str, Dict[str, Any]]:
    """返回该类型的 content_schema 字段定义（供 Web UI 等使用）。"""
    type_name = unit_type.value if hasattr(unit_type, "value") else str(unit_type)
    return _get_registry().get_content_schema(type_name)


# ── 子类型查询 ──────────────────────────────────────────────────────────────


def get_subtype_info(unit_type: UnitType) -> Optional[Dict[str, Any]]:
    """返回子类型配置（颜色/标签/字段名/行为等）。"""
    type_name = unit_type.value if hasattr(unit_type, "value") else str(unit_type)
    return _get_registry().get_subtype_config(type_name)


def get_subtype_field_names() -> Set[str]:
    """收集所有类型的子类型字段名，供实体引用检测等使用。"""
    registry = _get_registry()
    names: Set[str] = set()
    for type_name in registry.list_types():
        cfg = registry.get_subtype_config(type_name)
        if cfg and "field" in cfg:
            names.add(cfg["field"])
    return names
