"""
routes/search.py — 搜索 API

GET /api/search?q=&type=&scope= → 全文搜索
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from graph_store import GraphStore
from search_engine import SearchEngine
from graph_schema import UnitType, UnitStatus
from web.deps import get_store, get_project_root

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = Query("", description="关键词"),
    type: str = Query("", description="限定类型（scene/character_arc/...）"),
    scope: str = Query("", description="逗号分隔的类型列表（优先级高于 type）"),
    limit: int = Query(50, description="最大返回数"),
    store: GraphStore = Depends(get_store),
    project_root: str = Depends(get_project_root),
):
    if not q:
        return {"query": "", "total": 0, "results": [], "time_ms": 0}

    engine = SearchEngine(store)

    # 解析 scope
    type_filter = None
    if scope:
        types = []
        for t in scope.split(","):
            t = t.strip()
            if t:
                try:
                    types.append(UnitType(t))
                except ValueError:
                    pass
        if types:
            type_filter = types
    elif type:
        try:
            type_filter = [UnitType(type)]
        except ValueError:
            pass

    result_set = engine.search(
        keyword=q,
        scope=type_filter,
        max_results=limit,
    )

    results = []
    for r in result_set.results:
        results.append({
            "unit_id": r.unit_id,
            "unit_name": r.unit_name,
            "unit_type": r.unit_type.value if hasattr(r.unit_type, "value") else str(r.unit_type),
            "content_preview": r.content_preview[:200] if r.content_preview else "",
            "chapter": r.chapter,
            "tags": r.tags,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "score": r.score,
        })

    return {
        "query": q,
        "total": result_set.total,
        "results": results,
        "time_ms": result_set.time_ms,
    }