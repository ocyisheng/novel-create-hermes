"""统一质量检查数据类型。

定义 quality checkers 各模块共享的 dataclass 和枚举。
不修改现有 matchers/base.py 或 search_engine.py 中的 CheckResult，
仅提供向后兼容的超集定义。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class CheckSource(str, Enum):
    """检查来源：标识结果由哪层产出。"""

    MECHANICAL = "mechanical"  # 约束引擎 / matchers
    STATISTICAL = "statistical"  # 统计分析
    SEMANTIC = "semantic"  # 语义分析（LLM）


class CheckLayer(str, Enum):
    """检查层级：结构 / 统计 / 语义。"""

    STRUCTURE = "structure"
    STATISTICS = "statistics"
    SEMANTICS = "semantics"


@dataclass
class CheckResult:
    """统一约束检查结果（matchers/base.py 和 search_engine.py 的超集）。"""

    rule_id: str
    rule_name: str  # 新增字段，matchers/base.py 原本缺少
    severity: str  # "error" | "warning" | "info"
    description: str
    units_involved: List[str]
    detail: str = ""
    source: CheckSource = CheckSource.MECHANICAL
    check_layer: CheckLayer = CheckLayer.STRUCTURE


@dataclass
class SignalResult:
    """统计 / 模式信号检测结果。"""

    rule_id: str
    rule_name: str
    signal_type: str  # 如 "repetition", "pace_drop", "length_outlier"
    signal_data: Dict[str, Any] = field(default_factory=dict)
    units_involved: List[str] = field(default_factory=list)
    raw_value: float = 0.0
    threshold: float = 0.0


@dataclass
class QualityReport:
    """汇总一次质量检测的全部产出。"""

    mechanical_results: List[CheckResult] = field(default_factory=list)
    statistical_signals: List[SignalResult] = field(default_factory=list)
    deviations_created: int = 0
    timestamp: str = ""
