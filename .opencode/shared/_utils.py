"""shared/ 公共工具函数

所有项目维护脚本的共享基础模块。提供项目路径解析、YAML 读写、章节号提取、
嵌套字典访问、安全 YAML 加载等通用操作。
"""

import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


# ── 项目路径 ─────────────────────────────────────────────────────────────────

def find_project_root(start: Path) -> Path:
    """向上查找包含 config.yaml 的项目根目录。"""
    if (start / "config.yaml").exists():
        return start
    for parent in start.parents:
        if (parent / "config.yaml").exists():
            return parent
    return start


# ── YAML 读写 ────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    """安全读取 YAML 文件，不存在或格式错误时返回 {}。"""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {}


def save_yaml(path: Path, data: dict) -> None:
    """安全写入 YAML，覆盖前自动创建 .bak 备份。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bak = path.with_suffix(".yaml.bak")
        if bak.exists():
            bak.unlink()
        path.replace(bak)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_yaml_safe(path: Path) -> dict | None:
    """安全加载 YAML，失败时返回 None（不抛异常）。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError):
        return None


# ── 字典工具 ─────────────────────────────────────────────────────────────────

def get_nested(data: dict, dot_path: str):
    """按点号路径访问嵌套字典。如 get_nested(data, "a.b.c") 相当于 data["a"]["b"]["c"]。"""
    keys = dot_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# ── 时间戳 ───────────────────────────────────────────────────────────────────

def fmt_dt() -> str:
    """返回 ISO 格式当前时间戳。"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ── 章节号 ───────────────────────────────────────────────────────────────────

def extract_chapter_number(filepath: Path | str) -> int:
    """从文件名提取章节号。如 "第5章.txt" → 5，"第12章.yaml" → 12。"""
    if isinstance(filepath, str):
        filepath = Path(filepath)
    m = re.search(r"(\d+)", filepath.stem)
    return int(m.group(1)) if m else 0
