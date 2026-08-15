"""
时间工具函数 — 统一的 story time 读写接口。

所有叙事单元类型的故事时间统一存储在 NarrativeUnit.extra["time"] 中。
约定键名：time = {label: str, ordinal: float|None, precision: str}
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any

from graph_schema import NarrativeUnit


# ── 常量 ──────────────────────────────────────────────────────────────────────

STORY_TIME_KEY = "time"

ORDINAL_BASE = 10000   # 每章预留 10000 的序数空间
ORDINAL_OFFSET = 0.5   # 基线偏移，允许在第一个场景之前插入
VOLUME_BASE = 1000000  # 卷级序数基数（WORLD_RULE 纪年事件用）：每卷预留 1000000 的序数空间


# ── getter / setter ──────────────────────────────────────────────────────────


def get_story_time(unit: NarrativeUnit) -> Optional[Dict[str, Any]]:
    """获取故事时间 dict，不存在或格式错误时返回 None"""
    extra = unit.extra or {}
    ti = extra.get(STORY_TIME_KEY)
    return ti if isinstance(ti, dict) else None


def get_story_ordinal(unit: NarrativeUnit) -> Optional[float]:
    """获取故事时间序数，不存在返回 None"""
    ti = get_story_time(unit)
    if ti is None:
        return None
    val = ti.get("ordinal")
    if val is not None:
        return float(val)
    return None


def get_story_label(unit: NarrativeUnit) -> str:
    """获取人类可读时间标签，不存在返回空字符串"""
    ti = get_story_time(unit)
    if ti is None:
        return ""
    return str(ti.get("label", ""))


def get_story_precision(unit: NarrativeUnit) -> str:
    """获取精度标签，默认 'vague'"""
    ti = get_story_time(unit)
    if ti is None:
        return "vague"
    return str(ti.get("precision", "vague"))


def set_story_time(
    unit: NarrativeUnit,
    label: str,
    ordinal: Optional[float] = None,
    precision: str = "vague",
) -> None:
    """设置任意单元类型的故事时间（写入 extra['time']）"""
    if STORY_TIME_KEY not in unit.extra:
        unit.extra[STORY_TIME_KEY] = {}
    unit.extra[STORY_TIME_KEY] = {
        "label": label,
        "ordinal": ordinal,
        "precision": precision,
    }


# ── 排序 / 比较 ──────────────────────────────────────────────────────────────


def sort_by_story_time(units: List[NarrativeUnit]) -> List[NarrativeUnit]:
    """
    按故事时间排序（有 ordinal 的在前，无的在后）。
    同 ordinal 时按 precision 排序（exact < same < approximate < override < vague）。
    """
    def _key(u: NarrativeUnit):
        ordinal = get_story_ordinal(u)
        precision = get_story_precision(u)
        _precision_order = {"exact": 0, "same": 1, "approximate": 2, "override": 3, "vague": 4}
        prec_key = _precision_order.get(precision, 99)
        if ordinal is not None:
            return (0, ordinal, prec_key, u.unit_name or "")
        else:
            return (1, 0, prec_key, u.unit_name or "")

    return sorted(units, key=_key)


# ── 自动同步 content → extra.time ──────────────────────────────────────────


def auto_sync_story_time(unit: NarrativeUnit) -> bool:
    """
    从 content JSON 自动同步时间字段到 extra["time"]。
    仅在 extra["time"] 为空且 content 中有时间字段时写入。
    返回 True 表示有变更。

    这是 create_unit / update_unit 的自动钩子，确保 LLM 写入 content 后
    extra.time 不会被遗漏，使 TemporalMatcher 和 TimelineLedger 能读到标准化数据。
    """
    if get_story_time(unit) is not None:
        return False  # 已有 extra.time，不动

    content = unit.content
    if not content:
        return False

    try:
        import json
        content_dict = json.loads(content) if isinstance(content, str) else (content if isinstance(content, dict) else {})
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(content_dict, dict):
        return False

    label = content_dict.get("time_text", "") or ""
    ordinal = content_dict.get("time_ordinal")

    if not label and ordinal is None:
        return False  # content 中没有时间信息

    precision = "vague"
    if ordinal is not None:
        try:
            ordinal = float(ordinal)
            precision = "exact"
        except (TypeError, ValueError):
            ordinal = None

    set_story_time(unit, label=label, ordinal=ordinal, precision=precision)
    return True


# ── 序数自动计算 ────────────────────────────────────────────────────────────


def derive_ordinal(chapter: int, position: int, sub_position: int = 0) -> float:
    """
    序数派生唯一入口。

    公式：ordinal = chapter * ORDINAL_BASE + position * 100 + sub_position
    """
    return chapter * ORDINAL_BASE + position * 100 + sub_position


def compute_ordinal(chapter_number: int, scene_position: int) -> float:
    """
    根据章节号和章内场景位置计算自动序数。

    公式：ordinal = chapter_number * ORDINAL_BASE + scene_position * 100 + ORDINAL_OFFSET
    """
    return derive_ordinal(chapter_number, scene_position, sub_position=ORDINAL_OFFSET)


def next_ordinal(
    store,
    unit: NarrativeUnit,
    chapter: int,
    registry=None,
) -> float:
    """
    计算下一可用序数：同章场景按创建时间排序定位。

    委托 UnifiedTimelineIndex（懒导入避免循环依赖），保证与时间线索引一致。
    """
    from unified_timeline import UnifiedTimelineIndex
    index = UnifiedTimelineIndex(store, registry)
    return index.auto_ordinal(unit, chapter)


# ── 迁移 ─────────────────────────────────────────────────────────────────────


def backfill_story_time(unit: NarrativeUnit) -> bool:
    """
    从旧格式迁移到 extra.time。仅在 extra.time 为空时执行。
    
    迁移来源（按单元类型）：
    - SCENE / CHARACTER_ARC / PLOT_THREAD / WORLD_RULE / NOTE: content["时间"]
    - SCENE: content["时间序数"] → extra.time.ordinal
    - PLOT_THREAD: 关键事件[0]["章节"] → 推断 ordinal
    - WORLD_RULE 纪年事件: content["事件"] + content["时间"]
    
    返回 True 表示有变更。
    """
    if get_story_time(unit) is not None:
        return False

    import json
    label = ""
    ordinal = None
    precision = "vague"

    try:
        content = json.loads(unit.content) if isinstance(unit.content, str) else (unit.content or {})
        if not isinstance(content, dict):
            return False

        # 通用时间字段
        label = content.get("时间", "") or ""

        # 序数提取
        ordinal = content.get("time_ordinal")
        if ordinal is not None:
            ordinal = float(ordinal)
            precision = "exact"

        # WORLD_RULE 纪年事件：事件内容也可作为时间标签的一部分
        if label and content.get("事件"):
            label = f"{label} — {content['事件']}"

        # PLOT_THREAD：从关键事件推断时间
        if not label:
            events = content.get("key_events", [])
            if isinstance(events, list) and events:
                first = events[0]
                if isinstance(first, dict):
                    evt_label = first.get("event", "") or ""
                    evt_ch = first.get("chapter_number")
                    if evt_label:
                        label = evt_label
                    if evt_ch is not None:
                        ordinal = compute_ordinal(int(evt_ch), 0)
                        precision = "approximate"

        # CHARACTER_ARC：角色弧线描述可能含时间信息
        if not label:
            arc = content.get("character_arc_detail", {})
            if isinstance(arc, dict):
                start_state = arc.get("arc_start_state", "")
                if start_state:
                    label = start_state

    except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
        pass

    if label:
        set_story_time(unit, label=label, ordinal=ordinal, precision=precision)
        return True
    return False


# ── TimeUtils 类 ─────────────────────────────────────────────────────────────
#
# 时间操作唯一读取/派生入口。模块级函数保留为薄包装（向后兼容，
# graph_store.py 等仍以模块函数方式导入）。


class TimeUtils:
    """时间工具类 — 统一时间操作入口（读取 / 派生 / 排序）。"""

    STORY_TIME_KEY = STORY_TIME_KEY
    ORDINAL_BASE = ORDINAL_BASE
    ORDINAL_OFFSET = ORDINAL_OFFSET

    # ── getter / setter ──────────────────────────────────────────────────

    @staticmethod
    def get_story_time(unit: NarrativeUnit) -> Optional[Dict[str, Any]]:
        """获取故事时间 dict，不存在或格式错误时返回 None"""
        return get_story_time(unit)

    @staticmethod
    def get_story_ordinal(unit: NarrativeUnit) -> Optional[float]:
        """获取故事时间序数，不存在返回 None"""
        return get_story_ordinal(unit)

    @staticmethod
    def get_story_label(unit: NarrativeUnit) -> str:
        """获取人类可读时间标签，不存在返回空字符串"""
        return get_story_label(unit)

    @staticmethod
    def get_story_precision(unit: NarrativeUnit) -> str:
        """获取精度标签，默认 'vague'"""
        return get_story_precision(unit)

    @staticmethod
    def set_story_time(
        unit: NarrativeUnit,
        label: str,
        ordinal: Optional[float] = None,
        precision: str = "vague",
    ) -> None:
        """设置任意单元类型的故事时间（写入 extra['time']）"""
        set_story_time(unit, label=label, ordinal=ordinal, precision=precision)

    # ── 排序 / 比较 ──────────────────────────────────────────────────────

    @staticmethod
    def sort_by_story_time(units: List[NarrativeUnit]) -> List[NarrativeUnit]:
        """按故事时间排序（有 ordinal 的在前，无的在后）"""
        return sort_by_story_time(units)

    # ── 自动同步 ─────────────────────────────────────────────────────────

    @staticmethod
    def auto_sync_story_time(unit: NarrativeUnit) -> bool:
        """从 content JSON 自动同步时间字段到 extra["time"]。返回 True 表示有变更。"""
        return auto_sync_story_time(unit)

    @staticmethod
    def backfill_story_time(unit: NarrativeUnit) -> bool:
        """从旧格式迁移到 extra.time。返回 True 表示有变更。"""
        return backfill_story_time(unit)

    # ── 序数派生 ─────────────────────────────────────────────────────────

    @staticmethod
    def derive_ordinal(chapter: int, position: int, sub_position: int = 0) -> float:
        """
        序数派生唯一入口。

        公式：ordinal = chapter * ORDINAL_BASE + position * 100 + sub_position
        """
        return derive_ordinal(chapter, position, sub_position)

    @staticmethod
    def compute_ordinal(chapter_number: int, scene_position: int) -> float:
        """根据章节号和章内场景位置计算自动序数（含基线偏移 0.5）。"""
        return compute_ordinal(chapter_number, scene_position)

    @staticmethod
    def next_ordinal(
        store,
        unit: NarrativeUnit,
        chapter: int,
        registry=None,
    ) -> float:
        """
        计算下一可用序数：同章场景按创建时间排序定位。
        委托 UnifiedTimelineIndex，保证与时间线索引一致。
        """
        return next_ordinal(store, unit, chapter, registry)
