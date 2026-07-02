"""
Graph 存储引擎。

核心职责：
1. 叙事单元的 CRUD（通过事件溯源）
2. 关系的 CRUD
3. 事件日志的追加和查询
4. 快照的创建和恢复
5. 按需查询（邻居查询、路径查询、弱信号检测）

存储后端：当前使用 JSON Lines 文件（人类可读、可版本控制），
预留 SQLite 接口用于大规模项目。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from collections import defaultdict

from graph_schema import (
    NarrativeUnit,
    UnitType,
    UnitStatus,
    RelationType,
    Relation,
    Event,
    EventType,
    GraphSnapshot,
    create_unit_id,
    create_relation_id,
    create_event_id,
)
from schemas import validate_content, default_content


class GraphStore:
    """
    Graph 存储引擎。
    
    每个项目拥有一个独立的 graph 存储实例。
    存储路径：{project_root}/graph/
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.graph_dir = self.project_root / "graph"
        self.nodes_path = self.graph_dir / "nodes.jsonl"
        self.edges_path = self.graph_dir / "edges.jsonl"
        self.events_path = self.graph_dir / "events.olog"
        self.snapshots_dir = self.graph_dir / "snapshots"
        self._index_path = self.graph_dir / ".index.json"
        
        # 内存缓存
        self._units: Dict[str, NarrativeUnit] = {}
        self._relations: Dict[str, Relation] = {}
        self._events: List[Event] = []
        self._outgoing_edges: Dict[str, List[str]] = defaultdict(list)  # source_id → [rel_id]
        self._incoming_edges: Dict[str, List[str]] = defaultdict(list)  # target_id → [rel_id]
        self._unit_by_name: Dict[str, str] = {}  # unit_name → id
        
        # 脏标记
        self._dirty_nodes = False
        self._dirty_edges = False
        self._dirty_events = False
        
        # 是否已初始化
        self._initialized = False
    
    # ── 初始化与持久化 ──────────────────────────────────────────────────
    
    def initialize(self):
        """初始化存储：创建目录、加载现有数据"""
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)
        
        self._load_nodes()
        self._load_edges()
        self._load_events()
        self._rebuild_indices()
        self._initialized = True
    
    def _load_nodes(self):
        """从 JSONL 加载叙事单元"""
        if not self.nodes_path.exists():
            return
        with open(self.nodes_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    unit = NarrativeUnit.from_dict(data)
                    self._units[unit.id] = unit
    
    def _load_edges(self):
        """从 JSONL 加载关系"""
        if not self.edges_path.exists():
            return
        with open(self.edges_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    rel = Relation(
                        id=data["id"],
                        source_id=data["source_id"],
                        target_id=data["target_id"],
                        relation_type=RelationType(data["relation_type"]),
                        weight=data.get("weight", 0.5),
                        description=data.get("description", ""),
                        metadata=data.get("metadata", {}),
                    )
                    if "created_at" in data and isinstance(data["created_at"], str):
                        rel.created_at = datetime.fromisoformat(data["created_at"])
                    self._relations[rel.id] = rel
    
    def _load_events(self):
        """从 olog 文件加载事件"""
        if not self.events_path.exists():
            return
        with open(self.events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    event = Event(
                        event_id=data["event_id"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        actor=data["actor"],
                        event_type=EventType(data["event_type"]),
                        target_type=data.get("target_type"),
                        target_ids=data.get("target_ids", []),
                        payload=data.get("payload", {}),
                        session_id=data.get("session_id"),
                        parent_event_id=data.get("parent_event_id"),
                    )
                    self._events.append(event)
    
    def _rebuild_indices(self):
        """重建内存索引"""
        self._outgoing_edges.clear()
        self._incoming_edges.clear()
        self._unit_by_name.clear()
        
        for rel_id, rel in self._relations.items():
            self._outgoing_edges[rel.source_id].append(rel_id)
            self._incoming_edges[rel.target_id].append(rel_id)
        
        for uid, unit in self._units.items():
            self._unit_by_name[unit.unit_name] = uid
    
    def _flush_nodes(self):
        """将内存中的叙事单元写回 JSONL（全量覆写）"""
        with open(self.nodes_path, "w", encoding="utf-8") as f:
            for unit in self._units.values():
                f.write(json.dumps(unit.to_dict(), ensure_ascii=False) + "\n")
        self._dirty_nodes = False
    
    def _flush_edges(self):
        """将内存中的关系写回 JSONL"""
        with open(self.edges_path, "w", encoding="utf-8") as f:
            for rel in self._relations.values():
                f.write(json.dumps(rel.to_dict(), ensure_ascii=False) + "\n")
        self._dirty_edges = False
    
    def _flush_events(self):
        """将新增事件追加到 olog"""
        if not self._dirty_events:
            return
        # 事件只追加，不覆写
        with open(self.events_path, "a", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        self._dirty_events = False
    
    def flush(self):
        """将所有脏数据写回磁盘"""
        if self._dirty_nodes:
            self._flush_nodes()
        if self._dirty_edges:
            self._flush_edges()
        if self._dirty_events:
            self._flush_events()
    
    # ── 事件记录 ────────────────────────────────────────────────────────
    
    def _record_event(
        self,
        event_type: EventType,
        actor: str,
        target_type: Optional[str] = None,
        target_ids: Optional[List[str]] = None,
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
    ) -> Event:
        """记录一条事件"""
        event = Event(
            event_id=create_event_id(),
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            event_type=event_type,
            target_type=target_type,
            target_ids=target_ids or [],
            payload=payload or {},
            session_id=session_id,
            parent_event_id=parent_event_id,
        )
        self._events.append(event)
        self._dirty_events = True
        return event
    
    # ── 叙事单元操作 ────────────────────────────────────────────────────
    
    def create_unit(
        self,
        type: UnitType,
        unit_name: str,
        content: str = "",
        status: UnitStatus = UnitStatus.SPROUT,
        confidence: float = 0.5,
        tags: Optional[List[str]] = None,
        belongs_to_chapter: Optional[int] = None,
        belongs_to_volume: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
        actor: str = "script",
    ) -> NarrativeUnit:
        """创建一个新的叙事单元"""
        # 校验 content 结构（如果是 JSON）
        try:
            content_dict = json.loads(content) if isinstance(content, str) and content.startswith("{") else None
        except json.JSONDecodeError:
            content_dict = None
        if content_dict:
            errors = validate_content(type, content_dict)
            if errors:
                self._record_event(
                    EventType.SYSTEM_EVENT, actor=actor,
                    payload={"warning": "content schema 校验不通过", "errors": errors},
                )
        
        unit = NarrativeUnit(
            id=create_unit_id(type),
            type=type,
            unit_name=unit_name,
            content=content,
            status=status,
            confidence=confidence,
            tags=tags or [],
            belongs_to_chapter=belongs_to_chapter,
            belongs_to_volume=belongs_to_volume,
            extra=extra or {},
        )
        self._units[unit.id] = unit
        self._unit_by_name[unit.unit_name] = unit.id
        
        self._record_event(
            EventType.UNIT_CREATED,
            actor=actor,
            target_type="unit",
            target_ids=[unit.id],
            payload={"type": type.value, "name": unit_name},
        )
        self._dirty_nodes = True
        return unit
    
    def get_unit(self, unit_id: str) -> Optional[NarrativeUnit]:
        """按 ID 获取叙事单元"""
        return self._units.get(unit_id)
    
    def get_unit_by_name(self, name: str) -> Optional[NarrativeUnit]:
        """按名称获取叙事单元"""
        uid = self._unit_by_name.get(name)
        if uid:
            return self._units.get(uid)
        return None
    
    def find_units(
        self,
        type: Optional[UnitType] = None,
        status: Optional[UnitStatus] = None,
        tags: Optional[List[str]] = None,
        chapter: Optional[int] = None,
        volume: Optional[int] = None,
    ) -> List[NarrativeUnit]:
        """按条件查询叙事单元"""
        results = []
        for unit in self._units.values():
            if type and unit.type != type:
                continue
            if status and unit.status != status:
                continue
            if tags and not all(t in unit.tags for t in tags):
                continue
            if chapter is not None and unit.belongs_to_chapter != chapter:
                continue
            if volume is not None and unit.belongs_to_volume != volume:
                continue
            results.append(unit)
        return results
    
    def update_unit(
        self,
        unit_id: str,
        content: Optional[str] = None,
        status: Optional[UnitStatus] = None,
        confidence: Optional[float] = None,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
        unit_name: Optional[str] = None,
        actor: str = "script",
    ) -> Optional[NarrativeUnit]:
        """更新叙事单元（仅修改提供的字段）"""
        unit = self._units.get(unit_id)
        if not unit:
            return None
        
        changed_fields = {}
        if content is not None:
            changed_fields["content"] = (unit.content, content)
            unit.content = content
        if status is not None:
            changed_fields["status"] = (unit.status.value, status.value)
            unit.status = status
        if confidence is not None:
            changed_fields["confidence"] = (unit.confidence, confidence)
            unit.confidence = confidence
        if tags is not None:
            changed_fields["tags"] = (list(unit.tags), tags)
            unit.tags = tags
        if extra is not None:
            changed_fields["extra"] = (dict(unit.extra), extra)
            unit.extra = extra
        if unit_name is not None:
            # 更新名称索引
            old_name = unit.unit_name
            if old_name in self._unit_by_name:
                del self._unit_by_name[old_name]
            changed_fields["unit_name"] = (unit.unit_name, unit_name)
            unit.unit_name = unit_name
            self._unit_by_name[unit.unit_name] = unit.id
        
        unit.updated_at = datetime.now(timezone.utc)
        unit.version += 1
        
        self._record_event(
            EventType.UNIT_UPDATED,
            actor=actor,
            target_type="unit",
            target_ids=[unit_id],
            payload={"changed_fields": list(changed_fields.keys())},
        )
        self._dirty_nodes = True
        return unit
    
    def archive_unit(self, unit_id: str, actor: str = "script") -> bool:
        """归档一个叙事单元（软删除）"""
        unit = self._units.get(unit_id)
        if not unit:
            return False
        unit.status = UnitStatus.ARCHIVED
        unit.updated_at = datetime.now(timezone.utc)
        
        self._record_event(
            EventType.UNIT_ARCHIVED,
            actor=actor,
            target_type="unit",
            target_ids=[unit_id],
        )
        self._dirty_nodes = True
        return True
    
    def list_units(self, type: Optional[UnitType] = None) -> List[NarrativeUnit]:
        """列出所有未被归档的叙事单元"""
        return [
            u for u in self._units.values()
            if u.status != UnitStatus.ARCHIVED
            and (type is None or u.type == type)
        ]
    
    # ── 关系操作 ────────────────────────────────────────────────────────
    
    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        weight: float = 0.5,
        description: str = "",
        actor: str = "script",
    ) -> Optional[Relation]:
        """在两个叙事单元之间建立关系"""
        if source_id not in self._units or target_id not in self._units:
            return None
        
        # 检查是否已存在相同的关系
        for rel in self._relations.values():
            if (rel.source_id == source_id and rel.target_id == target_id
                    and rel.relation_type == relation_type):
                return rel
        
        rel = Relation(
            id=create_relation_id(),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            description=description,
        )
        self._relations[rel.id] = rel
        self._outgoing_edges[source_id].append(rel.id)
        self._incoming_edges[target_id].append(rel.id)
        
        self._record_event(
            EventType.RELATION_ADDED,
            actor=actor,
            target_type="relation",
            target_ids=[rel.id],
            payload={
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type.value,
                "relations_affected": [rel.id],
            },
        )
        self._dirty_edges = True
        return rel
    
    def remove_relation(self, relation_id: str, actor: str = "script") -> bool:
        """删除一条关系"""
        rel = self._relations.pop(relation_id, None)
        if not rel:
            return False
        
        # 更新索引
        if rel.source_id in self._outgoing_edges:
            self._outgoing_edges[rel.source_id] = [
                r for r in self._outgoing_edges[rel.source_id] if r != relation_id
            ]
        if rel.target_id in self._incoming_edges:
            self._incoming_edges[rel.target_id] = [
                r for r in self._incoming_edges[rel.target_id] if r != relation_id
            ]
        
        self._record_event(
            EventType.RELATION_REMOVED,
            actor=actor,
            target_type="relation",
            target_ids=[relation_id],
        )
        self._dirty_edges = True
        return True
    
    def get_relations(
        self,
        unit_id: Optional[str] = None,
        relation_type: Optional[RelationType] = None,
        direction: str = "both",  # "outgoing" | "incoming" | "both"
    ) -> List[Relation]:
        """查询一个叙事单元的关系"""
        if not unit_id:
            # 返回所有关系（可筛选类型）
            results = list(self._relations.values())
            if relation_type:
                results = [r for r in results if r.relation_type == relation_type]
            return results
        
        rel_ids = []
        if direction in ("outgoing", "both"):
            rel_ids.extend(self._outgoing_edges.get(unit_id, []))
        if direction in ("incoming", "both"):
            rel_ids.extend(self._incoming_edges.get(unit_id, []))
        
        results = [self._relations[rid] for rid in rel_ids if rid in self._relations]
        if relation_type:
            results = [r for r in results if r.relation_type == relation_type]
        return results
    
    def get_neighbors(
        self,
        unit_id: str,
        relation_type: Optional[RelationType] = None,
        max_depth: int = 1,
    ) -> Dict[int, Set[str]]:
        """
        获取叙事单元的邻居（按深度分组）。
        
        返回如 {1: {id1, id2}, 2: {id3, id4}}
        用于构建写作时的工作空间。
        """
        result: Dict[int, Set[str]] = {1: set(), 2: set()}
        visited: Set[str] = {unit_id}
        
        # 1 度邻居
        for rel in self.get_relations(unit_id):
            if relation_type and rel.relation_type != relation_type:
                continue
            if rel.source_id == unit_id and rel.target_id not in visited:
                result[1].add(rel.target_id)
                visited.add(rel.target_id)
            if rel.target_id == unit_id and rel.source_id not in visited:
                result[1].add(rel.source_id)
                visited.add(rel.source_id)
        
        # 2 度邻居
        if max_depth >= 2:
            for neighbor_id in result[1]:
                for rel in self.get_relations(neighbor_id):
                    if rel.source_id == neighbor_id and rel.target_id not in visited:
                        result[2].add(rel.target_id)
                    if rel.target_id == neighbor_id and rel.source_id not in visited:
                        result[2].add(rel.source_id)
        
        return result
    
    def find_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 5,
    ) -> Optional[List[str]]:
        """BFS 查找两个叙事单元之间的路径（返回节点 ID 链）"""
        if from_id not in self._units or to_id not in self._units:
            return None
        
        queue = [(from_id, [from_id])]
        visited = {from_id}
        
        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            
            for rel in self.get_relations(current):
                next_id = rel.target_id if rel.source_id == current else rel.source_id
                if next_id == to_id:
                    return path + [next_id]
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, path + [next_id]))
        
        return None
    
    # ── 弱信号检测 ──────────────────────────────────────────────────────
    
    def get_weak_signals(
        self,
        unit_id: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        检测当前焦点单元的"弱信号"——可能相关但不直接关联的信息。
        
        这是模仿人类创作中的"直觉"：写到某个场景时隐约感觉
        这个设定跟之前某个设定有冲突，但又不确定。
        
        返回格式：
        [{
            "unit_id": "...",
            "unit_name": "...",
            "signal_type": "potential_contradiction" | "missed_reference" | "unused_setup",
            "description": "...",
            "confidence": 0.0-1.0
        }]
        """
        unit = self._units.get(unit_id)
        if not unit:
            return []
        
        signals = []
        neighbors_1 = self.get_neighbors(unit_id, max_depth=1)[1]
        
        # 信号1：内容关键词匹配的未关联单元
        content_words = set(unit.content.lower().split())
        for other in self._units.values():
            if other.id == unit_id or other.id in neighbors_1:
                continue
            if other.status == UnitStatus.ARCHIVED:
                continue
            
            other_words = set(other.content.lower().split())
            common = content_words & other_words
            if len(common) >= 3:  # 3个以上关键词重叠
                signals.append({
                    "unit_id": other.id,
                    "unit_name": other.unit_name,
                    "unit_type": other.type.value,
                    "signal_type": "missed_reference",
                    "description": f"内容关键词重叠：{', '.join(list(common)[:5])}",
                    "confidence": min(0.5, len(common) * 0.1),
                })
        
        # 信号2：类型相同且在相似章节但无关系的单元
        if unit.belongs_to_chapter:
            same_chapter = self.find_units(
                type=unit.type,
                chapter=unit.belongs_to_chapter,
            )
            for other in same_chapter:
                if other.id != unit_id and other.id not in neighbors_1:
                    signals.append({
                        "unit_id": other.id,
                        "unit_name": other.unit_name,
                        "unit_type": other.type.value,
                        "signal_type": "unused_setup",
                        "description": f"同章节同类型但未关联：{other.unit_name}",
                        "confidence": 0.3,
                    })
        
        # 按置信度排序并截断
        signals.sort(key=lambda s: s["confidence"], reverse=True)
        return signals[:limit]
    
    # ── 快照操作 ────────────────────────────────────────────────────────
    
    def create_snapshot(self, metadata: Optional[Dict[str, Any]] = None) -> GraphSnapshot:
        """创建当前 graph 状态的快照"""
        snapshot = GraphSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            units=list(self._units.values()),
            relations=list(self._relations.values()),
            last_event_id=self._events[-1].event_id if self._events else "",
            metadata=metadata or {},
        )
        
        snapshot_path = self.snapshots_dir / f"{snapshot.snapshot_id}.json"
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
        
        return snapshot
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """从快照恢复 graph 状态"""
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.json"
        if not snapshot_path.exists():
            return False
        
        with open(snapshot_path, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
        
        self._units = {u["id"]: NarrativeUnit.from_dict(u) for u in data["units"]}
        self._relations = {}
        for r in data["relations"]:
            rel = Relation(
                id=r["id"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                relation_type=RelationType(r["relation_type"]),
                weight=r.get("weight", 0.5),
                description=r.get("description", ""),
                metadata=r.get("metadata", {}),
            )
            self._relations[rel.id] = rel
        
        self._rebuild_indices()
        self._dirty_nodes = True
        self._dirty_edges = True
        
        return True
    
    def get_snapshots(self) -> List[Dict[str, Any]]:
        """列出所有快照"""
        snapshots = []
        for f in sorted(self.snapshots_dir.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.loads(fh.read())
                snapshots.append({
                    "id": data["snapshot_id"],
                    "timestamp": data["timestamp"],
                    "unit_count": len(data["units"]),
                    "relation_count": len(data["relations"]),
                    "metadata": data.get("metadata", {}),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return snapshots
    
    # ── 统计信息 ────────────────────────────────────────────────────────
    
    def stats(self) -> Dict[str, Any]:
        """graph 统计信息"""
        type_counts = defaultdict(int)
        status_counts = defaultdict(int)
        for unit in self._units.values():
            type_counts[unit.type.value] += 1
            status_counts[unit.status.value] += 1
        
        return {
            "total_units": len(self._units),
            "total_relations": len(self._relations),
            "total_events": len(self._events),
            "by_type": dict(type_counts),
            "by_status": dict(status_counts),
            "snapshot_count": len(list(self.snapshots_dir.glob("*.json"))),
        }
    
    def get_schema_info(self, unit_type: UnitType) -> List[str]:
        """返回该类型的 content 字段要求（供注入 LLM prompt）"""
        from schemas import schema_info
        return schema_info(unit_type)
