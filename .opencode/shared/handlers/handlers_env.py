"""
handlers_env.py — 环境管理纯业务逻辑函数。

涵盖 3 个操作：check / fix / force。
提取自 novel_tool.py _handle_env。
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _discover_venv() -> Path:
    cwd = Path.cwd().resolve()
    for p in [cwd, cwd.parent] + list(cwd.parents):
        if (p / ".venv").exists():
            return p / ".venv"
    tool_root = Path(_SHARED_DIR).parent.parent
    return tool_root / ".venv"


def _find_requirements() -> Path:
    req = Path(_SHARED_DIR) / "env" / "scripts" / "requirements.txt"
    if req.exists():
        return req
    req2 = Path(_SHARED_DIR).parent.parent / ".opencode" / "shared" / "env" / "scripts" / "requirements.txt"
    if req2.exists():
        return req2
    return req


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / "Scripts" / "python.exe" if platform.system() == "Windows" else venv_dir / "bin" / "python3"


def handle_env_check() -> dict:
    """检查 Python 环境状态。"""
    VENV_DIR = _discover_venv()
    py_ver = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    python_ok = sys.version_info >= (3, 8)
    venv_ok = _venv_python(VENV_DIR).exists()

    deps_ok = False
    missing = []
    if venv_ok:
        try:
            r = subprocess.run(
                [str(_venv_python(VENV_DIR)), "-c", "import yaml; print(yaml.__version__)"],
                capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL,
            )
            deps_ok = r.returncode == 0
            if not deps_ok:
                missing.append("PyYAML")
        except Exception:
            missing.append("PyYAML")

    return {
        "python_version": py_ver,
        "python_ok": python_ok,
        "venv_exists": venv_ok,
        "venv_path": str(VENV_DIR),
        "deps_ok": deps_ok,
        "missing_deps": missing,
    }


def handle_env_fix() -> dict:
    """自动修复缺失依赖。"""
    VENV_DIR = _discover_venv()
    req = _find_requirements()
    venv_python = _venv_python(VENV_DIR)

    if req.exists():
        r = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", str(req)],
            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
        )
    else:
        r = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "pyyaml"],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        )

    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout[-500:] if hasattr(r, 'stdout') else "",
        "stderr": r.stderr[-500:] if hasattr(r, 'stderr') else "",
    }


def handle_env_force() -> dict:
    """强制重建 .venv 并安装依赖。"""
    VENV_DIR = _discover_venv()
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    python_cmd = "python" if platform.system() == "Windows" else "python3"
    r1 = subprocess.run(
        [python_cmd, "-m", "venv", str(VENV_DIR)],
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
    )
    if r1.returncode != 0:
        return {"error": f"创建虚拟环境失败: {r1.stderr}"}

    req = _find_requirements()
    venv_python = _venv_python(VENV_DIR)

    if req.exists():
        r2 = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", str(req)],
            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
        )
    else:
        r2 = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "pyyaml"],
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
        )

    return {
        "ok": r2.returncode == 0 if req.exists() else r2.returncode == 0,
        "venv_path": str(VENV_DIR),
    }
