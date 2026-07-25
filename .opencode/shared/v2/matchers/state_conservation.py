"""
状态守恒模式匹配器 — 检查状态变更是否有对应的事件/关系。
"""

from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit, RelationType, UnitType

from .base import BaseMatcher, CheckResult


class StateConservationMatcher(BaseMatcher):
    """状态守恒约束匹配器。"""

    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        params = constraint.params
        entity_type_str = params.get("entity_type", "")
        state_field = params.get("state_field", "status")
        forbidden_rel_str = params.get("forbidden_relation", "")
        allowed_exceptions = params.get("allowed_exception_values", [])

        # 过滤类型
        if entity_type_str:
            try:
                entity_ut = UnitType(entity_type_str.upper())
            except (ValueError, AttributeError):
                return None
            if unit.type != entity_ut:
                return None

        # 获取状态值
        if state_field == "status":
            state_val = unit.status
        else:
            state_val = getattr(unit, state_field, None)

        if state_val is None:
            return None

        status_str = state_val.value if hasattr(state_val, "value") else str(state_val)

        # 状态守恒：archived 状态下不应存在 forbidden_relation
        if status_str != "archived" or not forbidden_rel_str:
            return None

        try:
            forbidden_rel = RelationType(forbidden_rel_str.lower())
        except (ValueError, AttributeError):
            return None

        rels = store.get_relations(unit.id)
        forbidden_found = [r for r in rels if r.relation_type == forbidden_rel]

        if not forbidden_found:
            return None

        # 过滤例外
        exception_names = []
        for r in forbidden_found:
            tgt = store.get_unit(r.target_id)
            if tgt:
                tgt_name = tgt.unit_name
                if tgt_name not in allowed_exceptions:
                    exception_names.append(tgt_name)

        if not exception_names:
            return None

        exception_str = ", ".join(exception_names[:5])
        return CheckResult(
            rule_id=constraint.rule_id,
            severity=constraint.severity,
            description=f"「{unit.unit_name}」(状态={status_str}) 仍有 {len(forbidden_found)} 条 {forbidden_rel.value} 关系",
            units_involved=[unit.id],
            detail=f"关联对象: {exception_str}" if exception_str else "",
        )
