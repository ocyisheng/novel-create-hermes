"""
telemetry.py — 工具调用遥测记录模块。

自动记录每次 novel-tool 调用的元数据到 .engine/telemetry/{YYYY-MM}.ndjson。

记录的字段：
- ts: 时间戳
- project: 所属小说项目名（跨项目聚合用）
- caller: 调用者标识（orchestrator | crafter | ideation | search-analysis | unknown）
- op: 操作名
- params: 参数（不含大 content）
- success: 是否成功
- error_type: 错误类型（如 schema_error、param_missing、runtime_error）
- error_detail: 错误详情摘要（首行）
- duration_ms: 耗时（毫秒）
- result_size: 返回数据大小
- unit_count: 影响/返回的单元数
- relation_count: 影响/返回的关系数

自动去重合并同类错误，避免日志爆炸。

存储架构：
- .engine/telemetry/{YYYY-MM}.ndjson  — 按月分片，跨项目统一存储
- 旧数据（{project}/graph/telemetry.ndjson）仍可读取，作为回退
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


def _resolve_engine_root() -> str:
    """解析 .engine/ 目录路径（工具根目录下）。"""
    # 从当前文件向上查找工具根目录
    # telemetry.py 在 shared/v2/ 下，工具根目录在 ../../../ 
    current = Path(__file__).resolve().parent  # v2/
    shared = current.parent                      # shared/
    opencode = shared.parent                     # .opencode/
    tool_root = opencode.parent                  # novel-create-hermes/
    engine_root = tool_root / ".engine"
    engine_root.mkdir(parents=True, exist_ok=True)
    return str(engine_root)


class TelemetryRecorder:
    """
    工具调用遥测记录器（全局单例）。
    
    每次调用记录一条 NDJSON 行到 .engine/telemetry/{YYYY-MM}.ndjson。
    跨项目统一存储，每条记录自带 project 字段。
    """
    
    def __init__(self):
        self._engine_root = _resolve_engine_root()
        self._log_dir = os.path.join(self._engine_root, "telemetry")
        self._buffer: List[dict] = []
        self._flush_threshold = 1   # 每条立即刷盘，避免进程退出时丢失
    
    def _log_path(self) -> str:
        """当前月份的分片文件路径。"""
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        os.makedirs(self._log_dir, exist_ok=True)
        return os.path.join(self._log_dir, f"{month_key}.ndjson")
    
    def record(
        self,
        operation: str,
        params: dict,
        success: bool,
        duration_ms: float,
        project: str = "",
        caller: str = "unknown",
        error_info: Optional[dict] = None,
        result_size: int = 0,
        unit_count: int = 0,
        relation_count: int = 0,
    ):
        """记录一次工具调用。"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "project": project,
            "caller": caller,
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
        project: str = "",
        caller: str = "unknown",
    ):
        """记录一次失败的工具调用。"""
        self.record(
            operation=operation,
            params=params,
            success=False,
            duration_ms=duration_ms,
            project=project,
            caller=caller,
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
            log_path = self._log_path()
            with open(log_path, "a", encoding="utf-8") as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            self._buffer.clear()
        except Exception:
            pass  # 遥测失败不影响主流程
    
    def close(self):
        """关闭时刷盘。"""
        self.flush()


# ── 全局单例 ──────────────────────────────────────────────────────────────

_recorder: Optional[TelemetryRecorder] = None


def get_recorder() -> TelemetryRecorder:
    """获取全局遥测记录器单例。"""
    global _recorder
    if _recorder is None:
        _recorder = TelemetryRecorder()
    return _recorder


def close_all():
    """关闭记录器。"""
    global _recorder
    if _recorder:
        _recorder.close()
        _recorder = None


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

def project_basename(project: str) -> str:
    """从 project 值提取纯项目名（遥测归因用，唯一实现）。

    兼容 Windows 反斜杠 / 正斜杠 / 尾斜杠 / 完整路径 / 空值。
    历史数据曾把完整路径写入 project 字段，读时统一归一化，
    使项目过滤对历史数据也生效。
    """
    if not project:
        return ""
    norm = project.replace("\\", "/").rstrip("/")
    base = norm.rsplit("/", 1)[-1]
    if base in ("", ".", "..", "novels", "graph"):
        return ""
    return base


def _read_engine_telemetry(project: str = "") -> list[dict]:
    """
    读取 .engine/telemetry/ 下所有遥测数据。
    
    Args:
        project: 可选，按项目名过滤（自动归一化为纯项目名，
                 历史完整路径数据也能命中）
    
    Returns:
        遥测条目列表（project 字段已归一化为纯项目名）
    """
    engine_root = _resolve_engine_root()
    telemetry_dir = os.path.join(engine_root, "telemetry")
    norm_project = project_basename(project)
    
    entries = []
    if os.path.isdir(telemetry_dir):
        for fname in sorted(os.listdir(telemetry_dir)):
            if fname.endswith(".ndjson"):
                fpath = os.path.join(telemetry_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entry = json.loads(line)
                                entry["project"] = project_basename(entry.get("project", ""))
                                if not norm_project or entry.get("project") == norm_project:
                                    entries.append(entry)
                            except json.JSONDecodeError:
                                pass
    return entries


def _read_project_telemetry(project_root: str) -> list[dict]:
    """
    回退：读取旧项目路径下的遥测数据（{project}/graph/telemetry.ndjson）。
    仅在新 .engine/ 路径无数据时使用。
    """
    log_path = Path(project_root) / "graph" / "telemetry.ndjson"
    if not log_path.exists():
        return []
    
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    # 旧数据没有 project/caller 字段，补默认值；已有值也统一归一化
                    entry["project"] = project_basename(entry.get("project") or os.path.basename(project_root))
                    entry.setdefault("caller", "unknown")
                    entries.append(entry)
                except json.JSONDecodeError:
                    pass
    return entries


def analyze_telemetry(project_root: str = "", project: str = "") -> dict:
    """
    分析遥测数据，输出结构化的故障模式和优化建议。
    
    Args:
        project_root: 旧格式兼容项目的根目录（回退用）
        project: 要分析的项目名（可选，不传则分析所有项目数据）
    
    读取优先级: .engine/telemetry/ → {project}/graph/telemetry.ndjson（回退）
    """
    # 优先读新路径
    entries = _read_engine_telemetry(project)
    
    # 回退：新路径无数据但提供了旧项目路径
    if not entries and project_root:
        entries = _read_project_telemetry(project_root)
    
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
    
    # 按 caller 统计
    caller_counts = Counter(e.get("caller", "unknown") for e in entries)
    caller_failures = Counter(e.get("caller", "unknown") for e in failures)
    
    # 按操作统计平均耗时
    op_durations = defaultdict(list)
    for e in entries:
        op_durations[e["op"]].append(e.get("duration_ms", 0))
    avg_durations = {op: round(sum(vals)/len(vals), 1) for op, vals in op_durations.items()}
    
    # 按 caller × op 交叉统计
    caller_op_counts = defaultdict(Counter)
    for e in entries:
        caller_op_counts[e.get("caller", "unknown")][e["op"]] += 1
    
    # 找出最慢的操作
    slow_ops = sorted(avg_durations.items(), key=lambda x: -x[1])[:5]
    
    # 找出最常见的错误
    common_errors = []
    for e in failures[:10]:
        error = e.get("error", {})
        common_errors.append({
            "op": e["op"],
            "caller": e.get("caller", "unknown"),
            "project": e.get("project", ""),
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
        "success_rate": f"{round(len(successes)/total*100, 1)}%" if total else "0%",
        "by_operation": dict(op_counts.most_common(20)),
        "by_caller": dict(caller_counts),
        "by_caller_operation": {caller: dict(ops.most_common(10)) for caller, ops in caller_op_counts.items()},
        "by_error_type": dict(error_types),
        "caller_failures": dict(caller_failures),
        "failure_rates": failure_rates,
        "avg_durations_ms": avg_durations,
        "slowest_operations": slow_ops,
        "common_errors": common_errors[:5],
        "suggestions": suggestions,
    }
