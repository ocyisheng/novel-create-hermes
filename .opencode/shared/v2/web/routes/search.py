"""
routes/search.py — 搜索 API

GET /api/search?q=&type=&scope= → 全文搜索

通过 run_operation 调用 handlers 层。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from web.deps import get_project_root
from handlers import run_operation

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = Query("", description="关键词"),
    type: str = Query("", description="限定类型（scene/character_arc/...）"),
    scope: str = Query("", description="逗号分隔的类型列表（优先级高于 type）"),
    limit: int = Query(50, description="最大返回数"),
    project_root: str = Depends(get_project_root),
):
    if not q:
        return {"query": "", "total": 0, "results": [], "time_ms": 0}

    # scope 决定：显式 scope > 单 type > 全量
    effective_scope = scope if scope else type

    result = run_operation(
        "graph.search",
        project_root=project_root,
        keyword=q,
        scope=effective_scope,
        limit=limit,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "query": q,
        "total": result.get("total", 0),
        "results": result.get("results", []),
        "time_ms": result.get("time_ms", 0),
    }