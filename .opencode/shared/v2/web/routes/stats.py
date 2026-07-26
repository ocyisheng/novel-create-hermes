"""
routes/stats.py — 统计数据 API

GET /api/stats → 项目统计信息

通过 run_operation 调用 handlers 层。
"""

from fastapi import APIRouter, Depends
from web.deps import get_project_root
from handlers import run_operation

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(project_root: str = Depends(get_project_root)):
    """返回项目统计信息"""
    result = run_operation("graph.stats", project_root=project_root)
    if "error" in result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result["error"])

    total = result.get("total_units", 0)
    by_status = result.get("by_status", {})
    archived = by_status.get("archived", 0)

    return {
        "total_units": total,
        "archived": archived,
        "active": total - archived,
        "total_relations": result.get("total_relations", 0),
        "by_type": dict(sorted(result.get("by_type", {}).items())),
        "by_status": dict(sorted(by_status.items())),
    }