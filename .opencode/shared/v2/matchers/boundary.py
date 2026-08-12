"""
边界模式匹配器 — 检查相邻单元的开端/结尾是否匹配。
"""

import json
from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef, TypeRegistry
from graph_store import GraphStore
from graph_schema import NarrativeUnit, RelationType, UnitType

from .base import BaseMatcher, CheckResult


class BoundaryMatcher(BaseMatcher):
    """边界约束匹配器。"""

    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        params = constraint.params
        preceding_type_str = params.get("preceding_type", "")
        following_rel_str = params.get("following_relation", "PRECEDES")
        field = params.get("field", "")

        if not preceding_type_str or not field:
            return None

        # 仅对指定类型的单元做检查
        if unit.type.value != preceding_type_str:
            return None

        # 解析关系类型
        try:
            following_rel = RelationType(following_rel_str.lower())
        except (ValueError, AttributeError):
            return None

        # 获取当前单元的值
        this_val = self._get_content_value(unit.content, field, store)

        # 通过关系找后续单元
        for rel in store.get_relations(unit.id, direction="outgoing"):
            if rel.relation_type != following_rel:
                continue
            following = store.get_unit(rel.target_id)
            if not following:
                continue
            following_val = self._get_content_value(following.content, field, store)

            if this_val and following_val and this_val != following_val:
                return CheckResult(
                    rule_id=constraint.rule_id,
                    severity=constraint.severity,
                    description=f"边界不一致: 「{unit.unit_name}」的 {field} 为「{this_val}」，但后续单元「{following.unit_name}」的对应值为「{following_val}」",
                    units_involved=[unit.id, following.id],
                    detail=f"{unit.unit_name}({field}={this_val}) → {following.unit_name}({field}={following_val})",
                )

        return None

    def _get_content_value(
        self, content: Any, field_path: str, store: GraphStore
    ) -> Optional[str]:
        """从 content 中提取字段值。"""
        if not field_path:
            return None

        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                return None
        elif isinstance(content, dict):
            parsed = content
        else:
            return None

        if not isinstance(parsed, dict):
            return None

        registry = TypeRegistry.get_global(project_root=str(store.project_root))
        values = registry._traverse(parsed, field_path)
        if values:
            v = values[0]
            return str(v) if v is not None else None
        return None
