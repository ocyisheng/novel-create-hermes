"""
routes/pages.py — 前端页面路由

GET / → SPA 入口（index.html）
"""
from __future__ import annotations

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["pages"])

# 静态文件目录
_STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/")
def index():
    """SPA 入口：关系图页面"""
    index_path = _STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>前端文件未生成</h1><p>请确认 static/index.html 存在</p>", status_code=200)
    return FileResponse(str(index_path))