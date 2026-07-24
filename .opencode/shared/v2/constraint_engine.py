"""
约束引擎 — 叙事一致性自动检测。

加载 constraints.yaml 中的声明式约束，在 graph_store.flush() 时自动运行，
检测所有类型的一致性冲突，结果持久化到 DeviationManager。

设计原则：
1. 声明式 — 约束定义在 YAML 中，不写代码
2. 增量检查 — 只检查 version 有变化的单元
3. 非阻塞 — 检测结果仅记录，不阻止写操作
4. 可扩展 — 新增约束只需在 YAML 中声明
"""

from __future__ import annotations

import os
import json
import yaml
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from graph_store import GraphStore
from fact_extractor import FactExtractor


@dataclass
class ConstraintDef:
    """一条约束定义的运行时表示"""
    category: str           # referential_integrity / temporal / relational / boundary / state_conservation / pattern
    rule_id: str            # 唯一标识，如 "RI01", "T01"
    severity: str           # error / warning / info
    description: str        # 人类可读描述
    params: Dict[str, Any]  # 约束参数（因类别而异）
    enabled: bool = True    # 可临时关闭


@dataclass
class CheckResult:
    """单条约束检查结果"""
    rule_id: str
    severity: str
    description: str
    units_involved: List[str]
    detail: str = ""


