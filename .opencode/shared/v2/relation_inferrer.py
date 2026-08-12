"""
relation_inferrer.py — V2 关系推断引擎

在写作时自动从叙事单元的内容文本中提取关系，填补 GraphStore 的关系网络。
不侵入 GraphStore，作为一个可替换的策略层存在。

核心策略：
1. 规则引擎（同章节角色自动关联）
2. 内容扫描（全文匹配已知实体名）
3. 反向扫描（新角色创建后扫描已有内容）

使用方式：
    from relation_inferrer import RelationInferrer
    inferrer = RelationInferrer(store)
    inferrer.infer_on_create(new_unit)   # 创建后自动推断
    inferrer.batch_infer_all()           # 全量回填
"""

from __future__ import annotations

import sys
import os
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

V2_DIR = os.path.abspath(os.path.dirname(__file__))
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)

from graph_schema import (
    NarrativeUnit, UnitType, UnitStatus, RelationType,
    EventType, get_unit_chapter,
)
from graph_store import GraphStore
from render_utils import extract_entity_refs


# ── 结构层级类型集合 ────────────────────────────────────────────────
_STRUCTURE_TYPES = {UnitType.OUTLINE, UnitType.ARC_PLAN, UnitType.VOLUME_PLAN,
                    UnitType.CHAPTER_PLAN}


# ── 推断规则表 ─────────────────────────────────────────────────────

