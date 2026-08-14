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
                rule_name=constraint.description,
                severity=constraint.severity,
                description=f"「{unit.unit_name}」的 {rel_type.value} 关系数({count})低于最小值({min_count})",
                units_involved=[unit.id],
                detail=f"关系类型: {rel_type.value}, 当前: {count}, 预期 >= {min_count}",
            )

        if max_count is not None and count > max_count:
            return CheckResult(
                rule_id=constraint.rule_id,
                rule_name=constraint.description,
                severity=constraint.severity,
                description=f"「{unit.unit_name}」的 {rel_type.value} 关系数({count})超过最大值({max_count})",
                units_involved=[unit.id],
                detail=f"关系类型: {rel_type.value}, 当前: {count}, 预期 <= {max_count}",
            )

        # 第二阶段扩展：检查边的 payload 字段基数
        payload_field_cardinality = params.get("payload_field_cardinality")
        if payload_field_cardinality:
            field = payload_field_cardinality.get("field", "")
            min_items = payload_field_cardinality.get("min_items")
            max_items = payload_field_cardinality.get("max_items")
            if field and (min_items is not None or max_items is not None):
                for r in relevant:
                    field_values = registry._traverse(r.payload, field) if registry else None
                    if field_values is None and registry:
                        # fallback: 直接用 _traverse cls 方法
                        from type_registry import TypeRegistry
                        field_values = TypeRegistry._traverse(
                            TypeRegistry, r.payload, field
                        ) if isinstance(r.payload, dict) else None
                    if isinstance(field_values, list):
                        items_count = len(field_values)
                        if min_items is not None and items_count < min_items:
                            return CheckResult(
                                rule_id=f"{constraint.rule_id}_payload_min",
                                rule_name=constraint.description,
                                severity=constraint.severity,
                                description=f"「{unit.unit_name}」的 {rel_type.value} 边 payload.{field} 项数({items_count})低于最小值({min_items})",
                                units_involved=[unit.id, r.target_id],
                                detail=f"边 {r.id}, payload.{field} 项数: {items_count}, 预期 >= {min_items}",
                            )
                        if max_items is not None and items_count > max_items:
                            return CheckResult(
                                rule_id=f"{constraint.rule_id}_payload_max",
                                rule_name=constraint.description,
                                severity=constraint.severity,
                                description=f"「{unit.unit_name}」的 {rel_type.value} 边 payload.{field} 项数({items_count})超过最大值({max_items})",
                                units_involved=[unit.id, r.target_id],
                                detail=f"边 {r.id}, payload.{field} 项数: {items_count}, 预期 <= {max_items}",
                            )

        return None
