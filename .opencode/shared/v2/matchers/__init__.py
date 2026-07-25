"""
模式匹配器注册表。

每个 PatternMatcher 对应一个约束类别，由 ConstraintEngine 按需加载。
"""

from .temporal import TemporalMatcher
from .ref_integrity import RefIntegrityMatcher
from .cardinality import CardinalityMatcher
from .boundary import BoundaryMatcher
from .state_conservation import StateConservationMatcher
from .pattern import PatternMatcher

# 类别 → 匹配器实例的映射
MATCHERS = {
    "temporal": TemporalMatcher(),
    "referential_integrity": RefIntegrityMatcher(),
    "cardinality": CardinalityMatcher(),
    "boundary": BoundaryMatcher(),
    "state_conservation": StateConservationMatcher(),
    "pattern": PatternMatcher(),
}

__all__ = ["MATCHERS", "TemporalMatcher", "RefIntegrityMatcher",
           "CardinalityMatcher", "BoundaryMatcher",
           "StateConservationMatcher", "PatternMatcher"]
