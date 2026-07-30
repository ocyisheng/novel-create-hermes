"""
handlers_project.py — 项目管理纯业务逻辑函数。

涵盖 6 个操作：new / import / status / resume / switch / delete。
提取自 novel_tool.py _handle_project 和 project_init.py cmd_*。
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))
)
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


# ── 工具函数 ──────────────────────────────────────────────────────────────

def _find_novels_root() -> str:
    env = os.environ.get("NOVELS_ROOT")
    if env and os.path.isdir(env):
        return env
    cwd = os.path.join(os.getcwd(), "novels")
    if os.path.isdir(cwd):
        return cwd
    tool_root = os.path.abspath(os.path.join(_SHARED_DIR, "..", ".."))
    tool_novels = os.path.join(tool_root, "novels")
    if os.path.isdir(tool_novels):
        return tool_novels
    return cwd


NOVELS_ROOT = _find_novels_root()


def _project_path(name: str) -> str:
    return os.path.join(NOVELS_ROOT, name)


def _project_exists(name: str) -> bool:
    p = _project_path(name)
    return os.path.isdir(p) and os.path.isfile(os.path.join(p, "config.yaml"))


def _load_config(name: str) -> dict:
    cfg = os.path.join(_project_path(name), "config.yaml")
    if not os.path.exists(cfg):
        return {}
    import yaml
    with open(cfg, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_config(name: str, config: dict):
    import yaml
    cfg = os.path.join(_project_path(name), "config.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _calc_chapter_distribution(volumes: int, acts: int) -> list:
    total = 100
    if acts == 3:
        ratios = [0.25, 0.50, 0.25]
    else:
        ratios = [1.0 / acts] * acts
    act_chapters = [int(total * r) for r in ratios]
    base = total // volumes
    result = [base] * volumes
    remainder = total - base * volumes
    for i in range(remainder):
        result[i] += 1
    return result


def _get_store(project_root: str):
    from graph_store import GraphStore
    store = GraphStore(project_root)
    store.initialize()
    return store


# ── Handler 函数 ──────────────────────────────────────────────────────────

def handle_project_new(
    name: str,
    genre: str = "通用",
    v2: bool = True,
    volumes: int = 3,
    acts: int = 3,
    structure: str = "三幕",
) -> dict:
    """创建新小说项目。"""
    name = name.strip()
    genre = genre.strip()
    proj_dir = _project_path(name)

    if os.path.exists(proj_dir):
        return {"error": f"项目已存在: {proj_dir}"}

    if v2:
        return _create_v2_project(name, genre, proj_dir)

    # V1 项目
    dirs_v1 = [
        "chapters", "chapters/.metas", "characters", "ideation",
        "outline/分纲", "outline/分卷", "outline/情节线", "outline/追踪",
        "output", "quality", "styles", "worldbuilding",
    ]
    for d in dirs_v1:
        os.makedirs(os.path.join(proj_dir, d), exist_ok=True)
    for v in range(1, volumes + 1):
        os.makedirs(os.path.join(proj_dir, f"outline/分纲/第{v}卷"), exist_ok=True)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    chapter_dist = _calc_chapter_distribution(volumes, acts)
    config = {
        "架构": "v1",
        "项目名称": name,
        "项目类型": genre,
        "活跃风格": "通俗网文风",
        "当前状态": "起步",
        "预期结构": f"{volumes}卷{sum(chapter_dist)}章",
        "创建时间": now,
        "写作进度": {"当前卷": 0, "当前章": 0, "卷大纲状态": "", "卷大纲完成数": 0},
        "创作目标": {"目标字数": 200000, "目标章节数": sum(chapter_dist), "每日目标": 2000},
    }
    _save_config(name, config)

    return {
        "path": proj_dir,
        "v2": False,
        "volumes": volumes,
        "acts": acts,
        "structure": structure,
        "chapters": sum(chapter_dist),
    }


def _create_v2_project(name: str, genre: str, proj_dir: str) -> dict:
    """创建 V2 原生项目。"""
    v2_dirs = ["graph", "quality", "styles", "output"]
    for d in v2_dirs:
        os.makedirs(os.path.join(proj_dir, d), exist_ok=True)

    graph_ok = False
    try:
        from graph_store import GraphStore
        from graph_schema import EventType
        store = GraphStore(str(proj_dir))
        store.initialize()
        store._record_event(
            EventType.SYSTEM_EVENT, actor="project_init",
            payload={"action": "project_created", "project": name},
        )
        store.flush()
        for fname in ["nodes.jsonl", "edges.jsonl"]:
            fp = os.path.join(str(proj_dir), "graph", fname)
            if not os.path.exists(fp):
                open(fp, "w", encoding="utf-8").close()
        graph_ok = True
    except Exception as e:
        graph_ok = False

    import yaml
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    config = {
        "架构": "v2",
        "项目名称": name,
        "项目类型": genre,
        "活跃风格": "通俗网文风",
        "当前状态": "起步",
        "预期结构": "待定",
        "创建时间": now,
        "写作进度": {"当前卷": 0, "当前章": 0, "卷大纲状态": "", "卷大纲完成数": 0},
        "创作目标": {"目标字数": 200000, "目标章节数": 40, "每日目标": 2000},
    }
    _save_config(name, config)

    return {"path": proj_dir, "v2": True, "graph_initialized": graph_ok}


def handle_project_import(name: str, source_path: str) -> dict:
    """导入已有小说项目。"""
    name = name.strip()
    source = source_path.strip()
    if not os.path.exists(source):
        return {"error": f"源路径不存在: {source}"}
    proj_dir = _project_path(name)
    if os.path.exists(proj_dir):
        return {"error": f"目标项目已存在: {proj_dir}"}
    shutil.copytree(source, proj_dir)
    return {
        "path": proj_dir,
        "has_graph": os.path.isdir(os.path.join(proj_dir, "graph")),
    }


def handle_project_status(name: str, phase: str = "") -> dict:
    """查看项目状态。"""
    name = name.strip()
    if not _project_exists(name):
        return {"error": f"项目不存在: {name}"}

    config = _load_config(name)
    if not config:
        return {"error": "config.yaml 为空或格式错误"}

    proj = _project_path(name)
    is_v2 = config.get("架构") == "v2" or os.path.isdir(os.path.join(proj, "graph"))

    result = {
        "name": name,
        "path": proj,
        "config": config,
        "is_v2": is_v2,
    }

    # 更新 phase（如果提供）
    if phase:
        config["写作阶段"] = phase
        _save_config(name, config)
        result["phase_updated"] = phase

    # V2 统计
    if is_v2 and os.path.isfile(os.path.join(proj, "graph", "nodes.jsonl")):
        try:
            store = _get_store(proj)
            stats = store.stats()
            result["stats"] = stats
            result["v2_progress"] = _derive_progress(proj)
        except Exception:
            result["stats"] = None
            result["v2_progress"] = None

    return result


def _derive_progress(project_path: str) -> dict:
    """从 graph 实时推算写作进度。"""
    from graph_schema import UnitType, UnitStatus, get_unit_chapter
    store = _get_store(project_path)
    result = {}
    chunks = store.find_units(type=UnitType.CHUNK)
    chunk_chapters = sorted(set(
        get_unit_chapter(c) for c in chunks if get_unit_chapter(c) > 0
    ))
    result["current_chapter"] = max(chunk_chapters) if chunk_chapters else 0
    result["written_chapters"] = len(chunk_chapters)
    volumes = store.find_units(type=UnitType.VOLUME_PLAN)
    all_cp = store.find_units(type=UnitType.CHAPTER_PLAN)
    volume_progress = []
    for vol in sorted(volumes, key=lambda v: _vol_num(v)):
        vn = _vol_num(vol)
        vname = _vol_name(vol)
        descendant_ids = set(store.find_descendants(vol.id, max_depth=3))
        vol_cps = [cp for cp in all_cp if cp.id in descendant_ids]
        total = len(vol_cps)
        mature = sum(1 for cp in vol_cps if cp.status == UnitStatus.MATURE)
        ch_nums = sorted(set(
            get_unit_chapter(cp) for cp in vol_cps if get_unit_chapter(cp) > 0
        ))
        ch_range = (
            f"{ch_nums[0]}-{ch_nums[-1]}"
            if len(ch_nums) >= 2
            else (str(ch_nums[0]) if ch_nums else "")
        )
        if total > 0 and mature == total:
            status = "completed"
        elif mature > 0:
            status = "in_progress"
        else:
            status = "pending"
        volume_progress.append({
            "volume": vn, "name": vname, "chapter_range": ch_range,
            "total_chapter_plans": total, "mature_chapter_plans": mature, "status": status,
        })
    result["volume_progress"] = volume_progress
    cur_vol = 0
    for vp in volume_progress:
        if vp["chapter_range"]:
            parts = vp["chapter_range"].split("-")
            try:
                lo, hi = int(parts[0]), int(parts[-1])
                if lo <= result["current_chapter"] <= hi:
                    cur_vol = vp["volume"]
                    break
            except (ValueError, IndexError):
                pass
    if cur_vol == 0 and volume_progress:
        cur_vol = volume_progress[-1]["volume"]
    result["current_volume"] = cur_vol
    result["total_chunks"] = len(chunks)
    result["total_chapter_plans"] = len(all_cp)
    return result


def _vol_num(unit) -> int:
    try:
        if unit.content and unit.content.startswith("{"):
            c = json.loads(unit.content)
            return int(c.get("卷号", 0))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        pass
    return 0


def _vol_name(unit) -> str:
    try:
        if unit.content and unit.content.startswith("{"):
            c = json.loads(unit.content)
            return str(c.get("volume_title", ""))
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return ""


def handle_project_resume(name: str) -> dict:
    """续写项目（刷新最后编辑时间）。"""
    name = name.strip()
    if not _project_exists(name):
        return {"error": f"项目不存在: {name}"}
    config = _load_config(name)
    config["最后编辑"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    _save_config(name, config)
    return {"ok": True}


def handle_project_switch(name: str, dry_run: bool = False) -> dict:
    """切换当前项目。"""
    name = name.strip()
    proj_path = _project_path(name)

    if not _project_exists(name) and not dry_run:
        return {"error": f"项目不存在: {name}"}

    config = _load_config(name) if _project_exists(name) else {}
    genre = config.get("项目类型", "未知")
    style = config.get("活跃风格", "通俗网文风")

    # 写入 novel-context.md
    tool_root = os.path.abspath(os.path.join(_SHARED_DIR, "..", ".."))
    ctx_dir = os.path.join(tool_root, ".omo", "notepads")
    os.makedirs(ctx_dir, exist_ok=True)
    ctx_path = os.path.join(ctx_dir, "novel-context.md")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    context = f"""__CURRENT_PROJECT__: {name}

# 项目上下文: {name}

> 由项目管理器自动生成。不要手动编辑此文件。

## 项目信息
- 项目名称：{name}
- 项目类型：{genre}
- 项目路径：{proj_path}
- 环境已初始化：True

## 当前状态
- 活跃风格：{style}
- 切换时间：{now}
"""

    if not dry_run:
        with open(ctx_path, "w", encoding="utf-8") as f:
            f.write(context)

    has_graph = os.path.isdir(os.path.join(proj_path, "graph"))
    return {
        "ok": not dry_run,
        "dry_run": dry_run,
        "project": name,
        "path": proj_path,
        "genre": genre,
        "style": style,
        "has_graph": has_graph,
    }


def handle_project_delete(name: str, force: bool = False) -> dict:
    """删除项目。"""
    name = name.strip()
    proj = _project_path(name)
    if not os.path.isdir(proj):
        return {"error": f"项目目录不存在: {proj}"}
    if not force:
        return {"error": "删除需要 force=True 确认", "needs_force": True}
    shutil.rmtree(proj, ignore_errors=True)
    return {"deleted": True, "path": proj}
