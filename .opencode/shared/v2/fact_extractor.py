"""
事实提取器 — 从叙事单元的 content JSON 中提取结构化事实。

供约束引擎（ConstraintEngine）消费，从自由文本的 content 中按路径提取值。
支持 JSONPath 风格的点分路径和数组遍历。

示例：
  extract_field: "events[].age"
  对 character_arc.content.events 数组，提取所有事件的 age 值，
  附带 ordinal 等上下文。
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Any, Set
from graph_store import GraphStore


class FactExtractor:
    """
    从 unit.content 中提取约束检查所需的结构化事实。
    
    支持：
    - 点分路径（如 "events[].age"）
    - 数组遍历（如 "events[].location"）
    - 单一字段提取（如 "end_state"）
    """
    
    def __init__(self, store: GraphStore):
        self.store = store
    
    def get_units_by_type(self, unit_type_str: str) -> list:
        """按类型名获取所有活跃单元。"""
        from graph_schema import UnitType
        if not unit_type_str:
            return []
        try:
            ut = UnitType(unit_type_str.upper())
        except (ValueError, AttributeError):
            return []
        return [
            u for u in self.store._units.values()
            if u.type == ut and u.status.name != "ARCHIVED"
        ]
    
    def find_entity(self, name: str, target_type: str, match_field: str = "unit_name") -> bool:
        """在 graph 中查找指定名称/ID 的实体是否存在。"""
        if target_type == "*":
            # 任意类型
            for u in self.store._units.values():
                if u.status.name == "ARCHIVED":
                    continue
                if match_field == "unit_name" and u.unit_name == name:
                    return True
                if match_field == "id" and u.id == name:
                    return True
            return False
        else:
            # 指定类型
            from graph_schema import UnitType
            try:
                ut = UnitType(target_type.upper())
            except (ValueError, AttributeError):
                return False
            for u in self.store._units.values():
                if u.status.name == "ARCHIVED":
                    continue
                if u.type != ut:
                    continue
                if match_field == "unit_name" and u.unit_name == name:
                    return True
                if match_field == "id" and u.id == name:
                    return True
            return False
    
    def extract_field_values(self, unit, field_path: str) -> List[Any]:
        """
        从单元的 content 中按路径提取所有值。
        
        支持路径语法：
        - "events[].age" → 遍历 events 数组，提取每个元素的 age
        - "end_state" → 直接取 content.end_state
        - "scenes[].scene_id" → 遍历 scenes 数组，提取 scene_id
        """
        if not field_path:
            return []
        
        content = unit.content
        if not content:
            return []
        
        # content 可能是 JSON 字符串或 dict
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                return []
        
        if not isinstance(content, dict):
            return []
        
        # 解析路径
        return self._traverse(content, field_path)
    
    def extract_field_value(self, unit, field_path: str) -> Optional[str]:
        """
        从单元的 content 中提取单个值（非数组版本）。
        如果路径包含数组遍历，返回第一个值。
        """
        values = self.extract_field_values(unit, field_path)
        if values:
            v = values[0]
            return str(v) if v is not None else None
        return None
    
    def _traverse(self, data: Any, path: str) -> List[Any]:
        """
        递归遍历 JSON 数据，按路径提取所有值。
        
        "events[].age" → 在 data["events"] 中遍历每个元素，取 "age"
        "end_state"    → 取 data["end_state"]
        """
        parts = self._parse_path(path)
        
        current = [data]
        for part in parts:
            next_current = []
            is_array_traversal = part.endswith("[]")
            key = part[:-2] if is_array_traversal else part
            
            for item in current:
                if not isinstance(item, dict):
                    continue
                if key not in item:
                    continue
                value = item[key]
                
                if is_array_traversal:
                    if isinstance(value, list):
                        next_current.extend(value)
                    else:
                        next_current.append(value)
                else:
                    next_current.append(value)
            
            current = next_current
            if not current:
                return []
        
        return current
    
    def _parse_path(self, path: str) -> List[str]:
        """解析点分路径为部分列表。"""
        parts = []
        for part in path.split("."):
            part = part.strip()
            if part:
                parts.append(part)
        return parts
