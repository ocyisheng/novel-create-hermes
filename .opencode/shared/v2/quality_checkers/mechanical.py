"""
MechanicalChecker — 机械检查层。

迁移自 search_engine.py（R1-R6, R9）和 constraint_engine.py（确定性约束），
使用统一 CheckResult（source=MECHANICAL, check_layer=STRUCTURE）。

职责边界：
  ✅ 结构性一致性检查（归档角色、关系对称、孤立单元等）
  ✅ 类型约束检查（基数、边合法性、payload 校验、状态守恒）
  ❌ 统计/节奏分析（R7/R10-R12）→ StatisticalChecker
  ❌ 语义分析（LLM）→ SemanticChecker
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Type

from graph_schema import (
    NarrativeUnit, UnitType, UnitStatus, RelationType,
    get_unit_chapter,
)
from graph_store import GraphStore
from time_utils import get_story_ordinal

from quality_checkers.types import CheckResult, CheckSource, CheckLayer

logger = logging.getLogger(__name__)


class MechanicalChecker:
    """
    机械检查器 — 纯确定性结构检查，无 LLM 调用。

    用法：
        checker = MechanicalChecker(store)
        results = checker.check_all()
    """

    def __init__(
        self,
        store: GraphStore,
        registry: Optional[Any] = None,  # TypeRegistry, 避免循环导入
    ):
        self.store = store
        self._registry = registry
        self._registry_loaded = False

    def _get_registry(self):
        """延迟加载 TypeRegistry。"""
        if not self._registry_loaded:
            if self._registry is None:
                try:
                    from type_registry import TypeRegistry
                    self._registry = TypeRegistry.get_global(
                        project_root=str(self.store.project_root)
                    )
                except Exception as e:
                    logger.warning("TypeRegistry 加载失败: %s", e)
            self._registry_loaded = True
        return self._registry

    # NOTE: R1-R6 rule family duplicates quality_checkers/mechanical.py;
    # canonical LLM-facing entry is graph.quality_check (NarrativeQualityEngine).
    # Do not add new duplicate rules here.
    def check_all(self) -> List[CheckResult]:
        """运行所有机械检查规则（R1-R6, R9 + 约束引擎规则）。"""
        results: List[CheckResult] = []
        # R1-R6, R9: 迁移自 search_engine.py
        results.extend(self._check_archived_characters_in_scenes())
        results.extend(self._check_orphan_units())
        results.extend(self._check_archived_with_active_relations())
        results.extend(self._check_chunk_missing_file())
        results.extend(self._check_chunk_no_chapter())
        results.extend(self._check_precedes_ordinal_conflicts())
        # 约束引擎确定性检查
        results.extend(self._check_edge_legality())
        results.extend(self._check_payload_schema())
        results.extend(self._check_state_conservation())
        return results

    # ── R1: 归档角色仍出场 ────────────────────────────────────────────────

    def _check_archived_characters_in_scenes(self) -> List[CheckResult]:
        """规则 1: 已故/归档角色仍在参与场景"""
        results = []
        for unit in self.store._units.values():
            if unit.type != UnitType.CHARACTER_ARC:
                continue
            if unit.status != UnitStatus.ARCHIVED:
                continue

            # PARTICIPATES_IN 对称类型：物理方向无意义，任一端是场景即视为出场。
            # get_relations(unit.id) 采集双向；对每条边找"另一端"判断是否场景。
            for rel in self.store.get_relations(unit.id):
                if rel.relation_type != RelationType.PARTICIPATES_IN:
                    continue
                other_id = rel.target_id if rel.source_id == unit.id else rel.source_id
                target = self.store.get_unit(other_id)
                if target and target.type == UnitType.SCENE:
                        results.append(CheckResult(
                            rule_id="R1",
                            rule_name="已故角色仍在出场",
                            severity="error",
                            description=(
                                f"角色『{unit.unit_name}』已归档({unit.status.value})，"
                                f"但仍在场景『{target.unit_name}』中出场"
                            ),
                            units_involved=[unit.id, target.id],
                            source=CheckSource.MECHANICAL,
                            check_layer=CheckLayer.STRUCTURE,
                        ))
        return results

    # ── R3: 孤立单元 ───────────────────────────────────────────────────────

    def _check_orphan_units(self) -> List[CheckResult]:
        """规则 3: 孤立单元（没有任何关系）"""
        orphan_count = 0
        orphan_names: List[str] = []
        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            rels = self.store.get_relations(unit.id)
            if not rels:
                orphan_count += 1
                orphan_names.append(f"{unit.unit_name} ({unit.type.value})")

        detail = ""
        if orphan_names:
            detail = "孤立单元:\n" + "\n".join(f"  - {n}" for n in orphan_names[:10])
            if len(orphan_names) > 10:
                detail += f"\n  ... 等共 {len(orphan_names)} 个"

        return [CheckResult(
            rule_id="R3",
            rule_name="孤立单元",
            severity="info",
            description=f"有 {orphan_count} 个单元没有任何关系",
            units_involved=[],
            detail=detail,
            source=CheckSource.MECHANICAL,
            check_layer=CheckLayer.STRUCTURE,
        )]

    # ── R4: 归档单元仍有活跃关系 ───────────────────────────────────────────

    def _check_archived_with_active_relations(self) -> List[CheckResult]:
        """规则 4: 已归档但仍有活跃关系的单元

        活跃关系判定（新关系模型）：
        - 对称类型（RELATES_TO/CONTRADICTS/PARTICIPATES_IN 等，inverse==自身）：
          方向无意义，任一端关联即算活跃——单条物理边即可双向可达；
        - 非对称类型（CAUSES/REFERENCES 等）：仅单元为源端的出边算活跃。
        """
        results = []
        for unit in self.store._units.values():
            if unit.status != UnitStatus.ARCHIVED:
                continue
            all_rels = self.store.get_relations(unit.id)
            active = [
                r for r in all_rels
                if r.relation_type.is_symmetric or r.source_id == unit.id
            ]
            if active:
                rel_names = []
                for rel in active[:5]:
                    tgt = self.store.get_unit(rel.target_id)
                    tn = tgt.unit_name if tgt else "?"
                    rel_names.append(f"{rel.relation_type.value}→{tn}")
                results.append(CheckResult(
                    rule_id="R4",
                    rule_name="归档单元仍有活跃关系",
                    severity="warning",
                    description=(
                        f"单元『{unit.unit_name}』({unit.type.value})已归档，"
                        f"但仍有 {len(active)} 条活跃关系"
                    ),
                    units_involved=[unit.id],
                    detail="关系: " + ", ".join(rel_names) if rel_names else "",
                    source=CheckSource.MECHANICAL,
                    check_layer=CheckLayer.STRUCTURE,
                ))
        return results

    # ── R5: CHUNK 文件丢失 ──────────────────────────────────────────────────

    def _check_chunk_missing_file(self) -> List[CheckResult]:
        """规则 5: CHUNK 的正文文件（正文路径/正文分片）不存在"""
        results = []
        project_root = self.store.project_root
        for unit in self.store._units.values():
            if unit.type != UnitType.CHUNK:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue
            try:
                content_dict = json.loads(unit.content) if unit.content else {}
            except (json.JSONDecodeError, ValueError):
                continue
            # 优先检查正文分片
            slice_info = content_dict.get("slice_info")
            if slice_info:
                slice_path = slice_info.get("文件", "")
                if slice_path and not (project_root / slice_path).exists():
                    results.append(CheckResult(
                        rule_id="R5a",
                        rule_name="CHUNK 分片文件丢失",
                        severity="warning",
                        description=f"CHUNK『{unit.unit_name}』的分片文件不存在: {slice_path}",
                        units_involved=[unit.id],
                        source=CheckSource.MECHANICAL,
                        check_layer=CheckLayer.STRUCTURE,
                    ))
                continue  # 有 slice_info 就不检查 file_path
            # 回退到 file_path
            source_path = content_dict.get("file_path", "")
            if not source_path:
                continue
            if not (project_root / source_path).exists():
                results.append(CheckResult(
                    rule_id="R5",
                    rule_name="CHUNK 正文文件丢失",
                    severity="warning",
                    description=f"CHUNK『{unit.unit_name}』的正文文件不存在: {source_path}",
                    units_involved=[unit.id],
                    source=CheckSource.MECHANICAL,
                    check_layer=CheckLayer.STRUCTURE,
                ))
        return results

    # ── R6: CHUNK 章节号不一致 ──────────────────────────────────────────────

    def _check_chunk_no_chapter(self) -> List[CheckResult]:
        """规则 6: CHUNK content 中有章节号但 chapter_number 未同步。"""
        count = 0
        names: List[str] = []
        for unit in self.store._units.values():
            if unit.type != UnitType.CHUNK:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue
            # 仅当 content 中显式设置了章节号但 get_unit_chapter 返回 0 时才标记
            if not get_unit_chapter(unit) and unit.content:
                try:
                    content_dict = json.loads(unit.content) if isinstance(unit.content, str) else {}
                    if content_dict.get("chapter_number") is not None:
                        count += 1
                        names.append(unit.unit_name)
                except (json.JSONDecodeError, ValueError):
                    pass

        detail = ""
        if names:
            detail = "\n".join(f"  - {n}" for n in names[:10])
            if len(names) > 10:
                detail += f"\n  ... 等共 {len(names)} 个"

        return [CheckResult(
            rule_id="R6",
            rule_name="CHUNK 章节号不一致",
            severity="info",
            description=(
                f"有 {count} 个 CHUNK 的 content 含章节号但 chapter_number 未同步"
                if count else "CHUNK 章节状态一致"
            ),
            units_involved=[],
            detail=detail,
            source=CheckSource.MECHANICAL,
            check_layer=CheckLayer.STRUCTURE,
        )]

    # ── R9: PRECEDES/ordinal 冲突 ───────────────────────────────────────────

    def _check_precedes_ordinal_conflicts(self) -> List[CheckResult]:
        """
        检测 PRECEDES 边方向与故事时间序数排序的不一致。
        纯结构检查：A PRECEDES B 但 ordinal(A) >= ordinal(B)。
        """
        results: List[CheckResult] = []

        for rel_id, rel in self.store._relations.items():
            if rel.relation_type != RelationType.PRECEDES:
                continue

            src = self.store.get_unit(rel.source_id)
            tgt = self.store.get_unit(rel.target_id)
            if not src or not tgt:
                continue

            ord_src = get_story_ordinal(src)
            ord_tgt = get_story_ordinal(tgt)
            if ord_src is None or ord_tgt is None:
                continue

            if ord_src >= ord_tgt:
                results.append(CheckResult(
                    rule_id="R9",
                    rule_name="事件顺序冲突",
                    severity="error",
                    description=(
                        f"PRECEDES 边方向与序数不一致: {src.unit_name} → {tgt.unit_name}"
                    ),
                    units_involved=[rel.source_id, rel.target_id],
                    detail=(
                        f"{src.unit_name}(ord={ord_src}) PRECEDES {tgt.unit_name}(ord={ord_tgt})，"
                        f"但序数 {ord_src} >= {ord_tgt}"
                    ),
                    source=CheckSource.MECHANICAL,
                    check_layer=CheckLayer.STRUCTURE,
                ))

        return results

    # ── 约束引擎: 边合法性检查 ──────────────────────────────────────────────

    def _check_edge_legality(self) -> List[CheckResult]:
        """
        按类型定义的 relations.allowed / forbidden_when 校验边的合法性。
        迁移自 constraint_engine._validate_relations，对所有活跃单元执行。
        """
        registry = self._get_registry()
        if not registry:
            return []

        results: List[CheckResult] = []
        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            type_def = registry.get_type(
                unit.type.value if hasattr(unit.type, "value") else str(unit.type)
            )
            if not type_def:
                continue

            all_rels = self.store.get_relations(unit.id)
            rels = [r for r in all_rels if r.source_id == unit.id]
            for rel in rels:
                rel_type_name = rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type)

                # (a) 检查 forbidden_when
                for fw in type_def.relations.forbidden_when:
                    if fw.relation_type == rel_type_name:
                        if fw.condition_field == "status":
                            state_val = unit.status
                            status_str = state_val.value if hasattr(state_val, "value") else str(state_val)
                            if status_str == fw.condition_eq:
                                results.append(CheckResult(
                                    rule_id=f"relation_forbidden_{fw.relation_type}",
                                    rule_name=f"禁止关系: {fw.relation_type}",
                                    severity="warning",
                                    description=f"「{unit.unit_name}」(状态={status_str}) 不应有 {fw.relation_type} 关系",
                                    units_involved=[unit.id],
                                    detail=f"关系: {rel.id}, 目标: {rel.target_id}",
                                    source=CheckSource.MECHANICAL,
                                    check_layer=CheckLayer.STRUCTURE,
                                ))

                # (b) 检查 allowed
                allowed_rules = type_def.relations.allowed
                if rel_type_name not in allowed_rules:
                    results.append(CheckResult(
                        rule_id=f"relation_not_allowed_{rel_type_name}",
                        rule_name=f"未声明边类型: {rel_type_name}",
                        severity="info",
                        description=f"「{unit.unit_name}」使用了类型定义中未声明的边类型 {rel_type_name}",
                        units_involved=[unit.id],
                        detail=f"关系: {rel.id} ({rel.source_id} → {rel.target_id})",
                        source=CheckSource.MECHANICAL,
                        check_layer=CheckLayer.STRUCTURE,
                    ))
                else:
                    rule = allowed_rules[rel_type_name]
                    target_types = rule.target_type
                    if "*" not in target_types:
                        target = self.store.get_unit(rel.target_id)
                        if target:
                            tgt_type = target.type.value if hasattr(target.type, "value") else str(target.type)
                            if tgt_type not in target_types:
                                results.append(CheckResult(
                                    rule_id=f"relation_target_type_{rel_type_name}",
                                    rule_name=f"边目标类型错误: {rel_type_name}",
                                    severity="info",
                                    description=(
                                        f"「{unit.unit_name}」的 {rel_type_name} 边连接了不允许的类型 "
                                        f"{tgt_type}（期望 {target_types}）"
                                    ),
                                    units_involved=[unit.id, rel.target_id],
                                    detail=f"关系: {rel.id}, 目标: {target.unit_name} ({tgt_type})",
                                    source=CheckSource.MECHANICAL,
                                    check_layer=CheckLayer.STRUCTURE,
                                ))

        return results

    # ── 约束引擎: payload schema 校验 ──────────────────────────────────────

    def _check_payload_schema(self) -> List[CheckResult]:
        """
        校验边的 payload 是否符合类型定义的 payload_schema。
        迁移自 constraint_engine._check_relations_incremental，全量扫描。
        """
        registry = self._get_registry()
        if not registry:
            return []

        results: List[CheckResult] = []
        for rel_id, rel in self.store._relations.items():
            source = self.store.get_unit(rel.source_id)
            if not source:
                continue

            source_type = source.type.value if hasattr(source.type, "value") else str(source.type)
            rel_type = rel.relation_type.value if hasattr(rel.relation_type, "value") else str(rel.relation_type)

            # payload schema 校验
            schema = registry.get_relation_payload_schema(source_type, rel_type)
            if not schema:
                continue

            violations = registry._validate_dict(rel.payload, schema)
            if violations:
                truncated = violations[:5]
                results.append(CheckResult(
                    rule_id=f"payload_schema_{rel_type}",
                    rule_name=f"Payload schema 违规: {rel_type}",
                    severity="warning",
                    description=f"「{source.unit_name}」的 {rel_type} 边 payload 不合 schema",
                    units_involved=[rel.source_id, rel.target_id],
                    detail="; ".join(truncated),
                    source=CheckSource.MECHANICAL,
                    check_layer=CheckLayer.STRUCTURE,
                ))

        return results

    # ── 约束引擎: 状态守恒检查 ──────────────────────────────────────────────

    def _check_state_conservation(self) -> List[CheckResult]:
        """
        检查状态转换合法性。
        迁移自 constraint_engine._check_archived_units + matchers 的 state_conservation 逻辑。
        对所有活跃单元和已归档单元运行状态守恒约束。
        """
        registry = self._get_registry()
        if not registry:
            return []

        try:
            from matchers import MATCHERS
        except ImportError:
            return []

        state_matcher = MATCHERS.get("state_conservation")
        if not state_matcher:
            return []

        results: List[CheckResult] = []
        for unit in self.store._units.values():
            type_def = registry.get_type(
                unit.type.value if hasattr(unit.type, "value") else str(unit.type)
            )
            if not type_def:
                continue

            for constraint in type_def.constraints:
                if not constraint.enabled or constraint.category != "state_conservation":
                    continue
                try:
                    facts = registry.extract_facts(type_def.unit_type, unit.content)
                    result = state_matcher.check(
                        constraint, unit, facts, self.store, registry=registry
                    )
                    if result:
                        # 转换为统一 CheckResult
                        results.append(CheckResult(
                            rule_id=result.rule_id,
                            rule_name=f"状态守恒: {constraint.description}",
                            severity=result.severity,
                            description=result.description,
                            units_involved=result.units_involved,
                            detail=result.detail,
                            source=CheckSource.MECHANICAL,
                            check_layer=CheckLayer.STRUCTURE,
                        ))
                except Exception as e:
                    logger.warning(
                        "state_conservation 约束检查失败 (unit=%s, rule=%s): %s",
                        getattr(unit, "id", "?"),
                        getattr(constraint, "rule_id", "?"),
                        e,
                    )

        return results
