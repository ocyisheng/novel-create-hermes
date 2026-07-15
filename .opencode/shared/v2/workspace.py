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
    get_unit_chapter,
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
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    structures: List[Dict[str, Any]] = field(default_factory=list)  # 废弃，保留向后兼容
    outlines: List[Dict[str, Any]] = field(default_factory=list)
    arc_plans: List[Dict[str, Any]] = field(default_factory=list)
    volume_plans: List[Dict[str, Any]] = field(default_factory=list)
    chapter_plans: List[Dict[str, Any]] = field(default_factory=list)
    narrative_voices: List[Dict[str, Any]] = field(default_factory=list)
    thematic_motifs: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[Dict[str, Any]] = field(default_factory=list)
    
    # 弱信号
    weak_signals: List[Dict[str, Any]] = field(default_factory=list)
    
    # 前置/后置上下文
    previous_unit: Optional[Dict[str, Any]] = None
    next_unit: Optional[Dict[str, Any]] = None
    
    # 场景级信息（写章节时的上下文）
    story_time: str = ""                    # 故事内时间
    location: str = ""                      # 地点
    scene_function: str = ""                # 本场景叙事目标
    character_states: List[Dict[str, str]] = field(default_factory=list)  # [{name, status, description}]
    writing_guides: List[str] = field(default_factory=list)  # 写作指引
    
    # 活跃风格（V2：从 config.yaml 读取后注入）
    active_style: str = ""
    active_style_name: str = ""
    
    # 完整性评分
    completeness_score: float = 1.0
    missing_gaps: List[str] = field(default_factory=list)

    # 字段 Schema 信息（注入到 prompt，指导 LLM 按格式写入 content JSON）
    schema_info: List[str] = field(default_factory=list)
    
    def to_prompt_block(self, preheat_level: str = "warm") -> str:
        """
        将工作空间渲染为 prompt 块。
        
        段1：当前焦点（场景级信息）
        段2：你需要知道（上下文 + 目标 + 角色状态）
        段3：写作指引
        段4：关联信息（按预热级别）
        段5：输出要求（焦点类型的 content JSON Schema）
        """
        lines = []
        lines.append("### 当前焦点")
        
        if self.focus_unit and self.focus_unit.type == UnitType.SCENE:
            # 场景级信息
            lines.append(f"你正在写场景：{self.focus_unit.unit_name}")
            ch = get_unit_chapter(self.focus_unit) or "?"
            lines.append(f"归属：第{ch}章")
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
            if self.focus_type == "chunk":
                ch = get_unit_chapter(self.focus_unit) or "?"
                lines.append(f"章节：第{ch}章")
                if self.previous_unit:
                    lines.append(f"前版：{self.previous_unit.get('unit_name', '?')}")
                if self.next_unit:
                    lines.append(f"后版：{self.next_unit.get('unit_name', '?')}")
                # 多场景时列出场景清单而非单个时间/地点
                if len(self.scenes) > 1:
                    lines.append(f"包含 {len(self.scenes)} 个场景：")
                    for s in self.scenes:
                        lines.append(f"  - {s.get('unit_name', '?')}")
                elif self.location:
                    lines.append(f"地点：{self.location}")
                    if self.story_time:
                        lines.append(f"时间：{self.story_time}")
        lines.append("")
        
        # 段2：你需要知道
        lines.append("### 你需要知道")
        idx = 1
        if self.scene_function:
            lines.append(f"{idx}. 【核心】{self.scene_function}"); idx += 1
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
            if self.scenes:
                lines.append(f"### 场景 ({len(self.scenes)})")
                for s in self.scenes[:5]:
                    ch = s.get("chapter", "")
                    ch_str = f"（第{ch}章）" if ch else ""
                    lines.append(f"- {s.get('unit_name', '?')} {ch_str}")
                lines.append("")
            if self.chunks:
                lines.append(f"### 正文 ({len(self.chunks)})")
                for ck in self.chunks[:5]:
                    lines.append(f"- {ck.get('unit_name', '?')}")
                lines.append("")
            if self.structures:
                lines.append(f"### 结构设计 ({len(self.structures)})")
                for st in self.structures[:3]:
                    lines.append(f"- {st.get('unit_name', '?')}")
                lines.append("")
            if self.narrative_voices:
                lines.append(f"### 叙述腔调 ({len(self.narrative_voices)})")
                for nv in self.narrative_voices[:3]:
                    lines.append(f"- {nv.get('unit_name', '?')}")
                lines.append("")
            if self.thematic_motifs:
                lines.append(f"### 主体意象 ({len(self.thematic_motifs)})")
                for tm in self.thematic_motifs[:3]:
                    lines.append(f"- {tm.get('unit_name', '?')}")
                lines.append("")
            if self.notes:
                lines.append(f"### 笔记 ({len(self.notes)})")
                for nt in self.notes[:5]:
                    lines.append(f"- {nt.get('unit_name', '?')}")
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
        
        # 输出要求（焦点类型的 content JSON 格式约束，LLM 写入时的字段规范）
        if self.schema_info:
            lines.append("### 输出要求")
            lines.extend(self.schema_info)
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
            "chunk_count": len(self.chunks),
            "structure_count": len(self.structures),
            "narrative_voice_count": len(self.narrative_voices),
            "thematic_motif_count": len(self.thematic_motifs),
            "note_count": len(self.notes),
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
    
    # 预热级别 → 加载深度映射（默认值，可从 config.yaml 覆盖）
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
        self._project_config: Optional[Dict[str, Any]] = None
    
    # ── 从 config.yaml 加载预热配置 ─────────────────────────────────────
    
    def _load_project_config(self) -> Dict[str, Any]:
        """读取项目的 config.yaml，优先从 store.project_root 加载"""
        if self._project_config is not None:
            return self._project_config
        
        self._project_config = {}
        try:
            config_path = self.store.project_root / "config.yaml"
            if config_path.exists():
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    self._project_config = yaml.safe_load(f) or {}
        except Exception:
            pass  # 静默失败，回退到默认值
        return self._project_config
    
    def _get_preheat_config(self, preheat_level: str) -> Dict[str, Any]:
        """
        获取指定预热级别的配置，优先级：config.yaml > 类默认值。
        
        映射表（config.yaml 中文键 → 代码键）：
          角色上限 → character_limit
          情节线上限 → plot_limit
          世界观上限 → world_limit
          弱信号检测 → weak_signals
        """
        defaults = self.PREHEAT_DEPTH.get(preheat_level, self.PREHEAT_DEPTH["warm"]).copy()
        
        project_config = self._load_project_config()
        warmup_config = project_config.get("上下文预热", {})
        level_config = warmup_config.get(preheat_level, {})
        
        # 中文键 → 代码键映射
        KEY_MAP = {
            "角色上限": "character_limit",
            "情节线上限": "plot_limit",
            "世界观上限": "world_limit",
        }
        
        for cn_key, code_key in KEY_MAP.items():
            if cn_key in level_config and level_config[cn_key] is not None:
                defaults[code_key] = level_config[cn_key]
        
        # 弱信号检测（不在分级别配置里，在顶层）
        if "弱信号检测" in warmup_config:
            defaults["weak_signals"] = bool(warmup_config["弱信号检测"])
        
        return defaults
    
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
        config = self._get_preheat_config(preheat_level)
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
        
        # 6. 场景级信息提取（仅 SCENE 焦点需要）
        if focus.type == UnitType.SCENE:
            self._enrich_scene_context(ws, focus)
        
        # 7. 完整性评估
        self._assess_completeness(ws)
        
        # 8. 加载焦点类型的 content 字段 Schema（注入 prompt 指导 LLM 写 JSON）
        from schemas import schema_info as _schema_info
        ws.schema_info = _schema_info(focus.type)
        
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
                        "chapter": get_unit_chapter(neighbor),
                    })
                elif neighbor.type == UnitType.CHUNK:
                    ws.chunks.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                    })
                elif neighbor.type in (UnitType.STRUCTURE,):
                    ws.structures.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
                elif neighbor.type == UnitType.OUTLINE:
                    ws.outlines.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
                elif neighbor.type == UnitType.ARC_PLAN:
                    ws.arc_plans.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
                elif neighbor.type == UnitType.VOLUME_PLAN:
                    ws.volume_plans.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
                elif neighbor.type == UnitType.CHAPTER_PLAN:
                    ws.chapter_plans.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
                elif neighbor.type == UnitType.NARRATIVE_VOICE:
                    ws.narrative_voices.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                    })
                elif neighbor.type == UnitType.THEMATIC_MOTIF:
                    ws.thematic_motifs.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                    })
                elif neighbor.type == UnitType.NOTE:
                    ws.notes.append({
                        "unit_id": neighbor.id,
                        "unit_name": neighbor.unit_name,
                        "tags": neighbor.tags,
                    })
    
    def _load_type_specific(self, ws: Workspace, focus: NarrativeUnit, config: Dict[str, Any]):
        """加载与焦点类型相关的特定上下文"""
        
        if focus.type == UnitType.SCENE:
            # 正在写场景：找同章的角色弧线 + 情节线
            ch = get_unit_chapter(focus)
            if ch:
                same_chapter = self.store.find_units(
                    chapter=ch
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
                        "chapter": get_unit_chapter(source),
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
                        "chapter": get_unit_chapter(source),
                    })
        
        elif focus.type == UnitType.CHUNK:
            # 正在写正文：通过 BELONGS_TO 找所属场景，再由场景加载角色和情节线
            for rel in self.store.get_relations(focus.id, direction="outgoing"):
                if rel.relation_type != RelationType.BELONGS_TO:
                    continue
                scene = self.store.get_unit(rel.target_id)
                if not scene or scene.type != UnitType.SCENE:
                    continue
                
                # 记录场景（去重）
                if not any(e["unit_id"] == scene.id for e in ws.scenes):
                    ws.scenes.append({
                        "unit_id": scene.id,
                        "unit_name": scene.unit_name,
                        "chapter": get_unit_chapter(scene),
                    })
                
                # 从场景 content 提取时间/地点/核心冲突/角色状态/写作指引
                self._extract_scene_context(ws, scene)
                
                # 通过场景加载关联角色和情节线（1-hop from scene）
                seen_chars = {e["unit_id"] for e in ws.character_arcs}
                seen_plots = {e["unit_id"] for e in ws.plot_threads}
                for rel2 in self.store.get_relations(scene.id, direction="both"):
                    neighbor = self.store.get_unit(
                        rel2.source_id if rel2.target_id == scene.id else rel2.target_id
                    )
                    if not neighbor or neighbor.id == focus.id:
                        continue
                    if neighbor.type == UnitType.CHARACTER_ARC:
                        if neighbor.id not in seen_chars and len(ws.character_arcs) < config["character_limit"]:
                            seen_chars.add(neighbor.id)
                            ws.character_arcs.append({
                                "unit_id": neighbor.id,
                                "unit_name": neighbor.unit_name,
                            })
                    elif neighbor.type == UnitType.PLOT_THREAD:
                        if neighbor.id not in seen_plots and len(ws.plot_threads) < config["plot_limit"]:
                            seen_plots.add(neighbor.id)
                            ws.plot_threads.append({
                                "unit_id": neighbor.id,
                                "unit_name": neighbor.unit_name,
                            })
        
        elif focus.type == UnitType.WORLD_RULE:
            # 世界观焦点：找引用了该规则的场景
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if source and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
        
        elif focus.type in (
            UnitType.OUTLINE, UnitType.ARC_PLAN, UnitType.VOLUME_PLAN, UnitType.CHAPTER_PLAN,
        ):
            # 结构类焦点（总纲/部篇大纲/卷大纲/章纲）共享逻辑：
            # CONTAINS 递归聚合子结构 + PLANS 查找计划场景
            STRUCTURE_TYPES = {UnitType.OUTLINE, UnitType.ARC_PLAN, UnitType.VOLUME_PLAN,
                               UnitType.CHAPTER_PLAN}
            
            # 阶段 1：收集当前节点 + 所有后代节点（CONTAINS 边，层级关系）
            structure_ids = {focus.id}
            descendants = self.store.find_descendants(focus.id, max_depth=10)
            structure_ids.update(descendants)
            
            # 阶段 2：子结构单元按实际类型路由到对应列表
            for sid in structure_ids:
                if sid != focus.id:
                    child = self.store.get_unit(sid)
                    if child and child.type in STRUCTURE_TYPES:
                        _target_list = {
                            UnitType.OUTLINE: ws.outlines,
                            UnitType.ARC_PLAN: ws.arc_plans,
                            UnitType.VOLUME_PLAN: ws.volume_plans,
                            UnitType.CHAPTER_PLAN: ws.chapter_plans,
                        }
                        entry = {"unit_id": child.id, "unit_name": child.unit_name, "tags": child.tags}
                        target = _target_list.get(child.type, ws.structures)
                        target.append(entry)
            
            # 阶段 3：通过 PLANS 边查找章纲计划的所有 SCENE（规划层）
            seen_scene_ids: Set[str] = set()
            seen_chunk_ids: Set[str] = set()
            for sid in structure_ids:
                for rel in self.store.get_relations(sid, relation_type=RelationType.PLANS, direction="outgoing"):
                    scene = self.store.get_unit(rel.target_id)
                    if scene and scene.type == UnitType.SCENE and scene.id not in seen_scene_ids:
                        seen_scene_ids.add(scene.id)
                        ws.scenes.append({
                            "unit_id": scene.id,
                            "unit_name": scene.unit_name,
                            "chapter": get_unit_chapter(scene),
                        })
                # 同时查找 BELONGS_TO/REFERENCES 入边（兼容旧数据，逐步迁移到 PLANS）
                for rel in self.store.get_relations(sid, direction="incoming"):
                    source = self.store.get_unit(rel.source_id)
                    if not source:
                        continue
                    if source.type == UnitType.SCENE and source.id not in seen_scene_ids:
                        seen_scene_ids.add(source.id)
                        ws.scenes.append({
                            "unit_id": source.id,
                            "unit_name": source.unit_name,
                            "chapter": get_unit_chapter(source),
                        })
                    elif source.type == UnitType.CHUNK and source.id not in seen_chunk_ids:
                        seen_chunk_ids.add(source.id)
                        ws.chunks.append({
                            "unit_id": source.id,
                            "unit_name": source.unit_name,
                        })
        
        elif focus.type == UnitType.NARRATIVE_VOICE:
            # 叙述腔调焦点：找使用该腔调的场景
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if source and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
        
        elif focus.type == UnitType.THEMATIC_MOTIF:
            # 主体意象焦点：找关联的场景和角色
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if source and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
                elif source and source.type == UnitType.CHARACTER_ARC:
                    if len(ws.character_arcs) < config["character_limit"]:
                        ws.character_arcs.append({
                            "unit_id": source.id,
                            "unit_name": source.unit_name,
                        })
    
    def _load_prev_next(self, ws: Workspace, focus: NarrativeUnit):
        """加载同类型的前置/后置叙事单元"""
        # 分组优先级：structure_path → CONTAINS 兄弟 → 同类型全部
        anchor_path = focus.structure_path
        focus_ch = get_unit_chapter(focus)
        
        all_same_type = self.store.find_units(type=focus.type)
        same_group: List[NarrativeUnit] = []
        
        if anchor_path:
            # 用 structure_path 的最后一层做锚点
            anchor_last = anchor_path[-1] if anchor_path else None
            same_group = [
                u for u in all_same_type
                if u.structure_path and len(u.structure_path) > 0
                and u.structure_path[-1] == anchor_last
                and u.id != focus.id
            ]
        elif focus.type in (UnitType.OUTLINE, UnitType.ARC_PLAN, UnitType.VOLUME_PLAN, UnitType.CHAPTER_PLAN):
            # CONTAINS 兄弟查找：找共享同一父级 CONTAINS 边的兄弟
            parents = self.store.get_relations(focus.id, relation_type=RelationType.CONTAINS, direction="incoming")
            if parents:
                parent_id = parents[0].source_id
                # 查找父级的所有 outgoing CONTAINS 目标
                siblings = self.store.get_relations(parent_id, relation_type=RelationType.CONTAINS, direction="outgoing")
                sibling_ids = {r.target_id for r in siblings if r.target_id != focus.id}
                same_group = [u for u in all_same_type if u.id in sibling_ids]
        
        # 找创建时间排序中的前后单元
        same_group.sort(key=lambda u: u.created_at)
        for i, u in enumerate(same_group):
            if u.id == focus.id:
                if i > 0:
                    prev = same_group[i - 1]
                    ws.previous_unit = {"unit_id": prev.id, "unit_name": prev.unit_name}
                if i < len(same_group) - 1:
                    nxt = same_group[i + 1]
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
        
        elif ws.focus_type == "chunk":
            # 正文写作需要场景上下文
            if not ws.scenes:
                gaps.append("没有关联到场景信息，写作上下文可能不足")
            if not ws.character_arcs and not ws.plot_threads:
                gaps.append("没有加载到角色或情节线上下文")
        
        elif ws.focus_type == "plot_thread":
            # 情节线设计应该有关联场景
            if not ws.scenes:
                gaps.append("没有关联到任何场景")
        
        elif ws.focus_type == "world_rule":
            # 世界观设定应该有关联场景
            if not ws.scenes:
                gaps.append("没有关联到使用该设定的场景")
        
        elif ws.focus_type in ("outline", "arc_plan", "volume_plan"):
            # 聚合节点（总纲/部篇大纲/卷大纲）：应包含子结构单元（CONTAINS 边）
            children = self.store.get_relations(
                ws.focus_unit.id, relation_type=RelationType.CONTAINS, direction="outgoing"
            ) if ws.focus_unit else []
            if children:
                # 按类型检查正确的子列表
                _check_field = {
                    "outline": ws.outlines,
                    "arc_plan": ws.arc_plans,
                    "volume_plan": ws.volume_plans,
                }
                if not _check_field.get(ws.focus_type, []):
                    gaps.append(f"{ws.focus_type} 聚合节点但没有加载到子结构单元")
            # 聚合节点是否还关联场景/正文是可选的

        elif ws.focus_type == "chapter_plan":
            # 叶子节点（章纲）：应通过 PLANS 边关联计划场景
            plans = self.store.get_relations(
                ws.focus_unit.id, relation_type=RelationType.PLANS, direction="outgoing"
            ) if ws.focus_unit else []
            if not plans and not ws.scenes and not ws.chunks:
                gaps.append("章纲未通过 PLANS 边关联任何计划场景")
        
        elif ws.focus_type == "narrative_voice":
            # 叙述腔调应该有关联场景
            if not ws.scenes:
                gaps.append("没有关联到使用该腔调的场景")
        
        elif ws.focus_type == "thematic_motif":
            # 主体意象应该有关联的场景或角色
            if not ws.scenes and not ws.character_arcs:
                gaps.append("没有关联到使用该意象的场景或角色")
        
        elif ws.focus_type == "note":
            # 笔记不要求强关联，只需邻居信息
            pass
        
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
    
    def _extract_scene_context(self, ws: Workspace, scene_unit: NarrativeUnit):
        """从 SCENE 单元提取场景上下文到工作空间（供 SCENE/CHUNK 焦点共用）"""
        content = self._parse_json_content(scene_unit)
        if not content:
            return
        
        # 提取场景信息（多次调用时累加，避免最后一条覆盖前面）
        t = content.get("时间", "")
        if t:
            ws.story_time = f"{ws.story_time}；{t}" if ws.story_time else t
        loc = content.get("地点", "")
        if loc:
            ws.location = f"{ws.location}；{loc}" if ws.location else loc
        
        # 场域核心信息（多次调用时累加）
        func = content.get("核心冲突", content.get("一句话概要", ""))
        if func:
            ws.scene_function = f"{ws.scene_function}；{func}" if ws.scene_function else func
        
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
        scene_type = content.get("子类型", "")
        if scene_type:
            ws.writing_guides.append(f"场域功能：{scene_type}")
        summary = content.get("一句话概要", "")
        if summary:
            ws.writing_guides.append(f"场景概要：{summary}")
    
    def _enrich_scene_context(self, ws: Workspace, focus: NarrativeUnit):
        """提取场景级上下文信息（SCENE 焦点专用）"""
        if not focus or focus.type != UnitType.SCENE:
            return
        self._extract_scene_context(ws, focus)
