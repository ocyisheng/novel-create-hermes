"""
handlers_analyze.py — 使用数据分析纯业务逻辑函数。

涵盖操作: analyze.usage、analyze.telemetry、verify.improvement。
"""

import json
import os

from ._common import ensure_sys_path

ensure_sys_path()


def handle_analyze_usage(project_root: str, mode: str = "full", json_output: bool = False) -> dict:
    """
    收集使用数据并返回分析报告。
    
    Args:
        project_root: 项目路径（用于读取 graph/ 数据）
        mode: "full" | "quick"
        json_output: 是否输出 JSON
    """
    from usage_analyzer import collect_usage_data, format_report, project_basename

    telemetry_project = project_basename(project_root) if project_root else ""
    report = collect_usage_data(project_root, telemetry_project=telemetry_project)
    if "error" in report:
        return report

    if json_output:
        return {"report": json.dumps(report, ensure_ascii=False, indent=2, default=str)}
    else:
        return {"report": format_report(report, verbose=(mode == "full"))}


def handle_analyze_telemetry(project_root: str = "") -> dict:
    """
    分析遥测数据，返回故障模式和优化建议。
    
    Args:
        project_root: 项目路径（可选，不传则分析所有项目数据）
    """
    from telemetry import analyze_telemetry, close_all, project_basename

    telemetry_project = project_basename(project_root) if project_root else ""
    result = analyze_telemetry(project_root=project_root, project=telemetry_project)
    close_all()
    return result