# 每条规则定义：(源类型, 目标类型, 产出关系类型, 方向, 权重)
# direction: "source_to_target" | "target_to_source"
INFER_RULES: list[tuple[UnitType, UnitType, RelationType, str, float]] = [
    # 场景 → 角色：角色参与场景
    (UnitType.SCENE, UnitType.CHARACTER_ARC, RelationType.PARTICIPATES_IN,
     "target_to_source", 0.5),
    # 场景 → 情节线：场景实现情节线
    (UnitType.SCENE, UnitType.PLOT_THREAD, RelationType.IMPLEMENTS,
     "source_to_target", 0.5),
    # 正文 → 场景：正文属于场景
    (UnitType.CHUNK, UnitType.SCENE, RelationType.BELONGS_TO,
     "source_to_target", 0.5),
    # 正文 → 角色：正文涉及角色
    (UnitType.CHUNK, UnitType.CHARACTER_ARC, RelationType.REFERENCES,
     "source_to_target", 0.3),
    # 角色 → 世界观：角色关联世界观规则
    (UnitType.CHARACTER_ARC, UnitType.WORLD_RULE, RelationType.REFERENCES,
     "source_to_target", 0.4),
    # 情节线 → 世界观：情节线关联世界观
    (UnitType.PLOT_THREAD, UnitType.WORLD_RULE, RelationType.REFERENCES,
     "source_to_target", 0.4),
    # 场景 → 世界观：场景涉及世界观规则
    (UnitType.SCENE, UnitType.WORLD_RULE, RelationType.REFERENCES,
     "source_to_target", 0.3),
    # 笔记 → 任何：笔记引用其他单元
    (UnitType.NOTE, None, RelationType.REFERENCES,
     "source_to_target", 0.2),
    # ── 新型关系推断规则 ──────────────────────────────────────────────
    # 场景 → 世界观（地点）：场景位于某地
    (UnitType.SCENE, UnitType.WORLD_RULE, RelationType.LOCATED_AT,
     "source_to_target", 0.5),
    # 角色 → 世界观（地点）：角色位于某地
    (UnitType.CHARACTER_ARC, UnitType.WORLD_RULE, RelationType.LOCATED_AT,
     "source_to_target", 0.3),
    # 世界观 → 世界观（地域层级）：地区包含子地区
    (UnitType.WORLD_RULE, UnitType.WORLD_RULE, RelationType.CONTAINS,
     "source_to_target", 0.5),
    # 角色 → 角色：关联关系（通用容器，具体语义见 label）
    (UnitType.CHARACTER_ARC, UnitType.CHARACTER_ARC, RelationType.RELATES_TO,
     "source_to_target", 0.3),
    # NOTE: CONTROLS / MEMBER_OF 不做子串推断——子串出现≠存在控制/归属关系。
    # 强语义关系由显式字段（character_arc.affiliation / world_rule 声明）或 LLM 建边承载。
    # ── OUTLINE / ARC_PLAN / VOLUME_PLAN / CHAPTER_PLAN 推断规则 ─────
    (UnitType.OUTLINE, UnitType.PLOT_THREAD, RelationType.IMPLEMENTS, "source_to_target", 0.5),
    (UnitType.ARC_PLAN, UnitType.PLOT_THREAD, RelationType.IMPLEMENTS, "source_to_target", 0.5),
    (UnitType.VOLUME_PLAN, UnitType.PLOT_THREAD, RelationType.IMPLEMENTS, "source_to_target", 0.5),
    (UnitType.CHAPTER_PLAN, UnitType.PLOT_THREAD, RelationType.IMPLEMENTS, "source_to_target", 0.5),
    (UnitType.OUTLINE, UnitType.SCENE, RelationType.PLANS, "source_to_target", 0.7),
    (UnitType.ARC_PLAN, UnitType.SCENE, RelationType.PLANS, "source_to_target", 0.7),
    (UnitType.VOLUME_PLAN, UnitType.SCENE, RelationType.PLANS, "source_to_target", 0.7),
    (UnitType.CHAPTER_PLAN, UnitType.SCENE, RelationType.PLANS, "source_to_target", 0.7),
    # 腔调 → 场景：腔调策略适用于场景
    (UnitType.NARRATIVE_VOICE, UnitType.SCENE, RelationType.REFERENCES,
     "source_to_target", 0.4),
    # 腔调 → 正文：腔调约束作用于正文
    (UnitType.NARRATIVE_VOICE, UnitType.CHUNK, RelationType.REFERENCES,
     "source_to_target", 0.3),
    # ── THEMATIC_MOTIF 推断规则 ────────────────────────────────────────────
    # 主题意象 → 场景：意象出现在场景
    (UnitType.THEMATIC_MOTIF, UnitType.SCENE, RelationType.REFERENCES,
     "source_to_target", 0.5),
    # 主题意象 → 角色：意象关联角色
    (UnitType.THEMATIC_MOTIF, UnitType.CHARACTER_ARC, RelationType.REFERENCES,
     "source_to_target", 0.4),
    # 主题意象 → 情节线：意象呼应情节
    (UnitType.THEMATIC_MOTIF, UnitType.PLOT_THREAD, RelationType.REFERENCES,
     "source_to_target", 0.3),
    # 主题意象 ↔ 主题意象：意象间对照/共振
    (UnitType.THEMATIC_MOTIF, UnitType.THEMATIC_MOTIF, RelationType.PARALLEL,
     "source_to_target", 0.3),
]


