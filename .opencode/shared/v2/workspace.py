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
    
    # 场景级信息（写章节时的上下文）
    story_time: str = ""                    # 故事内时间
    location: str = ""                      # 地点
    scene_function: str = ""                # 本场景叙事目标
    tension_targets: Dict[str, int] = field(default_factory=dict)  # 张力目标
    character_states: List[Dict[str, str]] = field(default_factory=list)  # [{name, status, description}]
    previous_scene_summary: str = ""        # 前置场景摘要
    writing_guides: List[str] = field(default_factory=list)  # 写作指引
    
    # 活跃风格（V2：从 config.yaml 读取后注入）
    active_style: str = ""
    active_style_name: str = ""
    
    # 完整性评分
    completeness_score: float = 1.0
    missing_gaps: List[str] = field(default_factory=list)
    
    def to_prompt_block(self, preheat_level: str = "warm") -> str:
        """
        将工作空间渲染为三段式 prompt 块。
        
        段1：当前焦点（场景级信息）
        段2：你需要知道（上下文 + 目标 + 角色状态）
        段3：写作指引
        段4：关联信息（按预热级别）
        """
        lines = []
        lines.append("### 当前焦点")
        
        if self.focus_unit and self.focus_unit.type == UnitType.SCENE:
            # 场景级信息
            lines.append(f"你正在写场景：{self.focus_unit.unit_name}")
            ch = self.focus_unit.belongs_to_chapter or "?"
            vol = self.focus_unit.belongs_to_volume or "?"
            lines.append(f"归属：第{ch}章 · 卷{vol}")
            if self.story_time:
                lines.append(f"时间：{self.story_time}")
            if self.location:
                lines.append(f"地点：{self.location}")
            if self.character_states:
                roles = "，".join(
                    f"{s.get('name','?')}（{s.get('status','?')}）" for s in self.character_states[:5]
                )
                lines.append(f"出场角色：{roles}")
        else:
            # 非场景焦点
            lines.append(f"类型：{self.focus_type}")
            if self.focus_unit:
                lines.append(f"名称：{self.focus_unit.unit_name}")
        lines.append("")
        
        # 段2：你需要知道
        lines.append("### 你需要知道")
        idx = 1
        if self.previous_scene_summary:
            lines.append(f"{idx}. 【前置】{self.previous_scene_summary}"); idx += 1
        if self.scene_function:
            lines.append(f"{idx}. 【功能】{self.scene_function}"); idx += 1
        if self.tension_targets:
            parts = " / ".join(f"{k}={v}" for k, v in sorted(self.tension_targets.items()))
            lines.append(f"{idx}. 【张力】{parts}"); idx += 1
        for cs in self.character_states:
            desc = cs.get("description", "")
            if desc:
                lines.append(f"{idx}. 【角色】{cs.get('name','?')}：{desc}"); idx += 1
        if self.missing_gaps:
            for gap in self.missing_gaps:
                lines.append(f"{idx}. ⚠️ {gap}"); idx += 1
        lines.append("")
        
        # 段3：写作指引
        if self.writing_guides:
            lines.append("### 写作指引")
            for g in self.writing_guides:
                lines.append(f"- {g}")
            lines.append("")
        
        # 段4：关联信息（按预热级别）
        if self.immediate_context:
            lines.append("### 直接关联")
            for item in self.immediate_context:
                name = item.get("unit_name", "?")
                rel_type = item.get("relation_type", "?")
                unit_type = item.get("unit_type", "?")
                lines.append(f"- [{unit_type}] {name} ({rel_type})")
            lines.append("")
        
        if preheat_level in ("warm", "hot"):
            if self.character_arcs:
                lines.append(f"### 角色 ({len(self.character_arcs)})")
                for ca in self.character_arcs[:5]:
                    lines.append(f"- {ca.get('unit_name', '?')}")
                lines.append("")
            if self.plot_threads:
                lines.append(f"### 情节线 ({len(self.plot_threads)})")
                for pt in self.plot_threads[:3]:
                    lines.append(f"- {pt.get('unit_name', '?')}")
                lines.append("")
            if self.world_rules:
                lines.append(f"### 世界观 ({len(self.world_rules)})")
                for wr in self.world_rules[:3]:
                    lines.append(f"- {wr.get('unit_name', '?')}")
                lines.append("")
        
        # 活跃风格（所有预热级别都注入）
        if self.active_style:
            lines.append(f"### 活跃风格：{self.active_style_name}")
            lines.append(self.active_style)
            lines.append("")
        
        if preheat_level == "hot" and self.weak_signals:
            lines.append("### 弱信号")
            for sig in self.weak_signals:
                lines.append(f"- {sig.get('description', '')}")
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
    # 预热级别的选择由 Agent prompt (novel-writer.md) 根据写作模式决定
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
        
        # 5. 活跃风格加载
        self._load_active_style(ws, extra_context or {})
        
        # 6. 场景级信息提取
        self._enrich_scene_context(ws, focus)
        
        # 7. 完整性评估
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
    
    def _load_active_style(self, ws: Workspace, extra_context: Dict[str, Any]):
        """
        从额外上下文或 config.yaml 加载活跃风格。
        
        优先使用 extra_context 中的 style_name 和 style_content（编排层传入），
        兜底查找项目目录下的 styles/ 或 builtin/。
        """
        style_name = extra_context.get("active_style_name", "")
        style_content = extra_context.get("active_style_content", "")
        
        if style_name and style_content:
            ws.active_style_name = style_name
            ws.active_style = style_content
            return
        
        # 兜底：从 project_root 读取 config.yaml
        import os
        project_root = extra_context.get("project_root", "")
        if not project_root:
            return
        
        config_path = os.path.join(project_root, "config.yaml")
        if not os.path.exists(config_path):
            return
        
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            style_name = config.get("活跃风格", "")
            if not style_name:
                return
            
            # 尝试 styles/{名称}.yaml
            style_path = os.path.join(project_root, "styles", f"{style_name}.yaml")
            if os.path.exists(style_path):
                with open(style_path, "r", encoding="utf-8") as f:
                    ws.active_style = f.read()
                    ws.active_style_name = style_name
                return
            
            # 兜底：builtin/{名称}.yaml（从项目根目录查找 skill 内置风格）
            builtin_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "skills", "novel-style", "builtin", f"{style_name}.yaml"
            )
            if os.path.exists(builtin_path):
                with open(builtin_path, "r", encoding="utf-8") as f:
                    ws.active_style = f.read()
                    ws.active_style_name = style_name
        except Exception:
            pass  # 安静失败，不阻塞预热
    
    
    def _parse_json_content(self, unit: NarrativeUnit) -> dict:
        """解析叙事单元的 content 为 dict（如是 JSON 格式）"""
        if not unit or not unit.content:
            return {}
        try:
            return json.loads(unit.content)
        except (json.JSONDecodeError, ValueError):
            return {}
    
    def _enrich_scene_context(self, ws: Workspace, focus: NarrativeUnit):
        """提取场景级上下文信息"""
        if not focus or focus.type != UnitType.SCENE:
            return
        
        content = self._parse_json_content(focus)
        if not content:
            return
        
        # 提取场景信息
        ws.story_time = content.get("故事时间", "")
        
        locations = content.get("涉及地点", [])
        if isinstance(locations, list):
            ws.location = "，".join(str(l) for l in locations if l)
        elif isinstance(locations, str):
            ws.location = locations
        
        # 从结构规划中提取场景功能
        structure = content.get("结构规划", {})
        if isinstance(structure, dict):
            development = structure.get("发展", {})
            if isinstance(development, dict):
                ws.scene_function = development.get("核心冲突", "")
            # 前置场景摘要
            opening = structure.get("开篇", {})
            closing = structure.get("收尾", {})
            if isinstance(closing, dict):
                ws.previous_scene_summary = closing.get("下章铺垫", closing.get("结果", ""))
        
        # 张力目标
        tension = content.get("张力曲线", {})
        if isinstance(tension, dict):
            ws.tension_targets = {k: int(v) for k, v in tension.items() if isinstance(v, (int, float))}
        
        # 角色状态
        characters = content.get("出场角色", [])
        if isinstance(characters, list):
            for c in characters:
                if isinstance(c, dict):
                    ws.character_states.append({
                        "name": c.get("角色名", ""),
                        "status": c.get("状态", ""),
                        "description": c.get("场景作用", ""),
                    })
                elif isinstance(c, str):
                    ws.character_states.append({"name": c, "status": "", "description": ""})
        
        # 写作指引
        guides = []
        chapter_type = content.get("子类型", content.get("章节类型", ""))
        if chapter_type:
            guides.append(f"本章类型：{chapter_type}")
        if isinstance(opening, dict) and opening.get("方式"):
            guides.append(f"开篇方式：{opening['方式']}")
        if "开场" in tension:
            guides.append("推荐冷笔开场")
        ws.writing_guides = guides
