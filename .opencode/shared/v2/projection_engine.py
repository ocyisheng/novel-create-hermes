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
          "in_place"  — 写入原有文件位置（默认，向后兼容）
          "hybrid"    — 同时写入原位和 projections/ 目录
          "graph_only" — 跳过所有文件写入，仅返回内容（V2 纯模式）
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
        output_mode="graph_only" 时跳过文件写入（纯 V2 模式）。
        output_mode="hybrid" 时同时写入原位和 projections/。
        返回写入的文件路径，graph_only 模式返回空字符串。
        """
        content = self.project(view, params, force_rebuild)
        
        # graph_only 模式：跳过所有文件写入
        if self.output_mode == "graph_only":
            return ""
        
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
                RelationType.IMPLEMENTS, RelationType.REFERENCES,
                RelationType.LOCATED_AT)]
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
        # Combine IMPLEMENTS + LOCATED_AT to show all scene ties
        related_rels = (
            self.store.get_relations(unit.id, relation_type=RelationType.IMPLEMENTS)
            + self.store.get_relations(unit.id, relation_type=RelationType.LOCATED_AT)
        )
        for rel in related_rels:
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

    # ── 结构化文档导出（V2 原生） ──────────────────────────────────

    def export_docs(self, output_dir: Optional[str] = None) -> List[str]:
        """
        将 V2 graph 数据导出为结构化 Markdown 文档（graph/export/）。
        供人阅读或其他项目复用。
        返回写入的文件路径列表。
        """
        export_dir = Path(output_dir) if output_dir else self.project_root / "graph" / "export"
        export_dir.mkdir(parents=True, exist_ok=True)

        written = []

        # 1. index.md — 项目总览
        written.append(self._export_index(export_dir))

        # 2. characters.md — 角色档案
        written.append(self._export_characters(export_dir))

        # 3. worldbuilding.md — 世界观规则
        written.append(self._export_worldbuilding(export_dir))

        # 4. plot.md — 情节线
        written.append(self._export_plot(export_dir))

        # 5. scenes.md — 场景列表（按章节）
        written.append(self._export_scenes(export_dir))

        # 6. timeline.md — 时间线
        written.append(self._export_timeline(export_dir))

        # 7. relations.md — 关系网络摘要
        written.append(self._export_relations(export_dir))

        return written

    def _export_index(self, export_dir: Path) -> str:
        """项目总览"""
        stats = self.store.stats()
        lines = [
            f"# {self.project_root.name} — 创作项目文档",
            "",
            f"> 由 V2 GraphStore 自动导出",
            f"> 导出时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 项目统计",
            "",
            f"- 叙事单元: {stats['total_units']}",
            f"- 关系: {stats['total_relations']}",
            f"- 事件: {stats['total_events']}",
            "",
            "## 内容",
            "",
            "- [角色档案](characters.md)",
            "- [世界观](worldbuilding.md)",
            "- [情节线](plot.md)",
            "- [场景列表](scenes.md)",
            "- [时间线](timeline.md)",
            "- [关系网络](relations.md)",
            "",
        ]

        # 按类型统计
        if stats.get('by_type'):
            lines.append("## 叙事单元分布")
            lines.append("")
            for typ, count in sorted(stats['by_type'].items()):
                lines.append(f"- {typ}: {count}")
            lines.append("")

        content = "\n".join(lines)
        path = export_dir / "index.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _export_characters(self, export_dir: Path) -> str:
        """角色档案"""
        units = self.store.find_units(type=UnitType.CHARACTER_ARC)
        lines = [
            f"# 角色档案",
            f"",
            f"共 {len(units)} 个角色",
            f"",
        ]

        for u in units:
            lines.append(f"---")
            lines.append(f"")
            lines.append(f"## {u.unit_name}")
            lines.append(f"")
            lines.append(f"- **状态**: {u.status.value}")
            lines.append(f"- **确信度**: {u.confidence}")
            if u.tags:
                lines.append(f"- **标签**: {', '.join(u.tags)}")

            # 内容
            if u.content:
                # 尝试按 JSON 解析，否则当纯文本
                try:
                    content_dict = json.loads(u.content)
                    for k, v in content_dict.items():
                        if isinstance(v, dict):
                            lines.append(f"")
                            lines.append(f"### {k}")
                            for sk, sv in v.items():
                                lines.append(f"- **{sk}**: {sv}")
                        elif isinstance(v, list):
                            lines.append(f"")
                            lines.append(f"### {k}")
                            for item in v:
                                lines.append(f"- {item}")
                        else:
                            lines.append(f"- **{k}**: {v}")
                except json.JSONDecodeError:
                    preview = u.content[:500]
                    lines.append(f"")
                    lines.append(preview)

            # 关联关系
            rels = self.store.get_relations(u.id)
            if rels:
                lines.append(f"")
                lines.append(f"### 关联")
                for rel in rels:
                    if rel.source_id == u.id:
                        target = self.store.get_unit(rel.target_id)
                        if target:
                            lines.append(f"- → {target.unit_name} ({rel.relation_type.value})")
                    else:
                        source = self.store.get_unit(rel.source_id)
                        if source:
                            lines.append(f"- ← {source.unit_name} ({rel.relation_type.value})")
            lines.append(f"")

        content = "\n".join(lines)
        path = export_dir / "characters.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _export_worldbuilding(self, export_dir: Path) -> str:
        """世界观规则"""
        units = self.store.find_units(type=UnitType.WORLD_RULE)
        lines = [
            f"# 世界观",
            f"",
            f"共 {len(units)} 条规则",
            f"",
        ]

        for u in units:
            lines.append(f"---")
            lines.append(f"")
            lines.append(f"## {u.unit_name}")
            lines.append(f"")
            lines.append(f"- **状态**: {u.status.value}")
            if u.tags:
                lines.append(f"- **标签**: {', '.join(u.tags)}")
            if u.content:
                preview = u.content[:1000]
                lines.append(f"")
                lines.append(preview)
            lines.append(f"")

        content = "\n".join(lines)
        path = export_dir / "worldbuilding.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _export_plot(self, export_dir: Path) -> str:
        """情节线"""
        units = self.store.find_units(type=UnitType.PLOT_THREAD)
        lines = [
            f"# 情节线",
            f"",
            f"共 {len(units)} 条",
            f"",
        ]

        for u in units:
            lines.append(f"---")
            lines.append(f"")
            lines.append(f"## {u.unit_name}")
            lines.append(f"")
            lines.append(f"- **状态**: {u.status.value}")

            # 关联场景
            rels = self.store.get_relations(u.id, direction="incoming")
            scenes = []
            for rel in rels:
                source = self.store.get_unit(rel.source_id)
                if source and source.type == UnitType.SCENE:
                    scenes.append(source)
            if scenes:
                lines.append(f"- **关联场景**: {len(scenes)}")
                for s in sorted(scenes, key=lambda x: x.belongs_to_chapter or 0):
                    lines.append(f"  - 第{s.belongs_to_chapter or '?'}章: {s.unit_name}")

            if u.content:
                lines.append(f"")
                lines.append(u.content[:500])
            lines.append(f"")

        content = "\n".join(lines)
        path = export_dir / "plot.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _export_scenes(self, export_dir: Path) -> str:
        """场景列表（按章节）"""
        scenes = self.store.find_units(type=UnitType.SCENE)
        scenes.sort(key=lambda s: (s.belongs_to_chapter or 0, s.created_at))

        # 按章节分组
        from collections import defaultdict
        by_chapter = defaultdict(list)
        for s in scenes:
            by_chapter[s.belongs_to_chapter or 0].append(s)

        lines = [
            f"# 场景列表",
            f"",
            f"共 {len(scenes)} 个场景",
            f"",
        ]

        for ch in sorted(by_chapter.keys()):
            ch_scenes = by_chapter[ch]
            label = f"第{ch}章" if ch else "未分配章节"
            lines.append(f"## {label} ({len(ch_scenes)} 场景)")
            lines.append(f"")
            for s in ch_scenes:
                lines.append(f"### {s.unit_name}")
                lines.append(f"")
                lines.append(f"- **状态**: {s.status.value}")
                lines.append(f"- **确信度**: {s.confidence}")
                if s.tags:
                    lines.append(f"- **标签**: {', '.join(s.tags)}")

                # 关联角色
                rels = self.store.get_relations(s.id, direction="incoming")
                chars = []
                for rel in rels:
                    source = self.store.get_unit(rel.source_id)
                    if source and source.type == UnitType.CHARACTER_ARC:
                        chars.append(source.unit_name)
                if chars:
                    lines.append(f"- **出场角色**: {', '.join(chars)}")

                if s.content:
                    preview = s.content[:300]
                    lines.append(f"")
                    lines.append(preview)
                lines.append(f"")

        content = "\n".join(lines)
        path = export_dir / "scenes.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _export_timeline(self, export_dir: Path) -> str:
        """时间线"""
        scenes = self.store.find_units(type=UnitType.SCENE)
        scenes.sort(key=lambda s: (s.belongs_to_chapter or 0, s.created_at))

        lines = [
            f"# 时间线",
            f"",
            f"由场景章节顺序排列",
            f"",
        ]

        for s in scenes:
            ch = s.belongs_to_chapter or "?"
            lines.append(f"- **第{ch}章**: {s.unit_name}")

        # 也包含 NOTE 类型中带"时间线"标签的内容
        notes = self.store.find_units(type=UnitType.NOTE)
        timeline_notes = [n for n in notes if "时间线" in n.tags]
        if timeline_notes:
            lines.append(f"")
            lines.append(f"## 时间线笔记")
            lines.append(f"")
            for n in timeline_notes:
                lines.append(f"### {n.unit_name}")
                if n.content:
                    lines.append(f"")
                    lines.append(n.content[:500])
                lines.append(f"")

        content = "\n".join(lines)
        path = export_dir / "timeline.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def _export_relations(self, export_dir: Path) -> str:
        """关系网络摘要"""
        all_rels = self.store.get_relations()
        by_type: Dict[str, int] = {}
        by_pair: Dict[str, list] = {}

        for rel in all_rels:
            by_type[rel.relation_type.value] = by_type.get(rel.relation_type.value, 0) + 1
            source = self.store.get_unit(rel.source_id)
            target = self.store.get_unit(rel.target_id)
            if source and target:
                key = f"{source.unit_name} → {target.unit_name}"
                if key not in by_pair:
                    by_pair[key] = []
                by_pair[key].append(rel.relation_type.value)

        lines = [
            f"# 关系网络",
            f"",
            f"共 {len(all_rels)} 条关系",
            f"",
            f"## 关系类型分布",
            f"",
        ]
        for rt, count in sorted(by_type.items(), key=lambda x: -x[1]):
            lines.append(f"- {rt}: {count}")

        lines.append(f"")
        lines.append(f"## 关系列表（节选）")
        lines.append(f"")

        # 按关联对展示（取频率最高的前 50）
        sorted_pairs = sorted(by_pair.items(), key=lambda x: -len(x[1]))[:50]
        for pair, types in sorted_pairs:
            lines.append(f"- {pair}  [{', '.join(set(types))}]")

        if len(by_pair) > 50:
            lines.append(f"")
            lines.append(f"... 共 {len(by_pair)} 对关联，仅显示前 50")

        content = "\n".join(lines)
        path = export_dir / "relations.md"
        path.write_text(content, encoding="utf-8")
        return str(path)