class RelationInferrer:
    """
    关系推断引擎。

    每次 create_unit 后调用 infer_on_create()，自动扫描内容建立关系。
    已存在的关系不会被重复创建（GraphStore.add_relation 自动去重）。
    """

    def __init__(self, store: GraphStore):
        self.store = store
        self._stats = {"created": 0, "skipped": 0}
        self._batch_mode = False

    # ── 公共 API ────────────────────────────────────────────────────

    def infer_on_create(self, unit: NarrativeUnit) -> int:
        """
        在创建/更新单元后调用，自动推断关系。
        返回本次新建的关系数。
        """
        count = 0
        # 0. 声明驱动实体引用建边：
        #    TypeRegistry entity_reference fact_fields（含 rel_type）为优先通道，
        #    硬编码 ENTITY_REF_FIELDS 字段名作为兜底（无声明或声明遗漏时）。
        if unit.content:
            try:
                import json
                content_dict = json.loads(unit.content) if isinstance(unit.content, str) else {}
                if isinstance(content_dict, dict):
                    count += self._infer_declared_refs(unit, content_dict)
                    ref_names = extract_entity_refs(content_dict)
                    for ref_name in ref_names:
                        target = self.store.get_unit_by_name(ref_name)
                        if target and target.id != unit.id:
                            if self._create_rel(unit.id, target.id, RelationType.REFERENCES, 0.5):
                                count += 1
            except (json.JSONDecodeError, ValueError):
                pass
        # 1. 同章节自动关联（规则引擎）
        if unit.type == UnitType.SCENE and get_unit_chapter(unit):
            count += self._infer_same_chapter(unit)
        # 2. 内容扫描（纯文本子串匹配，补充结构化提取遗漏的引用）
        if unit.content:
            count += self._infer_by_content(unit)
        # 3. 如果新建的是角色，反向扫描已有内容
        if unit.type == UnitType.CHARACTER_ARC:
            count += self._infer_reverse_scan(unit)
        # 4. 如果新建的是结构类单元，推断层级关系（CONTAINS 边）
        if unit.type in (UnitType.OUTLINE, UnitType.ARC_PLAN, UnitType.VOLUME_PLAN, UnitType.CHAPTER_PLAN):
            count += self._infer_structure_hierarchy(unit)
        # 5. 如果新建的是时间事件，推断 LOCATED_AT 和 INVOLVES 边
        if unit.type == UnitType.TEMPORAL_EVENT:
            count += self._infer_event_relations(unit)
        return count

    def infer_by_content(self, content: str, source_unit: NarrativeUnit) -> int:
        """
        对任意文本内容执行推断（用于外部调用）。
        返回新建的关系数。
        """
        return self._infer_by_content(source_unit, override_content=content)

    def batch_infer_all(self, progress_callback=None) -> int:
        """
        全量扫描所有已有单元，批量回填关系。
        用于迁移后一次性补全。
        返回新建关系总数。
        """
        self._batch_mode = True
        total = 0
        units = list(self.store._units.values())
        total_units = len(units)
        for i, u in enumerate(units):
            if u.status == UnitStatus.ARCHIVED:
                continue
            created = self.infer_on_create(u)
            total += created
            if progress_callback and (i + 1) % 10 == 0:
                progress_callback(i + 1, total_units, total)
        # 批量模式的事件合并：只记一条 SYSTEM_EVENT
        if total > 0:
            self._record_batch_event(total)
        self.store.flush()
        self._batch_mode = False
        return total

    # ── 内部方法 ────────────────────────────────────────────────────

    def _infer_declared_refs(self, unit: NarrativeUnit, content_dict: dict) -> int:
        """
        声明驱动实体引用建边。

        遍历 TypeRegistry 中该单元类型的 entity_reference fact_fields：
        - 按 path 提取引用值（extract_facts）
        - 按 match_field 解析目标单元（id → get_unit，unit_name → get_unit_by_name）
        - 按声明的 rel_type 建立关系（默认 references）
        返回新建的关系数。
        """
        from type_registry import TypeRegistry
        count = 0
        type_name = unit.type.value if hasattr(unit.type, "value") else str(unit.type)
        registry = TypeRegistry.get_global(project_root=str(self.store.project_root))
        td = registry.get_type(type_name)
        if not td:
            return count
        ref_fields = [f for f in td.fact_fields if f.type == "entity_reference"]
        if not ref_fields:
            return count

        facts = registry.extract_facts(type_name, content_dict)
        for ff in ref_fields:
            rel_type = self._resolve_declared_rel_type(ff.rel_type)
            if rel_type is None:
                continue
            for val in facts.get(ff.name, []) or []:
                if not val or not isinstance(val, str):
                    continue
                target = self._resolve_ref_target(val, ff.match_field, ff.target_type)
                if target and target.id != unit.id:
                    if self._create_rel(unit.id, target.id, rel_type, 0.5):
                        count += 1
        return count

    def _resolve_ref_target(self, val: str, match_field: Optional[str],
                            target_type: Optional[str]) -> Optional[NarrativeUnit]:
        """按 match_field 解析实体引用值到目标单元。

        - id → GraphStore.get_unit（如章纲 scene_refs 引场景 ID）
        - unit_name / None → GraphStore.get_unit_by_name（如 location_ref 引地点名）
        返回目标单元；不存在或类型不符返回 None。
        """
        target = None
        if match_field == "id":
            target = self.store.get_unit(val)
        else:
            target = self.store.get_unit_by_name(val)
        if target is None:
            return None
        if target_type:
            type_name = target.type.value if hasattr(target.type, "value") else str(target.type)
            allowed = target_type if isinstance(target_type, list) else [target_type]
            if type_name not in allowed:
                return None
        return target

    @staticmethod
    def _resolve_declared_rel_type(rel_type: str) -> Optional[RelationType]:
        """将声明的 rel_type 字符串解析为 RelationType；非法时返回 None。"""
        try:
            return RelationType(rel_type.lower())
        except (ValueError, AttributeError):
            return None

    def _infer_same_chapter(self, scene: NarrativeUnit) -> int:
        """同章节角色自动参与场景（规则引擎），支持 structure_path 回退"""
        count = 0
        scene_ch = get_unit_chapter(scene)
        scene_path = scene.structure_path
        
        for u in self.store._units.values():
            if u.type != UnitType.CHARACTER_ARC or u.status == UnitStatus.ARCHIVED:
                continue
            
            if scene_ch:
                if get_unit_chapter(u) == scene_ch:
                    if self._create_rel(u.id, scene.id, RelationType.PARTICIPATES_IN, 0.5):
                        count += 1
            elif scene_path and u.structure_path:
                # 按 structure_path 最后一层匹配（章节号）
                if (len(scene_path) > 0 and len(u.structure_path) > 0
                        and scene_path[-1] == u.structure_path[-1]):
                    if self._create_rel(u.id, scene.id, RelationType.PARTICIPATES_IN, 0.5):
                        count += 1
        return count

    def _infer_by_content(
        self, unit: NarrativeUnit, override_content: str | None = None
    ) -> int:
        """
        扫描内容文本，匹配已知实体名。
        根据类型对决定方向和关系类型。
        """
        count = 0
        content = override_content or unit.content
        if not content:
            return count

        for other_id, other in self.store._units.items():
            if other.id == unit.id or other.status == UnitStatus.ARCHIVED:
                continue
            # 跳过内容为空或名称太短的匹配目标
            if len(other.unit_name) < 2:
                continue
            # 检查名称是否出现在内容中
            if other.unit_name not in content:
                continue

            # 查找匹配的规则（可返回多条）
            matched_rules = self._match_rules(unit.type, other.type)
            if not matched_rules:
                # 没有精确匹配的规则，用默认
                if self._create_rel(unit.id, other.id, RelationType.REFERENCES, 0.2):
                    count += 1
            else:
                for rel_type, direction, weight in matched_rules:
                    if direction == "source_to_target":
                        source, target = unit.id, other.id
                    else:
                        source, target = other.id, unit.id
                    # 推断关系语义标签（如"仇敌""师徒"），由 YAML 配置驱动
                    label = self._infer_relation_label(unit, other, content, rel_type)
                    if self._create_rel(source, target, rel_type, weight, label=label):
                        count += 1

        return count

    def _infer_relation_label(
        self, unit: NarrativeUnit, other: NarrativeUnit,
        content: str, rel_type: RelationType,
    ) -> str:
        """
        推断关系语义标签（通用版）。

        从内容中查找对方名称出现的上下文窗口，逐个检查 YAML 配置的所有
        标签关键词集。首个匹配到关键词的标签名即为返回值。
        不匹配任何标签 → ""（无标签）。

        配置驱动：YAML key = 标签名（如"仇敌""师徒""盟友"），value.keywords = 关键词列表。
        不限制单元类型——任何配置了 auto_label 的类型对都能自动打标签。
        """
        idx = content.find(other.unit_name)
        if idx < 0:
            return ""
        # 取角色名前后各 50 字作为上下文窗口
        start = max(0, idx - 50)
        end = min(len(content), idx + len(other.unit_name) + 50)
        context = content[start:end]

        # 从 type_registry 读取全部标签配置
        from type_registry import TypeRegistry
        labels = TypeRegistry.get_global(
            project_root=str(self.store.project_root)
        ).get_relation_auto_labels(
            unit.type.value, rel_type.value
        )

        for label_name, keywords in labels.items():
            if any(kw in context for kw in keywords):
                return label_name
        return ""

    def _infer_reverse_scan(self, character: NarrativeUnit) -> int:
        """
        新角色创建后，反向扫描已有内容。
        如果已有场景/正文中提到了角色名，建立关系。
        """
        count = 0
        name = character.unit_name
        if len(name) < 2:
            return count

        for u in self.store._units.values():
            if u.id == character.id or u.status == UnitStatus.ARCHIVED:
                continue
            if not u.content or name not in u.content:
                continue

            if u.type == UnitType.SCENE:
                if self._create_rel(character.id, u.id, RelationType.PARTICIPATES_IN, 0.5):
                    count += 1
            elif u.type in (UnitType.CHUNK, UnitType.WORLD_RULE, UnitType.PLOT_THREAD):
                if self._create_rel(character.id, u.id, RelationType.REFERENCES, 0.3):
                    count += 1
            elif u.type == UnitType.NOTE:
                if self._create_rel(u.id, character.id, RelationType.REFERENCES, 0.2):
                    count += 1

        return count

    def _infer_structure_hierarchy(self, unit: NarrativeUnit) -> int:
        """
        新结构单元创建后，推断其在结构层级中的位置。
        
        策略：
        1. 如果单元已通过 parent_id 建立了 CONTAINS 边，跳过。
        2. 基于 unit_name 的名称模式推断父级：
           - "XX卷"名称 → 尝试匹配"总纲"或相同系列名的"篇大纲"作为父级
           - "第X章"名称 → 尝试匹配"卷大纲"作为父级
        3. 基于 structure_path（若存在）的路径前缀匹配。
        返回新建的关系数。
        """
        count = 0
        # 跳过已有 CONTAINS 入边的（已被手动指定 parent_id）
        incoming_contains = self.store.get_relations(
            unit.id, relation_type=RelationType.CONTAINS, direction="incoming"
        )
        if incoming_contains:
            return count
        
        # 策略 A：基于 structure_path 前缀匹配
        if unit.structure_path and len(unit.structure_path) > 1:
            parent_path = unit.structure_path[:-1]
            for other in self.store._units.values():
                if other.id == unit.id or other.status == UnitStatus.ARCHIVED:
                    continue
                if other.type not in _STRUCTURE_TYPES:
                    continue
                if other.structure_path is not None and len(other.structure_path) == len(parent_path) \
                        and other.structure_path == parent_path:
                    if self._create_rel(other.id, unit.id, RelationType.CONTAINS, 0.8):
                        count += 1
                    return count
        
        # 策略 B：基于名称模式
        name = unit.unit_name
        
        # "第X章" → 找卷大纲
        import re
        chapter_match = re.match(r'^第(\d+)章', name)
        if chapter_match:
            ch_num = int(chapter_match.group(1))
            for other in self.store._units.values():
                if other.id == unit.id or other.status == UnitStatus.ARCHIVED:
                    continue
                if other.type not in _STRUCTURE_TYPES:
                    continue
                # 匹配"XX卷"或"XX卷大纲"
                if '卷' in other.unit_name:
                    vol_ch = get_unit_chapter(other)
                    if vol_ch:
                        # 卷大纲的章节号应 <= 当前章号
                        if vol_ch <= ch_num:
                            # 检查相邻单元
                            pass  # 简化：不自动推断
        return count

    def _infer_event_relations(self, unit: NarrativeUnit) -> int:
        """
        新建 TEMPORAL_EVENT 后，从 content 推断关系：
        - content.location → LOCATED_AT 边关联到 world_rule
        - content.characters[].name → INVOLVES 边关联到 character_arc
        """
        import json
        count = 0
        try:
            content = json.loads(unit.content) if isinstance(unit.content, str) else (unit.content or {})
        except (json.JSONDecodeError, ValueError, TypeError):
            return count
        if not isinstance(content, dict):
            return count

        # 从 location 字段推断 LOCATED_AT
        location_name = content.get("location", "") or ""
        if location_name:
            target = self.store.get_unit_by_name(location_name)
            if target and target.type == UnitType.WORLD_RULE:
                if self._create_rel(unit.id, target.id, RelationType.LOCATED_AT, 0.5):
                    count += 1

        # 从 characters[] 字段推断 INVOLVES
        raw_chars = content.get("characters", [])
        if isinstance(raw_chars, list):
            for item in raw_chars:
                char_name = ""
                if isinstance(item, dict):
                    char_name = item.get("name", "")
                elif isinstance(item, str):
                    char_name = item
                if char_name:
                    target = self.store.get_unit_by_name(char_name)
                    if target and target.type == UnitType.CHARACTER_ARC:
                        if self._create_rel(unit.id, target.id, RelationType.INVOLVES, 0.5):
                            count += 1

        return count

    # ── 辅助方法 ────────────────────────────────────────────────────

    def _match_rules(
        self, source_type: UnitType, target_type: UnitType
    ) -> list[tuple[RelationType, str, float]]:
        """
        在规则表中查找匹配 (source_type, target_type) 的所有规则。
        返回列表，可能包含多条规则（如同一类型对的不同关系类型）。
        通配规则（target_type=None）仅作为无精确匹配时的回退。
        """
        exact = []
        wildcard = None
        for st, tt, rel_type, direction, weight in INFER_RULES:
            if st == source_type and tt == target_type:
                exact.append((rel_type, direction, weight))
            elif st == source_type and tt is None and wildcard is None:
                wildcard = (rel_type, direction, weight)
        return exact if exact else ([wildcard] if wildcard else [])

    def _create_rel(
        self, source_id: str, target_id: str,
        rel_type: RelationType, weight: float,
        label: str = "",
    ) -> bool:
        """
        创建一条关系。已存在则跳过。
        批量模式下不产生独立事件。
        证据锚点：payload 写入 source=auto + 出处章节（若有）。
        """
        actor = "relation_inferrer"
        payload: dict = {"source": "auto"}
        src_unit = self.store.get_unit(source_id)
        if src_unit is not None:
            ch = get_unit_chapter(src_unit)
            if ch:
                payload["chapter"] = ch
        rel = self.store.add_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=rel_type,
            weight=weight,
            description="auto-inferred",
            label=label,
            actor=actor,
            record_event=not self._batch_mode,
            payload=payload,
        )
        if rel:
            self._stats["created"] += 1
            return True
        self._stats["skipped"] += 1
        return False

    def _record_batch_event(self, total: int):
        """批量模式下合并事件"""
        from graph_schema import EventType as ET
        self.store._record_event(
            ET.SYSTEM_EVENT,
            actor="relation_inferrer",
            payload={"batch_infer": total},
        )

    def stats(self) -> dict:
        return dict(self._stats)

    def reset_stats(self):
        self._stats = {"created": 0, "skipped": 0}
