"""
图模式匹配器 — 在 edges 上做路径模式匹配（扩展预留）。

当前为占位实现，未来支持 Cypher-like 查询：
  MATCH (a)-[:ALLIED_WITH]->(b) WHERE a.unit_name = "林渊" RETURN b
"""

from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit

from .base import BaseMatcher, CheckResult


class PatternMatcher(BaseMatcher):
    """图模式匹配器（预留）。"""

    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        """
        图模式检测。

        当前为基础占位，仅返回 None。
        未来实现：
          params.match.traverse 定义 edge 遍历路径 → 在 edges 上递归搜索。
        """
        # TODO: 实现图模式匹配逻辑
        # params = constraint.params
        # if "match" in params:
        #     traversals = params["match"].get("traverse", [])
        #     for t in traversals:
        #         edge_type = t.get("edge_type", "")
        #         depth = t.get("depth", 1)
        #         results = self._traverse_graph(store, unit.id, edge_type, depth)
        #         ...
        return None

    def _traverse_graph(
        self,
        store: GraphStore,
        start_id: str,
        edge_type: str,
        max_depth: int,
    ) -> List[str]:
        """
        在 graph 上按边类型遍历（预留）。
        """
        from graph_schema import RelationType
        try:
            rel_type = RelationType(edge_type.lower())
        except (ValueError, AttributeError):
            return []

        visited = {start_id}
        frontier = {start_id}
        depth = 0
        results = []

        while frontier and depth < max_depth:
            next_frontier = set()
            for node_id in frontier:
                for rel in store.get_relations(node_id, direction="outgoing"):
                    if rel.relation_type != rel_type:
                        continue
                    if rel.target_id not in visited:
                        visited.add(rel.target_id)
                        next_frontier.add(rel.target_id)
                        results.append(rel.target_id)
            frontier = next_frontier
            depth += 1

        return results
