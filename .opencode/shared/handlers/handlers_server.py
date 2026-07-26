"""
handlers_server.py — Web Server 相关 handler

server.start : 启动本地 Web 服务（FastAPI + 前端 SPA）
"""

import os
import sys

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


def handle_server_start(
    project_root: str = "",
    host: str = "127.0.0.1",
    port: int = 8765,
) -> dict:
    """启动本地 Web 服务。

    Args:
        project_root: 项目根目录
        host: 监听地址
        port: 监听端口

    Returns:
        启动状态 dict
    """
    from web.server import run_server

    if not project_root:
        return {"error": "缺少 project_root 参数"}

    # 验证项目目录
    if not os.path.isdir(project_root):
        return {"error": f"项目目录不存在: {project_root}"}

    try:
        run_server(project_root=project_root, host=host, port=port)
        return {"ok": True, "url": f"http://{host}:{port}"}
    except Exception as e:
        return {"error": f"服务启动失败: {e}"}