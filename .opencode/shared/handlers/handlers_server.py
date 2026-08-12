"""
handlers_server.py — Web Server 相关 handler

web.start  : 启动本地 Web 服务（FastAPI + 前端 SPA，subprocess 非阻塞）
web.restart : 重启 Web 服务（kill 旧进程 → 启动新进程）
web.stop   : 停止 Web 服务（kill 进程 + 清理元数据文件）
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

def _web_server_dir() -> str:
    _dir = os.path.join(os.path.dirname(os.path.dirname(_SHARED_DIR)), ".engine", "web-server")
    os.makedirs(_dir, exist_ok=True)
    return _dir

def _pid_path() -> str:
    return os.path.join(_web_server_dir(), "web-server.json")

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
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
        else:
            os.kill(pid, 9)
        return True
    except Exception:
        return False


# ── 日志路径（按天） ────────────────────────────────────────────────

def _today_log_paths() -> tuple[str, str]:
    """返回 (stdout日志路径, stderr日志路径)，按天分割。"""
    from datetime import date
    day = date.today().isoformat()
    d = _web_server_dir()
    return (
        os.path.join(d, f"web-server-{day}.log"),
        os.path.join(d, f"web-server-{day}-err.log"),
    )


# ── 端口轮询 ──────────────────────────────────────────────────────

def _wait_for_port(host: str, port: int, timeout: float = 5.0, interval: float = 0.3) -> bool:
    """轮询等待端口开始监听，超时返回 False。"""
    import socket, time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


# ── 子进程启动（共用） ────────────────────────────────────────────

def _start_server_process(project_root: str, host: str, port: int) -> dict:
    """启动 uvicorn 子进程，返回 {'ok', 'url', 'pid', 'log_path'} 或 {'error'}。"""
    import socket

    # 端口先行检测（确认未被占用）
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.close()
    except OSError:
        sock.close()
        return {"error": f"端口 {port} 已被占用，请先关闭已有服务或换端口"}

    script = os.path.join(_V2_DIR, "web", "server.py")
    python = sys.executable
    url = f"http://{host}:{port}"

    # 日志路径（按天追加）
    out_path, err_path = _today_log_paths()

    # 启动子进程
    # 注意：daemon 环境下不要设 creationflags（CREATE_NO_WINDOW 会导致子进程初始化失败），
    # 用 stdin=DEVNULL 避免继承 daemon 的 stdin 管道。
    try:
        proc = subprocess.Popen(
            [python, script, "--project-root", project_root, "--host", host, "--port", str(port)],
            stdout=open(out_path, "ab"),
            stderr=open(err_path, "ab"),
            stdin=subprocess.DEVNULL,
        )
    except Exception as e:
        return {"error": f"子进程启动失败: {e}"}

    pid = proc.pid

    # 轮询等待端口就绪
    ready = _wait_for_port(host, port, timeout=5.0)
    if not ready:
        crash_info = ""
        for p in [err_path, out_path]:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        c = f.read(2000)
                    if c.strip():
                        crash_info += f"\n--- {p} ---\n{c}"
                except Exception:
                    pass
        _kill_proc(pid)
        msg = f"服务启动超时（5s 内未监听 {host}:{port}）"
        if crash_info:
            msg += f"\n进程输出：{crash_info}"
        return {"error": msg, "log_path": err_path}

    # 端口已就绪 — 通过 netstat 获取真实 PID（子进程 PID 可能与 Popen 返回的不同）
    real_pid = pid
    try:
        import subprocess as _sp
        ns = _sp.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        for line in ns.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    candidate = parts[-1]
                    if candidate.isdigit():
                        real_pid = int(candidate)
                        break
    except Exception:
        pass

    _save_meta(project_root, real_pid, host, port)
    return {"ok": True, "url": url, "pid": real_pid, "log_path": out_path}


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

    result = _start_server_process(project_root, host, port)
    if "error" in result:
        return result
    return {"ok": True, "url": result["url"], "pid": result["pid"]}


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

    # 3) 启动新进程（共用 _start_server_process）
    result = _start_server_process(project_root, host, port)
    if "error" in result:
        return result
    return {
        "ok": True, "url": result["url"], "pid": result["pid"],
        "killed_old": killed, "old_pid": old_pid,
    }


# ── web.stop ─────────────────────────────────────────────────────

def handle_server_stop() -> dict:
    """停止 Web 服务：kill 进程 + 清理元数据文件。"""
    meta = _load_meta()
    if not meta:
        return {"ok": True, "message": "没有正在运行的 Web 服务", "killed": False}

    pid = meta.get("pid")
    killed = False
    if pid:
        killed = _kill_proc(pid)

    # 清理元数据文件
    try:
        p = _pid_path()
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass

    return {
        "ok": True,
        "killed": killed,
        "pid": pid,
        "host": meta.get("host"),
        "port": meta.get("port"),
    }