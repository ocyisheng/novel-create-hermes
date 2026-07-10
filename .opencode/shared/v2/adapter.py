"""
兼容适配器：让现有 SKILL.md 代码通过 graph 存储工作。

设计目标：
1. 现有 SKILL.md 的写文件代码不改，无缝切换到 graph 后端
2. 每写一个 YAML/TXT 文件 → 同时写入 graph + 投影回文件
3. 提供"迁移模式"：从现有文件系统一次性导入到 graph

适配策略（三种模式）：
- DUAL_WRITE: 同时写入 graph 和文件（默认，安全迁移）
- GRAPH_ONLY: 只写 graph，依赖投影引擎生成文件（纯净模式）
- LEGACY_FALLBACK: 只写文件，不写 graph（回退模式）
"""

from __future__ import annotations

import json
import os
import yaml
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict

from graph_schema import (
    NarrativeUnit,
    UnitType,
    UnitStatus,
    RelationType,
    create_unit_id,
)
from graph_store import GraphStore
from projection_engine import ProjectionEngine, ProjectionView


class AdapterMode(str, Enum):
    DUAL_WRITE = "dual_write"          # graph + 文件双写
    GRAPH_ONLY = "graph_only"          # 只写 graph
    LEGACY_FALLBACK = "legacy_fallback"  # 只写文件


class WriteMode(str, Enum):
    """对应现有架构中的写入方式"""
    CREATE = "create"                   # 新建文件（write）
    OVERWRITE = "overwrite"             # 覆写（write）
    APPEND = "append"                   # 追加（edit）
    DELETE = "delete"                   # 删除


