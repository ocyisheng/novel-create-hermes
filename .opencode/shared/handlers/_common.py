"""
handlers._common — 共享工具函数（单一权威实现）。

消除 handlers_*.py 间的重复代码与行为分歧。
所有 handler 文件应从这里导入，不再在本地定义同名函数。
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Optional, List, Tuple

# ── sys.path 统一引导 ──────────────────────────────────────────────────────
# 所有 handlers/*.py 都在 shared/handlers/ 下，工具根目录在 ../../../
# v2/ 目录在 ../v2/
_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")


def ensure_sys_path() -> None:
    """确保 shared/ 和 v2/ 在 sys.path 中（幂等）。"""
    for _d in (_SHARED_DIR, _V2_DIR):
        if _d not in sys.path:
            sys.path.insert(0, _d)


# 调用一次，保证后续导入 graph_store 等 v2 模块可用
ensure_sys_path()


# ── 项目路径解析 ──────────────────────────────────────────────────────────

def _find_novels_root() -> str:
    """查找 novels/ 根目录。

    优先级：
    1. 环境变量 NOVELS_ROOT（若存在且为目录）
    2. 当前工作目录下的 novels/
    3. 工具根目录下的 novels/（即 novel-create-hermes/novels/）
    4. 回退到 cwd/novels（即使不存在，由调用方判断）
    """
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


# 供测试 patch 的模块级属性（handlers_project.NOVELS_ROOT 兼容）
NOVELS_ROOT = _find_novels_root()


def _resolve_project(project: str) -> str:
    """将项目名解析为绝对路径。

    行为（与 handlers_graph._resolve_project 一致，最完整版）：
    - 空串 → 空串
    - 绝对路径 → 直接返回
    - 相对路径 → 依次尝试 NOVELS_ROOT、cwd/novels、tool_root/novels 拼接；
      首个存在的目录胜出；全不存在时回退到绝对化后的相对路径

    测试 patch 兼容：test_novel_tool.py 通过 patch("handlers.handlers_project.NOVELS_ROOT", tmpdir)
    重定向项目根，因此这里惰性读取 handlers_project.NOVELS_ROOT（未 patch 时与
    _common.NOVELS_ROOT 同值），保证 patch 后能命中测试目录。
    """
    if not project:
        return ""
    if os.path.isabs(project):
        return project
    novels = _patchable_novels_root()
    cand = os.path.join(novels, project)
    if os.path.isdir(cand):
        return cand
    return os.path.abspath(project)


def _patchable_novels_root() -> str:
    """读取 NOVELS_ROOT（优先 handlers_project.NOVELS_ROOT 以兼容测试 patch）。"""
    try:
        from . import handlers_project as _hp
        return _hp.NOVELS_ROOT
    except (ImportError, AttributeError):
        return NOVELS_ROOT


# ── 分页工具 ──────────────────────────────────────────────────────────────

def _paginate(items: list, limit: int = 0, offset: int = 0) -> Tuple[list, int]:
    """返回 (切片后的 items, 真实总数)。limit<=0 表示不限制。"""
    total = len(items)
    if limit and limit > 0:
        items = items[offset:offset + limit]
    elif offset:
        items = items[offset:]
    return items, total


# ── 写作进度推算（handlers_graph 与 handlers_project 共用）──────────────────

def _derive_progress(project_path: str) -> dict:
    """从 graph 实时推算写作进度。"""
    from graph_schema import UnitType, UnitStatus, get_unit_chapter
    # 延迟导入避免循环依赖
    from graph_store import GraphStore
    store = GraphStore(project_path)
    store.initialize()
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
    """从单元 content 提取卷号。"""
    try:
        if unit.content and unit.content.startswith("{"):
            c = json.loads(unit.content)
            return int(c.get("卷号", 0))
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        pass
    return 0


def _vol_name(unit) -> str:
    """从单元 content 提取卷标题。"""
    try:
        if unit.content and unit.content.startswith("{"):
            c = json.loads(unit.content)
            return str(c.get("volume_title", ""))
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return ""


# ── 编排层写操作权限检查（单一策略 + 单一消息模板）──────────────────────────

_ORCHESTRATOR_WRITE_BLOCKED = True


def set_orchestrator_write_blocked(blocked: bool) -> None:
    """设置是否禁止编排层直接写 graph（默认禁止）"""
    global _ORCHESTRATOR_WRITE_BLOCKED
    _ORCHESTRATOR_WRITE_BLOCKED = blocked


def check_write_permission(actor: str, operation: str) -> Optional[dict]:
    """检查调用者是否有权限直接写 graph。返回 dict | None 而非抛异常。

    允许的 actor：
      - novel-writer（创作通路，主执行者）
      - novel-planner（仅 NOTE 白名单，由调用方在具体 handler 中二次校验）
      - novel-v2-crafter / v2-crafter（迁移期遗留别名，兼容旧调用）
      - script（迁移脚本 / CLI 直调）
      - fix-asymmetry（自动补齐反向边）
      - novel-tool（统一工具适配层）
      - web-ui（Web 界面）

    禁止的 actor：orchestrator（编排层应通过 novel-writer）或其他未识别值

    Returns:
        None（允许）或 {"error": ..., "blocked_operation": ...}（拒绝，error 含修正指引）
    """
    if not _ORCHESTRATOR_WRITE_BLOCKED:
        return None

    ALLOWED_WRITE_ACTORS = {
        "novel-writer", "novel-v2-crafter", "v2-crafter",
        "novel-planner", "script", "fix-asymmetry", "novel-tool", "web-ui"
    }
    if actor not in ALLOWED_WRITE_ACTORS:
        return {
            "error": (
                f"不允许直接调用 {operation}（actor={actor}）。"
                f"叙事内容写操作必须通过 novel-writer 主 agent 执行。"
                f"请调度 task(subagent_type='novel-writer', load_skills=['novel-v2-core', 'novel-v2-writing'], ...)"
            ),
            "blocked_operation": operation,
        }
    return None


def check_planner_restriction(actor: str, operation: str, allowed_hint: str = "") -> Optional[dict]:
    """novel-planner 白名单二次校验（D17 物理强制）。

    check_write_permission 对 novel-planner 放行（其被允许以 note 为边界工作），
    具体 handler 仍需按操作二次校验。本函数统一拒绝文案——单一消息模板，
    消除 9 个 handler 内各自拼写的中文报错。

    Args:
        actor: 调用者标识
        operation: 操作名（如 graph.archive_unit）
        allowed_hint: 允许边界说明（如 "规划主 agent 只能创建 note"）；
                      为空时使用通用拒绝文案

    Returns:
        None（允许）或 {"error": ...}（拒绝，文案含 "novel-planner" 供测试断言）
    """
    if actor != "novel-planner":
        return None
    hint = allowed_hint or "规划主 agent 的写操作以 note 为边界，如需其他操作请切换到 novel-writer"
    return {"error": f"novel-planner 不允许执行 {operation}。{hint}"}


# ── 通用内容处理 ──────────────────────────────────────────────────────────

def _repair_content(content: str) -> str:
    """解析并修复 JSON 内容字符串，返回规范化的 JSON 字符串。"""
    if not content:
        return content
    try:
        from json_repair import loads as repair_loads
        content = json.dumps(repair_loads(content), ensure_ascii=False)
    except ModuleNotFoundError:
        # json_repair 未安装时不做修复
        pass
    except Exception:
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
    return content


def _parse_tags(tags_str: Optional[str]) -> Optional[List[str]]:
    """解析逗号分隔的标签字符串为列表，None 表示未提供。"""
    if not tags_str:
        return None
    return [t.strip() for t in tags_str.split(",") if t.strip()]


def _unit_to_dict(u) -> dict:
    """将 NarrativeUnit 转为标准 dict（供 handler 返回）。"""
    return {
        "id": u.id,
        "name": u.unit_name,
        "type": u.type.value if hasattr(u.type, "value") else str(u.type),
        "status": u.status.value if hasattr(u.status, "value") else str(u.status),
        "confidence": u.confidence,
        "tags": list(u.tags) if u.tags else [],
        "chapter": u.chapter_number,
        "version": u.version,
        "content": u.content,
        "created_at": str(u.created_at) if u.created_at else None,
        "updated_at": str(u.updated_at) if u.updated_at else None,
    }


def _validate_content_schema(unit_type, content: str) -> list:
    """校验 content JSON 是否符合该类型的字段 Schema，返回错误列表。"""
    if not content or not content.startswith("{"):
        return []
    try:
        from schemas import validate_content
        content_dict = json.loads(content)
        if not isinstance(content_dict, dict):
            return []
        return validate_content(unit_type, content_dict)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("content schema 校验异常（按无错误处理）: %s", e)
        return []


def _auto_detect_chapter(content: str, unit_name: str) -> Optional[int]:
    """自动推断章节号：从 content JSON 或单元名称提取。"""
    import re
    chapter = None
    if content and content.startswith("{"):
        try:
            content_dict = json.loads(content)
            if isinstance(content_dict, dict) and "chapter_number" in content_dict:
                chapter = int(content_dict["chapter_number"])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    if not chapter and unit_name:
        m = re.search(r'第(\d+)章', unit_name)
        if m:
            chapter = int(m.group(1))
    return chapter


def _chunk_source_path(c, project_root: str) -> str:
    """解析 CHUNK 单元正文的来源文件路径（用于去重与读取）。"""
    try:
        cd = json.loads(c.content) if isinstance(c.content, str) else (c.content or {})
    except (json.JSONDecodeError, ValueError):
        cd = {}
    slice_info = cd.get("slice_info")
    if slice_info:
        sp = slice_info.get("文件", "")
        if sp:
            return str(Path(project_root) / sp)
    source_path = cd.get("file_path", "")
    if source_path:
        return str(Path(project_root) / source_path)
    return ""


def _read_chunk_text(c, project_root: str) -> str:
    """从 CHUNK 单元读取正文文本。"""
    src = _chunk_source_path(c, project_root)
    if src and os.path.exists(src):
        return Path(src).read_text(encoding="utf-8")
    return ""


# ── 关系类型解析 ──────────────────────────────────────────────────────────

def _resolve_rel_type(rel_type: str):
    """解析关系类型：先按 name 查，再按 value 查，都失败时返回 RELATES_TO + 原始输入作为 label。"""
    from graph_schema import RelationType
    try:
        rtype = RelationType[rel_type.upper()]
        return rtype, ""
    except KeyError:
        try:
            rtype = RelationType(rel_type.lower())
            return rtype, ""
        except ValueError:
            # 非枚举值（如"师徒""母子"）→ 降级为 RELATES_TO（关联容器），原始输入存为语义标签
            return RelationType.RELATES_TO, rel_type


# 公开导出（供 handlers_*.py 导入）
__all__ = [
    "ensure_sys_path",
    "_SHARED_DIR", "_V2_DIR",
    "_find_novels_root", "NOVELS_ROOT", "_resolve_project",
    "_paginate",
    "_derive_progress", "_vol_num", "_vol_name",
    "set_orchestrator_write_blocked", "check_write_permission",
    "check_planner_restriction",
    "_repair_content", "_parse_tags", "_unit_to_dict",
    "_validate_content_schema", "_auto_detect_chapter",
    "_chunk_source_path", "_read_chunk_text",
    "_resolve_rel_type",
]