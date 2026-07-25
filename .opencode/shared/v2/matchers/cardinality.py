"""
基数模式匹配器 — 检查关系的数量是否符合最小/最大基数要求。
"""

from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit, RelationType, UnitType

from .base import BaseMatcher, CheckResult


class CardinalityMatcher(BaseMatcher):
    """基数约束匹配器。"""

    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        params = constraint.params
        rel_type_str = params.get("relation_type", "")
        min_count = params.get("min_count")
        max_count = params.get("max_count")
        target_types = params.get("target_type", [])

        if not rel_type_str:
            return None

        # 解析关系类型
        try:
            rel_type = RelationType(rel_type_str.lower())
        except (ValueError, AttributeError):
            return None

        # 获取单元的所有关系
        rels = store.get_relations(unit.id)

        # 按关系类型过滤
        relevant = [r for r in rels if r.relation_type == rel_type]

        # 如果指定了目标类型，进一步过滤
        if target_types:
            filtered = []
            for r in relevant:
                target = store.get_unit(r.target_id)
                if target and target.type.value in target_types:
                    filtered.append(r)
                elif not target:
                    filtered.append(r)  # 目标不存在时也计入（引用完整性会捕获）
            relevant = filtered

        count = len(relevant)

        if min_count is not None and count < min_count:
            return CheckResult(
                rule_id=constraint.rule_id,
                severity=constraint.severity,
                description=f"「{unit.unit_name}」的 {rel_type.value} 关系数({count})低于最小值({min_count})",
                units_involved=[unit.id],
                detail=f"关系类型: {rel_type.value}, 当前: {count}, 预期 >= {min_count}",
            )

        if max_count is not None and count > max_count:
            return CheckResult(
                rule_id=constraint.rule_id,
                severity=constraint.severity,
                description=f"「{unit.unit_name}」的 {rel_type.value} 关系数({count})超过最大值({max_count})",
                units_involved=[unit.id],
                detail=f"关系类型: {rel_type.value}, 当前: {count}, 预期 <= {max_count}",
            )

        return None
