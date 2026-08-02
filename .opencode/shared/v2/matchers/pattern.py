"""
图模式匹配器 — 在 edges 上做多步路径模式匹配。

支持三种检测模式：
  traverse  多步线性路径遍历 + 端点条件检查
  intersect 分路交汇检测（如"仇敌是否同场景"）
  cycle     单边 BFS 环路检测

使用方式：
  在 YAML 约束中声明 params.match，PatternMatcher 自动执行。
  不限制单元类型——任何配置了 pattern 约束的类型都能检测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit, RelationType

from .base import BaseMatcher, CheckResult


# ── 数据类 ────────────────────────────────────────────────────────


@dataclass
class TraverseStep:
    """遍历单步定义"""
    edge_type: str
    direction: str = "outgoing"  # outgoing | incoming | both
    label_filter: Optional[str] = None


@dataclass
class TraverseResult:
    """多步遍历结果"""
    endpoints: Set[str] = field(default_factory=set)       # 最终抵达的节点
    all_reached: Set[str] = field(default_factory=set)      # 所有到达过的节点
    paths: List[List[str]] = field(default_factory=list)    # 完整路径记录
    cycled: bool = False                                    # 是否检测到环路


# ── 匹配器 ────────────────────────────────────────────────────────


class PatternMatcher(BaseMatcher):
    """图模式匹配器。"""

    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        match = constraint.params.get("match", {})
        if not match:
            return None

        mode = match.get("mode", "traverse")

        try:
            if mode == "cycle":
                return self._check_cycle(match, constraint, unit, store)
            elif mode == "intersect":
                return self._check_intersect(match, constraint, unit, store)
            else:  # traverse
                return self._check_traverse(match, constraint, unit, store)
        except Exception:
            # 单条 pattern 失败不影响其他约束
            return None

    # ── 遍历引擎 ──────────────────────────────────────────────────

    def _parse_steps(self, data: Any) -> List[TraverseStep]:
        """从 YAML match 结构解析遍历步骤列表。"""
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            # 兼容单步简写：直接用 edge_type/direction/label_filter
            if "edge_type" in data:
                raw_list = [data]
            else:
                raw_list = data.get("steps", [])
        else:
            return []

        steps: List[TraverseStep] = []
        for s in raw_list:
            if not isinstance(s, dict):
                continue
            et = s.get("edge_type", "")
            if not et:
                continue
            steps.append(TraverseStep(
                edge_type=et,
                direction=s.get("direction", "outgoing"),
                label_filter=s.get("label_filter"),
            ))
        return steps

    def _traverse(
        self,
        store: GraphStore,
        start_id: str,
        steps: List[TraverseStep],
        max_depth: int = 5,
    ) -> TraverseResult:
        """
        多步异边路径遍历。

        按 steps 顺序依次扩展 frontier（steps 中的每一步 = 一跳）：
          hop 0: {start} → 按 step[0] 边类型/方向/label 过滤 → frontier[1]
          hop 1: frontier[1] → step[1] → frontier[2]
        总跳数受 max_depth 限制（取 min(max_depth, len(steps))）。
        返回最终 frontier 及路径记录。
        """
        if max_depth < 1:
            max_depth = 1

        # frontier: {node_id: path_from_start}
        frontier: Dict[str, List[str]] = {start_id: [start_id]}
        result = TraverseResult()

        for step_idx in range(min(max_depth, len(steps))):
            step = steps[step_idx]
            try:
                rel_type = RelationType(step.edge_type.lower())
            except (ValueError, AttributeError):
                return result

            next_frontier: Dict[str, List[str]] = {}

            for node_id, path in frontier.items():
                for rel in store.get_relations(node_id, direction=step.direction):
                    if rel.relation_type != rel_type:
                        continue
                    if step.label_filter and rel.label != step.label_filter:
                        continue

                    # 确定邻居 ID
                    if step.direction == "incoming":
                        neighbor = rel.source_id
                    elif step.direction == "outgoing":
                        neighbor = rel.target_id
                    else:  # both
                        neighbor = rel.source_id if rel.source_id != node_id else rel.target_id

                    if neighbor == start_id:
                        # 回到起点 → 环路（记录完整环路路径）
                        result.cycled = True
                        result.paths.append(path + [start_id])
                        continue

                    if neighbor not in path:
                        new_path = path + [neighbor]
                        next_frontier[neighbor] = new_path
                        result.paths.append(new_path)

            frontier = next_frontier
            if not frontier:
                break

        result.endpoints = set(frontier.keys())
        result.all_reached = {
            node for path in result.paths for node in path
        } | {start_id}
        return result

    def _traverse_from_many(
        self,
        store: GraphStore,
        start_ids: Set[str],
        steps: List[TraverseStep],
        max_depth: int = 5,
    ) -> TraverseResult:
        """从多个起点合并执行多步遍历。"""
        combined = TraverseResult()
        for sid in start_ids:
            partial = self._traverse(store, sid, steps, max_depth)
            combined.endpoints.update(partial.endpoints)
            combined.all_reached.update(partial.all_reached)
            combined.paths.extend(partial.paths)
            if partial.cycled:
                combined.cycled = True
        return combined

    # ── 模式: traverse（线性路径遍历）──────────────────────────────

    def _check_traverse(
        self,
        match: dict,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        store: GraphStore,
    ) -> Optional[CheckResult]:
        """线性多步路径遍历 + 端点条件检查。"""
        steps = self._parse_steps(match)
        if not steps:
            return None

        max_depth = match.get("max_depth", 5)
        result = self._traverse(store, unit.id, steps, max_depth)

        expect = match.get("expect", "at_least_one")
        check_value = match.get("check_value", 1)
        found = len(result.endpoints)

        passed = False
        if expect == "none":
            passed = found == 0
        elif expect == "at_least_one":
            passed = found >= check_value
        elif expect == "exactly":
            passed = found == check_value

        if passed:
            return None

        return CheckResult(
            rule_id=constraint.rule_id,
            severity=constraint.severity,
            description=(
                f"「{unit.unit_name}」{constraint.description}: "
                f"期望 {expect} {check_value}，实际找到 {found} 个"
            ),
            units_involved=[unit.id] + sorted(result.endpoints)[:10],
            detail=(
                f"路径: {' → '.join(s.edge_type for s in steps)}, "
                f"终点: {', '.join(sorted(result.endpoints)[:5]) or '无'}"
            ),
        )

    # ── 模式: cycle（环路检测）────────────────────────────────────

    def _check_cycle(
        self,
        match: dict,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        store: GraphStore,
    ) -> Optional[CheckResult]:
        """
        环路检测。

        YAML:
          params:
            match:
              mode: cycle
              edge_type: controls
              direction: outgoing
              max_depth: 10

        从起点沿指定边类型遍历，如果在 max_depth 内回到起点 → 环路。
        """
        edge_type = match.get("edge_type", "")
        if not edge_type:
            return None
        direction = match.get("direction", "outgoing")
        try:
            max_depth = int(match.get("max_depth", 10))
        except (TypeError, ValueError):
            max_depth = 10
        if max_depth < 1:
            max_depth = 1

        try:
            rel_type = RelationType(edge_type.lower())
        except (ValueError, AttributeError):
            return None

        start_id = unit.id
        # 沿同一边类型重复扩展，最多 max_depth 跳；
        # visited 只阻止"回到本路径内已访问节点"的再扩展，防止指数爆炸，
        # 但仍允许不同路径间的节点复用，从而能发现 A→B→A 这类多节点环路。
        frontier: Dict[str, List[str]] = {start_id: [start_id]}
        visited: Set[str] = set()
        cycle_paths: List[List[str]] = []

        for _ in range(max_depth):
            next_frontier: Dict[str, List[str]] = {}
            for node_id, path in frontier.items():
                if node_id in visited:
                    continue
                visited.add(node_id)

                for rel in store.get_relations(node_id, direction=direction):
                    if rel.relation_type != rel_type:
                        continue

                    # 确定邻居 ID
                    if direction == "incoming":
                        neighbor = rel.source_id
                    elif direction == "outgoing":
                        neighbor = rel.target_id
                    else:  # both
                        neighbor = rel.source_id if rel.source_id != node_id else rel.target_id

                    if neighbor == start_id:
                        # 回到起点 → 环路
                        cycle_paths.append(path + [start_id])
                        continue
                    if neighbor not in path:
                        next_frontier[neighbor] = path + [neighbor]

            frontier = next_frontier
            if not frontier:
                break

        if not cycle_paths:
            return None

        # 找到具体环路路径
        detail_parts = []
        for p in cycle_paths[:3]:
            names = []
            for nid in p:
                u = store.get_unit(nid)
                names.append(u.unit_name if u else nid[:8])
            detail_parts.append(" → ".join(names))

        return CheckResult(
            rule_id=constraint.rule_id,
            severity=constraint.severity,
            description=(
                f"「{unit.unit_name}」{constraint.description}: "
                f"检测到 {edge_type} 环路"
            ),
            units_involved=[unit.id],
            detail="; ".join(detail_parts),
        )

    # ── 模式: intersect（分路交汇检测）────────────────────────────

    def _check_intersect(
        self,
        match: dict,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        store: GraphStore,
    ) -> Optional[CheckResult]:
        """
        分路交汇检测。

        核心用例：角色 A 的仇敌 B 与 A 从未在同场景中出现。

        YAML:
          params:
            match:
              mode: intersect
              from_start:        # 从 A 出发沿此路径 → 获取"直接可达集"
                edge_type: participates_in
                direction: incoming
              via_relation:      # 从 A 经此路径到中间节点，再经 then 到"间接可达集"
                edge_type: relates_to
                direction: outgoing
                label_filter: 仇敌
                then:
                  edge_type: participates_in
                  direction: incoming
              check: shared_none    # direct ∩ indirect 应为空

        check 可选值:
          shared_none:     直接可达集 ∩ 间接可达集 应为空（如仇敌从未同场景）
          shared_at_least: 直接可达集 ∩ 间接可达集 应至少有一个交集
        """
        from_start_cfg = match.get("from_start")
        via_relation_cfg = match.get("via_relation")
        if not from_start_cfg or not via_relation_cfg:
            return None

        check = match.get("check", "shared_none")

        # 1. 从起点走 from_start 路径 → 直接可达集
        start_steps = self._parse_steps(from_start_cfg)
        if not start_steps:
            return None
        direct = self._traverse(store, unit.id, start_steps)
        direct_set = direct.endpoints | {unit.id}

        # 2. 从起点走 via_relation → 中间节点集
        via_steps = self._parse_steps(via_relation_cfg)
        if not via_steps:
            return None
        intermediate = self._traverse(store, unit.id, via_steps)
        intermediate_set = intermediate.endpoints

        if not intermediate_set:
            # 没有中间节点（如角色没有仇敌），模式不存在 → 通过
            return None

        # 3. 从中间节点走 then → 间接可达集
        then_cfg = via_relation_cfg.get("then") if isinstance(via_relation_cfg, dict) else None
        if not then_cfg:
            return None
        then_steps = self._parse_steps(then_cfg)
        if not then_steps:
            return None
        indirect = self._traverse_from_many(store, intermediate_set, then_steps)
        indirect_set = indirect.endpoints

        # 4. 检查交集
        shared = direct_set & indirect_set
        shared_count = len(shared)

        if check == "shared_none" and shared_count == 0:
            units_involved = [unit.id] + sorted(intermediate_set)[:5] + sorted(indirect_set)[:3]
            shared_detail = (
                f"经 {via_steps[0].edge_type} 找到 {len(intermediate_set)} 个中间节点"
            )
            if then_steps:
                shared_detail += (
                    f"，再经 {then_steps[0].edge_type} 到 {len(indirect_set)} 个节点"
                )
            shared_detail += f"，与起点直接可达集({len(direct_set)})无交集"
            return CheckResult(
                rule_id=constraint.rule_id,
                severity=constraint.severity,
                description=f"「{unit.unit_name}」{constraint.description}",
                units_involved=units_involved,
                detail=shared_detail,
            )

        if check == "shared_at_least" and shared_count == 0:
            return CheckResult(
                rule_id=constraint.rule_id,
                severity=constraint.severity,
                description=(
                    f"「{unit.unit_name}」{constraint.description}: "
                    f"期望有共享节点，但直接可达集与间接可达集无交集"
                ),
                units_involved=[unit.id] + sorted(indirect_set)[:5],
                detail=(
                    f"经 {via_steps[0].edge_type} 到 {len(intermediate_set)} 个中间节点，"
                    f"再经 {then_steps[0].edge_type} 到 {len(indirect_set)} 个节点，"
                    f"均与起点直接可达集({len(direct_set)})无交集"
                ),
            )

        return None  # 符合预期 → 通过
