"""
投影引擎：将叙事单元网络 → 用户可读的文档视图。

核心原则：文件的真相源不再是文件本身，而是 graph 状态。
投影是 graph 在某个时间点的快照的序列化视图。

投影策略：
- 全量投影：从 graph 完全重建目标视图（用于初始化和修复）
- 增量投影：在 graph 变更后只更新变动的投影部分（用于日常操作）
- 延迟投影：只有在视图被读取时才执行投影（用于不常访问的视图）
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict

from graph_schema import (
    NarrativeUnit,
    UnitType,
    UnitStatus,
    RelationType,
    ProjectionView,
)
from graph_store import GraphStore


class ProjectionEngine:
    """
    投影引擎。
    
    将 graph 中的叙事单元网络投影为多视图文档体系。
    支持全量重建和增量更新。
    """
    
    # 投影文件路径模板（相对于项目根目录）
    PROJECTION_PATHS = {
        ProjectionView.OUTLINE: "outline/总纲.yaml",
        ProjectionView.CHAPTER_OUTLINE: "outline/分纲/卷{volume}/第{chapter}章.yaml",
        ProjectionView.CHARACTER: "characters/{name}.yaml",
        ProjectionView.WORLDBUILDING: "worldbuilding/{name}.yaml",
        ProjectionView.PLOT: "outline/情节线/{name}.yaml",
        ProjectionView.TRACKING: "outline/追踪/{name}.yaml",
        ProjectionView.TIMELINE: "outline/时间线设计.yaml",
    }
    
    def __init__(self, store: GraphStore, project_root: str, output_mode: str = "in_place"):
        """
        output_mode:
          "in_place" — 写入原有文件位置（默认）
          "hybrid"   — 同时写入原位和 projections/ 目录
        """
        self.store = store
        self.project_root = Path(project_root)
        self.output_mode = output_mode
        self.projections_dir = self.project_root / "projections"
        self._projection_cache: Dict[str, str] = {}  # path → content
        
        # 注册投影器
        self._projectors: Dict[ProjectionView, Callable] = {
            ProjectionView.OUTLINE: self._project_outline,
            ProjectionView.CHAPTER_OUTLINE: self._project_chapter_outline,
            ProjectionView.CHARACTER: self._project_character,
            ProjectionView.WORLDBUILDING: self._project_worldbuilding,
            ProjectionView.PLOT: self._project_plot,
            ProjectionView.TRACKING: self._project_tracking,
            ProjectionView.TIMELINE: self._project_timeline,
        }
    
    # ── 公共 API ────────────────────────────────────────────────────────
    
    def project(
        self,
        view: ProjectionView,
        params: Optional[Dict[str, Any]] = None,
        force_rebuild: bool = False,
    ) -> str:
        """
        生成指定视图的投影。
        
        params 示例：
        - {"name": "林昭"} → 角色档案投影
        - {"volume": 1, "chapter": 3} → 分纲投影
        """
        projector = self._projectors.get(view)
        if not projector:
            raise ValueError(f"未注册的投影视图: {view}")
        
        return projector(**(params or {}))
    
    def project_to_file(
        self,
        view: ProjectionView,
        params: Optional[Dict[str, Any]] = None,
        force_rebuild: bool = False,
    ) -> str:
        """
        生成投影并写入文件。
        output_mode="hybrid" 时同时写入原位和 projections/。
        返回写入的文件路径（原位）。
        """
        content = self.project(view, params, force_rebuild)
        file_path = self._resolve_in_place_path(view, params or {})
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # hybrid 模式：同时写入 projections/
        if self.output_mode == "hybrid":
            proj_path = self._resolve_projection_path(view, params or {})
            os.makedirs(os.path.dirname(proj_path), exist_ok=True)
            with open(proj_path, "w", encoding="utf-8") as f:
                f.write(content)
        
        return file_path
    
    def rebuild_all(self) -> List[str]:
        """全量重建所有投影"""
        written = []
        
        # 1. 总纲投影
        written.append(self.project_to_file(ProjectionView.OUTLINE))
        
        # 2. 角色投影
        for unit in self.store.find_units(type=UnitType.CHARACTER_ARC):
            if unit.status != UnitStatus.ARCHIVED:
                written.append(
                    self.project_to_file(ProjectionView.CHARACTER, {"unit_id": unit.id})
                )
        
        # 3. 世界观投影
        for unit in self.store.find_units(type=UnitType.WORLD_RULE):
            if unit.status != UnitStatus.ARCHIVED:
                written.append(
                    self.project_to_file(ProjectionView.WORLDBUILDING, {"unit_id": unit.id})
                )
        
        # 4. 情节线投影
        for unit in self.store.find_units(type=UnitType.PLOT_THREAD):
            if unit.status != UnitStatus.ARCHIVED:
                written.append(
                    self.project_to_file(ProjectionView.PLOT, {"unit_id": unit.id})
                )
        
        # 5. 时间线投影
        written.append(self.project_to_file(ProjectionView.TIMELINE))
        
        return written
    
    def _resolve_in_place_path(self, view: ProjectionView, params: Dict[str, Any]) -> str:
        """解析原位文件路径"""
        path = self._format_path(view, params)
        return str(self.project_root / path)
    
    def _resolve_projection_path(self, view: ProjectionView, params: Dict[str, Any]) -> str:
        """解析 projections/ 目录下的路径"""
        path = self._format_path(view, params)
        return str(self.projections_dir / path)
    
    def _format_path(self, view: ProjectionView, params: Dict[str, Any]) -> str:
        """根据视图和参数格式化相对路径"""
        template = self.PROJECTION_PATHS[view]
        
        if view == ProjectionView.CHAPTER_OUTLINE:
            return template.format(
                volume=params.get("volume", 1),
                chapter=params.get("chapter", 1),
            )
        elif view in (ProjectionView.CHARACTER, ProjectionView.WORLDBUILDING,
                       ProjectionView.PLOT):
            name = params.get("name", params.get("unit_id", "unknown"))
            return template.format(name=name)
        elif view == ProjectionView.TRACKING:
            name = params.get("name", "综合")
            return template.format(name=name)
        else:
            return template
    
    # ── 各视图投影器 ────────────────────────────────────────────────────
    
    def _project_outline(self, **kwargs) -> str:
        """总纲投影：从 graph 中聚合 plot_thread + scene 生成总纲视图"""
        lines = []
        lines.append("# 总纲（V2 Graph 投影）")
        lines.append(f"# 生成时间: {datetime.now(timezone.utc).isoformat()}")
        lines.append("")
        
        # 项目信息
        lines.append("## 项目信息")
        lines.append("")
        lines.append("```yaml")
        
        # 从 graph 中获取项目信息
        project_units = self.store.find_units(type=UnitType.WORLD_RULE)
        lines.append(f"叙事单元总数: {len(self.store.list_units())}")
        lines.append(f"场景数: {len(self.store.find_units(type=UnitType.SCENE))}")
        lines.append(f"角色弧线数: {len(self.store.find_units(type=UnitType.CHARACTER_ARC))}")
        lines.append(f"情节线数: {len(self.store.find_units(type=UnitType.PLOT_THREAD))}")
        lines.append(f"世界观规则数: {len(project_units)}")
        lines.append(f"笔记数: {len(self.store.find_units(type=UnitType.NOTE))}")
        lines.append("```")
        lines.append("")
        
        # 情节线摘要
        lines.append("## 情节线总览")
        lines.append("")
        for pt in self.store.find_units(type=UnitType.PLOT_THREAD):
            status_emoji = {
                UnitStatus.SPROUT: "🌱",
                UnitStatus.GROWING: "🔄",
                UnitStatus.MATURE: "✅",
                UnitStatus.FROZEN: "❄️",
                UnitStatus.ARCHIVED: "📦",
            }.get(pt.status, "📝")
            lines.append(f"- {status_emoji} **{pt.unit_name}** ({pt.status.value})")
            if pt.content:
                content_preview = pt.content[:100] + "..." if len(pt.content) > 100 else pt.content
                lines.append(f"  - {content_preview}")
            # 关联场景数
            related = self.store.get_relations(pt.id, direction="outgoing")
            scene_relations = [r for r in related if r.relation_type in (
                RelationType.IMPLEMENTS, RelationType.REFERENCES)]
            if scene_relations:
                lines.append(f"  - 关联场景/事件: {len(scene_relations)} 个")
            lines.append("")
        
        # 角色清单
        lines.append("## 角色清单")
        lines.append("")
        for ca in self.store.find_units(type=UnitType.CHARACTER_ARC):
            lines.append(f"- {ca.unit_name} (confidence: {ca.confidence})")
        lines.append("")
        
        # 章节概况（从 scene 的时间线信息推算）
        scenes = self.store.find_units(type=UnitType.SCENE)
        if scenes:
            lines.append("## 章节概况")
            lines.append("")
            chapters = defaultdict(list)
            for s in scenes:
                ch = s.belongs_to_chapter or 0
                chapters[ch].append(s)
            for ch in sorted(chapters.keys()):
                chapter_scenes = chapters[ch]
                lines.append(f"### 第{ch}章（{len(chapter_scenes)} 个场景）")
                for s in chapter_scenes:
                    lines.append(f"- {s.unit_name}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _project_chapter_outline(self, volume: int = 1, chapter: int = 1) -> str:
        """分纲投影：将指定章节的场景群投影为分纲 YAML"""
        scenes = self.store.find_units(
            type=UnitType.SCENE,
            chapter=chapter,
            volume=volume,
        )
        
        lines = []
        lines.append(f"# 第{chapter}章 分纲（V2 Graph 投影）")
        lines.append(f"volume: {volume}")
        lines.append(f"chapter: {chapter}")
        lines.append(f"scene_count: {len(scenes)}")
        lines.append(f"projected_at: {datetime.now(timezone.utc).isoformat()}")
        lines.append("")
        
        for i, scene in enumerate(scenes):
            lines.append(f"## 场景{i+1}: {scene.unit_name}")
            lines.append(f"id: {scene.id}")
            lines.append(f"status: {scene.status.value}")
            lines.append(f"confidence: {scene.confidence}")
            if scene.tags:
                lines.append(f"tags: {', '.join(scene.tags)}")
            lines.append("")
            if scene.content:
                lines.append(scene.content)
                lines.append("")
            
            # 关联信息
            neighbors = self.store.get_neighbors(scene.id, max_depth=1)
            degree_1 = neighbors.get(1, set())
            if degree_1:
                lines.append("**关联单元:**")
                for nid in degree_1:
                    neighbor = self.store.get_unit(nid)
                    if neighbor:
                        lines.append(f"- {neighbor.type.value}: {neighbor.unit_name}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _project_character(self, unit_id: str = "", name: str = "", **kwargs) -> str:
        """角色档案投影"""
        unit = None
        if unit_id:
            unit = self.store.get_unit(unit_id)
        elif name:
            unit = self.store.get_unit_by_name(name)
        
        if not unit:
            return f"# 角色档案\n\n（未找到角色: {name or unit_id}）\n"
        
        lines = []
        lines.append(f"# 角色档案: {unit.unit_name}")
        lines.append(f"id: {unit.id}")
        lines.append(f"type: {unit.type.value}")
        lines.append(f"status: {unit.status.value}")
        lines.append(f"confidence: {unit.confidence}")
        if unit.tags:
            lines.append(f"tags: [{', '.join(unit.tags)}]")
        lines.append("")
        
        # 角色内容（结构化 JSON 或自由文本）
        if unit.content:
            try:
                content_dict = json.loads(unit.content)
                for key, value in content_dict.items():
                    if isinstance(value, dict):
                        lines.append(f"## {key}")
                        for k, v in value.items():
                            lines.append(f"{k}: {v}")
                        lines.append("")
                    elif isinstance(value, list):
                        lines.append(f"## {key}")
                        for item in value:
                            lines.append(f"- {item}")
                        lines.append("")
                    else:
                        lines.append(f"## {key}")
                        lines.append(str(value))
                        lines.append("")
            except json.JSONDecodeError:
                lines.append(unit.content)
        else:
            lines.append("（暂无详细内容）")
        lines.append("")
        
        # 关联关系
        lines.append("---")
        lines.append("## 关联")
        for rel in self.store.get_relations(unit.id, direction="outgoing"):
            target = self.store.get_unit(rel.target_id)
            if target:
                lines.append(f"- {rel.relation_type.value} → {target.unit_name} ({target.type.value})")
        for rel in self.store.get_relations(unit.id, direction="incoming"):
            source = self.store.get_unit(rel.source_id)
            if source:
                lines.append(f"- {source.unit_name} → {rel.relation_type.value} → 本角色")
        
        return "\n".join(lines)
    
    def _project_worldbuilding(self, unit_id: str = "", name: str = "", **kwargs) -> str:
        """世界观规则投影"""
        unit = None
        if unit_id:
            unit = self.store.get_unit(unit_id)
        elif name:
            unit = self.store.get_unit_by_name(name)
        
        if not unit:
            return f"# 世界观\n\n（未找到: {name or unit_id}）\n"
        
        lines = []
        lines.append(f"# 世界观: {unit.unit_name}")
        lines.append(f"id: {unit.id}")
        lines.append(f"status: {unit.status.value}")
        lines.append(f"confidence: {unit.confidence}")
        if unit.tags:
            lines.append(f"tags: [{', '.join(unit.tags)}]")
        lines.append("")
        
        if unit.content:
            lines.append(unit.content)
        
        return "\n".join(lines)
    
    def _project_plot(self, unit_id: str = "", name: str = "", **kwargs) -> str:
        """情节线投影"""
        unit = None
        if unit_id:
            unit = self.store.get_unit(unit_id)
        elif name:
            unit = self.store.get_unit_by_name(name)
        
        if not unit:
            return f"# 情节线\n\n（未找到: {name or unit_id}）\n"
        
        lines = []
        lines.append(f"# 情节线: {unit.unit_name}")
        lines.append(f"id: {unit.id}")
        lines.append(f"status: {unit.status.value}")
        lines.append("")
        
        if unit.content:
            lines.append(unit.content)
            lines.append("")
        
        # 关联的场景
        lines.append("## 关联场景")
        for rel in self.store.get_relations(unit.id, relation_type=RelationType.IMPLEMENTS):
            target = self.store.get_unit(rel.target_id)
            if target:
                lines.append(f"- {target.unit_name} (ch.{target.belongs_to_chapter})")
        
        return "\n".join(lines)
    
    def _project_tracking(self, name: str = "综合", **kwargs) -> str:
        """追踪统计投影"""
        lines = []
        lines.append(f"# 追踪统计: {name}")
        lines.append(f"projected_at: {datetime.now(timezone.utc).isoformat()}")
        lines.append("")
        
        stats = self.store.stats()
        lines.append("## Graph 统计")
        for key, value in stats.items():
            lines.append(f"{key}: {value}")
        lines.append("")
        
        # 按章节统计场景
        lines.append("## 章节进展")
        scenes = self.store.find_units(type=UnitType.SCENE)
        chapters = defaultdict(list)
        for s in scenes:
            ch = s.belongs_to_chapter or 0
            chapters[ch].append(s)
        for ch in sorted(chapters.keys()):
            ch_scenes = chapters[ch]
            mature = sum(1 for s in ch_scenes if s.status == UnitStatus.MATURE)
            lines.append(f"第{ch}章: {len(ch_scenes)} 场景 ({mature} 已完成)")
        
        return "\n".join(lines)
    
    def _project_timeline(self, **kwargs) -> str:
        """时间线投影"""
        scenes = self.store.find_units(type=UnitType.SCENE)
        scenes.sort(key=lambda s: (s.belongs_to_chapter or 0, s.created_at))
        
        lines = []
        lines.append("# 时间线设计（V2 Graph 投影）")
        lines.append(f"projected_at: {datetime.now(timezone.utc).isoformat()}")
        lines.append("")
        lines.append("## 场景时间线")
        lines.append("")
        
        for scene in scenes:
            ch = scene.belongs_to_chapter or "?"
            lines.append(f"- **第{ch}章**: {scene.unit_name}")
            if scene.tags:
                lines.append(f"  - 标签: {', '.join(scene.tags)}")
        
        return "\n".join(lines)
