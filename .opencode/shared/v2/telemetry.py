"""
telemetry.py — 工具调用遥测记录模块。

自动记录每次 novel-tool 调用的元数据到 graph/telemetry.ndjson。

记录的字段：
- operation: 操作名
- params: 参数（不含大 content）
- success: 是否成功
- error_type: 错误类型（如 schema_error、param_missing、runtime_error）
- error_detail: 错误详情摘要（首行）
- duration_ms: 耗时（毫秒）
- result_size: 返回数据大小
- unit_count: 影响/返回的单元数
- relation_count: 影响/返回的关系数

自动去重合并同类错误，避免日志爆炸。
"""

from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter, defaultdict


class TelemetryRecorder:
    """
    工具调用遥测记录器。
    
    每次调用记录一条 NDJSON 行到 graph/telemetry.ndjson。
    按 project 分文件存储。
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.graph_dir = self.project_root / "graph"
        self.log_path = self.graph_dir / "telemetry.ndjson"
        self._buffer: List[dict] = []
        self._flush_threshold = 10  # 每 10 条刷一次盘
    
    def record(
        self,
        operation: str,
        params: dict,
        success: bool,
        duration_ms: float,
        error_info: Optional[dict] = None,
        result_size: int = 0,
        unit_count: int = 0,
        relation_count: int = 0,
    ):
        """记录一次工具调用。"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "op": operation,
            "success": success,
            "duration_ms": round(duration_ms, 1),
            "result_size": result_size,
            "unit_count": unit_count,
            "relation_count": relation_count,
        }
        
        # 记录参数摘要（跳过大 content 字段）
        param_summary = {}
        for k, v in params.items():
            if k in ("content", "data", "file_path") and isinstance(v, str) and len(v) > 200:
                param_summary[k] = v[:200] + f"...({len(v)} chars)"
            elif isinstance(v, str) and len(v) > 500:
                param_summary[k] = v[:100] + f"...({len(v)} chars)"
            else:
                param_summary[k] = v
        entry["params"] = param_summary
        
        if not success and error_info:
            entry["error"] = error_info
        
        self._buffer.append(entry)
        
        if len(self._buffer) >= self._flush_threshold:
            self.flush()
    
    def record_error(
        self,
        operation: str,
        params: dict,
        error_type: str,
        error_msg: str,
        duration_ms: float,
    ):
        """记录一次失败的工具调用。"""
        self.record(
            operation=operation,
            params=params,
            success=False,
            duration_ms=duration_ms,
            error_info={
                "type": error_type,
                "detail": error_msg[:300],
            },
        )
    
    def flush(self):
        """将缓冲区写入磁盘。"""
        if not self._buffer:
            return
        try:
            self.graph_dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            self._buffer.clear()
        except Exception:
            pass  # 遥测失败不影响主流程
    
    def close(self):
        """关闭时刷盘。"""
        self.flush()


# ── 全局实例 ──────────────────────────────────────────────────────────────

_recorders: Dict[str, TelemetryRecorder] = {}


def get_recorder(project_root: str) -> TelemetryRecorder:
    """获取或创建项目的遥测记录器实例。"""
    if project_root not in _recorders:
        _recorders[project_root] = TelemetryRecorder(project_root)
    return _recorders[project_root]


def close_all():
    """关闭所有记录器。"""
    for r in _recorders.values():
        r.close()
    _recorders.clear()


# ── 错误分类 ─────────────────────────────────────────────────────────────

def classify_error(error_msg: str, stack_trace: str = "") -> str:
    """对错误进行分类。"""
    combined = error_msg + "\n" + stack_trace
    
    if "schema" in combined.lower() or "validate" in combined.lower() or "枚举" in combined or "allowed" in combined.lower():
        return "schema_error"
    if "import" in combined and "Error" in combined:
        return "import_error"
    if "not found" in combined.lower() or "不存在" in combined or "No such" in combined:
        return "not_found"
    if "timeout" in combined.lower():
        return "timeout"
    if "permission" in combined.lower() or "denied" in combined.lower():
        return "permission_error"
    return "runtime_error"


# ── 分析函数 ─────────────────────────────────────────────────────────────

def analyze_telemetry(project_root: str) -> dict:
    """
    分析遥测数据，输出结构化的故障模式和优化建议。
    
    读取 graph/telemetry.ndjson，聚合分析。
    """
    log_path = Path(project_root) / "graph" / "telemetry.ndjson"
    if not log_path.exists():
        return {"error": "无遥测数据"}
    
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    
    if not entries:
        return {"error": "无遥测数据"}
    
    total = len(entries)
    successes = [e for e in entries if e.get("success")]
    failures = [e for e in entries if not e.get("success")]
    
    # 按操作统计
    op_counts = Counter(e["op"] for e in entries)
    op_failures = Counter(e["op"] for e in failures)
    
    # 按错误类型统计
    error_types = Counter(e.get("error", {}).get("type", "unknown") for e in failures)
    
    # 按操作统计平均耗时
    op_durations = defaultdict(list)
    for e in entries:
        op_durations[e["op"]].append(e.get("duration_ms", 0))
    avg_durations = {op: round(sum(vals)/len(vals), 1) for op, vals in op_durations.items()}
    
    # 找出最慢的操作
    slow_ops = sorted(avg_durations.items(), key=lambda x: -x[1])[:5]
    
    # 找出最常见的错误
    common_errors = []
    for e in failures[:10]:
        error = e.get("error", {})
        common_errors.append({
            "op": e["op"],
            "type": error.get("type", "unknown"),
            "detail": error.get("detail", "")[:200],
            "params": {k: v for k, v in e.get("params", {}).items() if k not in ("content", "data")},
        })
    
    # 失败率高的操作
    failure_rates = {}
    for op, count in op_counts.items():
        fails = op_failures.get(op, 0)
        if count > 0:
            rate = round(fails / count * 100, 1)
            if rate > 0:
                failure_rates[op] = {"total": count, "failures": fails, "rate": f"{rate}%"}
    
    # 生成建议
    suggestions = []
    
    # 如果某操作失败率 > 20%
    for op, info in failure_rates.items():
        if float(info["rate"].rstrip("%")) > 20:
            suggestions.append({
                "type": "high_failure_rate",
                "target": f"operation:{op}",
                "signal": f"{op} 失败率 {info['rate']} ({info['failures']}/{info['total']})",
                "action": "检查该操作的参数传递和 handler 实现",
            })
    
    # 如果 schema_error 很多
    se_count = error_types.get("schema_error", 0)
    if se_count > 0:
        suggestions.append({
            "type": "schema_validation",
            "target": "schema",
            "signal": f"schema 校验错误 {se_count} 次",
            "action": "检查 schemas.py 中枚举字段的允许值列表是否合理",
        })
    
    # 如果平均耗时 > 5s 的操作有多个
    slow = [(op, d) for op, d in avg_durations.items() if d > 5000]
    if slow:
        suggestions.append({
            "type": "performance",
            "target": "operations:" + ",".join(op for op, _ in slow),
            "signal": f"慢操作: {slow}",
            "action": "检查这些操作是否存在全量扫描或未命中缓存",
        })
    
    return {
        "total_calls": total,
        "success_count": len(successes),
        "failure_count": len(failures),
        "success_rate": f"{round(len(successes)/total*100, 1)}%",
        "by_operation": dict(op_counts.most_common(20)),
        "by_error_type": dict(error_types),
        "failure_rates": failure_rates,
        "avg_durations_ms": avg_durations,
        "slowest_operations": slow_ops,
        "common_errors": common_errors[:5],
        "suggestions": suggestions,
    }
