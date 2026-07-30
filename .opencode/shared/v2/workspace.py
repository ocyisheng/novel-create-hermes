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
class StoryTimeInfo:
    """故事时间信息（从 NarrativeUnit.extra["time"] 提取）"""
    raw: str = ""                              # 原始自由文本
    ordinal: Optional[float] = None            # 可排序序数，由 CharacterTimelineLedger 赋值
    precision: str = "vague"                   # exact|same|day|month|year|era|relative|vague


@dataclass
class CharacterStateEntry:
    """角色在某场景中的出场状态"""
    name: str = ""
    status: str = ""
    description: str = ""
    scene_id: str = ""                         # 来源场景单元 ID
    scene_name: str = ""                       # 场景名称
    scene_order: int = 0                       # 场景在章内顺序（0-based）
    story_ordinal: Optional[float] = None      # 故事时间序数
    prev_state: Optional[Dict[str, str]] = None  # 上一章结束时状态（Ledger 注入）


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
    story_time: Optional[StoryTimeInfo] = None  # 故事内时间（取代原 str 拼接）
    location: str = ""                           # 地点（多场景用；分隔）
    scene_function: str = ""                     # 本场景叙事目标
    character_states: List[CharacterStateEntry] = field(default_factory=list)  # 有序角色状态
    writing_guides: List[str] = field(default_factory=list)  # 写作指引
    
    # 活跃风格（V2：从 config.yaml 读取后注入）
    active_style: str = ""
    active_style_name: str = ""
    
    # ════════════════════════════════════════════════
    # 时间序列数据（用于工作空间 Prompt 注入）
    # ════════════════════════════════════════════════

    # 全局时间线摘要（按预热级别裁剪）
    global_timeline_summary: Optional[Dict[str, Any]] = None
    """{
        total_scenes: int,            # 场景总数
        chapters: [{chapter, scene_count}],  # 各章场景数
        focus_position: int,          # 焦点在全局时间线中的索引（0-based）
        focus_ordinal: float,         # 焦点场景的故事序数
    }"""

    # 焦点实体的时间线事件列表（已排序）
    entity_timeline: List[Dict[str, Any]] = field(default_factory=list)
    """[{
        story_ordinal: float,    # 故事序数
        time_label: str,         # 人类可读时间标签
        event: str,              # 事件描述（场景名称）
        location: str,           # 地点
        source_type: str,        # chapter/plot/world
        node_id: str,            # 关联节点 ID
    }]"""

    # 角色状态快照序列（焦点为 CHARACTER_ARC 或 SCENE 时）
    character_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    """[{
        character_name: str,
        chapter: int,
        story_ordinal: float,
        location: str,
        status: str,
        source_scene_name: str,
    }]"""

    # 角色状态变化摘要（自动从快照序列推导的文本摘要）
    character_evolution: str = ""
    """如 '林昭: 凡人(第1章) → 炼气三层(第3章) → 筑基初期(第5章)'"""

    # 地点/物品时间线
    location_timeline: List[Dict[str, Any]] = field(default_factory=list)

    # 当前焦点的故事序数（方便排序引用）
    story_ordinal: Optional[float] = None

    # 时间线上下文提示（给 LLM 的可读指引，由 _suggest_temporal_context 生成）
    temporal_context_hint: str = ""
    """如 '当前焦点在 ordinal ~2300（第3章），
         林渊当前修为：凡人，将要引气入体。
         本章在时间线上处于 2200-2500 区间。'"""

    # ════════════════════════════════════════════════
    # 关系图数据
    # ════════════════════════════════════════════════

    # 焦点实体的结构化 Ego Network
    ego_graph: Optional[Dict[str, Any]] = None
    """{
        center_id: str,
        node_count: int,
        edge_count: int,
        nodes: [{id, name, type, hop}],       # 邻居节点列表
        edges: [{from, to, type, label, direction}],  # 边列表
        by_type: {关系类型: [邻居信息]},       # 按关系类型分组
    }"""

    # 关系聚合摘要文本（供 LLM 直接消费）
    relation_summary: str = ""
    """如 'PARTICIPATES_IN: 林昭出现在 12 个场景中；IMPLEMENTS: 参与情节线-主线·逆天改命'"""

    # 跨实体路径（hot 预热时）
    entity_paths: List[Dict[str, Any]] = field(default_factory=list)

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
            if self.story_time and self.story_time.raw:
                lines.append(f"时间：{self.story_time.raw}")
            if self.location:
                lines.append(f"地点：{self.location}")
            if self.character_states:
                roles = "，".join(
                    f"{s.name}（{s.status}）" if s.status else s.name
                    for s in self.character_states[:5]
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
                    if self.story_time and self.story_time.raw:
                        lines.append(f"时间：{self.story_time.raw}")
        lines.append("")
        
        # 段2：你需要知道
        lines.append("### 你需要知道")
        idx = 1
        if self.scene_function:
            lines.append(f"{idx}. 【核心】{self.scene_function}"); idx += 1
        
        # 角色上一章状态（有 prev_state 的角色先展示）
        prev_states = [cs for cs in self.character_states if cs.prev_state]
        if prev_states:
            lines.append(f"{idx}. 【角色上一章状态】"); idx += 1
            seen_prev = set()
            for cs in prev_states:
                if cs.name not in seen_prev:
                    seen_prev.add(cs.name)
                    lines.append(f"   - {cs.name}：{cs.prev_state}")
        
        for cs in self.character_states:
            if cs.description:
                lines.append(f"{idx}. 【角色】{cs.name}：{cs.description}"); idx += 1
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
            if self.narrative_voices:
                lines.append(f"### 叙述腔调 ({len(self.narrative_voices)})")
                for nv in self.narrative_voices[:3]:
                    lines.append(f"- {nv.get('unit_name', '?')}")
                lines.append("")
            if self.thematic_motifs:
                lines.append(f"### 主题意象 ({len(self.thematic_motifs)})")
                for tm in self.thematic_motifs[:3]:
                    lines.append(f"- {tm.get('unit_name', '?')}")
                lines.append("")
            if self.notes:
                lines.append(f"### 笔记 ({len(self.notes)})")
                for nt in self.notes[:5]:
                    lines.append(f"- {nt.get('unit_name', '?')}")
                lines.append("")
        
        # ═══════════════════════════════════════════════════════════
        # 时间轴段落（预热级别裁剪）
        # ═══════════════════════════════════════════════════════════
        if self.global_timeline_summary and preheat_level in ("warm", "hot"):
            lines.append("### 时间轴")
            summary = self.global_timeline_summary
            total_scenes = summary.get("total_scenes", 0)
            lines.append(f"全局时间线：共 {total_scenes} 个场景，{summary.get('total_events', 0)} 个事件")
            fp = summary.get("focus_position")
            fo = summary.get("focus_ordinal")
            if fp is not None and total_scenes:
                fo_str = f"{fo:.1f}" if fo is not None else "?"
                lines.append(f"焦点位置：第 {fp + 1}/{total_scenes} 个场景（序数 #{fo_str}）")
            so = self.story_ordinal
            if so is not None:
                lines.append(f"故事坐标：#{so:.1f}")
            lines.append("")

        if self.entity_timeline and preheat_level in ("warm", "hot"):
            lines.append(f"### 实体时间线（{len(self.entity_timeline)} 个事件）")
            for evt in self.entity_timeline:
                marker = "→ " if evt.get("is_focus") else "  "
                loc_str = f" 📍{evt['location']}" if evt.get("location") else ""
                ord_val = evt.get("story_ordinal")
                ord_str = f"{ord_val:.1f}" if ord_val is not None else "?"
                lines.append(f"{marker}#{ord_str} {evt.get('time_label', '')}{loc_str}  {evt.get('event', '')}")
            lines.append("")

        if self.character_snapshots and preheat_level in ("warm", "hot"):
            lines.append(f"### 角色状态演变（{len(self.character_snapshots)} 个快照）")
            for snap in self.character_snapshots:
                status_str = f" [{snap['status']}]" if snap.get("status") else ""
                loc_str = f" @{snap['location']}" if snap.get("location") else ""
                lines.append(f"  第{snap['chapter']}章{loc_str}{status_str}  {snap.get('source_scene_name', '')}")
            lines.append("")

        if self.character_evolution:
            lines.append(f"### 角色轨迹")
            lines.append(self.character_evolution)
            lines.append("")

        if self.location_timeline and preheat_level == "hot":
            lines.append(f"### 地点时间线（{len(self.location_timeline)} 个事件）")
            for evt in self.location_timeline:
                ord_val = evt.get("story_ordinal")
                ord_str = f"{ord_val:.1f}" if ord_val is not None else "?"
                lines.append(f"  #{ord_str} {evt.get('time_label', '')} 📍{evt.get('location', '')}  {evt.get('event', '')}")
            lines.append("")

        # ═══════════════════════════════════════════════════════════
        # 关系网络段落（预热级别裁剪）
        # ═══════════════════════════════════════════════════════════
        if self.relation_summary and preheat_level in ("warm", "hot"):
            lines.append("### 关系网络")
            lines.append(self.relation_summary)
            lines.append("")

        if self.ego_graph and preheat_level == "hot":
            eg = self.ego_graph
            lines.append(f"### 关系图结构（{eg.get('node_count', 0)} 节点 · {eg.get('edge_count', 0)} 条边）")
            by_type = eg.get("by_type", {})
            for rel_type, neighbors in sorted(by_type.items()):
                names = [n["name"] for n in neighbors[:8]]
                extra = f" …等{len(neighbors)}" if len(neighbors) > 8 else ""
                dirs = set(n["direction"] for n in neighbors)
                dir_str = ""
                if dirs == {"incoming"}:
                    dir_str = " ← "
                elif dirs == {"outgoing"}:
                    dir_str = " → "
                lines.append(f"  {rel_type}{dir_str}{', '.join(names)}{extra}")
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
        
        # 时间线上下文提示（指导 LLM 产出精确的时间线信息）
        if self.temporal_context_hint and preheat_level in ("warm", "hot"):
            lines.append("### 时间线上下文")
            lines.append(self.temporal_context_hint)
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
            "timeline_event_count": len(self.entity_timeline),
            "snapshot_count": len(self.character_snapshots),
            "has_ego_graph": self.ego_graph is not None,
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
            "timeline_events": 0,       # 时间线事件数（0=不加载）
            "snapshot_limit": 0,         # 角色快照数
            "graph_depth": 1,            # 关系图深度
            "graph_internal_edges": False,  # 邻居间内部边
        },
        "warm": {
            "neighbor_depth": 1,
            "character_limit": 5,
            "plot_limit": 3,
            "world_limit": 3,
            "weak_signals": False,
            "prev_next": True,
            "timeline_events": 5,
            "snapshot_limit": 5,
            "graph_depth": 1,
            "graph_internal_edges": True,
        },
        "hot": {
            "neighbor_depth": 2,
            "character_limit": 10,
            "plot_limit": 5,
            "world_limit": 5,
            "weak_signals": True,
            "prev_next": True,
            "timeline_events": 20,
            "snapshot_limit": 20,
            "graph_depth": 2,
            "graph_internal_edges": True,
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
        
        # 7. 时间序列数据加载（复用 CharacterTimelineLedger）
        self._load_timeline_data(ws, focus, config)

        # 7.5 时间线上下文提示生成（指导 LLM 产出的内容包含精确时间信息）
        self._suggest_temporal_context(ws, focus, config)

        # 8. 结构化关系图加载（Ego Network）
        self._load_ego_graph(ws, focus, config)
        
        # 9. 完整性评估
        self._assess_completeness(ws)
        
        # 10. 加载焦点类型的 content 字段 Schema（注入 prompt 指导 LLM 写 JSON）
        from schemas import schema_info as _schema_info
        ws.schema_info = _schema_info(focus.type)
        
        return ws
    
    @staticmethod
    def _is_active(unit: Optional[NarrativeUnit]) -> bool:
        """检查单元是否非归档状态"""
        return unit is not None and unit.status != UnitStatus.ARCHIVED

    def _load_neighbors(self, ws: Workspace, focus: NarrativeUnit, config: Dict[str, Any]):
        """加载邻居叙事单元摘要"""
        neighbors = self.store.get_neighbors(focus.id, max_depth=config["neighbor_depth"])
        degree_1 = neighbors.get(1, set())
        
        for nid in degree_1:
            neighbor = self.store.get_unit(nid)
            if neighbor:  # get_neighbors 已排除归档单元
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
            # 检核场景 content 中引用的实体是否缺失
            self._detect_missing_references(ws, config)
        
        elif focus.type == UnitType.CHARACTER_ARC:
            # 正在设计角色：找涉及该角色的场景 + 关联情节线（跳过已归档）
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if self._is_active(source) and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
                elif self._is_active(source) and source.type == UnitType.PLOT_THREAD:
                    ws.plot_threads.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                    })
            # 检核场景 content 中引用的其他实体是否缺失
            self._detect_missing_references(ws, config)
        
        elif focus.type == UnitType.PLOT_THREAD:
            # 正在设计情节线：找通过场景关联的角色（跳过已归档）
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if self._is_active(source) and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
        
        elif focus.type == UnitType.CHUNK:
            # 正在写正文：通过 BELONGS_TO 找所属场景，再由场景加载角色和情节线（跳过已归档）
            # 先收集所有场景，按故事时间排序后再处理
            belonging_scenes: List[NarrativeUnit] = []
            for rel in self.store.get_relations(focus.id, direction="outgoing"):
                if rel.relation_type != RelationType.BELONGS_TO:
                    continue
                scene = self.store.get_unit(rel.target_id)
                if not scene or scene.type != UnitType.SCENE:
                    continue
                if scene.status == UnitStatus.ARCHIVED:
                    continue
                belonging_scenes.append(scene)
            
            # 按故事时间序数排序（无 ordinals 的放后面，按章节号兜底）
            def _scene_sort_key(sc):
                extra = sc.extra or {}
                ti = extra.get("time", {}) if isinstance(extra, dict) else {}
                ord_val = ti.get("ordinal") if isinstance(ti, dict) else None
                if ord_val is not None:
                    return (0, float(ord_val), "")
                ch = get_unit_chapter(sc) or 0
                return (1, ch * 10000, sc.unit_name or "")
            
            belonging_scenes.sort(key=_scene_sort_key)
            
            for scene_order, scene in enumerate(belonging_scenes):
                # 记录场景（去重）
                if not any(e["unit_id"] == scene.id for e in ws.scenes):
                    ws.scenes.append({
                        "unit_id": scene.id,
                        "unit_name": scene.unit_name,
                        "chapter": get_unit_chapter(scene),
                    })
                
                # 从场景 content 提取时间/地点/核心冲突/角色状态/写作指引
                self._extract_scene_context(ws, scene, scene_order=scene_order)
                
                # 通过场景加载关联角色和情节线（1-hop from scene）
                seen_chars = {e["unit_id"] for e in ws.character_arcs}
                seen_plots = {e["unit_id"] for e in ws.plot_threads}
                for rel2 in self.store.get_relations(scene.id, direction="both"):
                    neighbor = self.store.get_unit(
                        rel2.source_id if rel2.target_id == scene.id else rel2.target_id
                    )
                    if not neighbor or neighbor.id == focus.id:
                        continue
                    if self._is_active(neighbor) and neighbor.type == UnitType.CHARACTER_ARC:
                        if neighbor.id not in seen_chars and len(ws.character_arcs) < config["character_limit"]:
                            seen_chars.add(neighbor.id)
                            ws.character_arcs.append({
                                "unit_id": neighbor.id,
                                "unit_name": neighbor.unit_name,
                            })
                    elif self._is_active(neighbor) and neighbor.type == UnitType.PLOT_THREAD:
                        if neighbor.id not in seen_plots and len(ws.plot_threads) < config["plot_limit"]:
                            seen_plots.add(neighbor.id)
                            ws.plot_threads.append({
                                "unit_id": neighbor.id,
                                "unit_name": neighbor.unit_name,
                            })
            # 检核场景 content 中引用的实体是否缺失
            self._detect_missing_references(ws, config)
        
        elif focus.type == UnitType.WORLD_RULE:
            # 世界观焦点：找引用了该规则的场景（跳过已归档）
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if self._is_active(source) and source.type == UnitType.SCENE:
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
            
            # 阶段 1：收集当前节点 + 所有后代节点（CONTAINS 边，层级关系，跳过已归档）
            structure_ids = {focus.id}
            descendants = self.store.find_descendants(focus.id, max_depth=10)
            structure_ids.update(
                sid for sid in descendants
                if self._is_active(self.store.get_unit(sid))
            )
            
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
            
            # 阶段 3：通过 PLANS 边查找章纲计划的所有 SCENE（规划层，跳过已归档）
            seen_scene_ids: Set[str] = set()
            seen_chunk_ids: Set[str] = set()
            for sid in structure_ids:
                for rel in self.store.get_relations(sid, relation_type=RelationType.PLANS, direction="outgoing"):
                    scene = self.store.get_unit(rel.target_id)
                    if self._is_active(scene) and scene.type == UnitType.SCENE and scene.id not in seen_scene_ids:
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
                    if self._is_active(source) and source.type == UnitType.SCENE and source.id not in seen_scene_ids:
                        seen_scene_ids.add(source.id)
                        ws.scenes.append({
                            "unit_id": source.id,
                            "unit_name": source.unit_name,
                            "chapter": get_unit_chapter(source),
                        })
                    elif self._is_active(source) and source.type == UnitType.CHUNK and source.id not in seen_chunk_ids:
                        seen_chunk_ids.add(source.id)
                        ws.chunks.append({
                            "unit_id": source.id,
                            "unit_name": source.unit_name,
                        })
        
        elif focus.type == UnitType.NARRATIVE_VOICE:
            # 叙述腔调焦点：找使用该腔调的场景（跳过已归档）
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if self._is_active(source) and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
        
        elif focus.type == UnitType.THEMATIC_MOTIF:
            # 主体意象焦点：找关联的场景和角色（跳过已归档）
            for rel in self.store.get_relations(focus.id, direction="incoming"):
                source = self.store.get_unit(rel.source_id)
                if self._is_active(source) and source.type == UnitType.SCENE:
                    ws.scenes.append({
                        "unit_id": source.id,
                        "unit_name": source.unit_name,
                        "chapter": get_unit_chapter(source),
                    })
                elif self._is_active(source) and source.type == UnitType.CHARACTER_ARC:
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
    
    # ════════════════════════════════════════════════
    # 时间序列数据加载
    # ════════════════════════════════════════════════

    def _load_timeline_data(self, ws: Workspace, focus: NarrativeUnit, config: Dict[str, Any]):
        """
        为焦点加载时间序列数据。
        使用 TemporalEventIndex（统一全类型时间线索引），
        向后兼容 CharacterTimelineLedger 的输出格式。
        """
        from temporal_index import TemporalEventIndex

        num_events = config.get("timeline_events", 5)
        if num_events <= 0:
            return

        index = TemporalEventIndex(self.store).build()

        # 1. 全局时间线摘要
        scene_count = len(index._by_type.get("scene_event", []))
        ws.global_timeline_summary = {
            "total_events": len(index._events),
            "total_scenes": scene_count,
            "by_type": {t: len(indices) for t, indices in index._by_type.items()},
        }

        focus_name = focus.unit_name or ""

        # 2. 焦点实体的时间线事件（跨类型）
        if focus.type == UnitType.CHARACTER_ARC:
            # 角色时间线：所有关联事件（scene + cultivation + plot + ...）
            char_events = index.query().for_entity(focus_name).limit(num_events).all()
            for e in char_events:
                ws.entity_timeline.append(self._event_to_entity_dict(e))

            # 角色状态快照（只从 scene_event 提取）
            scene_events = index.query().for_entity(focus_name).by_type("scene_event").all()
            limit = config.get("snapshot_limit", 5)
            for e in scene_events[:limit]:
                ws.character_snapshots.append({
                    "character_name": focus_name,
                    "chapter": e.chapter,
                    "story_ordinal": e.ordinal,
                    "location": e.location,
                    "status": "",
                    "source_scene_name": e.summary,
                })
            # 自动推导角色演变摘要
            if scene_events:
                parts = []
                seen_keys = set()
                for e in scene_events:
                    status_key = f"第{e.chapter}章"
                    if e.location:
                        status_key += f"·{e.location}"
                    if status_key not in seen_keys:
                        seen_keys.add(status_key)
                        parts.append(status_key)
                if len(parts) >= 2:
                    ws.character_evolution = f"{focus_name}: {' → '.join(parts[:6])}"

        elif focus.type == UnitType.SCENE:
            # 场景：取前后相邻事件（不限类型）
            all_events = index._events
            pos = next((i for i, e in enumerate(all_events) if e.source_id == focus.id), -1)
            if pos >= 0:
                ws.global_timeline_summary["focus_position"] = pos
                if all_events[pos].ordinal is not None:
                    ws.global_timeline_summary["focus_ordinal"] = all_events[pos].ordinal
                    ws.story_ordinal = all_events[pos].ordinal
                start = max(0, pos - 2)
                end = min(len(all_events), pos + 3)
                for e in all_events[start:end]:
                    d = self._event_to_entity_dict(e)
                    d["is_focus"] = e.source_id == focus.id
                    ws.entity_timeline.append(d)

        elif focus.type == UnitType.WORLD_RULE:
            # 地点/世界观时间线：按事件 location 字段匹配
            loc_name = focus_name
            for e in index._events:
                if e.location == loc_name or (loc_name and loc_name in (e.location or "")):
                    ws.location_timeline.append(self._event_to_entity_dict(e))

        elif focus.type == UnitType.PLOT_THREAD:
            # 情节线时间线：该 source 的事件
            plot_events = index.query().from_source(focus.id).limit(num_events).all()
            for e in plot_events:
                ws.entity_timeline.append(self._event_to_entity_dict(e))

    @staticmethod
    def _event_to_entity_dict(e) -> Dict[str, Any]:
        """将 TemporalEvent 转为 entity_timeline / location_timeline 的 dict 格式。"""
        return {
            "story_ordinal": e.ordinal if e.ordinal is not None else 0,
            "time_label": e.time_label,
            "event": f"[{e.event_type}] {e.summary}" if e.event_type != "scene_event" else e.summary,
            "location": e.location,
            "source_type": e.source_type,
            "node_id": e.source_id,
        }

    # ── 时间线上下文提示 ─────────────────────────────────────────────────

    def _suggest_temporal_context(
        self,
        ws: Workspace,
        focus: NarrativeUnit,
        config: Dict[str, Any],
    ):
        """生成时间线上下文提示，注入 ws.temporal_context_hint。

        目的是让 LLM 在生成内容时明确知道当前焦点在时间线上的位置、
        涉及的实体当前状态，从而产出更精确的时间线信息
        （如精确的 time_text、ordinal、cast[].role_status）。
        """
        from temporal_index import TemporalEventIndex

        parts: List[str] = []
        focus_name = focus.unit_name or ""
        focus_chapter = get_unit_chapter(focus)

        # 1. 焦点在时间线上的位置
        if ws.story_ordinal is not None:
            ordinal = ws.story_ordinal
            ch = int(ordinal // 10000) if ordinal else focus_chapter
            ch_info = f"第{ch}章" if ch else ""
            parts.append(f"当前焦点在故事时间序数 ~{ordinal:.0f}")
            if ch_info:
                parts[-1] += f"（{ch_info}）"
        elif focus_chapter:
            parts.append(f"当前焦点在第 {focus_chapter} 章")
        else:
            parts.append(f"当前焦点：{focus_name}")

        # 2. 附近的事件（从 entity_timeline 取前 3）
        nearby = ws.entity_timeline[:3]
        if nearby:
            nearby_strs = []
            for evt in nearby:
                e_ord = evt.get("story_ordinal", "")
                e_label = evt.get("time_label", "")
                e_summary = evt.get("event", "")
                e_loc = evt.get("location", "")
                ts = f"#{e_ord:.0f}" if isinstance(e_ord, (int, float)) and e_ord else ""
                if e_label:
                    ts = e_label if not ts else f"{ts} {e_label}"
                loc_str = f"📍{e_loc}" if e_loc else ""
                nearby_strs.append(f"  {ts} {e_summary} {loc_str}".strip())
            if nearby_strs:
                parts.append("附近事件：")
                parts.extend(nearby_strs)

        # 3. 涉及实体的当前状态（从 character_states 取）
        char_states = ws.character_states
        if char_states:
            state_lines = []
            seen_chars: Set[str] = set()
            for cs in char_states:
                if cs.name and cs.name not in seen_chars:
                    seen_chars.add(cs.name)
                    if cs.status:
                        state_lines.append(f"  {cs.name}：{cs.status}")
            if state_lines:
                parts.append("当前角色状态：")
                parts.extend(state_lines)

        # 4. 预期产出提示
        parts.append("")
        parts.append(
            "请确保本章产生的 content 包含精确的时间信息"
            "（time_text/location/cast[].role_status），"
            "时间线信息（time_ordinal）将在写入时自动同步。"
        )

        ws.temporal_context_hint = "\n".join(parts)

    # ════════════════════════════════════════════════
    # 关系图数据加载
    # ════════════════════════════════════════════════

    def _load_ego_graph(self, ws: Workspace, focus: NarrativeUnit, config: Dict[str, Any]):
        """
        为焦点加载结构化 Ego Network。
        复用 GraphStore.get_relations()，按关系类型分组聚合。
        """
        graph_depth = config.get("graph_depth", 1)
        include_internal = config.get("graph_internal_edges", False)

        nodes = {}
        edges = []
        by_type = defaultdict(list)
        visited = {focus.id}

        # 中心节点
        nodes[focus.id] = {
            "id": focus.id,
            "name": focus.unit_name,
            "type": focus.type.value,
            "hop": 0,
        }

        # 1-hop 邻居
        for rel in self.store.get_relations(focus.id):
            other_id = rel.target_id if rel.source_id == focus.id else rel.source_id
            direction = "outgoing" if rel.source_id == focus.id else "incoming"
            other = self.store.get_unit(other_id)
            if not other or other.status == UnitStatus.ARCHIVED:
                continue

            if other_id not in visited:
                nodes[other_id] = {
                    "id": other_id,
                    "name": other.unit_name,
                    "type": other.type.value,
                    "hop": 1,
                }
                visited.add(other_id)

            edge_entry = {
                "from": rel.source_id,
                "to": rel.target_id,
                "type": rel.relation_type.value,
                "label": rel.label or "",
                "direction": direction,
            }
            edges.append(edge_entry)
            by_type[rel.relation_type.value].append({
                "name": other.unit_name,
                "type": other.type.value,
                "direction": direction,
            })

        # 1-hop 邻居之间的内部边（warm+）
        if include_internal and graph_depth >= 1:
            one_hop_ids = {nid for nid, info in nodes.items() if info["hop"] == 1}
            seen_edge_pairs = {(e["from"], e["to"], e["type"]) for e in edges}
            for nid in one_hop_ids:
                for rel in self.store.get_relations(nid):
                    pair_key = (rel.source_id, rel.target_id, rel.relation_type.value)
                    if pair_key in seen_edge_pairs:
                        continue
                    a_in = rel.source_id in visited
                    b_in = rel.target_id in visited
                    if a_in and b_in and rel.source_id != rel.target_id:
                        seen_edge_pairs.add(pair_key)
                        edges.append({
                            "from": rel.source_id,
                            "to": rel.target_id,
                            "type": rel.relation_type.value,
                            "label": rel.label or "",
                        })

        # 2-hop（hot 时）
        if graph_depth >= 2:
            one_hop_ids = {nid for nid, info in nodes.items() if info["hop"] == 1}
            new_visited = set(visited)
            for nid in list(one_hop_ids):
                for rel in self.store.get_relations(nid):
                    other_id = rel.target_id if rel.source_id == nid else rel.source_id
                    if other_id in new_visited:
                        continue
                    other = self.store.get_unit(other_id)
                    if not other or other.status == UnitStatus.ARCHIVED:
                        continue
                    nodes[other_id] = {
                        "id": other_id,
                        "name": other.unit_name,
                        "type": other.type.value,
                        "hop": 2,
                    }
                    new_visited.add(other_id)

        ws.ego_graph = {
            "center_id": focus.id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": list(nodes.values()),
            "edges": edges,
            "by_type": dict(by_type),
        }

        # 生成关系摘要文本（给 LLM 直接消费）
        parts = []
        for rel_type, neighbors in sorted(by_type.items()):
            names = [n["name"] for n in neighbors[:5]]
            extra = f"等{len(neighbors)}个" if len(neighbors) > 5 else ""
            parts.append(f"{rel_type}: {'、'.join(names)}{extra}")
        ws.relation_summary = "；".join(parts)

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
    
    def _detect_missing_references(self, ws: Workspace, config: Dict[str, Any]):
        """
        遍历已加载的场景和焦点场景，检核 content 中引用的实体是否在 graph 中存在。

        使用 TypeRegistry fact_fields 中 type=entity_reference 的声明
        取代 hardcoded 字段名。新增事实字段自动获得引用检测。
        """
        from type_registry import TypeRegistry

        # 构建已有实体名索引
        existing_chars = {e["unit_name"] for e in ws.character_arcs}
        existing_worlds = {e["unit_name"] for e in ws.world_rules}
        existing_plots = {e["unit_name"] for e in ws.plot_threads}
        _TARGET_MAP = {
            "character_arc": existing_chars,
            "world_rule": existing_worlds,
            "plot_thread": existing_plots,
        }
        _TARGET_LABEL = {
            "character_arc": "CHARACTER_ARC",
            "world_rule": "WORLD_RULE",
            "plot_thread": "PLOT_THREAD",
        }

        # 收集所有需要检核的场景：已加载的场景 + 焦点本身（如果它是 SCENE）
        scene_ids_to_check = set()
        for se in ws.scenes:
            sid = se.get("unit_id", "")
            if sid:
                scene_ids_to_check.add(sid)
        if ws.focus_unit and ws.focus_unit.type == UnitType.SCENE:
            scene_ids_to_check.add(ws.focus_unit.id)

        registry = TypeRegistry.get_global()

        for sid in scene_ids_to_check:
            scene = self.store.get_unit(sid)
            if not scene:
                continue
            content = self._parse_json_content(scene)
            if not content:
                continue

            scene_name = scene.unit_name or "?"
            scene_type = content.get("subtype", "")
            scene_pov = content.get("pov_character", "")
            scene_summary = content.get("one_line_summary", "")
            ctx_parts = []
            if scene_type:
                ctx_parts.append(scene_type)
            if scene_pov:
                ctx_parts.append(f"POV:{scene_pov}")
            ctx_str = "，".join(ctx_parts)

            # 从 TypeRegistry 读取该类型的所有 fact_fields（entity_reference 类型）
            type_name = scene.type.value if hasattr(scene.type, "value") else str(scene.type)
            td = registry.get_type(type_name)
            ref_fields = [f for f in (td.fact_fields if td else [])
                          if f.type == "entity_reference"]

            for ff in ref_fields:
                target = ff.target_type or ""
                existing_set = _TARGET_MAP.get(target)
                label = _TARGET_LABEL.get(target, target.upper())
                if existing_set is None:
                    continue

                # 用 extract_facts 按路径提取值
                facts = registry.extract_facts(type_name, content)
                values = facts.get(ff.name, [])

                for val in values:
                    if val and isinstance(val, str) and val not in existing_set:
                        gap = f"场景「{scene_name}」（{ctx_str}）引用了「{val}」（{ff.description or ff.name}）但 graph 无对应 {label} 单元"
                        if scene_summary:
                            gap += f"。场景概要：{scene_summary}"
                        if gap not in ws.missing_gaps:
                            ws.missing_gaps.append(gap)

    def _extract_scene_context(self, ws: Workspace, scene_unit: NarrativeUnit, scene_order: int = 0):
        """从 SCENE 单元提取场景上下文到工作空间（供 SCENE/CHUNK 焦点共用）

        Args:
            scene_order: 场景在章内的顺序（0-based），写入 CharacterStateEntry 用于时间线排序
        """
        content = self._parse_json_content(scene_unit)
        if not content:
            return
        
        # extra.time 已在 GraphStore.create_unit/update_unit 中由
        # auto_sync_story_time 自动同步，此处不再重复。
        
        # 提取场景信息（多次调用时累加，避免最后一条覆盖前面）
        t = content.get("time_text", "")
        if t:
            raw = f"{ws.story_time.raw}；{t}" if ws.story_time else t
            existing_ordinal = ws.story_time.ordinal if ws.story_time else None
            existing_precision = ws.story_time.precision if ws.story_time else "vague"
            ws.story_time = StoryTimeInfo(raw=raw, ordinal=existing_ordinal, precision=existing_precision)
        else:
            if not ws.story_time:
                ws.story_time = StoryTimeInfo()
        
        loc = content.get("location", "")
        if loc:
            ws.location = f"{ws.location}；{loc}" if ws.location else loc
        
        # 场域核心信息（多次调用时累加）
        func = content.get("core_conflict", content.get("one_line_summary", ""))
        if func:
            ws.scene_function = f"{ws.scene_function}；{func}" if ws.scene_function else func
        
        # 提取 extra.time 中的序数
        extra = scene_unit.extra or {}
        time_info = extra.get("time", {})
        if isinstance(time_info, dict):
            story_ordinal = time_info.get("ordinal")
            precision = time_info.get("precision", "vague")
            if story_ordinal is not None and (ws.story_time.ordinal is None 
                or precision == "same"):
                ws.story_time.ordinal = story_ordinal
                ws.story_time.precision = precision
        
        # 角色状态（构建 CharacterStateEntry 对象）
        characters = content.get("cast", [])
        if isinstance(characters, list):
            for c in characters:
                if isinstance(c, dict):
                    ws.character_states.append(CharacterStateEntry(
                        name=c.get("name", ""),
                        status=c.get("role_status", ""),
                        description=c.get("role_in_scene", ""),
                        scene_id=scene_unit.id,
                        scene_name=scene_unit.unit_name or "",
                        scene_order=scene_order,
                        story_ordinal=ws.story_time.ordinal,
                    ))
                elif isinstance(c, str):
                    ws.character_states.append(CharacterStateEntry(
                        name=c, scene_id=scene_unit.id,
                        scene_name=scene_unit.unit_name or "",
                        scene_order=scene_order,
                        story_ordinal=ws.story_time.ordinal,
                    ))
        
        # 写作指引
        scene_type = content.get("subtype", "")
        if scene_type:
            ws.writing_guides.append(f"场域功能：{scene_type}")
        summary = content.get("one_line_summary", "")
        if summary:
            ws.writing_guides.append(f"场景概要：{summary}")

    def _enrich_scene_context(self, ws: Workspace, focus: NarrativeUnit):
        """提取场景级上下文信息（SCENE 焦点专用）"""
        if not focus or focus.type != UnitType.SCENE:
            return
        self._extract_scene_context(ws, focus, scene_order=0)
