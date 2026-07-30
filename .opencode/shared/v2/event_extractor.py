"""
event_extractor.py — 焦点内容 → TEMPORAL_EVENT 事件抽取层

职责：
  在 focus content 被写入 graph 后，自动解析 content 中的结构化信息，
  提取实体状态变化，创建对应的 TEMPORAL_EVENT 节点。

设计原则：
  - 不做文本推断：只解析 content 中已明确的结构化字段（cast / events / key_events）
  - 不与 LLM 争辩：content 中有什么就抽什么，不猜测隐含事件
  - 增量友好：每次只处理一个单元，不扫描全局
  - 幂等：同一内容重复调用不会重复创建事件

使用：
    extractor = EventExtractor(store)
    events = extractor.extract(unit_id, content, unit_type)
    for evt in events:
        store.create_unit(type=TEMPORAL_EVENT, content=evt, ...)
        store.add_relation(entity_id, event_id, HAS_EVENT)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict

from graph_schema import UnitType, UnitStatus, RelationType
from graph_store import GraphStore
from type_registry import TypeRegistry
from time_utils import get_story_time

logger = logging.getLogger(__name__)


# ── 抽取结果的数据类 ─────────────────────────────────────────────────────


@dataclass
class ExtractedEvent:
    """EventExtractor 的单条输出——准备写入 TEMPORAL_EVENT 节点的内容字典。"""

    # 事件核心
    event_type: str                         # "scene_event" | "cultivation" | "plot_event" | ...
    summary: str                            # 事件简述

    # 时间坐标（由编排层/调用者提供默认值，EventExtractor 尝试从 content 中读取更精确的值）
    ordinal: Optional[float] = None
    precision: str = "vague"                # exact / chapter / volume / vague
    time_label: str = ""

    # 关联实体
    source_entity_id: str = ""              # 关联的主实体 ID（将建 HAS_EVENT 边）
    source_entity_name: str = ""            # 关联的主实体名称
    characters: List[str] = field(default_factory=list)  # 参与者名列表
    location: str = ""                      # 地点名称

    # 状态变化（可选）
    state_before: Optional[str] = None      # 变化前的状态
    state_after: Optional[str] = None       # 变化后的状态

    # 额外详情
    details: Dict[str, Any] = field(default_factory=dict)

    def to_temporal_content(self) -> Dict[str, Any]:
        """转为 TEMPORAL_EVENT 节点的 content JSON。"""
        d: Dict[str, Any] = {
            "event_type": self.event_type,
            "summary": self.summary,
            "ordinal": self.ordinal,
            "precision": self.precision,
            "time_label": self.time_label,
            "location": self.location,
        }
        if self.state_before is not None:
            d["state_before"] = self.state_before
        if self.state_after is not None:
            d["state_after"] = self.state_after
        if self.details:
            d["details"] = self.details
        return d


# ── 事件抽取器 ──────────────────────────────────────────────────────────


class EventExtractor:
    """
    从焦点 content 中抽取实体状态变化，生成 ExtractedEvent 列表。

    用法：
        extractor = EventExtractor(store)
        events = extractor.extract(unit_id, content, unit_type, default_ordinal=2500)
        for evt in events:
            ...  # 创建 TEMPORAL_EVENT 节点
    """

    def __init__(
        self,
        store: GraphStore,
        registry: Optional[TypeRegistry] = None,
    ):
        self.store = store
        self.registry = registry or TypeRegistry.get_global()
        self._stored_old_content: Optional[dict] = None

    # ── 主入口 ───────────────────────────────────────────────────────────

    def extract(
        self,
        unit_id: str,
        content: Any,
        unit_type: UnitType,
        *,
        old_content: Any = None,
        default_ordinal: Optional[float] = None,
        default_precision: str = "vague",
        actor: str = "event_extractor",
    ) -> List[ExtractedEvent]:
        """
        从 content 中抽取事件。

        Args:
            unit_id: 刚刚写入的单元 ID
            content: 写入的 content（dict、str 或 None）
            unit_type: 单元类型
            old_content: 写入前的旧 content（用于 diff 检测变化，如修为变化）
            default_ordinal: 默认 ordinal（由调用者根据焦点上下文提供）
            default_precision: 默认精度
            actor: 操作者标识

        Returns:
            ExtractedEvent 列表（空列表 = 没有可抽取的事件）
        """
        parsed = self._parse_content(content)
        if not parsed:
            return []

        type_handlers = {
            UnitType.SCENE: self._extract_scene,
            UnitType.CHUNK: self._extract_chunk,
            UnitType.CHARACTER_ARC: self._extract_character_arc,
            UnitType.PLOT_THREAD: self._extract_plot_thread,
            UnitType.WORLD_RULE: self._extract_world_rule,
        }

        handler = type_handlers.get(unit_type)
        if handler is None:
            return []

        # 获取单元自身的信息
        unit = self.store.get_unit(unit_id)
        unit_name = unit.unit_name if unit else "?"

        # 如果调用者提供了 old_content，用它替换 store 中的值
        # （因为 store 中已经是新 content，diff 检测会失效）
        if old_content is not None:
            self._stored_old_content = self._parse_content(old_content)
        else:
            self._stored_old_content = None

        events = handler(unit_id, unit_name, parsed, default_ordinal=default_ordinal)

        # 为没有 ordinals 的事件应用默认值
        for evt in events:
            if evt.ordinal is None:
                evt.ordinal = default_ordinal
                evt.precision = default_precision

        return events

    # ── SCENE ──────────────────────────────────────────────────────────

    def _extract_scene(
        self,
        unit_id: str,
        unit_name: str,
        content: dict,
        *,
        default_ordinal: Optional[float] = None,
    ) -> List[ExtractedEvent]:
        """从 SCENE content 抽取事件。"""
        events: List[ExtractedEvent] = []

        # 1. 场景本身 → scene_event
        ordinal = self._resolve_ordinal(unit_id, content, default_ordinal)
        time_label = self._field_str(content, "time_text", "时间")
        location = self._field_str(content, "location", "地点")
        summary = self._field_str(content, "one_line_summary", "一句话概要")
        cast = self._extract_cast(content)

        scene_event = ExtractedEvent(
            event_type="scene_event",
            summary=summary or unit_name,
            ordinal=ordinal[0] if ordinal else default_ordinal,
            precision=ordinal[1] if ordinal else "vague",
            time_label=time_label,
            source_entity_id=unit_id,
            source_entity_name=unit_name,
            characters=[c["name"] for c in cast if isinstance(c, dict) and c.get("name")],
            location=location,
            details={"subtype": self._field_str(content, "subtype", "子类型")},
        )
        events.append(scene_event)

        # 2. 每个 cast 成员的状态变化
        for c in cast:
            if not isinstance(c, dict):
                continue
            char_name = c.get("name", "")
            role_status = c.get("role_status", "")
            if not char_name or not role_status:
                continue

            # 查找该角色上一次的状态
            prev_status = self._find_previous_cast_status(char_name, unit_id)

            events.append(ExtractedEvent(
                event_type="character_state",
                summary=f"{char_name} 状态：{role_status}",
                ordinal=ordinal[0] if ordinal else default_ordinal,
                precision=ordinal[1] if ordinal else "vague",
                time_label=time_label,
                source_entity_id=unit_id,
                source_entity_name=unit_name,
                characters=[char_name],
                location=location,
                state_before=prev_status,
                state_after=role_status,
                details={"scene_name": unit_name},
            ))

        # 3. 场景中的关键时间点（key_moments）
        key_moments = self._field_list(content, "key_moments", "关键情节")
        for i, km in enumerate(key_moments):
            if not isinstance(km, dict):
                continue
            km_type = km.get("type", "key_moment")
            km_desc = km.get("description", km.get("event", ""))
            if not km_desc:
                continue
            km_ordinal = km.get("ordinal", ordinal[0] if ordinal else None)
            km_precision = km.get("precision", ordinal[1] if ordinal else "vague")
            km_characters = km.get("characters", [])

            events.append(ExtractedEvent(
                event_type=km_type,
                summary=km_desc,
                ordinal=float(km_ordinal) if km_ordinal is not None else None,
                precision=km_precision,
                time_label=km.get("time_label", time_label),
                source_entity_id=unit_id,
                source_entity_name=unit_name,
                characters=km_characters if isinstance(km_characters, list) else [],
                location=km.get("location", location),
                details={"moment_index": i},
            ))

        return events

    # ── CHUNK ──────────────────────────────────────────────────────────

    def _extract_chunk(
        self,
        unit_id: str,
        unit_name: str,
        content: dict,
        *,
        default_ordinal: Optional[float] = None,
    ) -> List[ExtractedEvent]:
        """从 CHUNK content 抽取事件。

        CHUNK（正文片段）通常不直接包含结构化事件，但可以包含
        time_text / time_ordinal 字段。如果有，就生成一个 scene_event。
        """
        time_text = self._field_str(content, "time_text", "时间")
        if not time_text and default_ordinal is None:
            return []

        ordinal = self._resolve_ordinal(unit_id, content, default_ordinal)
        summary = self._field_str(content, "summary", "概要") or unit_name

        return [ExtractedEvent(
            event_type="scene_event",
            summary=summary,
            ordinal=ordinal[0] if ordinal else default_ordinal,
            precision=ordinal[1] if ordinal else "vague",
            time_label=time_text,
            source_entity_id=unit_id,
            source_entity_name=unit_name,
            characters=[],
            location=self._field_str(content, "location", "地点"),
        )]

    # ── CHARACTER_ARC ────────────────────────────────────────────────

    def _extract_character_arc(
        self,
        unit_id: str,
        unit_name: str,
        content: dict,
        *,
        default_ordinal: Optional[float] = None,
    ) -> List[ExtractedEvent]:
        """从 CHARACTER_ARC content 抽取事件：修为变化、弧光变化、events[]。"""
        events: List[ExtractedEvent] = []

        # 获取旧 content 用于 diff
        old_content = self._get_old_content(unit_id)

        # 1. 修为/能力变化（cultivation）
        old_realm = self._get_nested_str(old_content, "能力设定", "修为") if old_content else None
        new_realm = self._get_nested_str(content, "能力设定", "修为")
        if new_realm and new_realm != old_realm:
            events.append(ExtractedEvent(
                event_type="cultivation",
                summary=f"{unit_name} 修为变化：{old_realm or '无'} → {new_realm}",
                ordinal=default_ordinal,
                precision="vague",
                time_label="",
                source_entity_id=unit_id,
                source_entity_name=unit_name,
                characters=[unit_name],
                state_before=old_realm,
                state_after=new_realm,
                details={"field": "realm", "old_realm": old_realm, "new_realm": new_realm},
            ))

        # 2. 阵营/势力变化
        old_camp = self._get_nested_str(old_content, "能力设定", "阵营") if old_content else None
        new_camp = self._get_nested_str(content, "能力设定", "阵营")
        if new_camp and new_camp != old_camp:
            events.append(ExtractedEvent(
                event_type="allegiance",
                summary=f"{unit_name} 阵营变化：{old_camp or '无'} → {new_camp}",
                ordinal=default_ordinal,
                precision="vague",
                source_entity_id=unit_id,
                source_entity_name=unit_name,
                characters=[unit_name],
                state_before=old_camp,
                state_after=new_camp,
                details={"old_camp": old_camp, "new_camp": new_camp},
            ))

        # 3. 弧线起止状态变化
        old_arc = self._get_nested_str(old_content, "character_arc_detail", "arc_start_state") if old_content else None
        new_arc = self._get_nested_str(content, "character_arc_detail", "arc_start_state")
        if new_arc and new_arc != old_arc:
            events.append(ExtractedEvent(
                event_type="arc_change",
                summary=f"{unit_name} 弧线起点变化",
                ordinal=default_ordinal,
                precision="vague",
                source_entity_id=unit_id,
                source_entity_name=unit_name,
                characters=[unit_name],
                state_before=old_arc,
                state_after=new_arc,
                details={"field": "arc_start_state"},
            ))

        # 4. 关键事件（events[] / 关键事件）
        raw_events = self._field_list(content, "events", "关键事件")
        for i, item in enumerate(raw_events):
            if not isinstance(item, dict):
                continue
            evt = self._build_from_arc_event(item, unit_id, unit_name, i)
            if evt:
                events.append(evt)

        return events

    def _build_from_arc_event(
        self,
        item: dict,
        unit_id: str,
        unit_name: str,
        index: int,
    ) -> Optional[ExtractedEvent]:
        """从 character_arc.events[] 的单个条目构建事件。"""
        ordinal = self._field_num(item, "ordinal", "序数")
        type_label = self._field_str(item, "type", "类型", "事件")
        event_type = self._infer_event_type(type_label)
        summary = type_label or self._field_str(item, "event", "事件") or f"事件#{index}"
        location = self._field_str(item, "location", "地点")
        details = {}

        realm = self._field_str(item, "realm", "修为")
        age = self._field_num(item, "age", "年龄")
        if realm:
            details["realm"] = realm
        if age is not None:
            details["age"] = age

        return ExtractedEvent(
            event_type=event_type,
            summary=summary,
            ordinal=ordinal,
            precision="exact" if ordinal is not None else "vague",
            time_label=f"#{ordinal:.1f}" if ordinal is not None else "",
            source_entity_id=unit_id,
            source_entity_name=unit_name,
            characters=[unit_name],
            location=location,
            details=details,
        )

    # ── PLOT_THREAD ──────────────────────────────────────────────────

    def _extract_plot_thread(
        self,
        unit_id: str,
        unit_name: str,
        content: dict,
        *,
        default_ordinal: Optional[float] = None,
    ) -> List[ExtractedEvent]:
        """从 PLOT_THREAD 的 key_events[] 提取 plot_event。"""
        events: List[ExtractedEvent] = []

        raw_events = self._field_list(content, "key_events", "关键事件")
        for i, item in enumerate(raw_events):
            if not isinstance(item, dict):
                continue

            ch = self._field_num(item, "chapter_number", "章节")
            if ch is not None:
                ordinal = float(ch) * 10000
            else:
                ordinal = default_ordinal

            summary = self._field_str(item, "event", "事件")
            if not summary:
                continue

            events.append(ExtractedEvent(
                event_type="plot_event",
                summary=summary,
                ordinal=ordinal,
                precision="chapter" if ch is not None else "vague",
                time_label=f"第{int(ch)}章" if ch is not None else "",
                source_entity_id=unit_id,
                source_entity_name=unit_name,
                location="",
                details={"chapter": int(ch)} if ch is not None else {},
            ))

        return events

    # ── WORLD_RULE ───────────────────────────────────────────────────

    def _extract_world_rule(
        self,
        unit_id: str,
        unit_name: str,
        content: dict,
        *,
        default_ordinal: Optional[float] = None,
    ) -> List[ExtractedEvent]:
        """从 WORLD_RULE 的纪年事件字段提取 chronicle。"""
        event_location = self._field_str(content, "event_location", "位置")
        event_volume = self._field_num(content, "event_volume", "所属卷")
        if not event_location and event_volume is None:
            return []

        ordinal = float(event_volume) * 1000000 if event_volume is not None else default_ordinal

        details = {}
        if event_location:
            details["location"] = event_location
        if event_volume is not None:
            details["volume"] = event_volume

        return [ExtractedEvent(
            event_type="chronicle",
            summary=event_location or unit_name,
            ordinal=ordinal,
            precision="volume" if event_volume is not None else "vague",
            time_label=f"第{int(event_volume)}卷" if event_volume else "",
            source_entity_id=unit_id,
            source_entity_name=unit_name,
            location=event_location,
            details=details,
        )]

    # ── 辅助方法 ────────────────────────────────────────────────────

    def _resolve_ordinal(
        self,
        unit_id: str,
        content: dict,
        default_ordinal: Optional[float] = None,
    ) -> Optional[Tuple[float, str]]:
        """确定 ordinal，优先级：content.ordinal > extra.time.ordinal > default。

        Returns:
            (ordinal, precision) 或 None
        """
        # 1. content 中的显式序数
        ordinal = self._field_num(content, "ordinal", "time_ordinal", "时间序数")
        if ordinal is not None:
            return (ordinal, "exact")

        # 2. extra.time（自动同步的序数）
        unit = self.store.get_unit(unit_id)
        if unit:
            st = get_story_time(unit)
            if st:
                st_ord = st.get("ordinal")
                if st_ord is not None:
                    return (float(st_ord), st.get("precision", "exact"))

        # 3. 从 chapter_number 推导
        if unit:
            ch = getattr(unit, "chapter_number", None)
            if ch:
                return (float(ch) * 10000 + 0.5, "chapter")

        # 4. 默认
        if default_ordinal is not None:
            return (default_ordinal, "vague")

        return None

    def _find_previous_cast_status(
        self,
        character_name: str,
        current_scene_id: str,
    ) -> Optional[str]:
        """查找角色在之前场景中的 role_status。

        通过遍历 SCENE 单元（按章节号倒序），找包含该角色且 ordinal
        小于当前场景的最近一个场景。
        """
        # 收集所有活跃的 SCENE 单元
        scenes = self.store.find_units(type=UnitType.SCENE)
        # 也查 CHUNK 单元
        chunks = self.store.find_units(type=UnitType.CHUNK)
        candidates = list(scenes) + list(chunks)

        latest_scene = None
        latest_ordinal: float = -1.0

        # 获取当前场景的 ordinal 作为上限
        current_unit = self.store.get_unit(current_scene_id)
        current_ordinal: float = 0.0
        if current_unit:
            st = get_story_time(current_unit)
            if st:
                ord_val = st.get("ordinal")
                if ord_val is not None:
                    current_ordinal = float(ord_val)

        for candidate in candidates:
            if candidate.id == current_scene_id:
                continue

            # 检查该角色的名字是否在场景的 cast 中
            content = self._parse_content(candidate.content)
            if not content:
                continue
            cast = self._extract_cast(content)
            found = False
            for c in cast:
                if isinstance(c, dict) and c.get("name") == character_name:
                    found = True
                    break
                if isinstance(c, str) and c == character_name:
                    found = True
                    break
            if not found:
                continue

            # 获取该场景的 ordinal
            st = get_story_time(candidate)
            ord_val = float(st.get("ordinal", 0)) if st else 0

            # 必须严格在当前场景之前或相等（避免找到未来的场景）
            if ord_val > current_ordinal:
                continue

            if ord_val > latest_ordinal:
                latest_ordinal = ord_val
                latest_scene = candidate

        if not latest_scene:
            return None

        # 解析该场景的 cast，找该角色的 role_status
        scene_content = self._parse_content(latest_scene.content)
        if not scene_content:
            return None

        cast = self._extract_cast(scene_content)
        for c in cast:
            if isinstance(c, dict) and c.get("name") == character_name:
                return c.get("role_status", "")

        return None

    def _get_old_content(self, unit_id: str) -> Optional[dict]:
        """获取单元写入前的 content。

        优先使用调用者传入的 old_content（用于 diff 检测），
        fallback 到从 store 读取（注意 store 中的值已被新内容覆盖）。"""
        if self._stored_old_content is not None:
            return self._stored_old_content
        unit = self.store.get_unit(unit_id)
        if not unit:
            return None
        return self._parse_content(unit.content)

    @staticmethod
    def _infer_event_type(raw_type: str) -> str:
        """从中文事件类型推导标准化 event_type。"""
        if not raw_type:
            return "note"
        type_map = {
            "cultivation": ("修炼", "突破", "晋级", "渡劫", "悟道"),
            "battle": ("战斗", "厮杀", "对决", "切磋", "斗法"),
            "plot_event": ("剧情", "事件", "转折", "发现"),
            "relationship": ("结交", "决裂", "仇视", "联盟"),
        }
        for etype, keywords in type_map.items():
            for kw in keywords:
                if kw in raw_type:
                    return etype
        return "note"

    @staticmethod
    def _extract_cast(content: dict) -> list:
        """从 content 中提取 cast/出场角色。"""
        raw = EventExtractor._field_list(content, "cast", "出场角色")
        return raw

    # ── 中英文兼容字段读取 ────────────────────────────────────────────

    @staticmethod
    def _field(d: dict, *keys: str) -> Any:
        for k in keys:
            if k in d:
                return d[k]
        return None

    @staticmethod
    def _field_str(d: dict, *keys: str) -> str:
        val = EventExtractor._field(d, *keys)
        return str(val) if val else ""

    @staticmethod
    def _field_list(d: dict, *keys: str) -> list:
        val = EventExtractor._field(d, *keys)
        return val if isinstance(val, list) else []

    @staticmethod
    def _field_num(d: dict, *keys: str) -> Optional[float]:
        val = EventExtractor._field(d, *keys)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_content(content: Any) -> dict:
        if not content:
            return {}
        if isinstance(content, dict):
            return content
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}

    @staticmethod
    def _get_nested_str(d: dict, *keys: str) -> Optional[str]:
        """从嵌套 dict 中安全读取字符串值。"""
        current = d
        for k in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(k)
            if current is None:
                return None
        return str(current) if current is not None else None
