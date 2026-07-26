"""
deps.py — FastAPI 依赖注入
提供 GraphStore 实例给路由处理器，走统一 _get_store 入口。
"""

from fastapi import Request, HTTPException
from graph_store import GraphStore
from handlers.handlers_graph import _get_store

# 本地进程内缓存（独立模式兜底，守护进程模式下 _get_store 自带 LRU）
_store_cache: dict[str, GraphStore] = {}


def get_store(request: Request) -> GraphStore:
    """从统一入口 _get_store 获取 GraphStore（优先进程内缓存）。"""
    root: str | None = getattr(request.app.state, "project_root", None)
    if root is None:
        raise HTTPException(status_code=503, detail="GraphStore 未初始化，请先设置项目")
    if root not in _store_cache:
        _store_cache[root] = _get_store(root)
    return _store_cache[root]


def get_project_root(request: Request) -> str:
    """获取当前项目的根目录路径。"""
    root: str | None = getattr(request.app.state, "project_root", None)
    if root is None:
        raise HTTPException(status_code=503, detail="未设置项目根目录")
    return root