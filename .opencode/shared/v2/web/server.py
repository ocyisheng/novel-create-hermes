"""
server.py — FastAPI 应用入口

启动本地 Web 服务，提供 REST API + 前端 SPA。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ── sys.path ──────────────────────────────────────────────────────
_V2_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _V2_DIR not in sys.path:
    sys.path.insert(0, _V2_DIR)
_SHARED_DIR = os.path.dirname(_V2_DIR)
if _SHARED_DIR not in sys.path:
    sys.path.insert(0, _SHARED_DIR)


# ── routes ────────────────────────────────────────────────────────

from web.routes.nodes import router as nodes_router
from web.routes.edges import router as edges_router
from web.routes.graph import router as graph_router
from web.routes.search import router as search_router
from web.routes.stats import router as stats_router
from web.routes.pages import router as pages_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """生命周期管理：启动时加载 graph，关闭时 flush。"""
    root = getattr(app.state, "project_root", None)
    if root:
        _init_store(app, root)
    yield
    # 关闭时 flush
    store = getattr(app.state, "graph_store", None)
    if store:
        try:
            store.flush()
        except Exception:
            pass


def _init_store(app, project_root: str):
    """初始化 GraphStore 并挂到 app.state（通过统一入口 _get_store）。"""
    from handlers.handlers_graph import _get_store
    try:
        store = _get_store(project_root)
        app.state.graph_store = store
        app.state.project_root = project_root
    except Exception as e:
        raise RuntimeError(f"GraphStore 初始化失败: {e}")


def create_app(project_root: str = "") -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title="novel-web-server",
        description="novel-create-hermes 本地 Web 服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — 本地开发全部放行
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API 路由
    app.include_router(nodes_router)
    app.include_router(edges_router)
    app.include_router(graph_router)
    app.include_router(search_router)
    app.include_router(stats_router)
    app.include_router(pages_router)

    # 挂载静态文件
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 项目根 API
    @app.get("/api/project")
    def get_project_info():
        root = getattr(app.state, "project_root", None)
        if not root:
            raise HTTPException(status_code=503, detail="未设置项目根目录")
        name = os.path.basename(root) if root else "未知"
        store = getattr(app.state, "graph_store", None)
        stats = {}
        if store:
            stats = {
                "total_units": len(store._units),
                "total_relations": len(store._relations),
            }
        return {
            "name": name,
            "root": root,
            "is_v2": True,
            "stats": stats,
        }

    @app.post("/api/project/switch")
    def switch_project(body: dict):
        """切换到另一个项目"""
        new_root = body.get("project_root", "")
        if not new_root:
            raise HTTPException(status_code=400, detail="缺少 project_root")

        # flush 当前
        current = getattr(app.state, "graph_store", None)
        if current:
            try:
                current.flush()
            except Exception:
                pass

        _init_store(app, new_root)
        return {"ok": True, "project_root": new_root}

    @app.get("/api/project/search-scope")
    def get_search_scope():
        """返回可用类型列表（供前端筛选下拉用）"""
        from graph_schema import UnitType
        return {
            "types": [
                {"value": t.value, "label": _type_label(t)}
                for t in UnitType
            ]
        }

    if project_root:
        _init_store(app, project_root)

    return app


def _type_label(t) -> str:
    from graph_schema import UnitType
    labels = {
        UnitType.CHARACTER_ARC: "角色",
        UnitType.SCENE: "场景",
        UnitType.PLOT_THREAD: "情节线",
        UnitType.WORLD_RULE: "世界观",
        UnitType.THEMATIC_MOTIF: "主题意象",
        UnitType.NOTE: "笔记",
        UnitType.CHUNK: "正文",
        UnitType.OUTLINE: "总纲",
        UnitType.ARC_PLAN: "部篇大纲",
        UnitType.VOLUME_PLAN: "卷大纲",
        UnitType.CHAPTER_PLAN: "章纲",
        UnitType.STRUCTURE: "结构",
        UnitType.NARRATIVE_VOICE: "叙述腔调",
    }
    return labels.get(t, t.value)


# ── 启动入口 ──────────────────────────────────────────────────────

def run_server(project_root: str, host: str = "127.0.0.1", port: int = 8765):
    """启动 uvicorn 服务器。"""
    import uvicorn

    app = create_app(project_root=project_root)
    print(f"  🌐  Web 服务启动 → http://{host}:{port}")
    print(f"  📁  项目: {project_root}")
    print(f"  📖  API 文档 → http://{host}:{port}/docs")
    print(f"  🗺️  关系图谱 → http://{host}:{port}/")
    print()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    # 作为脚本直接运行时解析参数
    import argparse

    parser = argparse.ArgumentParser(description="novel-web-server")
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    args = parser.parse_args()

    run_server(args.project_root, args.host, args.port)