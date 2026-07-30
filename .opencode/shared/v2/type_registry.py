"""
类型注册表 — 加载、校验、查询叙事单元类型定义。

取代：
  - fact_extractor.py（事实提取职责合并到此模块）
  - constraints.yaml（约束定义分散到各类型定义中）

职责：
  1. 加载内置和项目级类型定义 YAML
  2. 校验 content 格式是否符合类型 schema
  3. 按类型定义的 fact_fields 提取结构化事实
  4. 暴露类型查询接口
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml


# ── 类型定义的运行时表示 ──────────────────────────────────────────────


@dataclass
class FactFieldDef:
    """事实字段定义"""
    name: str
    path: str
    type: str                       # temporal_sequence | entity_reference | scalar | text
    ordering: Optional[str] = None  # 时序字段的序数路径
    target_type: Optional[str] = None  # entity_reference 的目标类型
    match_field: Optional[str] = None  # entity_reference 的匹配字段
    description: str = ""


@dataclass
class ConstraintDef:
    """单条约束定义的运行时表示"""
    rule_id: str
    category: str                   # temporal | referential_integrity | cardinality | boundary | state_conservation | pattern
    severity: str                   # error | warning | info
    description: str
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PayloadConstraintDef:
    """边 payload 约束定义"""
    rule_id: str
    category: str          # temporal | boundary | pattern
    severity: str
    description: str
    fields: List[str]      # payload 中的字段路径
    check: str             # field_a_lt_field_b | monotonic_increasing | field_not_null
    skip_when_null: bool = True
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationRule:
    """关系规则"""
    target_type: List[str]
    cardinality: str = "any"
    bidirectional: bool = False
    description: str = ""
    # 第二阶段扩展：payload schema + 约束
    payload_schema: Optional[Dict] = None
    payload_constraints: List[PayloadConstraintDef] = field(default_factory=list)
    auto_label: Optional[Dict] = None

    def __post_init__(self):
        if self.payload_schema is None:
            self.payload_schema = {}
        if self.payload_constraints is None:
            self.payload_constraints = []
        if self.auto_label is None:
            self.auto_label = {}


@dataclass
class ForbiddenWhen:
    """条件性禁止关系"""
    relation_type: str
    condition_field: str = "status"
    condition_eq: str = "archived"


@dataclass
class RelationDefSet:
    """关系定义集合"""
    allowed: Dict[str, RelationRule] = field(default_factory=dict)
    forbidden_when: List[ForbiddenWhen] = field(default_factory=list)


@dataclass
class StateTransition:
    """状态迁移"""
    to_status: str
    allowed_when: Optional[str] = None


@dataclass
class StateMachineDef:
    """状态机定义"""
    initial: str = "sprout"
    transitions: Dict[str, List[StateTransition]] = field(default_factory=dict)


@dataclass
class ContentSchema:
    """内容 schema（简化为字段声明列表）"""
    fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class TypeDefinition:
    """类型定义的完整运行时表示"""
    unit_type: str
    description: str = ""
    content_schema: ContentSchema = field(default_factory=ContentSchema)
    fact_fields: List[FactFieldDef] = field(default_factory=list)
    constraints: List[ConstraintDef] = field(default_factory=list)
    relations: RelationDefSet = field(default_factory=RelationDefSet)
    state_machine: StateMachineDef = field(default_factory=StateMachineDef)
    # 子类型配置（从 YAML subtype 节读取，替代 schemas.py SUBTYPE_REGISTRY）
    subtype_config: Optional[Dict[str, Any]] = None


# ── Schema 校验模式 ──────────────────────────────────────────────────

_VALID_TYPES = {"string", "number", "boolean", "array", "object", "any"}
_VALID_SEVERITIES = {"error", "warning", "info"}
_VALID_CATEGORIES = {
    "temporal", "referential_integrity", "cardinality",
    "boundary", "state_conservation", "pattern",
}
_VALID_CARDINALITIES = {"any", "0..1", "1", "1+", "0..n"}


# ── 类型注册表 ────────────────────────────────────────────────────────


class TypeRegistry:
    """
    类型注册表。

    加载顺序：
      1. 内置默认：.opencode/shared/v2/unit_types/<type>.yaml
      2. 项目级覆盖：{project_root}/.opencode/unit_types/<type>.yaml

    同名类型，项目级覆盖合并/覆盖内置定义。
    """

    _global_instance: Optional["TypeRegistry"] = None
    _BUILTIN_DIR = os.path.join(os.path.dirname(__file__), "unit_types")

    def __init__(self, project_root: Optional[str] = None, lazy: bool = False):
        self._project_root = project_root
        self._types: Dict[str, TypeDefinition] = {}
        self._loaded = False
        if not lazy:
            self.load_all()

    # ── 加载 ─────────────────────────────────────────────────────────────

    def load_all(self):
        """加载所有内置类型定义 + 项目级覆盖。"""
        self._types = {}

        # 1. 加载内置
        if os.path.isdir(self._BUILTIN_DIR):
            for fname in sorted(os.listdir(self._BUILTIN_DIR)):
                if fname.endswith(".yaml") or fname.endswith(".yml"):
                    fpath = os.path.join(self._BUILTIN_DIR, fname)
                    type_name = fname.rsplit(".", 1)[0]
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                        if data:
                            td = self._parse_definition(data)
                            self._types[type_name] = td
                    except Exception as e:
                        import warnings
                        warnings.warn(f"Failed to load builtin type '{type_name}': {e}")

        # 2. 加载项目级覆盖
        project_dir = None
        if self._project_root:
            project_dir = os.path.join(self._project_root, ".opencode", "unit_types")
        else:
            # 尝试从 CWD 推断
            cwd = os.getcwd()
            for candidate in [cwd, os.path.join(cwd, "..")]:
                pdir = os.path.join(candidate, ".opencode", "unit_types")
                if os.path.isdir(pdir):
                    project_dir = pdir
                    break

        if project_dir and os.path.isdir(project_dir):
            for fname in sorted(os.listdir(project_dir)):
                if fname.endswith(".yaml") or fname.endswith(".yml"):
                    fpath = os.path.join(project_dir, fname)
                    type_name = fname.rsplit(".", 1)[0]
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                        if data:
                            td = self._parse_definition(data)
                            # 如果内置已有，逐字段覆盖
                            if type_name in self._types:
                                existing = self._types[type_name]
                                if td.description:
                                    existing.description = td.description
                                if td.content_schema.fields:
                                    existing.content_schema.fields.update(td.content_schema.fields)
                                if td.fact_fields:
                                    existing.fact_fields = td.fact_fields
                                if td.constraints:
                                    # 按 rule_id 替换
                                    existing_ids = {c.rule_id for c in existing.constraints}
                                    for c in td.constraints:
                                        if c.rule_id in existing_ids:
                                            existing.constraints = [
                                                ec if ec.rule_id != c.rule_id else c
                                                for ec in existing.constraints
                                            ]
                                        else:
                                            existing.constraints.append(c)
                                if td.relations.allowed:
                                    existing.relations.allowed.update(td.relations.allowed)
                                if td.relations.forbidden_when:
                                    existing.relations.forbidden_when = td.relations.forbidden_when
                                if td.state_machine.transitions:
                                    existing.state_machine.transitions.update(td.state_machine.transitions)
                            else:
                                self._types[type_name] = td
                    except Exception as e:
                        import warnings
                        warnings.warn(f"Failed to load project type '{type_name}': {e}")

        self._loaded = True

    def reload(self):
        """重新加载所有定义。"""
        self._types = {}
        self.load_all()

    # ── 解析 ─────────────────────────────────────────────────────────────

    def _parse_definition(self, data: dict) -> TypeDefinition:
        """将 YAML dict 解析为 TypeDefinition。"""
        td = TypeDefinition(unit_type=data.get("unit_type", ""))

        td.description = data.get("description", "")

        # content_schema
        cs_data = data.get("content_schema", {}) or {}
        td.content_schema = ContentSchema(fields=self._parse_schema_fields(cs_data))

        # fact_fields
        ff_list = data.get("fact_fields", []) or []
        for ff in ff_list:
            td.fact_fields.append(FactFieldDef(
                name=ff.get("name", ""),
                path=ff.get("path", ""),
                type=ff.get("type", "text"),
                ordering=ff.get("ordering"),
                target_type=ff.get("target_type"),
                match_field=ff.get("match_field"),
                description=ff.get("description", ""),
            ))

        # constraints
        c_list = data.get("constraints", []) or []
        for c in c_list:
            constraint = ConstraintDef(
                rule_id=c.get("id", ""),
                category=c.get("category", ""),
                severity=c.get("severity", "info"),
                description=c.get("description", ""),
                enabled=c.get("enabled", True),
            )
            # 收集 category-specific 参数
            params = {}
            param_keys = [
                "fact_field", "check", "exceptions", "field", "state_field",
                "forbidden_relation", "allowed_exception_values",
                "relation_type", "min_count", "max_count", "target_type",
                "preceding_type", "following_relation",
                "source_type", "extract_field", "ordering_field", "monotonic",
                "exception_field", "exception_values",
                "match", "traverse",
            ]
            for k in param_keys:
                if k in c:
                    params[k] = c[k]
            # 兼容旧字段名 'on'（YAML 1.1 中 on 被解析为 boolean True）
            if "fact_field" in params and "on" not in params:
                params["on"] = params["fact_field"]
            if "on" in params and "fact_field" not in params:
                params["fact_field"] = params["on"]
            # 处理 exceptions 子字段
            exc = c.get("exceptions")
            if isinstance(exc, dict):
                if "field" in exc:
                    params["exception_field"] = exc["field"]
                if "values" in exc:
                    params["exception_values"] = exc["values"]
            constraint.params = params
            td.constraints.append(constraint)

        # relations
        rel_data = data.get("relations", {}) or {}
        allowed = rel_data.get("allowed", {}) or {}
        for rel_type_name, rule in allowed.items():
            if isinstance(rule, dict):
                # 解析 payload_constraints
                payload_constraints = []
                for pc in (rule.get("payload_constraints", []) or []):
                    payload_constraints.append(PayloadConstraintDef(
                        rule_id=pc.get("id", ""),
                        category=pc.get("category", ""),
                        severity=pc.get("severity", "info"),
                        description=pc.get("description", ""),
                        fields=pc.get("fields", pc.get("field", [])),
                        check=pc.get("check", ""),
                        skip_when_null=pc.get("skip_when_null", True),
                        params={k: v for k, v in pc.items()
                                if k not in ("id", "category", "severity",
                                             "description", "fields", "field",
                                             "check", "skip_when_null")},
                    ))
                td.relations.allowed[rel_type_name] = RelationRule(
                    target_type=rule.get("target_type", ["*"]),
                    cardinality=rule.get("cardinality", "any"),
                    bidirectional=rule.get("bidirectional", False),
                    description=rule.get("description", ""),
                    payload_schema=rule.get("payload_schema", {}),
                    payload_constraints=payload_constraints,
                    auto_label=rule.get("auto_label", {}),
                )

        fw_list = rel_data.get("forbidden_when", []) or []
        for fw in fw_list:
            condition = fw.get("condition", {})
            td.relations.forbidden_when.append(ForbiddenWhen(
                relation_type=fw.get("relation_type", ""),
                condition_field=condition.get("field", "status"),
                condition_eq=condition.get("eq", "archived"),
            ))

        # state_machine
        sm_data = data.get("state_machine", {}) or {}
        td.state_machine.initial = sm_data.get("initial", "sprout")
        trans = sm_data.get("transitions", {}) or {}
        for from_status, to_list in trans.items():
            td.state_machine.transitions[from_status] = [
                StateTransition(to_status=t.get("to_status", ""),
                                allowed_when=t.get("allowed_when"))
                for t in (to_list or [])
            ]

        # subtype 配置（替代 schemas.py SUBTYPE_REGISTRY）
        td.subtype_config = data.get("subtype")

        return td

    def _parse_schema_fields(self, schema: dict) -> Dict[str, Dict[str, Any]]:
        """将 content_schema 解析为字段 dict。保留 required/fields/items 等完整信息。"""
        fields = {}
        for key, val in (schema or {}).items():
            if isinstance(val, dict):
                entry = {
                    "type": val.get("type", "any"),
                    "nullable": val.get("nullable", False),
                    "required": val.get("required", False),
                    "description": val.get("description", ""),
                }
                if "enum" in val:
                    entry["enum"] = val["enum"]
                # 嵌套 dict 字段（如 character_arc 的 性格）
                if "fields" in val:
                    entry["fields"] = self._parse_schema_fields(val["fields"])
                # 列表项定义（如 scene 的 出场角色）
                if "items" in val:
                    items_val = val["items"]
                    if isinstance(items_val, dict):
                        items_entry: Dict[str, Any] = {"type": items_val.get("type", "any")}
                        if "properties" in items_val:
                            items_entry["properties"] = self._parse_schema_fields(items_val["properties"])
                        if items_val.get("nullable"):
                            items_entry["nullable"] = True
                        entry["items"] = items_entry
                    else:
                        entry["items"] = items_val
                fields[key] = entry
            else:
                fields[key] = {"type": "any", "nullable": True, "required": False, "description": ""}
        return fields

    # ── 查询 ─────────────────────────────────────────────────────────────

    def get_type(self, type_name: str) -> Optional[TypeDefinition]:
        """按类型名获取 TypeDefinition。"""
        return self._types.get(type_name)

    def list_types(self) -> Dict[str, TypeDefinition]:
        """列出所有已注册的类型。"""
        return dict(self._types)

    def has_type(self, type_name: str) -> bool:
        """判断类型是否存在。"""
        return type_name in self._types

    def get_content_schema(self, type_name: str) -> Dict[str, Dict[str, Any]]:
        """返回 content_schema 字段定义（含 required/nested/items 完整信息）。
           替代 schemas.SCHEMA_REGISTRY。"""
        td = self._types.get(type_name)
        if not td:
            return {}
        return td.content_schema.fields

    def get_required_fields(self, type_name: str) -> List[str]:
        """返回必填字段名列表。"""
        td = self._types.get(type_name)
        if not td:
            return []
        return [n for n, s in td.content_schema.fields.items() if s.get("required", False)]

    def get_subtype_config(self, type_name: str) -> Optional[Dict[str, Any]]:
        """返回子类型配置（替代 schemas.SUBTYPE_REGISTRY）。
           含 field/options/value_colors/behaviors 等。"""
        td = self._types.get(type_name)
        if not td:
            return None
        return td.subtype_config

    def schema_info(self, type_name: str) -> List[str]:
        """返回该类型的 Schema 摘要（供 LLM 参考注入 prompt）。
           替代 schemas.schema_info()。"""
        td = self._types.get(type_name)
        if not td:
            return [f"未知类型: {type_name}"]
        schema = td.content_schema.fields
        lines = [f"content JSON 字段要求 ({td.description or type_name}):"]
        for field, rules in schema.items():
            req = "必填" if rules.get("required") else "可选"
            t = rules.get("type", "any")
            desc = rules.get("description", "")
            opts = f" 选项: {rules['enum']}" if rules.get("enum") else ""
            desc_part = f" — {desc}" if desc else ""
            lines.append(f"  - {field} ({t}, {req}){opts}{desc_part}")
        return lines

    def default_content(self, type_name: str) -> str:
        """返回该类型的默认 content JSON（仅含必填字段的空值）。
           替代 schemas.default_content()。"""
        import json
        schema = self.get_content_schema(type_name)
        defaults: Dict[str, Any] = {}
        for field, rules in schema.items():
            if rules.get("required", False):
                t = rules.get("type")
                if t == "string":
                    defaults[field] = ""
                elif t == "number":
                    defaults[field] = 0
                elif t == "array":
                    defaults[field] = []
                elif t == "object":
                    defaults[field] = {}
                else:
                    defaults[field] = None
        return json.dumps(defaults, ensure_ascii=False)

    @property
    def loaded(self) -> bool:
        return self._loaded

    # ── Schema 校验 ──────────────────────────────────────────────────────

    def validate_content(self, type_name: str, content: Any) -> List[str]:
        """
        校验 content 是否符合类型的 content_schema。

        支持：
          - required 必填检查
          - 类型检查（string/number/boolean/array/object）
          - enum 枚举值检查
          - 嵌套 fields（dict 子字段）
          - items.properties（数组元素子字段）
          - nullable 空值放行

        返回错误信息列表，空列表 = 通过。
        """
        errors = []
        td = self._types.get(type_name)
        if not td or not td.content_schema.fields:
            return errors  # 无 schema 定义时不校验

        if content is None:
            content = {}

        # content 可能是 JSON 字符串
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                return errors  # 非 JSON 字符串跳过校验（向后兼容旧纯文本数据）
        else:
            parsed = content

        if not isinstance(parsed, dict):
            return errors  # 非 dict 跳过

        _TYPE_MAP = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for field_name, schema in td.content_schema.fields.items():
            field_type = schema.get("type", "any")
            nullable = schema.get("nullable", False)
            required = schema.get("required", False)

            # 必填检查
            if required:
                if field_name not in parsed or parsed[field_name] is None:
                    errors.append(f"缺少必填字段: {field_name}")
                    continue

            if field_name not in parsed:
                continue

            val = parsed[field_name]
            if val is None:
                if not nullable:
                    errors.append(f"字段 '{field_name}' 不可为空")
                continue

            # 类型检查
            expected = _TYPE_MAP.get(field_type)
            if expected and not isinstance(val, expected):
                errors.append(f"字段 '{field_name}' 应为 {field_type}，实际为 {type(val).__name__}")
                continue

            # enum 值检查
            enum_vals = schema.get("enum")
            if enum_vals and isinstance(val, str) and val not in enum_vals:
                errors.append(f"字段 '{field_name}' 值 '{val}' 不在允许范围内: {enum_vals}")

            # 嵌套 dict 字段检查
            sub_fields = schema.get("fields")
            if sub_fields and isinstance(val, dict):
                sub_errors = self._validate_content_dict(val, sub_fields, field_name)
                errors.extend(sub_errors)

            # 数组元素检查
            items_schema = schema.get("items")
            if items_schema and isinstance(val, list):
                properties = items_schema.get("properties") if isinstance(items_schema, dict) else None
                if properties:
                    for i, item in enumerate(val):
                        if isinstance(item, dict):
                            sub_errors = self._validate_content_dict(item, properties, f"{field_name}[{i}]")
                            errors.extend(sub_errors)
                else:
                    item_type = items_schema.get("type") if isinstance(items_schema, dict) else None
                    if item_type and item_type != "any":
                        item_expected = _TYPE_MAP.get(item_type)
                        if item_expected:
                            for i, item in enumerate(val):
                                if not isinstance(item, item_expected):
                                    errors.append(f"{field_name}[{i}] 应为 {item_type}，实际为 {type(item).__name__}")

        return errors

    def _validate_content_dict(self, data: Dict, fields_def: Dict, prefix: str) -> List[str]:
        """递归校验 dict 嵌套字段。"""
        errors = []
        for field_name, schema in fields_def.items():
            path = f"{prefix}.{field_name}"
            field_type = schema.get("type", "any")
            nullable = schema.get("nullable", False)
            required = schema.get("required", False)

            if required and (field_name not in data or data[field_name] is None):
                errors.append(f"缺少必填字段: {path}")
                continue

            if field_name not in data:
                continue

            val = data[field_name]
            if val is None:
                if not nullable:
                    errors.append(f"字段 '{path}' 不可为空")
                continue

            _TYPE_MAP = {
                "string": str, "number": (int, float),
                "boolean": bool, "array": list, "object": dict,
            }
            expected = _TYPE_MAP.get(field_type)
            if expected and not isinstance(val, expected):
                errors.append(f"字段 '{path}' 应为 {field_type}，实际为 {type(val).__name__}")
                continue

            enum_vals = schema.get("enum")
            if enum_vals and isinstance(val, str) and val not in enum_vals:
                errors.append(f"字段 '{path}' 值 '{val}' 不在允许范围内: {enum_vals}")

            sub = schema.get("fields")
            if sub and isinstance(val, dict):
                errors.extend(self._validate_content_dict(val, sub, path))

        return errors

    # ── 关系 payload schema ──────────────────────────────────────────────

    def get_relation_payload_schema(self, source_type: str, rel_type: str) -> Optional[Dict]:
        """获取某类型的特定关系上的 payload schema。"""
        td = self._types.get(source_type)
        if not td:
            return None
        rule = td.relations.allowed.get(rel_type)
        if not rule:
            return None
        return rule.payload_schema

    def get_relation_payload_constraints(self, source_type: str, rel_type: str) -> List[PayloadConstraintDef]:
        """获取某关系的 payload 级约束定义。"""
        td = self._types.get(source_type)
        if not td:
            return []
        rule = td.relations.allowed.get(rel_type)
        if not rule:
            return []
        return rule.payload_constraints

    def get_relation_auto_label_keywords(self, source_type: str, rel_type: str, label_type: str) -> set:
        """从 YAML 配置读取指定关系的自动标签关键词集。

        Args:
            source_type: 源类型名称（如 "character_arc"）
            rel_type: 关系类型名称（如 "relates_to"）
            label_type: 标签类型（如 "仇敌"）

        Returns:
            关键词集合，未配置时返回空集。
        """
        td = self._types.get(source_type)
        if not td:
            return set()
        rule = td.relations.allowed.get(rel_type)
        if not rule or not rule.auto_label:
            return set()
        label_cfg = rule.auto_label.get(label_type, {})
        if isinstance(label_cfg, dict):
            return set(label_cfg.get("keywords", []))
        return set()

    def get_relation_auto_labels(self, source_type: str, rel_type: str) -> dict[str, set]:
        """读取指定关系的全部自动标签配置 {标签名: 关键词集合}。

        Args:
            source_type: 源类型名称（如 "character_arc"）
            rel_type: 关系类型名称（如 "relates_to"）

        Returns:
            {标签名: 关键词集合} 字典，未配置或无关键词时返回空字典。
        """
        td = self._types.get(source_type)
        if not td:
            return {}
        rule = td.relations.allowed.get(rel_type)
        if not rule or not rule.auto_label:
            return {}
        result: dict[str, set] = {}
        for label_name, label_cfg in rule.auto_label.items():
            if isinstance(label_cfg, dict):
                kws = label_cfg.get("keywords", [])
                if kws:
                    result[label_name] = set(kws)
        return result

    def validate_relation_payload(self, source_type: str, rel_type: str, payload: Dict) -> List[str]:
        """校验 payload 是否符合该关系的 payload schema。
        
        返回错误信息列表，空列表 = 通过。
        复用 validate_content 的字段类型校验逻辑。
        """
        schema = self.get_relation_payload_schema(source_type, rel_type)
        if not schema:
            return []
        return self._validate_dict(payload, schema)

    def _validate_dict(self, data: Dict, schema: Dict, prefix: str = "") -> List[str]:
        """递归校验 dict 数据是否符合 schema 定义。"""
        errors = []
        for field_name, field_schema in (schema or {}).items():
            path = f"{prefix}.{field_name}" if prefix else field_name
            field_type = field_schema.get("type", "any")
            nullable = field_schema.get("nullable", False)
            value = data.get(field_name) if isinstance(data, dict) else None

            # null 处理
            if value is None:
                if not nullable:
                    errors.append(f"{path}: field is required (not nullable)")
                continue

            # 类型校验
            if field_type == "string" and not isinstance(value, str):
                errors.append(f"{path}: expected string, got {type(value).__name__}")
            elif field_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"{path}: expected number, got {type(value).__name__}")
            elif field_type == "boolean" and not isinstance(value, bool):
                errors.append(f"{path}: expected bool, got {type(value).__name__}")
            elif field_type == "array":
                if not isinstance(value, list):
                    errors.append(f"{path}: expected array, got {type(value).__name__}")
                else:
                    items_schema = field_schema.get("items", {})
                    if items_schema:
                        for i, item in enumerate(value):
                            item_path = f"{path}[{i}]"
                            if isinstance(item, dict):
                                item_errors = self._validate_dict(
                                    item, items_schema.get("properties", {}), item_path)
                                errors.extend(item_errors)
                            elif items_schema.get("type") and items_schema["type"] != "any":
                                item_type = items_schema["type"]
                                if item_type == "string" and not isinstance(item, str):
                                    errors.append(f"{item_path}: expected string, got {type(item).__name__}")
                                elif item_type == "number" and not isinstance(item, (int, float)):
                                    errors.append(f"{item_path}: expected number, got {type(item).__name__}")
            elif field_type == "object":
                if not isinstance(value, dict):
                    errors.append(f"{path}: expected object, got {type(value).__name__}")
                else:
                    props = field_schema.get("properties", {})
                    sub_errors = self._validate_dict(value, props, path)
                    errors.extend(sub_errors)
            # enum 校验
            enum_vals = field_schema.get("enum")
            if enum_vals and value is not None and value not in enum_vals:
                errors.append(f"{path}: value '{value}' not in {enum_vals}")

        return errors

    # ── 事实提取 ─────────────────────────────────────────────────────────

    def extract_facts(self, type_name: str, unit_content: Any) -> Dict[str, List[Any]]:
        """
        按类型定义的 fact_fields 从 content 中提取结构化事实。

        返回 dict: { fact_field_name: [values...] }

        取代 FactExtractor.extract_field_values()。
        """
        td = self._types.get(type_name)
        if not td:
            return {}

        if unit_content is None:
            unit_content = {}

        # 解析 JSON 字符串
        if isinstance(unit_content, str):
            try:
                parsed = json.loads(unit_content)
            except (json.JSONDecodeError, ValueError):
                return {}
        else:
            parsed = unit_content

        if not isinstance(parsed, dict):
            return {}

        facts: Dict[str, List[Any]] = {}
        for ff in td.fact_fields:
            values = self._traverse(parsed, ff.path)
            facts[ff.name] = values

        return facts

    def _traverse(self, data: Any, path: str) -> List[Any]:
        """
        递归遍历 JSON 数据，按点分路径提取所有值。

        支持：
          "events[].age" → 遍历 events 数组，取每个元素的 age
          "end_state"    → 取 data["end_state"]
        """
        parts = self._parse_path(path)
        current = [data]

        for part in parts:
            next_current = []
            is_array = part.endswith("[]")
            key = part[:-2] if is_array else part

            for item in current:
                if not isinstance(item, dict):
                    continue
                if key not in item:
                    continue
                value = item[key]

                if is_array:
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
        if not path:
            return []
        return [p.strip() for p in path.split(".") if p.strip()]

    # ── 单例 ─────────────────────────────────────────────────────────────

    @classmethod
    def get_global(cls, project_root: Optional[str] = None) -> "TypeRegistry":
        """获取全局单例。"""
        if cls._global_instance is None:
            cls._global_instance = cls(project_root=project_root, lazy=False)
        return cls._global_instance

    @classmethod
    def reset_global(cls):
        """重置全局单例（测试用）。"""
        cls._global_instance = None
