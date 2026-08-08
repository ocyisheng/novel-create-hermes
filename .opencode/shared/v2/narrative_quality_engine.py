"""
NarrativeQualityEngine — 统一质量检查入口。

编排三层检查：
- Layer 1: MechanicalChecker（机械检查）
- Layer 2: StatisticalDetector（信号收集）
- Layer 3: LLM 分析（由 skill 层完成，不在这里）

用法：
    engine = NarrativeQualityEngine(store)
    report = engine.run()                    # 全量检查
    report = engine.run(layers=["mechanical"]) # 仅机械检查
    report = engine.run_incremental()         # 增量检查（未来扩展）
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from graph_store import GraphStore
from quality_checkers.mechanical import MechanicalChecker
from quality_checkers.statistical import StatisticalDetector
from quality_checkers.types import QualityReport

logger = logging.getLogger(__name__)

# 默认运行的检查层
_DEFAULT_LAYERS: List[str] = ["mechanical", "statistical"]


class NarrativeQualityEngine:
    """
    统一质量检查入口。

    编排三层检查：
    - Layer 1: MechanicalChecker（机械检查）
    - Layer 2: StatisticalDetector（信号收集）
    - Layer 3: LLM 分析（由 skill 层完成，不在这里）
    """

    def __init__(
        self,
        store: GraphStore,
        registry: Optional[Any] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.store = store
        self._mechanical = MechanicalChecker(store, registry)
        self._statistical = StatisticalDetector(store, thresholds)

    def run(self, layers: Optional[List[str]] = None) -> QualityReport:
        """
        运行质量检查。

        Args:
            layers: 要运行的层，默认 ["mechanical", "statistical"]
                    只运行机械检查: ["mechanical"]
                    运行前两层: ["mechanical", "statistical"]

        Returns:
            QualityReport 包含机械结果和统计信号
        """
        if layers is None:
            layers = list(_DEFAULT_LAYERS)

        report = QualityReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if "mechanical" in layers:
            logger.info("Running mechanical checks...")
            report.mechanical_results = self._mechanical.check_all()
            logger.info(
                "Mechanical checks done: %d results", len(report.mechanical_results)
            )

        if "statistical" in layers:
            logger.info("Running statistical detection...")
            report.statistical_signals = self._statistical.detect_all()
            logger.info(
                "Statistical detection done: %d signals",
                len(report.statistical_signals),
            )

        return report

    def run_incremental(self) -> QualityReport:
        """
        增量运行（只检查修改过的单元）。

        当前实现调用全量 run()，未来可扩展为只检查
        version > since_version 的单元。
        """
        return self.run()
