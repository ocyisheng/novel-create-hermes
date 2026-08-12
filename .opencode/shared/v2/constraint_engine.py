"""
约束引擎（重构版） — 基于类型自描述的通用模式匹配引擎。

核心逻辑：
  1. 获取已修改的叙事单元
  2. 查找每个单元的类型定义（TypeRegistry）
  3. 按类型定义的 fact_fields 提取结构化事实
  4. 对每条约束，交给对应的 PatternMatcher 执行模式匹配
  5. 同时校验边的合法性（按类型定义的 relations.allowed / forbidden_when）

设计原则：
  1. 声明式 — 约束定义在类型定义 YAML 中，不写代码
  2. 增量检查 — 只检查 version 有变化的单元
  3. 非阻塞 — 检测结果仅记录 deviation，不阻止写操作
  4. 可扩展 — 新增约束类别只需新增一个 Matcher 子类
  5. 类型自描述 — 每个 UnitType 自己说有什么约束，不再有全局 constraints.yaml
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Set, Any, Callable

from graph_store import GraphStore
from graph_schema import NarrativeUnit, Relation, RelationType

from type_registry import TypeRegistry, ConstraintDef, PayloadConstraintDef
from matchers import MATCHERS
from matchers.base import CheckResult

logger = logging.getLogger(__name__)


class ConstraintEngine:
    """
    叙事约束引擎。

    用法：
        engine = ConstraintEngine(store)
        engine.register_with_store()  # 自动注册到 post_flush 钩子
        results = engine.run()        # 手动触发
    """

    def __init__(
        self,
        store: GraphStore,
        registry: Optional[TypeRegistry] = None,
    ):
        self.store = store
        self.registry = registry or TypeRegistry.get_global(
            project_root=str(store.project_root)
        )
        # DeviationManager 实例缓存（延迟创建，复用同一实例保证水位/偏差一致落盘）
        self._dm: Optional[Any] = None

    def register_with_store(self):
        """注册到 GraphStore 的 post_flush 钩子，使约束检查自动运行。"""
        self.store.register_post_flush_hook(lambda s: self._on_flush(s))

    def _on_flush(self, store: GraphStore):
        """flush 后自动调用的回调。run_incremental 自身已持久化。"""
        self.run_incremental()

    def _get_deviation_manager(self):
        """延迟创建并缓存 DeviationManager（与水位/偏差共用同一实例）。"""
        if self._dm is None:
            from deviation_manager import DeviationManager
            self._dm = DeviationManager(str(self.store.project_root))
        return self._dm

    def _current_max_unit_version(self) -> int:
        """当前所有单元（含归档）的最大 version；无单元时返回 0。"""
        return max(
            (u.version for u in self.store._units.values()), default=0
        )

    def run(self, full: bool = False) -> List[CheckResult]:
        """
        全量运行约束检查。
        
        遍历所有非 archived 单元，检查其类型定义中的约束。
        结果自动持久化到 DeviationManager。
        full=True 时同时推进增量水位（constraint_watermark），
        使后续 run_incremental() 基于水位只检查有变更的单元。
        """
        results = []
        for unit in self.store._units.values():
            if unit.status.name == "ARCHIVED":
                continue
            type_def = self.registry.get_type(
                unit.type.value if hasattr(unit.type, "value") else str(unit.type)
            )
            if not type_def:
                continue

            unit_results = self._check_unit(unit, type_def)
            results.extend(unit_results)

        dm = self._get_deviation_manager()
        self._persist_results(results, dm, full_scan=full)
        if full:
            # 全量扫描：记录所有单元已检查到当前版本，并推进最大水位
            checked = dm.constraint_checked
            for u in self.store._units.values():
                checked[u.id] = u.version
            dm.constraint_watermark = self._current_max_unit_version()
            dm.save()
        return results

    def run_incremental(self) -> List[CheckResult]:
        """
        增量运行：只检查 version 高于上次检查版本（constraint_checked 表）的单元。

        unit.version 是逐单元计数器（从 1 起），因此仅靠单一水位无法识别
        "新建但 version 未超过水位"的单元——这里用 {unit_id: 已检查版本} 表
        判定：未记录（新建）或 version 递增（修改）的单元必然被检查，
        未变化的单元不会被重新扫描。

        结果自动持久化到 DeviationManager；检查成功后推进水位与已检查表。
        """
        dm = self._get_deviation_manager()
        checked = dm.constraint_checked
        # 候选：未检查过（新建）或 version 超过已检查版本（修改）
        modified = [
            unit for unit in self.store._units.values()
            if unit.status.name != "ARCHIVED"
            and unit.version > checked.get(unit.id, 0)
        ]
        results = []

        # 检查活跃的已修改单元
        for unit in modified:
            type_def = self.registry.get_type(
                unit.type.value if hasattr(unit.type, "value") else str(unit.type)
            )
            if not type_def:
                continue
            unit_results = self._check_unit(unit, type_def)
            results.extend(unit_results)

        # 额外检查状态相关约束：从 events 中找到最近归档的单元
        # 增量候选不含 archived，但状态守恒需要检查
        archived_check = self._check_archived_units()
        results.extend(archived_check)

        # 第二阶段扩展：检查脏边的 payload 约束
        relation_results = self._check_relations_incremental()
        results.extend(relation_results)

        self._persist_results(results, dm, full_scan=False)

        # 记录本次已检查单元的版本，并推进最大水位（成功检查后）
        for unit in self.store._units.values():
            checked[unit.id] = unit.version
        dm.constraint_watermark = self._current_max_unit_version()
        dm.save()
        return results

    def _check_archived_units(self) -> List[CheckResult]:
        """
        检查已归档单元的状态守恒约束。
        由于 get_modified_units 过滤了 archived，这里单独处理。
        """
        results = []
        for unit in self.store._units.values():
            if unit.status.name != "ARCHIVED":
                continue
            type_def = self.registry.get_type(
                unit.type.value if hasattr(unit.type, "value") else str(unit.type)
            )
            if not type_def:
                continue
            # 只运行状态守恒约束
            for constraint in type_def.constraints:
                if not constraint.enabled or constraint.category != "state_conservation":
                    continue
                matcher = MATCHERS.get("state_conservation")
                if not matcher:
                    continue
                try:
                    facts = self.registry.extract_facts(type_def.unit_type, unit.content)
                    result = matcher.check(constraint, unit, facts, self.store, registry=self.registry)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.warning(
                        "state_conservation 约束检查失败 (unit=%s, rule=%s): %s",
                        getattr(unit, "id", "?"),
                        getattr(constraint, "rule_id", "?"),
                        e,
                    )
        return results

    def _check_unit(self, unit: NarrativeUnit, type_def) -> List[CheckResult]:
        """对单个单元运行所有约束检查。"""
        results = []

        # 1. 提取事实
        facts = self.registry.extract_facts(
            type_def.unit_type,
            unit.content,
        )

        # 2. 对每条约束做模式匹配
        for constraint in type_def.constraints:
            if not constraint.enabled:
                continue

            matcher = MATCHERS.get(constraint.category)
            if not matcher:
                continue

            try:
                result = matcher.check(constraint, unit, facts, self.store, registry=self.registry)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(
                    "约束检查失败 (unit=%s, rule=%s, category=%s): %s",
                    getattr(unit, "id", "?"),
                    getattr(constraint, "rule_id", "?"),
                    getattr(constraint, "category", "?"),
                    e,
                )

        # 3. 校验边的合法性
        relation_results = self._validate_relations(unit, type_def)
        results.extend(relation_results)

        return results

    def _validate_relations(self, unit: NarrativeUnit, type_def) -> List[CheckResult]:
        """
        按类型定义的 relations.allowed / forbidden_when 校验边的合法性。

        只校验以当前单元为 source 的 outgoing 边（关系的方向由创建者语义决定）。
        """
        results = []
        # get_relations 返回所有边（incoming + outgoing），只校验 outgoing
        all_rels = self.store.get_relations(unit.id)
        rels = [r for r in all_rels if r.source_id == unit.id]
        for rel in rels:
            rel_type_name = rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type)

            # (a) 检查 forbidden_when
            for fw in type_def.relations.forbidden_when:
                if fw.relation_type == rel_type_name:
                    # 检查条件字段
                    if fw.condition_field == "status":
                        state_val = unit.status
                        status_str = state_val.value if hasattr(state_val, "value") else str(state_val)
                        if status_str == fw.condition_eq:
                            results.append(CheckResult(
                                rule_id=f"relation_forbidden_{fw.relation_type}",
                                severity="warning",
                                description=f"「{unit.unit_name}」(状态={status_str}) 不应有 {fw.relation_type} 关系",
                                units_involved=[unit.id],
                                detail=f"关系: {rel.id}, 目标: {rel.target_id}",
                            ))

            # (b) 检查 allowed
            allowed_rules = type_def.relations.allowed
            if rel_type_name not in allowed_rules:
                # 不是明确允许的边类型 — 记录 info
                results.append(CheckResult(
                    rule_id=f"relation_not_allowed_{rel_type_name}",
                    severity="info",
                    description=f"「{unit.unit_name}」使用了类型定义中未声明的边类型 {rel_type_name}",
                    units_involved=[unit.id],
                    detail=f"关系: {rel.id} ({rel.source_id} → {rel.target_id})",
                ))
            else:
                rule = allowed_rules[rel_type_name]
                # 检查目标类型
                target_types = rule.target_type
                if "*" not in target_types:
                    target = self.store.get_unit(rel.target_id)
                    if target:
                        tgt_type = target.type.value if hasattr(target.type, "value") else str(target.type)
                        if tgt_type not in target_types:
                            results.append(CheckResult(
                                rule_id=f"relation_target_type_{rel_type_name}",
                                severity="info",
                                description=f"「{unit.unit_name}」的 {rel_type_name} 边连接了不允许的类型 {tgt_type}（期望 {target_types}）",
                                units_involved=[unit.id, rel.target_id],
                                detail=f"关系: {rel.id}, 目标: {target.unit_name} ({tgt_type})",
                            ))

        return results

    # ── 第二阶段：边 payload 约束检查 ───────────────────────────────────

    def _check_relations_incremental(self) -> List[CheckResult]:
        """
        增量检查被修改的边（dirty_relation_ids）的 payload。

        只检查有脏标记的边，避免全量扫描。
        """
        results = []
        dirty_ids = self.store.get_dirty_relation_ids()

        if not dirty_ids:
            return results

        for rel_id in dirty_ids:
            rel = self.store.get_relation(rel_id)
            if not rel:
                continue

            source = self.store.get_unit(rel.source_id)
            if not source:
                continue

            source_type = (
                source.type.value if hasattr(source.type, "value") else str(source.type)
            )
            rel_type = (
                rel.relation_type.value
                if hasattr(rel.relation_type, "value")
                else str(rel.relation_type)
            )

            # 1. payload schema 校验
            schema_violations = self._check_relation_payload_schema(
                source_type, rel_type, rel, source
            )
            results.extend(schema_violations)

            # 2. payload 约束检查
            constraint_results = self._check_relation_payload_constraints(
                source_type, rel_type, rel, source
            )
            results.extend(constraint_results)

        return results

    def _check_relation_payload_schema(
        self,
        source_type: str,
        rel_type: str,
        rel: Relation,
        source: NarrativeUnit,
    ) -> List[CheckResult]:
        """校验边的 payload 是否符合类型定义的 payload_schema。"""
        results = []
        schema = self.registry.get_relation_payload_schema(source_type, rel_type)
        if not schema:
            return results

        violations = self.registry._validate_dict(rel.payload, schema)
        if violations:
            # 只取前 5 条错误避免消息爆炸
            truncated = violations[:5]
            results.append(CheckResult(
                rule_id=f"payload_schema_{rel_type}",
                severity="warning",
                description=f"「{source.unit_name}」的 {rel_type} 边 payload 不合 schema",
                units_involved=[rel.source_id, rel.target_id],
                detail="; ".join(truncated),
            ))
        return results

    def _check_relation_payload_constraints(
        self,
        source_type: str,
        rel_type: str,
        rel: Relation,
        source: NarrativeUnit,
    ) -> List[CheckResult]:
        """校验边的 payload 约束定义。"""
        results = []
        constraints = self.registry.get_relation_payload_constraints(source_type, rel_type)
        if not constraints:
            return results

        for pc in constraints:
            try:
                result = self._check_single_payload_constraint(pc, rel, source)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(
                    "payload 约束检查失败 (rel=%s, rule=%s): %s",
                    getattr(rel, "id", "?"),
                    getattr(pc, "rule_id", "?"),
                    e,
                )

        return results

    def _check_single_payload_constraint(
        self,
        pc: PayloadConstraintDef,
        rel: Relation,
        source: NarrativeUnit,
    ) -> Optional[CheckResult]:
        """执行单条 payload 约束检查。"""
        if pc.category == "temporal":
            return self._check_payload_temporal(pc, rel, source)
        elif pc.category == "boundary":
            return self._check_payload_boundary(pc, rel, source)
        return None

    def _check_payload_temporal(
        self,
        pc: PayloadConstraintDef,
        rel: Relation,
        source: NarrativeUnit,
    ) -> Optional[CheckResult]:
        """payload 时序约束检查。"""
        # field_a_lt_field_b: 比较两个字段值，确保 a < b
        if pc.check == "field_a_lt_field_b" and len(pc.fields) >= 2:
            raw_a = self._traverse_payload(rel.payload, pc.fields[0])
            raw_b = self._traverse_payload(rel.payload, pc.fields[1])
            # _traverse 返回 List[Any]，提取第一个元素
            val_a = raw_a[0] if isinstance(raw_a, list) and raw_a else None
            val_b = raw_b[0] if isinstance(raw_b, list) and raw_b else None
            if val_a is not None and val_b is not None:
                try:
                    if float(val_a) >= float(val_b):
                        return CheckResult(
                            rule_id=pc.rule_id,
                            severity=pc.severity,
                            description=(
                                f"「{source.unit_name}」{pc.description}: "
                                f"{pc.fields[0]}={val_a} ≥ {pc.fields[1]}={val_b}"
                            ),
                            units_involved=[rel.source_id, rel.target_id],
                            detail=f"边 {rel.id}, payload.{pc.fields[0]}={val_a}, "
                                   f"payload.{pc.fields[1]}={val_b}",
                        )
                except (ValueError, TypeError):
                    return None
            # skip_when_null: 任一字段为空就跳过（默认 True）
            if not pc.skip_when_null:
                if val_a is None or val_b is None:
                    return CheckResult(
                        rule_id=pc.rule_id,
                        severity=pc.severity,
                        description=(
                            f"「{source.unit_name}」{pc.description}: "
                            f"{pc.fields[0]}={val_a}, {pc.fields[1]}={val_b}（字段为空但不可跳过）"
                        ),
                        units_involved=[rel.source_id, rel.target_id],
                    )
            return None

        # monotonic_increasing: 检查数组字段是否单调递增
        if pc.check == "monotonic_increasing" and len(pc.fields) >= 1:
            raw = self._traverse_payload(rel.payload, pc.fields[0])
            # _traverse 统一返回 List[Any]：
            #   - 直接数组路径（如 "upgrades"）→ [[{...}, {...}]]（外层包裹一层）
            #   - 数组元素路径（如 "upgrades[].ordinal"）→ [1, 2, 3]（已展平）
            # 仅当第一个元素本身是 list 时才解开外层包裹，两种路径都能正确取值。
            if isinstance(raw, list) and raw and isinstance(raw[0], list):
                values = raw[0]
            else:
                values = raw
            if not isinstance(values, list):
                return None
            if len(values) <= 1:
                return None
            prev = None
            for i, v in enumerate(values):
                if v is None:
                    continue
                # v 可能是 dict，提取 ordinal 字段
                item_val = None
                if isinstance(v, dict):
                    item_val = v.get('ordinal')
                else:
                    item_val = v
                if item_val is None:
                    continue
                try:
                    num = float(item_val)
                except (ValueError, TypeError):
                    continue
                if prev is not None and prev >= num:
                    return CheckResult(
                        rule_id=pc.rule_id,
                        severity=pc.severity,
                        description=(
                            f"「{source.unit_name}」{pc.description}: "
                            f"{pc.fields[0]}[{i - 1}]={prev} ≥ [{i}]={num}"
                        ),
                        units_involved=[rel.source_id, rel.target_id],
                        detail=f"边 {rel.id}, 值 {prev} → {num} 未递增",
                    )
                prev = num
            return None

        return None

    def _check_payload_boundary(
        self,
        pc: PayloadConstraintDef,
        rel: Relation,
        source: NarrativeUnit,
    ) -> Optional[CheckResult]:
        """payload 边界约束检查（如字段不可为空）。"""
        if pc.check == "field_not_null" and len(pc.fields) >= 1:
            raw = self._traverse_payload(rel.payload, pc.fields[0])
            # _traverse 返回列表，空列表或 None 都表示字段不存在
            val = raw[0] if isinstance(raw, list) and raw else raw
            if val is None or (isinstance(val, list) and not val):
                return CheckResult(
                    rule_id=pc.rule_id,
                    severity=pc.severity,
                    description=(
                        f"「{source.unit_name}」{pc.description}: "
                        f"{pc.fields[0]} 为空"
                    ),
                    units_involved=[rel.source_id, rel.target_id],
                    detail=f"边 {rel.id}, payload.{pc.fields[0]} 缺失",
                )
        return None

    def _traverse_payload(self, payload: Dict, path: str) -> Any:
        """在 payload dict 中按点分路径取值。"""
        return self.registry._traverse(payload, path)

    def _persist_results(
        self,
        results: List[CheckResult],
        dm: Optional[Any] = None,
        full_scan: bool = False,
    ):
        """将检查结果持久化到 DeviationManager。

        dm 可复用调用方已持有的实例（保证水位与偏差状态一致落盘）；
        full_scan 标记本次是否为全量扫描（影响自动 resolve 语义）。
        """
        try:
            if dm is None:
                dm = self._get_deviation_manager()
            dm.merge_from_check_results(results, full_scan=full_scan)
        except Exception as e:
            logger.warning(
                "ConstraintEngine._persist_results 失败: %s", e
            )
