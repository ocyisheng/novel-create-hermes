"""
工作空间构建器。

从叙事单元网络（graph）中，根据当前焦点构建最小必要上下文。
取代现有 chapter_context.py 的全量推送模式。
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

from graph_schema import (
    NarrativeUnit, UnitType, UnitStatus, RelationType,
)
from graph_store import GraphStore as GraphStoreImpl
GraphStore = GraphStoreImpl  # type alias for type annotations


@dataclass
class Workspace:
    """
    工作空间——当前焦点所需的上下文数据快照。
    
    不是全量数据转储。根据焦点类型和深度动态构建。
    """
    focus_unit: Optional[NarrativeUnit] = None
    focus_type: Optional[str] = None
    
    # 1度邻居（直接关联的叙事单元）
    immediate_context: List[Dict[str, Any]] = field(default_factory=list)
    
    # 类型特定的上下文
    character_arcs: List[Dict[str, Any]] = field(default_factory=list)
    plot_threads: List[Dict[str, Any]] = field(default_factory=list)
    world_rules: List[Dict[str, Any]] = field(default_factory=list)
    scenes: List[Dict[str, Any]] = field(default_factory=list)
    
    # 弱信号
    weak_signals: List[Dict[str, Any]] = field(default_factory=list)
    
    # 前置/后置上下文
    previous_unit: Optional[Dict[str, Any]] = None
    next_unit: Optional[Dict[str, Any]] = None
    
    # 完整性评分
    completeness_score: float = 1.0
    missing_gaps: List[str] = field(default_factory=list)
    
    def to_prompt_block(self, preheat_level: str = "warm") -> str:
        """
        将工作空间渲染为 prompt 块。
        
        preheat_level: "cold" | "warm" | "hot"
        """
        lines = []
        lines.append("## 工作空间")
        lines.append("")
        
        if self.focus_unit:
            lines.append(f"### 当前焦点")
            lines.append(f"类型: {self.focus_type or self.focus_unit.type.value}")
            lines.append(f"名称: {self.focus_unit.unit_name}")
            if self.focus_unit.tags:
                lines.append(f"标签: {', '.join(self.focus_unit.tags)}")
            lines.append("")
        
        # COLD: 始终显示 1 度邻居
        if self.immediate_context:
            lines.append("### 直接关联")
            for item in self.immediate_context:
                name = item.get("unit_name", "?")
                rel_type = item.get("relation_type", "?")
                unit_type = item.get("unit_type", "?")
                lines.append(f"- [{unit_type}] {name} ({rel_type})")
            lines.append("")
        
        # WARM: 类型特定上下文
        if preheat_level in ("warm", "hot"):
            if self.character_arcs:
                lines.append(f"### 角色 ({len(self.character_arcs)})")
                for ca in self.character_arcs[:5]:  # 最多 5 个
                    lines.append(f"- {ca.get('unit_name', '?')}")
                lines.append("")
            
            if self.plot_threads:
                lines.append(f"### 情节线 ({len(self.plot_threads)})")
                for pt in self.plot_threads[:3]:
                    lines.append(f"- {pt.get('unit_name', '?')}")
                lines.append("")
            
            if self.world_rules:
                lines.append(f"### 世界观规则 ({len(self.world_rules)})")
                for wr in self.world_rules[:3]:
                    lines.append(f"- {wr.get('unit_name', '?')}")
                lines.append("")
        
        # HOT: 弱信号 + 前后文
        if preheat_level == "hot":
            if self.weak_signals:
                lines.append("### ⚡ 弱信号（可能需要关注）")
                for sig in self.weak_signals:
                    lines.append(f"- {sig.get('description', '')}")
                lines.append("")
            
            if self.previous_unit:
                lines.append("### 前置")
                lines.append(f"{self.previous_unit.get('unit_name', '')}")
                lines.append("")
            
            if self.next_unit:
                lines.append("### 后置")
                lines.append(f"{self.next_unit.get('unit_name', '')}")
                lines.append("")
        
        if self.missing_gaps:
            lines.append("### 上下文缺口")
            for gap in self.missing_gaps:
                lines.append(f"- ⚠️ {gap}")
            lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "focus_unit_id": self.focus_unit.id if self.focus_unit else None,
            "focus_type": self.focus_type,
            "immediate_count": len(self.immediate_context),
            "character_count": len(self.character_arcs),
            "plot_thread_count": len(self.plot_threads),
            "world_rule_count": len(self.world_rules),
            "scene_count": len(self.scenes),
            "weak_signal_count": len(self.weak_signals),
            "completeness": self.completeness_score,
            "gaps": self.missing_gaps,
        }


class WorkspaceBuilder:
    """
    工作空间构建器。
    
    从 GraphStore 中，以当前焦点叙事单元为中心，
    按需加载关联数据。
    """
    
    # 预热级别 → 加载深度映射
    PREHEAT_DEPTH = {
        "cold": {
            "neighbor_depth": 1,
            "character_limit": 3,
            "plot_limit": 1,
            "world_limit": 1,
            "weak_signals": False,
            "prev_next": False,
        },
        "warm": {
            "neighbor_depth": 1,
            "character_limit": 5,
            "plot_limit": 3,
            "world_limit": 3,
            "weak_signals": False,
            "prev_next": True,
        },
        "hot": {
            "neighbor_depth": 2,
            "character_limit": 10,
            "plot_limit": 5,
            "world_limit": 5,
            "weak_signals": True,
            "prev_next": True,
        },
    }
    
    def __init__(self, store: GraphStoreImpl):
        self.store = store
    
    def build(
        self,
        focus_unit_id: str,
        preheat_level: str = "warm",
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Workspace:
        """
        以焦点叙事单元为中心构建工作空间。
        
        Args:
            focus_unit_id: 焦点叙事单元的 ID
            preheat_level: "cold" | "warm" | "hot"
            extra_context: 额外的上下文注入（如用户状态、用户意图）
        
        Returns:
            Workspace 对象
        """
        config = self.PREHEAT_DEPTH.get(preheat_level, self.PREHEAT_DEPTH["warm"])
        focus = self.store.get_unit(focus_unit_id)
        
        if not focus:
            return Workspace(
                missing_gaps=[f"焦点单元 {focus_unit_id} 未找到"]
            )
        
        ws = Workspace(
            focus_unit=focus,
            focus_type=focus.type.value,
        )
        
        # 1. 加载邻居
        self._load_neighbors(ws, focus, config)
        
        # 2. 加载类型特定上下文
        self._load_type_specific(ws, focus, config)
        
        # 3. 弱信号
        if config["weak_signals"]:
            ws.weak_signals = self.store.get_weak_signals(focus_unit_id, limit=5)
        
        # 4. 前置/后置
        if config["prev_next"]:
            self._load_prev_next(ws, focus)
        
        # 5. 完整性评估
        self._assess_completeness(ws)
        
        return ws
    
    def _load_neighbors(self, ws: Workspace, focus: NarrativeUnit, config: Dict[str, Any]):
        """加载邻居叙事单元摘要"""
        neighbors = self.store.get_neighbors(focus.id, max_depth=config["neighbor_depth"])
        degree_1 = neighbors.get(1, set())
        
        for nid in degree_1:
            neighbor = self.store.get_unit(nid)
            if neighbor and neighbor.status != UnitStatus.ARCHIVED:
                # 找到关系和类型
                rels = self.store.get_relations(focus.id, direction="outgoing")
                rel_types = [r.relation_type.value for r in rels if r.target_id == nid]
                
                ws.immediate_context.append({
                    "unit_id": neighbor.id,
                    "unit_name": neighbor.unit_name,
                    "unit_type": neighbor.type.value,
                    "relation_type": rel_types[0] if rel_types else "related",
                })
                
                # 按类型分别存储
                if neighbor.type == UnitType.CHARACTER_ARC:
                    ws.character_arcs.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                        "status": neighbor.status.value,
                    })
                elif neighbor.type == UnitType.PLOT_THREAD:
                    ws.plot_threads.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                    })
                elif neighbor.type == UnitType.WORLD_RULE:
                    ws.world_rules.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
                elif neighbor.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "chapter": neighbor.belongs_to_chapter,
                    })
    
    def _load_type_specific(self, ws: Workspace, focus: NarrativeUnit, config: Dict[str, Any]):
        """加载与焦点类型相关的特定上下文"""
        
        if focus.type == UnitType.SCENE:
            # 正在写场景：找同章的角色弧线 + 情节线
            if focus.belongs_to_chapter:
                same_chapter = self.store.find_units(
                    chapter=focus.belongs_to_chapter
                )
                for unit in same_chapter:
                    if unit.id == focus.id:
                        continue
                    if unit.type == UnitType.CHARACTER_ARC:
                        if len(ws.character_arcs) < config["character_limit"]:
                            ws.character_arcs.append({
                                "unit_id": unit.id,
                                "unit_name": unit.unit_name,
                            })
                    elif unit.type == UnitType.PLOT_THREAD:
                        if len(ws.plot_threads) < config["plot_limit"]:
                            ws.plot_threads.append({
                                "unit_id": unit.id,
                                "unit_name": unit.unit_name,
                            })
        
        elif focus.type == UnitType.CHARACTER_ARC:
            # 正在设计角色：找涉及该角色的场景 + 关联情节线
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if source and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": source.belongs_to_chapter,
                    })
                elif source and source.type == UnitType.PLOT_THREAD:
                    ws.plot_threads.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                    })
        
        elif focus.type == UnitType.PLOT_THREAD:
            # 正在设计情节线：找通过场景关联的角色
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if source and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": source.belongs_to_chapter,
                    })
    
    def _load_prev_next(self, ws: Workspace, focus: NarrativeUnit):
        """加载同类型的前置/后置叙事单元"""
        if focus.belongs_to_chapter is None:
            return
        
        all_same_type = self.store.find_units(type=focus.type)
        same_chapter = [
            u for u in all_same_type
            if u.belongs_to_chapter == focus.belongs_to_chapter
            and u.id != focus.id
        ]
        
        # 找创建时间排序中的前后单元
        same_chapter.sort(key=lambda u: u.created_at)
        for i, u in enumerate(same_chapter):
            if u.id == focus.id:
                if i > 0:
                    prev = same_chapter[i - 1]
                    ws.previous_unit = {"unit_id": prev.id, "unit_name": prev.unit_name}
                if i < len(same_chapter) - 1:
                    nxt = same_chapter[i + 1]
                    ws.next_unit = {"unit_id": nxt.id, "unit_name": nxt.unit_name}
                break
    
    def _assess_completeness(self, ws: Workspace):
        """评估上下文完整性"""
        gaps = []
        
        if ws.focus_type == "scene":
            # 场景写作应该有关联角色
            if not ws.character_arcs and not ws.immediate_context:
                gaps.append("没有加载到关联角色信息")
            # 应该有情节线上下文
            if not ws.plot_threads:
                gaps.append("没有加载到情节线信息")
        
        elif ws.focus_type == "character_arc":
            # 角色设计应该至少有场景引用
            if not ws.scenes:
                gaps.append("没有关联到任何场景")
        
        if not ws.immediate_context:
            gaps.append("没有加载到直接关联的叙事单元")
        
        ws.missing_gaps = gaps
        
        # 计算完整性评分
        if not gaps:
            ws.completeness_score = 1.0
        elif len(gaps) <= 2:
            ws.completeness_score = 0.7
        else:
            ws.completeness_score = 0.4