class LegacyFileAdapter:
    """
    兼容适配器。
    
    接管现有 SKILL.md 对文件系统的写入操作，
    在写入文件的同时维护 graph 数据。
    """
    
    # 已知的文件路径 → 叙事单元类型映射
    PATH_PATTERNS = [
        ("characters/", UnitType.CHARACTER_ARC),
        ("worldbuilding/", UnitType.WORLD_RULE),
        ("outline/情节线/", UnitType.PLOT_THREAD),
        ("outline/分纲/", UnitType.STRUCTURE),
        ("ideation/", UnitType.NOTE),
        ("quality/", UnitType.NOTE),
        ("chapters/", UnitType.CHUNK),
    ]
    
    def __init__(
        self,
        store: GraphStore,
        projection: ProjectionEngine,
        mode: AdapterMode = AdapterMode.DUAL_WRITE,
    ):
        self.store = store
        self.projection = projection
        self.mode = mode
        self._stats = {
            "graph_writes": 0,
            "file_writes": 0,
            "projections": 0,
            "migrations": 0,
            "errors": 0,
        }
    
    # ── 文件写入拦截 ────────────────────────────────────────────────────
    
    def write_file(
        self,
        file_path: str,
        content: str,
        mode: WriteMode = WriteMode.OVERWRITE,
        actor: str = "script",
    ) -> bool:
        """
        写入文件（同时维护 graph）。
        
        这是适配器的核心入口——SKILL.md 中所有 write_file 调用
        都应替换为 adapter.write_file()。
        
        如果适配器处于 DUAL_WRITE 模式：
        1. 解析文件内容 → 提取叙事单元
        2. 写入 graph
        3. 写回文件（确保文件与 graph 一致）
        """
        rel_path = self._relative_path(file_path)
        
        # Step 1: 解析叙事单元
        units = self._parse_file_to_units(rel_path, content)
        
        # Step 2: 写入 graph
        if self.mode != AdapterMode.LEGACY_FALLBACK:
            for unit in units:
                existing = self.store.get_unit_by_name(unit.unit_name)
                if existing:
                    self.store.update_unit(
                        existing.id,
                        content=unit.content,
                        status=unit.status,
                        tags=unit.tags,
                        extra=unit.extra,
                        actor=actor,
                    )
                else:
                    self.store.create_unit(
                        type=unit.type,
                        unit_name=unit.unit_name,
                        content=unit.content,
                        status=unit.status,
                        tags=unit.tags,
                        extra=unit.extra,
                        actor=actor,
                    )
                    self._stats["graph_writes"] += 1
        
        # Step 3: 写入文件
        if self.mode != AdapterMode.GRAPH_ONLY:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self._stats["file_writes"] += 1
        
        # Step 4: 触发投影更新
        if self.mode == AdapterMode.DUAL_WRITE:
            self._trigger_projection(rel_path)
        
        return True
    
    def write_yaml(
        self,
        file_path: str,
        data: dict,
        mode: WriteMode = WriteMode.OVERWRITE,
        actor: str = "script",
    ) -> bool:
        """写入 YAML 文件（同时维护 graph）"""
        content = yaml.dump(data, allow_unicode=True, sort_keys=False, default_style=None)
        return self.write_file(file_path, content, mode, actor)
    
    def write_chapter(
        self,
        file_path: str,
        chapter_text: str,
        chapter_number: int,
        version_label: str = "v1",
        actor: str = "script",
        scene_id: Optional[str] = None,
    ) -> bool:
        """
        写入章节正文（TXT）+ 更新 graph。
        
        章节正文存为 TXT 文件（file_path），
        graph 中的 CHUNK 单元只存元数据 JSON。
        file_path 为空时自动按约定生成：chapters/第{chapter_number}章_{version_label}.txt
        
        如果 scene_id 不为空，自动建立 CHUNK→SCENE 的 BELONGS_TO 关系。
        """
        import json
        
        if not file_path:
            file_path = f"chapters/第{chapter_number}章_{version_label}.txt"
        
        # Step 1: 检测重复（同一章节+同一版本标签的 CHUNK）
        unit_name = f"第{chapter_number}章_{version_label}"
        existing = self.store.get_unit_by_name(unit_name)
        if existing and existing.type == UnitType.CHUNK:
            # 已有同名 CHUNK：更新元数据，不创建新单元
            content_meta = json.dumps({
                "章节号": chapter_number,
                "正文路径": file_path,
                "子类型": version_label,
                "字数": len(chapter_text),
            }, ensure_ascii=False)
            self.store.update_unit(
                existing.id,
                content=content_meta,
                actor=actor,
            )
            self._stats["graph_writes"] += 1
            chunk_id = existing.id
        else:
            content_meta = json.dumps({
                "章节号": chapter_number,
                "正文路径": file_path,
                "子类型": version_label,
                "字数": len(chapter_text),
            }, ensure_ascii=False)
            chunk_unit = self.store.create_unit(
                type=UnitType.CHUNK,
                unit_name=unit_name,
                content=content_meta,
                belongs_to_chapter=chapter_number,
                actor=actor,
            )
            chunk_id = chunk_unit.id
            self._stats["graph_writes"] += 1
        
        # Step 2: 写 TXT 文件
        if self.mode != AdapterMode.GRAPH_ONLY:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(chapter_text)
            self._stats["file_writes"] += 1
        
        # Step 3: 建立 BELONGS_TO 关系到场景
        if scene_id:
            scene = self.store.get_unit(scene_id)
            if scene and scene.type == UnitType.SCENE:
                self.store.add_relation(
                    source_id=chunk_id,
                    target_id=scene_id,
                    relation_type=RelationType.BELONGS_TO,
                    actor=actor,
                )
        
        # Step 4: 持久化
        self.store.flush()
        
        return True
    
    # ── 迁移工具 ────────────────────────────────────────────────────────
    
    def migrate_project(self, project_root: str) -> Dict[str, Any]:
        """
        将现有项目文件一次性导入到 graph。
        
        扫描已知路径模式，解析 YAML/TXT 文件，
        创建对应的叙事单元和关系。
        """
        root = Path(project_root)
        migrated = {"characters": 0, "worldbuilding": 0, "plots": 0, "outlines": 0, "errors": 0}
        
        # 导入角色
        for f in root.glob("characters/*.yaml"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if data and "索引信息" in data:
                    name = data["索引信息"].get("名称", f.stem)
                    unit = self.store.create_unit(
                        type=UnitType.CHARACTER_ARC,
                        unit_name=name,
                        content=json.dumps(data, ensure_ascii=False),
                        status=UnitStatus.from_legacy_status(
                            data["索引信息"].get("状态", "active")
                        ),
                        actor="migration",
                    )
                    # 从摘要中提取标签
                    if "摘要" in data:
                        traits = data["摘要"].get("核心特质", [])
                        self.store.update_unit(unit.id, tags=traits, actor="migration")
                    migrated["characters"] += 1
            except Exception as e:
                migrated["errors"] += 1
        
        # 导入世界观
        for f in root.glob("worldbuilding/*.yaml"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if data and "索引信息" in data:
                    name = data["索引信息"].get("名称", f.stem)
                    self.store.create_unit(
                        type=UnitType.WORLD_RULE,
                        unit_name=name,
                        content=json.dumps(data, ensure_ascii=False),
                        status=UnitStatus.from_legacy_status(
                            data["索引信息"].get("状态", "active")
                        ),
                        actor="migration",
                    )
                    migrated["worldbuilding"] += 1
            except Exception as e:
                migrated["errors"] += 1
        
        # 导入情节线
        for f in root.glob("outline/情节线/*.yaml"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if data and "索引信息" in data:
                    name = data["索引信息"].get("名称", f.stem)
                    self.store.create_unit(
                        type=UnitType.PLOT_THREAD,
                        unit_name=name,
                        content=json.dumps(data, ensure_ascii=False),
                        status=UnitStatus.from_legacy_status(
                            data["索引信息"].get("状态", "active")
                        ),
                        actor="migration",
                    )
                    migrated["plots"] += 1
            except Exception as e:
                migrated["errors"] += 1
        
        # 导入分纲
        for f in root.glob("outline/分纲/**/*.yaml"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if data and "索引信息" in data:
                    ch = data["索引信息"].get("章节号", 0)
                    name = data["索引信息"].get("名称", f.stem)
                    vol = data["索引信息"].get("所属分卷", 1)
                    self.store.create_unit(
                        type=UnitType.STRUCTURE,
                        unit_name=name,
                        content=json.dumps(data, ensure_ascii=False),
                        belongs_to_chapter=ch,
                        belongs_to_volume=vol,
                        actor="migration",
                    )
                    migrated["outlines"] += 1
            except Exception as e:
                migrated["errors"] += 1
        
        self.store.flush()
        self._stats["migrations"] += 1
        return migrated
    
    # ── 内部方法 ────────────────────────────────────────────────────────
    
    def _relative_path(self, abs_path: str) -> str:
        """将绝对路径转为项目相对路径（统一用正斜杠）"""
        try:
            rel = str(Path(abs_path).relative_to(self.store.project_root))
        except ValueError:
            rel = abs_path
        return rel.replace("\\", "/")
    
    def _parse_file_to_units(
        self,
        rel_path: str,
        content: str,
    ) -> List[NarrativeUnit]:
        """
        根据文件路径和内容提取叙事单元。
        
        已知路径模式 → 精确映射
        未知路径 → 通用解析（提取文件名作为单元名）
        """
        for pattern, unit_type in self.PATH_PATTERNS:
            if pattern in rel_path:
                return self._parse_known_type(rel_path, content, unit_type)
        
        return self._parse_generic(rel_path, content)
    
    def _parse_known_type(
        self,
        rel_path: str,
        content: str,
        unit_type: UnitType,
    ) -> List[NarrativeUnit]:
        """解析已知路径模式的文件"""
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            data = None
        
        # 从文件名提取名称
        name = Path(rel_path).stem
        
        # 从 YAML 数据中提取结构化信息
        tags = []
        status = UnitStatus.SPROUT
        chapter = None
        volume = None
        extra = {}
        
        if isinstance(data, dict):
            if "索引信息" in data:
                idx = data["索引信息"]
                name = idx.get("名称", name)
                status = UnitStatus.from_legacy_status(idx.get("状态", "draft"))
                extra["entity_id"] = idx.get("实体ID", "")
                extra["legacy_type"] = idx.get("实体子类型", "")
            
            if "摘要" in data:
                summary = data["摘要"]
                tags = summary.get("核心特质", [])
                if isinstance(tags, str):
                    tags = [tags]
            
            if "索引信息" in data:
                idx = data["索引信息"]
                if "章节号" in idx:
                    chapter = idx["章节号"]
                if "所属分卷" in idx:
                    volume = idx["所属分卷"]
            
            content = json.dumps(data, ensure_ascii=False)
        
        return [
            NarrativeUnit(
                id=create_unit_id(),
                type=unit_type,
                unit_name=name,
                content=content,
                status=status,
                tags=tags,
                belongs_to_chapter=chapter,
                belongs_to_volume=volume,
                extra=extra,
            )
        ]
    
    def _parse_generic(self, rel_path: str, content: str) -> List[NarrativeUnit]:
        """通用解析——处理未知路径模式"""
        name = Path(rel_path).stem
        
        # 尝试解析 YAML
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                content = json.dumps(data, ensure_ascii=False)
        except yaml.YAMLError:
            pass  # 保留原始内容
        
        return [
            NarrativeUnit(
                id=create_unit_id(),
                type=UnitType.NOTE,
                unit_name=name,
                content=content,
            )
        ]
    
    def _trigger_projection(self, rel_path: str):
        """
        根据写入了什么文件类型，触发对应的投影更新。
        
        这不是全量重建——只更新直接相关的投影。
        """
        try:
            if rel_path.startswith("characters/"):
                name = Path(rel_path).stem
                self.projection.project_to_file(
                    ProjectionView.CHARACTER, {"name": name}
                )
                self._stats["projections"] += 1
            
            elif rel_path.startswith("worldbuilding/"):
                name = Path(rel_path).stem
                self.projection.project_to_file(
                    ProjectionView.WORLDBUILDING, {"name": name}
                )
                self._stats["projections"] += 1
            
            elif "情节线" in rel_path:
                name = Path(rel_path).stem
                self.projection.project_to_file(
                    ProjectionView.PLOT, {"name": name}
                )
                self._stats["projections"] += 1
            
            elif "分纲" in rel_path:
                # 尝试提取卷号和章节号
                parts = Path(rel_path).parts
                chapter = 1
                volume = 1
                for part in parts:
                    if "卷" in part:
                        vol_str = part.replace("卷", "")
                        try:
                            volume = int(vol_str)
                        except ValueError:
                            pass
                stem = Path(rel_path).stem
                if "第" in stem and "章" in stem:
                    ch_str = stem.replace("第", "").replace("章", "").strip()
                    try:
                        chapter = int(ch_str)
                    except ValueError:
                        pass
                self.projection.project_to_file(
                    ProjectionView.CHAPTER_OUTLINE,
                    {"volume": volume, "chapter": chapter},
                )
                self._stats["projections"] += 1
        
        except Exception:
            self._stats["errors"] += 1
    
    # ── 状态与统计 ──────────────────────────────────────────────────────
    
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)
    
    def set_mode(self, mode: AdapterMode):
        self.mode = mode
    
    @property
    def mode(self) -> AdapterMode:
        return self._mode
    
    @mode.setter
    def mode(self, value: AdapterMode):
        self._mode = value
