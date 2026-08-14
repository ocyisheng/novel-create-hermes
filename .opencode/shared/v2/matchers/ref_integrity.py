"""
引用完整性模式匹配器 — 检查 content 中引用的实体在 graph 中是否存在。
"""

from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit

from .base import BaseMatcher, CheckResult


class RefIntegrityMatcher(BaseMatcher):
    """引用完整性约束匹配器。"""

    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        params = constraint.params
        field_name = params.get("on", "")
        refs = facts.get(field_name, [])

        if not refs:
            return None

        # 从约束/类型定义获取目标类型和匹配字段
        target_type = params.get("target_type", "*")
        match_field = params.get("match_field", "unit_name")

        # 从类型定义的 fact_fields 获取更精确的 target_type
        if not params.get("target_type") and registry:
            td = registry.get_type(unit.type.value if hasattr(unit.type, "value") else str(unit.type))
            if td:
                for ff in td.fact_fields:
                    if ff.name == field_name:
                        if ff.target_type:
                            target_type = ff.target_type
                        if ff.match_field:
                            match_field = ff.match_field
                        break

        missing = []
        for ref in refs:
            if not ref or not isinstance(ref, str):
                continue
            ref = ref.strip()
            if not ref:
                continue
            if not self._entity_exists(store, ref, target_type, match_field):
                missing.append(ref)

        if missing:
            names = "、".join(missing)
            return CheckResult(
                rule_id=constraint.rule_id,
                rule_name=constraint.description,
                severity=constraint.severity,
                description=f"「{unit.unit_name}」引用了不存在的实体「{names}」",
                units_involved=[unit.id],
                detail=f"目标类型: {target_type}, 缺失引用: {missing}",
            )

        return None

    def _entity_exists(
        self,
        store: GraphStore,
        name: str,
        target_type: str,
        match_field: str,
    ) -> bool:
        """检查 entity 在 graph 中是否存在。"""
        from graph_schema import UnitType

        for u in store._units.values():
            if u.status.name == "ARCHIVED":
                continue
            if target_type != "*":
                try:
                    # UnitType 枚举值为小写，需要小写化匹配
                    ut = UnitType(target_type.lower())
                except (ValueError, AttributeError):
                    continue
                if u.type != ut:
                    continue
            if match_field == "unit_name" and u.unit_name == name:
                return True
            if match_field == "id" and u.id == name:
                return True
        return False
