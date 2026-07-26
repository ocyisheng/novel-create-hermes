"""
routes/stats.py — 统计数据 API

GET /api/stats → 项目统计信息
"""

from fastapi import APIRouter, Depends
from graph_store import GraphStore
from graph_schema import UnitStatus
from web.deps import get_store, get_project_root

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(store: GraphStore = Depends(get_store), project_root: str = Depends(get_project_root)):
    """返回项目统计信息"""
    units = store._units.values()

    total = len(units)
    by_type = {}
    by_status = {}
    archived = 0

    for u in units:
        t = u.type.value
        by_type[t] = by_type.get(t, 0) + 1

        s = u.status.value
        by_status[s] = by_status.get(s, 0) + 1

        if u.status == UnitStatus.ARCHIVED:
            archived += 1

    return {
        "total_units": total,
        "archived": archived,
        "active": total - archived,
        "total_relations": len(store._relations),
        "by_type": dict(sorted(by_type.items())),
        "by_status": dict(sorted(by_status.items())),
    }