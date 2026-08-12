"""
DeviationManager — LLM 跨 session 分析的状态存储。

定位：LLM 的持久化 notepad，用于在 align/cross-ref/full-diagnose
分析模式下追踪偏差状态的变更历史。

与 V2 设计哲学：
- 不依赖 events.olog 做增量判断，而是使用 unit.version 对比
- 数据以 YAML 文件形式存储在 graph/deviation_state.yaml
- 纯数据操作，不做任何 LLM 推理

职责边界：
  ✅ merge(new_items) → 合并新偏差（去重）
  ✅ filter_for_presentation() → 获取待展示列表
  ✅ resolve(id) / retain(id) → 状态管理
  ❌ "判断这是否真的是矛盾"
  ❌ "分析这个偏差的严重程度"
"""

from __future__ import annotations

import logging
import os
import re
import copy
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any

import yaml

from graph_store import _normalize_project_root

logger = logging.getLogger(__name__)

class DeviationSource(str, Enum):
    """偏差来源枚举"""
    MECHANICAL = "mechanical"           # 机械检查
    STATISTICAL_LLM = "statistical_llm" # 统计+LLM裁决
    SEMANTIC_LLM = "semantic_llm"       # 语义分析+LLM
    LEGACY = "legacy"                   # 旧格式兼容


# ── 数据类 ──────────────────────────────────────────────────────────────────


@dataclass
class DeviationItem:
    """单条偏差记录"""
    id: str
    dimension: str           # "character_trait" | "plot_consistency" | "world_rule" | ...
    entity: str              # 实体名称（如"林昭"）
    entity_id: str = ""      # 实体单元 ID（可选）
    scanned_version: int = 0 # 分析时的单元版本
    status: str = "pending"  # "pending" | "resolved" | "retained"
    severity: str = "info"   # "error" | "warning" | "info"
    first_detected: str = "" # ISO 时间戳
    last_detected: str = ""
    detection_count: int = 1
    summary: str = ""
    detail: str = ""
    suggested_changeset: Optional[Dict[str, Any]] = None
    source: str = "llm_analysis"  # 来源："llm_analysis" | "constraint_RI" | "constraint_T" | "graph_check" | "legacy"


@dataclass
class ScanState:
    """增量分析版本跟踪"""
    full_scan_version: int = 0
    last_scan_at: str = ""
    constraint_watermark: int = 0  # 约束引擎增量水位：已检查过的最大 unit.version
    constraint_checked: Dict[str, int] = field(default_factory=dict)  # {unit_id: 已检查版本}


@dataclass
class DeviationState:
    """完整的偏差状态文件"""
    format_version: str = "1.0"
    scan: ScanState = field(default_factory=ScanState)
    deviations: Dict[str, DeviationItem] = field(default_factory=dict)


# ── 管理器 ──────────────────────────────────────────────────────────────────


