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
    EventType,
)
from graph_store import GraphStore
from render_utils import extract_entity_refs


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
     "target_to_source", 0.5),
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
    # 世界观 → 世界观（势力管辖）：势力控制地域
    (UnitType.WORLD_RULE, UnitType.WORLD_RULE, RelationType.CONTROLS,
     "source_to_target", 0.4),
    # 角色 → 角色：同盟关系
    (UnitType.CHARACTER_ARC, UnitType.CHARACTER_ARC, RelationType.ALLIED_WITH,
     "source_to_target", 0.3),
    # 角色 → 世界观（势力）：角色属于势力
    (UnitType.CHARACTER_ARC, UnitType.WORLD_RULE, RelationType.MEMBER_OF,
     "source_to_target", 0.5),
    # ── STRUCTURE / NARRATIVE_VOICE 推断规则 ──────────────────────────
    # 结构 → 情节线：结构设计了情节线
    (UnitType.STRUCTURE, UnitType.PLOT_THREAD, RelationType.IMPLEMENTS,
     "source_to_target", 0.5),
    # 结构 → 场景：结构安排了场景节奏
    (UnitType.STRUCTURE, UnitType.SCENE, RelationType.REFERENCES,
     "source_to_target", 0.3),
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
        # 0. 从 entity_ref 语义字段提取结构化引用
        if unit.content:
            try:
                import json
                content_dict = json.loads(unit.content) if isinstance(unit.content, str) else {}
                if isinstance(content_dict, dict):
                    ref_names = extract_entity_refs(content_dict)
                    for ref_name in ref_names:
                        target = self.store.get_unit_by_name(ref_name)
                        if target and target.id != unit.id:
                            if self._create_rel(unit.id, target.id, RelationType.REFERENCES, 0.5):
                                count += 1
            except (json.JSONDecodeError, ValueError):
                pass
        # 1. 同章节自动关联（规则引擎）
        if unit.type == UnitType.SCENE and unit.belongs_to_chapter:
            count += self._infer_same_chapter(unit)
        # 2. 内容扫描（纯文本子串匹配，补充结构化提取遗漏的引用）
        if unit.content:
            count += self._infer_by_content(unit)
        # 3. 如果新建的是角色，反向扫描已有内容
        if unit.type == UnitType.CHARACTER_ARC:
            count += self._infer_reverse_scan(unit)
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

    def _infer_same_chapter(self, scene: NarrativeUnit) -> int:
        """同章节角色自动参与场景（规则引擎）"""
        count = 0
        for u in self.store._units.values():
            if (u.type == UnitType.CHARACTER_ARC
                    and u.status != UnitStatus.ARCHIVED
                    and u.belongs_to_chapter == scene.belongs_to_chapter):
                # 角色 → 场景：PARTICIPATES_IN
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
                    if self._create_rel(source, target, rel_type, weight):
                        count += 1

        return count

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
    ) -> bool:
        """
        创建一条关系。已存在则跳过。
        批量模式下不产生独立事件。
        """
        actor = "relation_inferrer"
        rel = self.store.add_relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=rel_type,
            weight=weight,
            description="auto-inferred",
            actor=actor,
            record_event=not self._batch_mode,
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
