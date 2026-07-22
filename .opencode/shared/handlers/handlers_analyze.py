"""
handlers_analyze.py — 使用数据分析纯业务逻辑函数。

涵盖操作: analyze.usage、analyze.telemetry、verify.improvement。
"""

import json
import os
import sys

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


def handle_analyze_usage(project_root: str, mode: str = "full", json_output: bool = False, project: str = "") -> dict:
    """
    收集使用数据并返回分析报告。
    
    Args:
        project_root: 项目路径（用于读取 graph/ 数据）
        mode: "full" | "quick"
        json_output: 是否输出 JSON
        project: 遥测数据按项目名过滤（可选，不传则分析所有项目数据）
    """
    from usage_analyzer import collect_usage_data, format_report

    report = collect_usage_data(project_root, telemetry_project=project)
    if "error" in report:
        return report

    if json_output:
        return {"report": json.dumps(report, ensure_ascii=False, indent=2, default=str)}
    else:
        return {"report": format_report(report, verbose=(mode == "full"))}


def handle_analyze_telemetry(project_root: str = "", project: str = "") -> dict:
    """
    分析遥测数据，返回故障模式和优化建议。
    
    Args:
        project_root: 旧格式回退路径
        project: 按项目名过滤（可选，不传则分析所有项目数据）
    """
    from telemetry import analyze_telemetry, close_all
    result = analyze_telemetry(project_root=project_root, project=project)
    close_all()
    return result
