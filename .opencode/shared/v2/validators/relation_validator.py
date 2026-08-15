"""
relation_validator.py — add_relation 写时校验层（T0.2）。

在边写入 graph 之前调用。使用 TypeRegistry（T0.1）声明做校验：
  1. 端点类型允许（endpoint_types）
  2. 基数（one_to_one，按已有边计数）
  3. payload schema（按源类型细粒度 schema，回退通用 schema）
  4. weight 范围 [0, 1]
  5. 角色（若声明了 allowed roles）
  6. PRECEDES/CAUSES（及 acyclic 类型）：有向 DAG 环检测（临时边 + 拓扑排序）

无状态：validate() 接收输入返回 ValidationResult，无副作用。
override=True 时校验失败降级为 warnings（由调用方决定是否记入 deviation ledger）。
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

from graph_schema import Relation
from type_registry import TypeRegistry


@dataclass(frozen=True)
class ValidationError:
    """单条校验错误/警告。"""
    field: str
    expected: str
    actual: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass(frozen=True)
class ValidationResult:
    """校验结果：errors 阻塞写入，warnings 由调用方决定。"""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)


class RelationValidator:
    """add_relation 写时校验器（无状态，可安全复用）。"""

    # PRECEDES/CAUSES 为有向 + 自反（对称）类型，需 DAG 环检测
    DAG_REL_TYPES = frozenset({"precedes", "causes"})

    # TypeRegistry 校验器消息解析（字符串消息 → 结构化 ValidationError）
    _RE_SOURCE = re.compile(r"不允许源类型 '(?P<actual>[^']+)'（允许: (?P<expected>.+)）")
    _RE_TARGET = re.compile(r"不允许目标类型 '(?P<actual>[^']+)'（允许: (?P<expected>.+)）")
    _RE_CARDINALITY = re.compile(r"为 one_to_one，源单元已存在 (?P<actual>\d+) 条该类型关系")
    _RE_PAYLOAD_TYPE = re.compile(r"^(?P<field>[^:]+): expected (?P<expected>\w+), got (?P<actual>\w+)$")
    _RE_PAYLOAD_REQUIRED = re.compile(r"^(?P<field>[^:]+): field is required \(not nullable\)$")
    _RE_PAYLOAD_ENUM = re.compile(r"^(?P<field>[^:]+): value '(?P<actual>[^']+)' not in (?P<expected>.+)$")
    _RE_UNKNOWN = re.compile(r"未知关系类型: (?P<actual>.+)")

    # (regex, fixed_field, field_group, expected_group, actual_group, fixed_expected)
    _MSG_PARSERS = (
        (_RE_SOURCE, "source", None, "expected", "actual", None),
        (_RE_TARGET, "target", None, "expected", "actual", None),
        (_RE_CARDINALITY, "cardinality", None, None, "actual", "one_to_one (≤1)"),
        (_RE_PAYLOAD_TYPE, None, "field", "expected", "actual", None),
        (_RE_PAYLOAD_REQUIRED, None, "field", None, None, "not null"),
        (_RE_PAYLOAD_ENUM, None, "field", "expected", "actual", None),
        (_RE_UNKNOWN, "rel_type", None, None, "actual", "known relation type"),
    )

    def __init__(self, registry: Optional[TypeRegistry] = None):
        self.registry = registry or TypeRegistry.get_global()

    # ── 主入口 ─────────────────────────────────────────────────────────

    def validate(
        self,
        source: str,
        target: str,
        rel_type: str,
        payload: Optional[Dict[str, Any]] = None,
        weight: float = 0.5,
        source_role: str = "",
        target_role: str = "",
        override: bool = False,
        source_type: Optional[str] = None,
        target_type: Optional[str] = None,
        existing_relations: Optional[Sequence[Relation]] = None,
        allowed_roles: Optional[Dict[str, List[str]]] = None,
    ) -> ValidationResult:
        """校验一条待写入的关系边。

        Args:
            source/target: 源/目标单元 ID（用于基数计数与 DAG 环检测）。
            rel_type: 关系类型值（如 "causes"）。
            source_type/target_type: 源/目标单元类型（用于端点/payload 校验）。
            existing_relations: 当前图中已存在的边（用于基数与 DAG）。
            allowed_roles: 可选角色白名单 {"source": [...], "target": [...]}，
                           未声明时跳过角色校验。
            override: True 时所有校验失败降级为 warnings。
        """
        rel_value = self._rel_value(rel_type)
        if self.registry.get_relation_type_def(rel_value) is None:
            result = ValidationResult(valid=False, errors=[
                ValidationError("rel_type", "known relation type", rel_value,
                                f"未知关系类型: {rel_value}", "error"),
            ])
            return self.validate_override(result, override)

        errors: List[ValidationError] = []
        errors.extend(self.validate_endpoint_types(source_type, target_type, rel_value))
        errors.extend(self.validate_cardinality(source, rel_value, existing_relations))
        errors.extend(self.validate_payload_schema(source_type, target_type, rel_value, payload))
        errors.extend(self.validate_weight(weight))
        errors.extend(self.validate_roles(source_role, target_role, allowed_roles))
        errors.extend(self.validate_dag(source, target, rel_value, existing_relations))
        return self.validate_override(
            ValidationResult(valid=not errors, errors=errors), override
        )

    # ── 单项校验 ───────────────────────────────────────────────────────

    def validate_endpoint_types(
        self, source_type: Optional[str], target_type: Optional[str], rel_type: str
    ) -> List[ValidationError]:
        """校验源/目标单元类型是否被该关系类型允许（TypeRegistry 声明）。"""
        if source_type is None or target_type is None:
            return []  # 调用方未提供单元类型，无法校验
        validator = self.registry.get_relation_validator(rel_type)
        messages = validator(source_type, target_type)
        return [e for e in (self._parse_registry_message(m) for m in messages)
                if e.field in ("source", "target")]

    def validate_cardinality(
        self, source_id: str, rel_type: str,
        existing_relations: Optional[Sequence[Relation]],
    ) -> List[ValidationError]:
        """校验 one_to_one 基数约束（按已有边计数）。"""
        rtd = self.registry.get_relation_type_def(rel_type)
        if rtd is None or rtd.cardinality != "one_to_one":
            return []
        existing_count = self._count_existing(source_id, rel_type, existing_relations)
        validator = self.registry.get_relation_validator(rel_type)
        messages = validator("", "", existing_count=existing_count)
        return [e for e in (self._parse_registry_message(m) for m in messages)
                if e.field == "cardinality"]

    def validate_payload_schema(
        self, source_type: Optional[str], target_type: Optional[str], rel_type: str,
        payload: Optional[Dict[str, Any]],
    ) -> List[ValidationError]:
        """校验 payload 是否符合声明 schema（按源类型细粒度，回退通用）。"""
        if not payload or source_type is None or target_type is None:
            return []
        validator = self.registry.get_relation_validator(rel_type)
        messages = validator(source_type, target_type, payload=payload)
        return [e for e in (self._parse_registry_message(m) for m in messages)
                if e.field not in ("source", "target", "cardinality", "rel_type")]

    def validate_weight(self, weight: Any) -> List[ValidationError]:
        """校验 weight 在 [0, 1] 范围内。"""
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            return [ValidationError(
                "weight", "number in [0, 1]", str(weight),
                f"weight 应为数值，实际为 {type(weight).__name__}", "error")]
        if weight < 0.0 or weight > 1.0:
            return [ValidationError(
                "weight", "[0, 1]", str(weight),
                f"weight {weight} 超出范围 [0, 1]", "error")]
        return []

    def validate_roles(
        self, source_role: str, target_role: str,
        allowed_roles: Optional[Dict[str, List[str]]] = None,
    ) -> List[ValidationError]:
        """校验端点角色是否在允许集合内（若声明）。"""
        if not allowed_roles:
            return []
        errors: List[ValidationError] = []
        source_allowed = allowed_roles.get("source") or []
        target_allowed = allowed_roles.get("target") or []
        if source_role and source_allowed and source_role not in source_allowed:
            errors.append(ValidationError(
                "source_role", str(source_allowed), source_role,
                f"source_role '{source_role}' 不在允许集合 {source_allowed} 内", "error"))
        if target_role and target_allowed and target_role not in target_allowed:
            errors.append(ValidationError(
                "target_role", str(target_allowed), target_role,
                f"target_role '{target_role}' 不在允许集合 {target_allowed} 内", "error"))
        return errors

    def validate_dag(
        self, source_id: str, target_id: str, rel_type: str,
        existing_relations: Optional[Sequence[Relation]],
    ) -> List[ValidationError]:
        """PRECEDES/CAUSES（及 acyclic 类型）：临时边 + 拓扑排序检测有向环。"""
        rtd = self.registry.get_relation_type_def(rel_type)
        if rtd is None:
            return []
        if rel_type not in self.DAG_REL_TYPES and not rtd.acyclic:
            return []
        if source_id == target_id:
            return [ValidationError(
                "dag", "acyclic (no self-loop)", f"{source_id}→{target_id}",
                f"关系 '{rel_type}' 自环 {source_id}→{target_id} 会形成环", "error")]
        relevant = {rel_type}
        if rtd.inverse and rtd.inverse != rel_type:
            relevant.add(rtd.inverse)
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        nodes: Set[str] = set()
        for r in existing_relations or []:
            if self._rel_value(r.relation_type) in relevant:
                adjacency[r.source_id].add(r.target_id)
                nodes.add(r.source_id)
                nodes.add(r.target_id)
        adjacency[source_id].add(target_id)  # 临时加入新边
        nodes.add(source_id)
        nodes.add(target_id)
        if self._has_cycle(adjacency, nodes):
            return [ValidationError(
                "dag", "acyclic (no cycle)", f"{source_id}→{target_id}",
                f"添加关系 '{rel_type}' {source_id}→{target_id} 会形成环", "error")]
        return []

    def validate_override(
        self, result: ValidationResult, override: bool
    ) -> ValidationResult:
        """override=True 时把 errors 降级为 warnings，valid 置 True。"""
        if not override or not result.errors:
            return result
        warnings = list(result.warnings)
        warnings.extend(
            ValidationError(e.field, e.expected, e.actual, e.message, "warning")
            for e in result.errors
        )
        return ValidationResult(valid=True, errors=[], warnings=warnings)

    # ── 内部辅助 ───────────────────────────────────────────────────────

    @staticmethod
    def _rel_value(rel_type: Any) -> str:
        """归一化关系类型为字符串值（兼容枚举/字符串）。"""
        return rel_type.value if hasattr(rel_type, "value") else str(rel_type)

    def _count_existing(
        self, source_id: str, rel_type: str,
        existing_relations: Optional[Sequence[Relation]],
    ) -> int:
        if not existing_relations:
            return 0
        return sum(1 for r in existing_relations
                   if r.source_id == source_id
                   and self._rel_value(r.relation_type) == rel_type)

    def _parse_registry_message(self, message: str) -> ValidationError:
        """将 TypeRegistry 校验器的字符串消息解析为结构化 ValidationError。"""
        for regex, fixed_field, field_g, exp_g, act_g, fixed_exp in self._MSG_PARSERS:
            m = regex.search(message)
            if not m:
                continue
            field = m.group(field_g) if field_g else fixed_field
            expected = fixed_exp if fixed_exp is not None else m.group(exp_g)
            actual = m.group(act_g) if act_g else "null"
            return ValidationError(field, expected, actual, message)
        return ValidationError("", "", "", message)

    @staticmethod
    def _has_cycle(adjacency: Dict[str, Set[str]], nodes: Set[str]) -> bool:
        """Kahn 拓扑排序：处理节点数 < 总节点数 ⇒ 存在环。"""
        in_degree = {n: 0 for n in nodes}
        for u in adjacency:
            for v in adjacency[u]:
                if v in in_degree:
                    in_degree[v] += 1
        queue = [n for n in nodes if in_degree[n] == 0]
        processed = 0
        while queue:
            u = queue.pop(0)
            processed += 1
            for v in adjacency.get(u, ()):
                if v in in_degree:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        queue.append(v)
        return processed < len(nodes)