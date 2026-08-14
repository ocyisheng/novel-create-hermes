"""
模式匹配器基类和公共类型。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from type_registry import ConstraintDef
from graph_store import GraphStore
from graph_schema import NarrativeUnit

# CheckResult 的规范定义在 quality_checkers.types（超集，含 source/check_layer）。
# 此处 re-export 以保持向后兼容：from matchers.base import CheckResult
from quality_checkers.types import CheckResult


class BaseMatcher(ABC):
    """模式匹配器基类。"""

    @abstractmethod
    def check(
        self,
        constraint: ConstraintDef,
        unit: NarrativeUnit,
        facts: Dict[str, List[Any]],
        store: GraphStore,
        registry: Any = None,
    ) -> Optional[CheckResult]:
        """
        执行单条约束检查。

        参数：
          constraint: 约束定义
          unit: 被检查的叙事单元
          facts: 按 fact_fields 提取的结构化事实 dict
          store: GraphStore 实例
          registry: TypeRegistry 实例（可选，用于类型查询）

        返回：
          None = 通过（无问题）
          CheckResult = 发现问题
        """
        ...
