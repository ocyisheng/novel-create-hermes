"""
handlers_server.py — Web Server 相关 handler

web.start  : 启动本地 Web 服务（FastAPI + 前端 SPA，subprocess 非阻塞）
web.restart : 重启 Web 服务（kill 旧进程 → 启动新进程）
"""

import os
import sys
import subprocess
import json

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

# ── PID 持久化 ────────────────────────────────────────────────────

def _pid_path() -> str:
    _engine_dir = os.path.join(os.path.dirname(_SHARED_DIR), ".engine", "daemon")
    os.makedirs(_engine_dir, exist_ok=True)
    return os.path.join(_engine_dir, "web-server.json")

def _save_meta(project_root: str, pid: int, host: str, port: int):
    with open(_pid_path(), "w", encoding="utf-8") as f:
        json.dump({"pid": pid, "project_root": project_root, "host": host, "port": port}, f)

def _load_meta() -> dict | None:
    p = _pid_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

def _kill_proc(pid: int) -> bool:
    """尝试 kill 进程，返回是否成功。"""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        else:
            os.kill(pid, 9)
        return True
    except Exception:
        return False


# ── web.start ────────────────────────────────────────────────────

def handle_server_start(
    project_root: str = "",
    host: str = "127.0.0.1",
    port: int = 8766,
) -> dict:
    """启动本地 Web 服务（subprocess，不阻塞 daemon）。"""
    if not project_root:
        return {"error": "缺少 project_root 参数"}
    if not os.path.isdir(project_root):
        return {"error": f"项目目录不存在: {project_root}"}

    # 端口检测
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.close()
    except OSError:
        return {"error": f"端口 {port} 已被占用，请先关闭已有服务或换端口"}
    finally:
        sock.close()

    script = os.path.join(_V2_DIR, "web", "server.py")
    python = sys.executable
    url = f"http://{host}:{port}"

    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [python, script, "--project-root", project_root, "--host", host, "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        _save_meta(project_root, proc.pid, host, port)
        return {"ok": True, "url": url, "pid": proc.pid}
    except Exception as e:
        return {"error": f"服务启动失败: {e}"}


# ── web.restart ──────────────────────────────────────────────────

def handle_server_restart(
    project_root: str = "",
    host: str = "127.0.0.1",
    port: int = 8766,
) -> dict:
    """重启 Web 服务：kill 旧进程 → 启动新进程。"""
    meta = _load_meta()
    old_pid = meta.get("pid") if meta else None
    old_port = meta.get("port", port) if meta else port
    old_host = meta.get("host", host) if meta else host
    old_root = meta.get("project_root", project_root) if meta else project_root

    # 用传入参数覆盖
    project_root = project_root or old_root
    host = host or old_host
    port = port or old_port

    # 1) kill 旧进程
    killed = False
    if old_pid:
        killed = _kill_proc(old_pid)

    # 2) 等待端口释放
    import socket, time
    for _ in range(10):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, port))
            sock.close()
            break
        except OSError:
            sock.close()
            time.sleep(0.5)
    else:
        return {"error": f"端口 {port} 在 5s 内未释放"}

    # 3) 启动新进程
    script = os.path.join(_V2_DIR, "web", "server.py")
    python = sys.executable
    url = f"http://{host}:{port}"

    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            [python, script, "--project-root", project_root, "--host", host, "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        _save_meta(project_root, proc.pid, host, port)
        return {
            "ok": True, "url": url, "pid": proc.pid,
            "killed_old": killed, "old_pid": old_pid,
        }
    except Exception as e:
        return {"error": f"重启失败: {e}"}