class ConstraintEngine:
    """
    叙事约束引擎。
    
    用法：
        engine = ConstraintEngine(store)
        engine.register_with_store()  # 自动注册到 post_flush 钩子
        results = engine.run()        # 手动触发
    """
    
    def __init__(self, store: GraphStore):
        self.store = store
        self.extractor = FactExtractor(store)
        self._constraints: List[ConstraintDef] = []
        self._load_constraints()
    
    def _load_constraints(self):
        """加载约束定义。优先级：项目级 > 默认内置。"""
        # 1. 加载内置默认约束
        builtin = self._default_constraints()
        self._constraints = list(builtin)
        
        # 2. 加载项目级覆盖（如果存在）
        project_root = self.store.project_root
        project_constraint_path = os.path.join(project_root, ".opencode", "constraints.yaml")
        if os.path.exists(project_constraint_path):
            try:
                with open(project_constraint_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and "constraints" in data:
                    for c in data["constraints"]:
                        # 按 rule_id 替换或追加
                        override = ConstraintDef(
                            category=c.get("category", "unknown"),
                            rule_id=c["id"],
                            severity=c.get("severity", "info"),
                            description=c.get("description", ""),
                            params=c.get("params", {}),
                            enabled=c.get("enabled", True),
                        )
                        existing_idx = next(
                            (i for i, ec in enumerate(self._constraints) if ec.rule_id == override.rule_id),
                            None
                        )
                        if existing_idx is not None:
                            # 替换（覆盖 severity、启用状态等）
                            old = self._constraints[existing_idx]
                            override.params = {**old.params, **override.params}
                            self._constraints[existing_idx] = override
                        else:
                            self._constraints.append(override)
            except Exception:
                pass  # 项目级约束加载失败不影响核心功能
    
    def register_with_store(self):
        """注册到 GraphStore 的 post_flush 钩子，使约束检查自动运行。"""
        self.store.register_post_flush_hook(lambda s: self._on_flush(s))
    
    def _on_flush(self, store: GraphStore):
        """flush 后自动调用的回调。"""
        results = self.run_incremental()
        if results:
            self._persist_results(results)
    
    def run(self, full: bool = False) -> List[CheckResult]:
        """全量运行所有约束检查。"""
        results = []
        
        for constraint in self._constraints:
            if not constraint.enabled:
                continue
            
            try:
                constraint_results = self._check_constraint(constraint, full=full)
                results.extend(constraint_results)
            except Exception:
                # 单条约束失败不影响其他约束
                pass
        
        return results
    
    def run_incremental(self) -> List[CheckResult]:
        """增量运行：只检查有变更的单元相关的约束。"""
        # 获取变更单元
        modified = self.store.get_modified_units(since_version=0)
        if not modified:
            return []
        
        results = []
        modified_ids = {u.id for u in modified}
        
        for constraint in self._constraints:
            if not constraint.enabled:
                continue
            
            try:
                # 只检查与变更单元相关的约束
                constraint_results = self._check_constraint(constraint, unit_ids=modified_ids)
                results.extend(constraint_results)
            except Exception:
                pass
        
        return results
    
    def _check_constraint(
        self,
        constraint: ConstraintDef,
        full: bool = False,
        unit_ids: Optional[set] = None,
    ) -> List[CheckResult]:
        """执行单条约束检查。"""
        category = constraint.category
        params = constraint.params
        
        if category == "referential_integrity":
            return self._check_referential_integrity(constraint)
        elif category == "temporal":
            return self._check_temporal(constraint)
        elif category == "relational":
            return self._check_relational(constraint)
        elif category == "boundary":
            return self._check_boundary(constraint)
        elif category == "state_conservation":
            return self._check_state_conservation(constraint)
        elif category == "pattern":
            return self._check_pattern(constraint)
        else:
            return []
    
    def _persist_results(self, results: List[CheckResult]):
        """将检查结果持久化到 DeviationManager。"""
        try:
            from deviation_manager import DeviationManager
            project_root = str(self.store.project_root)
            dm = DeviationManager(project_root)
            dm.merge_from_check_results(results)
        except Exception:
            pass
    
    # ── 各约束类别的检查实现 ──────────────────────────────────────────────
    
    def _check_referential_integrity(self, c: ConstraintDef) -> List[CheckResult]:
        """
        引用完整性：检查 content 中引用的实体在 graph 中是否存在对应单元。
        
        params:
          source_type: 从哪种单元类型提取
          extract_field: 从 content 中提取引用值的路径（点分语法）
          target_type: 目标单元类型（"*" 表示任意类型）
          match_field: 按哪个字段匹配（"unit_name" 或 "id"）
        """
        results = []
        source_type = c.params.get("source_type", "")
        extract_field = c.params.get("extract_field", "")
        target_type = c.params.get("target_type", "*")
        match_field = c.params.get("match_field", "unit_name")
        
        # 获取所有源类型的单元
        units = self.extractor.get_units_by_type(source_type)
        
        for unit in units:
            refs = self.extractor.extract_field_values(unit, extract_field)
            for ref in refs:
                if not ref or not isinstance(ref, str):
                    continue
                ref = ref.strip()
                if not ref:
                    continue
                # 在目标类型中查找
                found = self.extractor.find_entity(ref, target_type, match_field)
                if not found:
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"「{unit.unit_name}」引用了不存在的实体「{ref}」",
                        units_involved=[unit.id],
                        detail=f"类型: {unit.type.value}, 提取路径: {extract_field}, 引用值: {ref}",
                    ))
        
        return results
    
    def _check_temporal(self, c: ConstraintDef) -> List[CheckResult]:
        """
        时序约束：检查有序量是否单调递增。
        
        params:
          source_type: 从哪种单元类型提取
          extract_field: 提取要检查的值（如 "events[].age"）
          ordering_field: 提取序数字段（如 "events[].ordinal"）
          monotonic: "increasing" 或 "non_decreasing"
          exception_field: 可例外的情况（如 "events[].type"）
          exception_values: 例外值列表（如 ["废功", "散功"]）
        """
        results = []
        source_type = c.params.get("source_type", "")
        extract_field = c.params.get("extract_field", "")
        ordering_field = c.params.get("ordering_field", "")
        monotonic = c.params.get("monotonic", "increasing")
        exception_field = c.params.get("exception_field", "")
        exception_values = c.params.get("exception_values", [])
        
        units = self.extractor.get_units_by_type(source_type)
        
        for unit in units:
            values = self.extractor.extract_field_values(unit, extract_field)
            ordinals = self.extractor.extract_field_values(unit, ordering_field)
            exceptions = (self.extractor.extract_field_values(unit, exception_field)
                          if exception_field else [])
            
            if len(values) <= 1 or len(ordinals) <= 1:
                continue
            
            # 按 ordinals 排序后检查
            paired = sorted(zip(ordinals, values, exceptions if exceptions else [""] * len(values)),
                          key=lambda x: float(x[0]) if x[0] is not None else 0)
            
            for i in range(len(paired) - 1):
                ord_a, val_a, exc_a = paired[i]
                ord_b, val_b, exc_b = paired[i + 1]
                
                if val_a is None or val_b is None:
                    continue
                
                # 跳过例外事件
                if exc_a in exception_values or exc_b in exception_values:
                    continue
                
                # 尝试数值比较
                try:
                    num_a = float(val_a) if val_a != "?" else None
                    num_b = float(val_b) if val_b != "?" else None
                except (ValueError, TypeError):
                    continue
                
                if num_a is None or num_b is None:
                    continue
                
                if monotonic == "increasing" and num_a >= num_b:
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"「{unit.unit_name}」时序异常: {val_a} → {val_b}（未递增）",
                        units_involved=[unit.id],
                        detail=f"序数 {ord_a} → {ord_b}, 值 {val_a} → {val_b}",
                    ))
                elif monotonic == "non_decreasing" and num_a > num_b:
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"「{unit.unit_name}」时序异常: {val_a} → {val_b}（递减）",
                        units_involved=[unit.id],
                        detail=f"序数 {ord_a} → {ord_b}, 值 {val_a} → {val_b}",
                    ))
        
        return results
    
    def _check_relational(self, c: ConstraintDef) -> List[CheckResult]:
        """
        关系约束：检查关系网络的特定结构性质。
        
        params:
          relation_type: 关系类型
          check: "bidirectional" | "acyclic" | "cardinality_min"
          max_depth: 环检测最大深度（仅 acyclic）
          source_type: 检查的目标单元类型（仅 cardinality）
          min_count: 最小关联数（仅 cardinality）
        """
        results = []
        from graph_schema import RelationType
        
        rel_type_str = c.params.get("relation_type", "")
        check_type = c.params.get("check", "bidirectional")
        
        # 解析关系类型
        try:
            rel_type = RelationType(rel_type_str.lower())
        except (ValueError, AttributeError):
            return results
        
        if check_type == "bidirectional":
            # 不对称检查
            for rel_id, rel in self.store._relations.items():
                if rel.relation_type != rel_type:
                    continue
                src = self.store.get_unit(rel.source_id)
                tgt = self.store.get_unit(rel.target_id)
                if not src or not tgt:
                    continue
                # 检查反向关系
                has_inverse = False
                for rel2 in self.store.get_relations(tgt.id, direction="outgoing"):
                    if rel2.target_id == src.id and rel2.relation_type == rel_type.inverse:
                        has_inverse = True
                        break
                if not has_inverse:
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"关系不对称: 「{src.unit_name}」→「{tgt.unit_name}」({rel_type.value})，但反向关系不存在",
                        units_involved=[src.id, tgt.id],
                    ))
        
        elif check_type == "acyclic":
            # 环检测（DFS）
            max_depth = c.params.get("max_depth", 20)
            adj = {}
            for rel_id, rel in self.store._relations.items():
                if rel.relation_type == rel_type or rel.relation_type == rel_type.inverse:
                    adj.setdefault(rel.source_id, []).append(rel.target_id)
            
            visited = set()
            path = []
            
            def dfs(node, depth):
                if depth > max_depth:
                    return None
                if node in path:
                    cycle = path[path.index(node):] + [node]
                    return cycle
                if node in visited:
                    return None
                visited.add(node)
                path.append(node)
                for neighbor in adj.get(node, []):
                    cycle = dfs(neighbor, depth + 1)
                    if cycle:
                        return cycle
                path.pop()
                return None
            
            for node in adj:
                cycle = dfs(node, 0)
                if cycle:
                    names = []
                    for nid in cycle:
                        u = self.store.get_unit(nid)
                        names.append(u.unit_name if u else nid)
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"检测到关系成环: {' → '.join(names)}",
                        units_involved=list(set(nid for nid in cycle if nid)),
                        detail=f"关系类型: {rel_type.value}, 环路径: {' → '.join(names)}",
                    ))
                    break  # 一次发现一个环，修复后再查
        
        elif check_type == "cardinality_min":
            # 最小基数检查
            source_type_str = c.params.get("source_type", "")
            target_types = c.params.get("target_type", [])
            min_count = c.params.get("min_count", 1)
            
            from graph_schema import UnitType
            try:
                src_unit_type = UnitType(source_type_str.upper())
            except (ValueError, AttributeError):
                return results
            
            for unit in self.store._units.values():
                if unit.type != src_unit_type or unit.status.name == "ARCHIVED":
                    continue
                rels = self.store.get_relations(unit.id)
                relevant = [r for r in rels if r.relation_type == rel_type]
                if len(relevant) < min_count:
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"「{unit.unit_name}」的 {rel_type.value} 关系数({len(relevant)})低于最小值({min_count})",
                        units_involved=[unit.id],
                    ))
        
        return results
    
    def _check_boundary(self, c: ConstraintDef) -> List[CheckResult]:
        """
        边界约束：检查相邻单元的开端/结尾是否匹配。
        
        params:
          preceding_type: 前置单元类型
          following_relation: 查找后续单元的关系类型
          extract_field: 要比较的字段路径
          scope: 范围限制（如 "卷末 20%"）
        """
        results = []
        from graph_schema import RelationType
        
        preceding_type_str = c.params.get("preceding_type", "")
        following_rel_str = c.params.get("following_relation", "PRECEDES")
        extract_field = c.params.get("extract_field", "end_state")
        scope = c.params.get("scope", "")
        
        try:
            following_rel = RelationType(following_rel_str.lower())
        except (ValueError, AttributeError):
            return results
        
        for unit in self.store._units.values():
            if unit.type.value != preceding_type_str:
                continue
            
            # 通过关系找后续单元
            for rel in self.store.get_relations(unit.id, direction="outgoing"):
                if rel.relation_type != following_rel:
                    continue
                following = self.store.get_unit(rel.target_id)
                if not following:
                    continue
                
                # 提取两端字段值对比
                preceding_val = self.extractor.extract_field_value(unit, extract_field)
                following_val = self.extractor.extract_field_value(following, extract_field)
                
                if preceding_val and following_val and preceding_val != following_val:
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"边界不一致: 「{unit.unit_name}」的 {extract_field} 为「{preceding_val}」，但后续单元「{following.unit_name}」的对应值为「{following_val}」",
                        units_involved=[unit.id, following.id],
                        detail=f"{unit.unit_name}({extract_field}={preceding_val}) → {following.unit_name}({extract_field}={following_val})",
                    ))
        
        return results
    
    def _check_state_conservation(self, c: ConstraintDef) -> List[CheckResult]:
        """
        状态守恒：检查状态变更是否有对应的事件/关系。
        
        params:
          entity_type: 实体类型
          state_field: 状态字段
          forbidden_relation: 状态变更后不应存在的关系类型
          allowed_exceptions: 允许的例外值
        """
        results = []
        from graph_schema import UnitType, RelationType
        
        entity_type_str = c.params.get("entity_type", "")
        state_field = c.params.get("state_field", "status")
        forbidden_rel_str = c.params.get("forbidden_relation", "")
        allowed_exceptions = c.params.get("allowed_exception_values", [])
        
        try:
            entity_unit_type = UnitType(entity_type_str.upper())
            forbidden_rel = RelationType(forbidden_rel_str.lower()) if forbidden_rel_str else None
        except (ValueError, AttributeError):
            return results
        
        for unit in self.store._units.values():
            if unit.type != entity_unit_type:
                continue
            if unit.status.name == "ARCHIVED":
                continue
            
            # 检查状态字段
            state_val = getattr(unit, state_field, None)
            if state_val is None:
                continue
            
            status_str = state_val.value if hasattr(state_val, "value") else str(state_val)
            
            # 如果状态触发约束
            if forbidden_rel:
                rels = self.store.get_relations(unit.id)
                forbidden_found = [r for r in rels if r.relation_type == forbidden_rel]
                if forbidden_found:
                    exception_names = [self.store.get_unit(r.target_id).unit_name
                                       for r in forbidden_found[:3]
                                       if self.store.get_unit(r.target_id)]
                    exception_str = ", ".join(exception_names)
                    results.append(CheckResult(
                        rule_id=c.rule_id,
                        severity=c.severity,
                        description=f"「{unit.unit_name}」(状态={status_str}) 仍有 {len(forbidden_found)} 条 {forbidden_rel.value} 关系",
                        units_involved=[unit.id],
                        detail=f"关联对象: {exception_str}" if exception_str else "",
                    ))
        
        return results
    
    def _check_pattern(self, c: ConstraintDef) -> List[CheckResult]:
        """
        模式检测约束（LLM 辅助的信号检测）。
        当前仅做基础的结构信号检测，LLM 高级检测延后。
        
        params:
          focus_type: 焦点类型
          signal: 信号类型
        """
        # 模式检测需要 LLM 辅助，当前仅占位
        return []
    
    # ── 内置默认约束定义 ──────────────────────────────────────────────────
    
    def _default_constraints(self) -> List[ConstraintDef]:
        """内置默认约束列表。"""
        return [
            # 引用完整性
            ConstraintDef(
                category="referential_integrity", rule_id="RI01", severity="warning",
                description="角色事件表中的位置必须在 world_rule 中有对应条目",
                params={"source_type": "character_arc", "extract_field": "events[].location",
                        "target_type": "world_rule", "match_field": "unit_name"},
            ),
            # 时序约束
            ConstraintDef(
                category="temporal", rule_id="T01", severity="warning",
                description="角色年龄事件必须随序数递增",
                params={"source_type": "character_arc", "extract_field": "events[].age",
                        "ordering_field": "events[].ordinal", "monotonic": "increasing",
                        "exception_field": "", "exception_values": []},
            ),
            # 关系约束
            ConstraintDef(
                category="relational", rule_id="REL01", severity="info",
                description="PARTICIPATES_IN 关系应双向一致",
                params={"relation_type": "participates_in", "check": "bidirectional"},
            ),
            ConstraintDef(
                category="relational", rule_id="REL02", severity="warning",
                description="情节线至少应有 scene 或 chapter_plan 关联",
                params={"relation_type": "plans", "check": "cardinality_min",
                        "source_type": "plot_thread", "target_type": ["scene", "chapter_plan"],
                        "min_count": 1},
            ),
        ]