class DeviationManager:
    """
    偏差状态管理器。
    
    管理 graph/deviation_state.yaml 的读写和偏差数据的增删改。
    每个 V2 项目一个实例。
    """

    def __init__(self, project_root: str):
        self.project_root = str(_normalize_project_root(project_root))
        self.state_path = os.path.join(self.project_root, "graph", "deviation_state.yaml")
        self._state = DeviationState()
        self._load()

    # ── 持久化 ─────────────────────────────────────────────────────────

    def _load(self):
        """从 YAML 文件加载偏差状态"""
        if not os.path.exists(self.state_path):
            self._state = DeviationState()
            return
        
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            if not data:
                self._state = DeviationState()
                return
            
            self._state.format_version = data.get("format_version", "1.0")
            
            # 解析 scan 状态
            scan_data = data.get("scan", {})
            self._state.scan = ScanState(
                full_scan_version=scan_data.get("full_scan_version", 0),
                last_scan_at=scan_data.get("last_scan_at", ""),
                constraint_watermark=scan_data.get("constraint_watermark", 0),
                constraint_checked=dict(scan_data.get("constraint_checked", {})),
            )
            
            # 解析 deviations
            self._state.deviations = {}
            for d in data.get("deviations", []):
                item = DeviationItem(
                    id=d["id"],
                    dimension=d.get("dimension", "unknown"),
                    entity=d.get("entity", ""),
                    entity_id=d.get("entity_id", ""),
                    scanned_version=d.get("scanned_version", 0),
                    status=d.get("status", "pending"),
                    severity=d.get("severity", "info"),
                    first_detected=d.get("first_detected", ""),
                    last_detected=d.get("last_detected", ""),
                    detection_count=d.get("detection_count", 1),
                    summary=d.get("summary", ""),
                    detail=d.get("detail", ""),
                    suggested_changeset=d.get("suggested_changeset"),
                    source=d.get("source", "llm_analysis"),
                )
                self._state.deviations[item.id] = item
        except Exception as e:
            # 损坏的 YAML 无法恢复——先将损坏文件备份（防止数据永久丢失），
            # 再重置为空状态并明确告警。
            self._backup_corrupt_state_file()
            logger.warning(
                "偏差状态文件损坏，已备份到 .corrupt-<timestamp> 并重置为空状态: %s", e
            )
            self._state = DeviationState()

    def save(self):
        """将偏差状态原子写入 YAML 文件（tmp + fsync + os.replace）。

        保留 scanned_version 与 constraint_watermark，保证 save/load 往返不丢字段。
        """
        deviations_list = []
        for item in self._state.deviations.values():
            d = asdict(item)
            # 保留 scanned_version（不再丢弃——它是增量分析的关键元数据）
            deviations_list.append(d)

        data = {
            "format_version": self._state.format_version,
            "scan": {
                "full_scan_version": self._state.scan.full_scan_version,
                "last_scan_at": self._state.scan.last_scan_at,
                "constraint_watermark": self._state.scan.constraint_watermark,
                "constraint_checked": self._state.scan.constraint_checked,
            },
            "deviations": deviations_list,
        }

        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        # 原子写入：唯一 tmp 名 + fsync + os.replace，防止半写文件
        tmp_path = (
            f"{self.state_path}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
        )
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.state_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    def _backup_corrupt_state_file(self) -> None:
        """将损坏的偏差状态文件备份为 .corrupt-<timestamp>。

        仅在原文件存在时备份；备份失败不阻塞重置流程（记 warning）。
        """
        if not os.path.exists(self.state_path):
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_path = f"{self.state_path}.corrupt-{timestamp}"
        try:
            os.replace(self.state_path, backup_path)
            logger.warning("已备份损坏的偏差状态文件到: %s", backup_path)
        except OSError as e:
            logger.warning("备份损坏的偏差状态文件失败: %s", e)

    # ── 扫描状态管理 ──────────────────────────────────────────────────

    @property
    def full_scan_version(self) -> int:
        return self._state.scan.full_scan_version

    @full_scan_version.setter
    def full_scan_version(self, version: int):
        self._state.scan.full_scan_version = version
        self._state.scan.last_scan_at = datetime.now(timezone.utc).isoformat()

    @property
    def constraint_watermark(self) -> int:
        """约束引擎增量检查水位：已检查过的最大 unit.version。"""
        return self._state.scan.constraint_watermark

    @constraint_watermark.setter
    def constraint_watermark(self, version: int):
        self._state.scan.constraint_watermark = int(version)

    @property
    def constraint_checked(self) -> Dict[str, int]:
        """约束引擎已检查版本表：{unit_id: 已检查的 unit.version}。

        用于增量判定：unit.version > 表中记录的版本才需要重新检查。
        新单元（version=1，未记录）必然触发检查。
        """
        return self._state.scan.constraint_checked

    # ── 偏差操作 ───────────────────────────────────────────────────────

    def merge(self, new_items: List[DeviationItem]):
        """
        合并新偏差列表到状态中。
        
        合并规则：
        1. 新偏差（相同 dimension + entity 不存在于已有状态）→ 添加
        2. 已有偏差（相同 dimension + entity）→ 递增 detection_count，更新 last_detected
        3. resolved/retained 偏差再次检出 → 仅更新时序记录，不重置状态
        """
        now = datetime.now(timezone.utc).isoformat()

        for new_item in new_items:
            # 检查是否已存在（按 dimension + entity 匹配）
            existing = self._find_existing(new_item.dimension, new_item.entity, new_item.entity_id)
            
            if existing is None:
                # 全新偏差
                if not new_item.id:
                    new_item.id = self._generate_id()
                if not new_item.first_detected:
                    new_item.first_detected = now
                new_item.last_detected = now
                new_item.detection_count = 1
                self._state.deviations[new_item.id] = new_item
            else:
                # 已有偏差，更新
                existing.detection_count += 1
                existing.last_detected = now
                existing.scanned_version = new_item.scanned_version
                
                # 已解决/保留的偏差不再自动重置为 pending
                # 用户已做出明确判断（fixed / by-design），应尊重其决定
                # 仅更新检测计数和时间戳作为记录
                
                # 更新 summary/detail（取最新的）
                if new_item.summary:
                    existing.summary = new_item.summary
                if new_item.detail:
                    existing.detail = new_item.detail

    def resolve(self, deviation_id: str) -> bool:
        """标记偏差为已解决（用户/LLM 确认已修复）"""
        item = self._state.deviations.get(deviation_id)
        if not item:
            return False
        item.status = "resolved"
        return True

    def retain(self, deviation_id: str) -> bool:
        """标记偏差为已保留（用户确认是正常设计，不是问题）"""
        item = self._state.deviations.get(deviation_id)
        if not item:
            return False
        item.status = "retained"
        return True

    def delete(self, deviation_id: str) -> bool:
        """删除一条偏差记录"""
        if deviation_id in self._state.deviations:
            del self._state.deviations[deviation_id]
            return True
        return False

    def get(self, deviation_id: str) -> Optional[DeviationItem]:
        """获取指定偏差"""
        return self._state.deviations.get(deviation_id)

    def list_all(self) -> List[DeviationItem]:
        """列出所有偏差"""
        return list(self._state.deviations.values())

    def filter_for_presentation(self) -> List[DeviationItem]:
        """
        获取待展示的偏差列表。

        过滤规则：
        - status=pending → 展示
        - status=resolved → 跳过
        - status=retained → 跳过
        - 相同维度出现 ≥ 3 条 pending 的 → 折叠为一条聚合条目（摘要中标注条数），
          让 LLM 决定是否需要进一步折叠/分组，避免列表被同一维度刷屏。
        """
        pending = [
            item for item in self._state.deviations.values()
            if item.status == "pending"
        ]
        return self._collapse_same_dimension(pending)

    def _collapse_same_dimension(self, items: List[DeviationItem]) -> List[DeviationItem]:
        """将同一维度 ≥3 条 pending 偏差折叠为一条聚合条目。

        聚合条目保留维度、最高 severity、条数与实体列表；detail 中列出全部实体。
        少于 3 条的维度原样透传。
        """
        by_dimension: Dict[str, List[DeviationItem]] = {}
        for item in items:
            by_dimension.setdefault(item.dimension, []).append(item)

        result: List[DeviationItem] = []
        for dimension, group in by_dimension.items():
            if len(group) < 3:
                result.extend(group)
                continue
            group_sorted = sorted(
                group, key=lambda it: ("error", "warning", "info").index(it.severity)
                if it.severity in ("error", "warning", "info") else 99
            )
            entities = [g.entity or "?" for g in group][:8]
            entity_str = "、".join(entities)
            if len(group) > 8:
                entity_str += f" 等共 {len(group)} 条"
            collapsed = DeviationItem(
                id=f"{dimension}:collapse",
                dimension=dimension,
                entity=entity_str,
                status="pending",
                severity=group_sorted[0].severity,
                first_detected=min((g.first_detected for g in group if g.first_detected), default=""),
                last_detected=max((g.last_detected for g in group if g.last_detected), default=""),
                detection_count=sum(g.detection_count for g in group),
                summary=f"「{dimension}」维度共有 {len(group)} 条待处理偏差（已折叠），需 LLM 判断是否合并处理",
                detail="\n".join(
                    f"- [{g.severity}] {g.entity}：{g.summary}"
                    for g in group[:10]
                ),
            )
            result.append(collapsed)
        return result

    # ── 统计 ───────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """偏差统计"""
        total = len(self._state.deviations)
        by_status = {}
        by_severity = {}
        by_dimension = {}
        
        for item in self._state.deviations.values():
            by_status[item.status] = by_status.get(item.status, 0) + 1
            by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
            by_dimension[item.dimension] = by_dimension.get(item.dimension, 0) + 1
        
        return {
            "total": total,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_dimension": by_dimension,
            "full_scan_version": self._state.scan.full_scan_version,
        }

    def merge_from_check_results(self, results: list, full_scan: bool = False) -> Dict[str, int]:
        """
        将约束引擎/一致性检查结果合并到偏差状态中。
        
        接收 CheckResult dataclass 或兼容的 dict 列表。
        full_scan: True 表示本次检查覆盖全部单元（全量扫描）。此时本次
                  未再报出的 pending 偏差视为已修复，自动标记 resolved
                  并计入 stats["resolved"]；增量检查（full_scan=False）
                  不做自动解决，避免子集扫描误判。
        返回: {"new": N, "resolved": M, "updated": K}
        """
        from dataclasses import dataclass
        now = datetime.now(timezone.utc).isoformat()
        stats = {"new": 0, "resolved": 0, "updated": 0}
        seen_keys: Set[str] = set()
        
        # rule_id → source 映射表（按最长前缀优先匹配）
        SOURCE_RULES = [
            ("payload_schema_",  "constraint_payload_schema"),
            ("has_",             "constraint_cardinality"),
            ("archived_",        "constraint_state"),
            ("location_exists",  "constraint_ref_integrity"),
            ("age_",             "constraint_temporal"),
            ("realm_",           "constraint_temporal"),
        ]
        # 已知 payload 约束 rule_id 前缀（没有数字后缀）
        PAYLOAD_RULE_PREFIXES = frozenset({
            "entry_state_", "acquired_", "join_", "allied_", "since_",
            "upgrade_", "plans_",
        })
        
        def _derive_source(rid: str, result: Any = None) -> str:
            # 优先使用 CheckResult 对象的 source 字段
            if result is not None:
                src = getattr(result, "source", None)
                if src is not None:
                    # CheckSource 枚举 → DeviationSource 映射
                    _MAP = {
                        "mechanical": DeviationSource.MECHANICAL,
                        "statistical": DeviationSource.STATISTICAL_LLM,
                        "semantic": DeviationSource.SEMANTIC_LLM,
                    }
                    val = src.value if hasattr(src, "value") else str(src)
                    mapped = _MAP.get(val)
                    if mapped:
                        return mapped.value
            # fallback: 基于 rule_id 前缀的旧逻辑
            for prefix, source in SOURCE_RULES:
                if rid.startswith(prefix):
                    return source
            # 检查是否是 payload 约束
            for p in PAYLOAD_RULE_PREFIXES:
                if rid.startswith(p):
                    return "constraint_payload"
            # 旧风格 rule_id（如 "T01" → "constraint_T"）
            stripped = rid.rstrip("0123456789")
            if stripped != rid:
                return f"constraint_{stripped}"
            return "graph_check"
        
        def _extract_entity(desc: str) -> str:
            """从描述中提取「」内的实体名称。"""
            m = re.search(r'「(.+?)」', desc)
            return m.group(1) if m else desc[:80]
        
        for result in results:
            # 兼容 CheckResult dataclass 和 dict 两种输入
            if isinstance(result, dict):
                rule_id = result.get("rule_id", "UNKNOWN")
                severity = result.get("severity", "info")
                description = result.get("description", "")
                units_involved = result.get("units_involved", [])
                detail = result.get("detail", "")
            else:
                rule_id = result.rule_id
                severity = result.severity
                description = result.description
                units_involved = result.units_involved
                detail = getattr(result, "detail", "")
            
            source = _derive_source(rule_id, result)
            entity = _extract_entity(description)
            
            # 用 rule_id + 涉及单元 IDs 生成稳定 key
            unit_ids_sorted = sorted(units_involved) if units_involved else ["global"]
            key = f"{rule_id}:" + ":".join(unit_ids_sorted[:3])
            seen_keys.add(key)

            existing = self._state.deviations.get(key)
            if existing:
                existing.detection_count += 1
                existing.last_detected = now
                if existing.status == "pending":
                    existing.detail = detail or existing.detail
                    stats["updated"] += 1
                else:
                    # resolved/retained: 不重置状态，仅更新时序记录
                    # 用户已明确判断，应尊重其决定
                    if detail:
                        existing.detail = detail
                    stats["updated"] += 1
            else:
                self._state.deviations[key] = DeviationItem(
                    id=key,
                    dimension=rule_id,
                    entity=entity,
                    severity=severity,
                    status="pending",
                    first_detected=now,
                    last_detected=now,
                    summary=description[:200],
                    detail=detail,
                    source=source,
                )
                stats["new"] += 1

        # 全量扫描下：未再报出的 pending 偏差视为已修复，自动标记 resolved
        if full_scan and seen_keys:
            for key, item in list(self._state.deviations.items()):
                if item.status == "pending" and key not in seen_keys:
                    item.status = "resolved"
                    item.last_detected = now
                    stats["resolved"] += 1

        self.save()
        return stats
    
    def summary(self) -> Dict[str, Any]:
        """快速概览当前偏差状态（简化版 stats）"""
        counts = {"pending": 0, "resolved": 0, "retained": 0}
        severities = {"error": 0, "warning": 0, "info": 0}
        by_source = {}
        for d in self._state.deviations.values():
            counts[d.status] = counts.get(d.status, 0) + 1
            severities[d.severity] = severities.get(d.severity, 0) + 1
            by_source[d.source] = by_source.get(d.source, 0) + 1
        return {
            "total": len(self._state.deviations),
            "by_status": counts,
            "by_severity": severities,
            "by_source": by_source,
        }
    
    # ── 内部方法 ───────────────────────────────────────────────────────

    def _find_existing(self, dimension: str, entity: str, entity_id: str = "") -> Optional[DeviationItem]:
        """按 dimension + entity/entity_id 查找已有偏差"""
        for item in self._state.deviations.values():
            if item.dimension == dimension and item.entity == entity:
                return item
            if entity_id and item.entity_id == entity_id and item.dimension == dimension:
                return item
        return None

    def _generate_id(self) -> str:
        """生成唯一的偏差 ID"""
        return f"dev_{uuid.uuid4().hex[:8]}"
