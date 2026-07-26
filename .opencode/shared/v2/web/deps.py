"""
deps.py — FastAPI 依赖注入
提供 GraphStore 实例给路由处理器。
"""

from fastapi import Request, HTTPException
from graph_store import GraphStore


def get_store(request: Request) -> GraphStore:
    """从 app.state 获取当前项目的 GraphStore 实例。"""
    store: GraphStore | None = getattr(request.app.state, "graph_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="GraphStore 未初始化，请先设置项目")
    return store


def get_project_root(request: Request) -> str:
    """获取当前项目的根目录路径。"""
    root: str | None = getattr(request.app.state, "project_root", None)
    if root is None:
        raise HTTPException(status_code=503, detail="未设置项目根目录")
    return root