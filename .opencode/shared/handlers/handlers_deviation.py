"""
handlers_deviation.py — 偏差管理纯业务逻辑函数。

涵盖 7 个操作：merge / list / pending / resolve / retain / delete / stats。
提取自 novel_tool.py _handle_deviation。
"""

import json
import os
import sys
from typing import Optional

from graph_store import is_v2_project
from ._common import ensure_sys_path, _resolve_project, _paginate

ensure_sys_path()


def handle_deviation_merge(
    project_root: str,
    findings: list,
    source: str = "novel-tool",
    scan_version: int = 0,
    full_scan_version: Optional[int] = None,
) -> dict:
    """合并偏差发现。"""
    from deviation_manager import DeviationManager, DeviationItem

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)

    if isinstance(findings, str):
        findings = json.loads(findings)

    items = []
    for f in findings:
        item = DeviationItem(
            id="",
            dimension=f.get("dimension", "unknown"),
            entity=f.get("entity", ""),
            entity_id=f.get("entity_id", ""),
            scanned_version=f.get("scanned_version", scan_version),
            status=f.get("status", "pending"),
            severity=f.get("severity", "info"),
            summary=f.get("summary", ""),
            detail=f.get("detail", ""),
            suggested_changeset=f.get("suggested_changeset"),
        )
        items.append(item)

    mgr.merge(items)
    if full_scan_version is not None:
        mgr.full_scan_version = int(full_scan_version)
    mgr.save()
    stats = mgr.stats()

    return {
        "merged": len(findings),
        "total": stats["total"],
        "full_scan_version": mgr.full_scan_version,
    }


def handle_deviation_list(
    project_root: str,
    status: str = "",
    limit: int = 0,
    offset: int = 0,
    severity: str = "",
    dimension: str = "",
) -> dict:
    """列出偏差。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    all_items = mgr.list_all() if not status else [d for d in mgr.list_all() if d.status == status]

    if severity:
        all_items = [d for d in all_items if d.severity == severity]
    if dimension:
        all_items = [d for d in all_items if d.dimension == dimension]

    items, total = _paginate(all_items, limit, offset)

    return {
        "deviations": [
            {
                "id": d.id, "dimension": d.dimension,
                "entity": d.entity, "status": d.status,
                "severity": d.severity, "summary": d.summary,
                "detail": d.detail, "detection_count": d.detection_count,
            }
            for d in items
        ],
        "total": total,
        "returned": len(items),
        "truncated": len(items) < total,
    }


def handle_deviation_pending(project_root: str, limit: int = 0, offset: int = 0) -> dict:
    """列出待处理偏差。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    items = mgr.filter_for_presentation()
    items, total = _paginate(items, limit, offset)

    return {
        "deviations": [
            {
                "id": d.id, "dimension": d.dimension,
                "entity": d.entity, "severity": d.severity,
                "summary": d.summary,
            }
            for d in items
        ],
        "total": total,
        "returned": len(items),
        "truncated": len(items) < total,
    }


def handle_deviation_resolve(project_root: str, id: str) -> dict:
    """解决偏差。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    ok = mgr.resolve(id)
    if ok:
        mgr.save()
        return {"resolved": True}
    return {"error": f"偏差不存在: {id}"}


def handle_deviation_retain(project_root: str, id: str) -> dict:
    """保留偏差（标记为已确认，不再报告）。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    ok = mgr.retain(id)
    if ok:
        mgr.save()
        return {"retained": True}
    return {"error": f"偏差不存在: {id}"}


def handle_deviation_delete(project_root: str, id: str) -> dict:
    """删除偏差。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    ok = mgr.delete(id)
    if ok:
        mgr.save()
        return {"deleted": True}
    return {"error": f"偏差不存在: {id}"}


def handle_deviation_stats(project_root: str) -> dict:
    """偏差统计。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    return mgr.stats()

def handle_deviation_summary(project_root: str) -> dict:
    """偏差快速概览（简化版 stats，带 source 维度）。"""
    from deviation_manager import DeviationManager

    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效: {project}"}

    mgr = DeviationManager(project)
    return mgr.summary()
