"""
时序模式匹配器 — 检查有序量是否单调递增/非递减。
"""

from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit

from .base import BaseMatcher, CheckResult


class TemporalMatcher(BaseMatcher):
    """时序约束匹配器。"""

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
        sequence = facts.get(field_name, [])

        if len(sequence) <= 1:
            return None

        check_type = params.get("check", "monotonic_increasing")
        exception_field = params.get("exception_field", "")
        exception_values = params.get("exception_values", [])

        # 如果有例外，需要从 content 提取例外值
        # 但 temporal 约束的例外通过 constraints.yaml 的 exceptions.field/values 表达
        # 此处简化处理：直接用传入的 sequence
        try:
            values_num = []
            for v in sequence:
                if v is None:
                    values_num.append(None)
                else:
                    values_num.append(float(v) if v != "?" else None)
        except (ValueError, TypeError):
            return None

        # 过滤 None
        values_clean = [(i, v) for i, v in enumerate(values_num) if v is not None]
        if len(values_clean) <= 1:
            return None

        if check_type == "monotonic_increasing":
            for i in range(len(values_clean) - 1):
                idx_a, val_a = values_clean[i]
                idx_b, val_b = values_clean[i + 1]
                if val_a >= val_b:
                    # 检查此位置是否为例外
                    exc_field_val = self._get_exception_value(
                        unit.content, exception_field, idx_b, store
                    )
                    if exc_field_val in exception_values:
                        continue
                    return CheckResult(
                        rule_id=constraint.rule_id,
                        rule_name=constraint.description,
                        severity=constraint.severity,
                        description=f"「{unit.unit_name}」时序异常: {sequence[idx_a]} → {sequence[idx_b]}（未递增）",
                        units_involved=[unit.id],
                        detail=f"值 {sequence[idx_a]} → {sequence[idx_b]}",
                    )
        elif check_type == "monotonic_non_decreasing":
            for i in range(len(values_clean) - 1):
                idx_a, val_a = values_clean[i]
                idx_b, val_b = values_clean[i + 1]
                if val_a > val_b:
                    exc_field_val = self._get_exception_value(
                        unit.content, exception_field, idx_b, store
                    )
                    if exc_field_val in exception_values:
                        continue
                    return CheckResult(
                        rule_id=constraint.rule_id,
                        rule_name=constraint.description,
                        severity=constraint.severity,
                        description=f"「{unit.unit_name}」时序异常: {sequence[idx_a]} → {sequence[idx_b]}（递减）",
                        units_involved=[unit.id],
                        detail=f"值 {sequence[idx_a]} → {sequence[idx_b]}",
                    )

        return None

    def _get_exception_value(
        self,
        content: Any,
        exception_field: str,
        idx: int,
        store: GraphStore,
    ) -> Optional[str]:
        """从 content 中获取例外判断字段的值。"""
        if not exception_field:
            return None
        import json
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

        # 解析路径如 "events[].type"
        from type_registry import TypeRegistry
        registry = TypeRegistry.get_global(project_root=str(store.project_root))
        values = registry._traverse(parsed, exception_field)

        if 0 <= idx < len(values):
            return str(values[idx]) if values[idx] is not None else None
        return None
