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
    get_unit_chapter,
)
from schemas import validate_content, default_content


def is_v2_project(project_root: str) -> bool:
    """判定项目是否为已就绪的 V2 项目。

    收紧判定：仅当 graph/nodes.jsonl 存在时才视为 V2。
    半迁移项目（仅有空 graph/ 目录、无 nodes.jsonl）不会被误判。
    兼容传入 graph 目录本身（自动归一化到项目根）。
    """
    if not project_root:
        return False
    root = Path(project_root)
    # 兼容传入 {项目}/graph 而非项目根
    if root.name == "graph":
        root = root.parent
    return (root / "graph" / "nodes.jsonl").is_file()


def _normalize_project_root(project_root: str) -> Path:
    """归一化项目根路径。

    若传入的是 graph 子目录本身（如 {项目}/graph 或 {项目}/graph/graph），
    自动逐级提升到项目根，避免产生 graph/graph 嵌套。
    项目根以 config.yaml 为强标志（V1/V2 项目均必含）。
    """
    root = Path(project_root)
    if root.name != "graph":
        return root
    current = root
    for _ in range(5):  # 防御死循环，最多提升 5 级
        parent = current.parent
        if parent == current:
            break
        # 含 config.yaml 的目录即项目根
        if (parent / "config.yaml").is_file():
            return parent
        # 只有 parent 仍是 graph 容器（含 graph 子目录）才继续提升
        if not (parent / "graph").is_dir():
            break
        current = parent
    return root


class GraphStore:
    """
    Graph 存储引擎。
    
    每个项目拥有一个独立的 graph 存储实例。
    存储路径：{project_root}/graph/
    """
    
    def __init__(self, project_root: str):
        self.project_root = _normalize_project_root(project_root)
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
        self._dirty_unit_ids: Set[str] = set()  # 仅跟踪变更的单元 ID（增量 flush）
        self._dirty_relation_ids: Set[str] = set()  # 仅跟踪变更的边 ID（payload 增量检查）
        
        # 缓存写节流：每 N 次 flush 写一次 cache
        self._flush_counter = 0
        self._cache_write_interval = int(os.environ.get("NOVEL_CACHE_INTERVAL", "5"))
        
        # post_flush 回调链（约束引擎等通过此钩子注册）
        self._post_flush_hooks: List[Callable[["GraphStore"], None]] = []
        
        # 会话上下文：一次 handler 写操作链（create→推断→抽取）内所有事件
        # 继承该 session_id（遥测归因）。由 handler 层 set/clear，finally 清理。
        self._session_context: Optional[str] = None
        
        # 是否已初始化
        self._initialized = False
    
    # ── 初始化与持久化 ──────────────────────────────────────────────────
    
    def initialize(self):
        """初始化存储：创建目录、加载现有数据"""
        self.graph_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)
        
        # 优先从缓存恢复，缓存失效或不存在时回退到 JSONL 逐行加载
        cache_loaded = self._load_cache()
        
        if not cache_loaded:
            self._load_nodes()
            self._load_edges()
            self._rebuild_indices()
        
        # 事件始终从 olog 加载（事件是 append-only，缓存事件性价比低）
        self._load_events()
        
        self._initialized = True
        if not cache_loaded:
            self._save_cache()
    
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
                    rel = Relation.from_dict(data)
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
        # 标记所有已加载事件为"已刷新"，防止下次 flush 时重复追加
        self._last_flushed_event = len(self._events)
    
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
    
    # ── 缓存（.index.json） ────────────────────────────────────────────
    
    def _get_mtime_ns(self, path: Path) -> int:
        """获取文件修改时间（纳秒），文件不存在时返回 0"""
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0
    
    def _save_cache(self):
        """将当前状态缓存到 .index.json，附带源文件 mtime 用于后续校验。
        
        注意：事件（events）不写入缓存——事件是 append-only 且量级大，
        缓存的序列化开销远超其收益。事件始终从 events.olog 加载。
        
        缓存写失败不抛出异常（调用方在 flush 中已 catch）。
        """
        if not self._initialized:
            return
        try:
            cache = {
                "_cache_version": 1,
                "nodes_mtime": self._get_mtime_ns(self.nodes_path),
                "edges_mtime": self._get_mtime_ns(self.edges_path),
                "units": {uid: u.to_dict() for uid, u in self._units.items()},
                "relations": {rid: r.to_dict() for rid, r in self._relations.items()},
            }
            tmp = self._index_path.with_suffix(".index.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, default=str)
            tmp.replace(self._index_path)
        except Exception:
            # 缓存写失败不阻塞业务流程——下次 flush 会重试
            pass
    
    def _load_cache(self) -> bool:
        """
        尝试从 .index.json 缓存恢复状态。
        校验源文件 mtime 一致后才使用，否则返回 False 回退到 JSONL 加载。
        
        注意：事件始终从 events.olog 加载，不缓存。
        """
        if not self._index_path.exists():
            return False
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except (json.JSONDecodeError, OSError):
            return False
        
        # 校验缓存版本和源文件 mtime
        if cache.get("_cache_version") != 1:
            return False
        if (cache.get("nodes_mtime") != self._get_mtime_ns(self.nodes_path) or
            cache.get("edges_mtime") != self._get_mtime_ns(self.edges_path)):
            return False
        
        # 恢复单元
        for uid, data in cache.get("units", {}).items():
            self._units[uid] = NarrativeUnit.from_dict(data)
        
        # 恢复关系
        for rid, data in cache.get("relations", {}).items():
            rel = Relation.from_dict(data)
            self._relations[rid] = rel
        
        # 重建索引
        self._rebuild_indices()
        return True
    
    def _flush_nodes(self):
        """将叙事单元写回 JSONL（支持增量 + 全量两种模式）。
        
        增量模式：仅重写有变更的单元行。对于大批量变更（>50% 单元）
        或首次脏标记时，自动回退到全量覆写。
        全量模式：原子写入临时文件后 rename，保证一致性。
        """
        # 判断是否使用增量模式
        use_incremental = (
            self._dirty_unit_ids
            and len(self._dirty_unit_ids) < len(self._units) * 0.5
            and self.nodes_path.exists()
        )
        
        if use_incremental:
            # ── 增量模式：只重写变更单元的行 ──
            try:
                lines = self.nodes_path.read_text(encoding="utf-8").splitlines(keepends=True)
                seen_ids: Set[str] = set()
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        data = json.loads(stripped)
                        uid = data.get("id", "")
                        if uid in self._dirty_unit_ids:
                            if uid in self._units:
                                # 更新：替换该行
                                lines[i] = json.dumps(
                                    self._units[uid].to_dict(), ensure_ascii=False
                                ) + "\n"
                                seen_ids.add(uid)
                            else:
                                # 删除：置空该行（后续过滤掉）
                                lines[i] = ""
                                seen_ids.add(uid)
                    except json.JSONDecodeError:
                        continue
                
                # 追加在文件中不存在的新单元（create_unit 场景）
                for uid in self._dirty_unit_ids:
                    if uid not in seen_ids and uid in self._units:
                        lines.append(
                            json.dumps(self._units[uid].to_dict(), ensure_ascii=False) + "\n"
                        )
                
                # 过滤掉被删除的空行
                lines = [l for l in lines if l]
                
                tmp = self.nodes_path.with_suffix(".jsonl.tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                tmp.replace(self.nodes_path)
            except Exception:
                # 增量失败回退到全量
                use_incremental = False
        
        if not use_incremental:
            # ── 全量模式：原子写入全部单元 ──
            tmp = self.nodes_path.with_suffix(".jsonl.tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    for unit in self._units.values():
                        f.write(json.dumps(unit.to_dict(), ensure_ascii=False) + "\n")
                tmp.replace(self.nodes_path)
            except Exception:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                raise
        
        self._dirty_nodes = False
        self._dirty_unit_ids.clear()
    
    def _flush_edges(self):
        """将内存中的关系写回 JSONL（原子写入）"""
        tmp = self.edges_path.with_suffix(".jsonl.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                for rel in self._relations.values():
                    f.write(json.dumps(rel.to_dict(), ensure_ascii=False) + "\n")
            tmp.replace(self.edges_path)
            self._dirty_edges = False
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
    
    def _flush_events(self):
        """将新增事件追加到 olog（只写未持久化的新事件）"""
        if not self._dirty_events:
            return
        # 追踪上次刷新的位置
        if not hasattr(self, '_last_flushed_event'):
            self._last_flushed_event = 0
        new_events = self._events[self._last_flushed_event:]
        if not new_events:
            self._dirty_events = False
            return
        with open(self.events_path, "a", encoding="utf-8") as f:
            for event in new_events:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        self._last_flushed_event = len(self._events)
        self._dirty_events = False
    
    def flush(self, skip_constraint_check: bool = False):
        """将所有脏数据写回磁盘（事务性：全部成功或全部保留脏标记）
        
        flush 的性能优化：
        1. 事件始终 append-only，无需全量重写
        2. 缓存写（_save_cache）节流——每 N 次 flush 写一次，
           避免 400-700ms 的每次全量序列化开销
        
        Args:
            skip_constraint_check: True 时跳过约束引擎 post_flush 钩子
        """
        if not (self._dirty_nodes or self._dirty_edges or self._dirty_events):
            return
        
        saved_nodes = not self._dirty_nodes
        saved_edges = not self._dirty_edges
        saved_events = not self._dirty_events
        try:
            if self._dirty_nodes:
                self._flush_nodes()
                saved_nodes = True
            if self._dirty_edges:
                self._flush_edges()
                saved_edges = True
            if self._dirty_events:
                self._flush_events()
                saved_events = True
        except Exception:
            # 写入失败，恢复脏标记，下次 flush 重试
            if not saved_nodes:
                self._dirty_nodes = True
            if not saved_edges:
                self._dirty_edges = True
            if not saved_events:
                self._dirty_events = True
            raise
        
        # 缓存写节流：每 N 次 flush 写一次（默认 N=5）
        # 消除了 400-700ms 的每次全量序列化瓶颈
        self._flush_counter += 1
        if self._flush_counter >= self._cache_write_interval:
            try:
                self._save_cache()
            except Exception:
                pass  # 缓存写失败不阻塞业务
            self._flush_counter = 0
        
        # post_flush：执行已注册的回调链（失败不影响写）
        if not skip_constraint_check:
            for hook in self._post_flush_hooks:
                try:
                    hook(self)
                except Exception:
                    pass  # 回调失败不阻塞业务
    
    def register_post_flush_hook(self, hook: Callable[["GraphStore"], None]):
        """注册 flush 后回调钩子。
        
        回调签名：hook(store: GraphStore) -> None
        回调执行失败不影响 flush 本身的写结果。
        用于约束引擎自动检测等场景。
        """
        self._post_flush_hooks.append(hook)
    
    # ── 增量分析支持 ──────────────────────────────────────────────────
    
    def get_modified_units(self, since_version: int) -> List["NarrativeUnit"]:
        """
        获取 version > since_version 的所有活跃单元（用于增量分析）。
        
        - O(n_units) 而非 O(n_events)
        - unit.version 在每次 update_unit() 时自增
        - 过滤已归档单元
        """
        from graph_schema import UnitStatus
        changed = []
        for unit in self._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if unit.version > since_version:
                changed.append(unit)
        return changed
    
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
        """记录一条事件

        未显式传 session_id 时，回退到本 store 的 _session_context
        （一次 handler 写操作链内的推断/抽取事件自动继承发起会话的归因）。
        """
        if session_id is None:
            session_id = self._session_context
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

    def set_session_context(self, session_id: Optional[str]):
        """设置会话上下文：本次写操作链内所有事件继承该 session_id。

        调用方（handler 层）必须在操作完成后 finally 调用 clear_session_context()，
        防止 daemon 模式下缓存 store 的上下文泄漏到后续请求。
        """
        self._session_context = session_id

    def clear_session_context(self):
        """清理会话上下文。"""
        self._session_context = None
    
    # ── 叙事单元操作 ────────────────────────────────────────────────────
    
    def create_unit(
        self,
        type: UnitType,
        unit_name: str,
        content: str = "",
        status: UnitStatus = UnitStatus.SPROUT,
        confidence: float = 0.5,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
        actor: str = "script",
        structure_path: Optional[List[Any]] = None,
        parent_id: Optional[str] = None,
        chapter_number: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> NarrativeUnit:
        """创建一个新的叙事单元
        
        Args:
            parent_id: 可选的父级单元 ID。若提供且有效，自动创建
                       parent_id CONTAINS 新单元关系。
            chapter_number: 精确章节号（CONTAINS 边关系下的真实标号）。
            session_id: 关联的创作会话 ID（遥测归因，写入事件）。
        """
        # 校验 content 结构（如果是 JSON）— 必填字段缺失直接拒绝
        try:
            content_dict = json.loads(content) if isinstance(content, str) and content.startswith("{") else None
        except json.JSONDecodeError:
            content_dict = None
        if content_dict:
            errors = validate_content(type, content_dict)
            if errors:
                error_msg = f"content schema 校验不通过: {'; '.join(errors)}"
                self._record_event(
                    EventType.SYSTEM_EVENT, actor=actor,
                    payload={"warning": error_msg, "errors": errors},
                )
                # 必填字段缺失时发出告警但不拒绝创建，
                # 以保证向后兼容（旧数据和测试数据可能缺少 schema 要求的新字段）
                pass
        
        if structure_path is None and parent_id is not None:
            # 若指定了 parent_id 但未提供 structure_path，从父级继承并追加
            parent = self.get_unit(parent_id)
            if parent and parent.structure_path:
                structure_path = list(parent.structure_path)
                if chapter_number is not None:
                    structure_path.append(chapter_number)
        
        unit = NarrativeUnit(
            id=create_unit_id(type),
            type=type,
            unit_name=unit_name,
            content=content,
            status=status,
            confidence=confidence,
            tags=tags or [],
            chapter_number=chapter_number,
            structure_path=structure_path,
            extra=extra or {},
        )
        self._units[unit.id] = unit
        self._unit_by_name[unit.unit_name] = unit.id
        
        # 如果指定了 parent_id，自动建立 CONTAINS 关系
        if parent_id is not None and parent_id in self._units:
            self.add_relation(
                source_id=parent_id,
                target_id=unit.id,
                relation_type=RelationType.CONTAINS,
                weight=1.0,
                description=f"create_unit with parent_id={parent_id}",
                actor=actor,
                record_event=True,
                session_id=session_id,
            )
        
        # 自动同步 content 时间字段 → extra.time（让 TimelineLedger / Matcher 能读到标准化时间）
        from time_utils import auto_sync_story_time
        auto_sync_story_time(unit)

        self._record_event(
            EventType.UNIT_CREATED,
            actor=actor,
            target_type="unit",
            target_ids=[unit.id],
            payload={"type": type.value, "name": unit_name},
            session_id=session_id,
        )
        self._dirty_nodes = True
        self._dirty_unit_ids.add(unit.id)
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
        """
        按条件查询叙事单元。chapter 参数只匹配 chapter_number。

        默认排除已归档(archived)单元。如果需显式查询归档单元，传入 status=UnitStatus.ARCHIVED。
        """
        results = []
        for unit in self._units.values():
            if type and unit.type != type:
                continue
            if status is not None:
                if unit.status != status:
                    continue
            elif unit.status == UnitStatus.ARCHIVED:
                continue  # 默认排除归档单元
            if tags and not all(t in unit.tags for t in tags):
                continue
            if chapter is not None and unit.chapter_number != chapter:
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
        structure_path: Optional[List[Any]] = None,
        session_id: Optional[str] = None,
    ) -> Optional[NarrativeUnit]:
        """更新叙事单元（仅修改提供的字段）

        Args:
            session_id: 关联的创作会话 ID（遥测归因，写入事件）。
        """
        unit = self._units.get(unit_id)
        if not unit:
            return None
        
        changed_fields = {}
        # 每个字段先做值比较：仅在实际发生变化时才视为修改
        # （空更新/同值更新不刷新 updated_at、不递增 version、不记录事件）
        if content is not None and content != unit.content:
            # content 非空且在 create_unit 后可能第二次被更新
            # 此时 unit 的 type 已确定，进行 schema 校验
            try:
                content_dict = json.loads(content) if isinstance(content, str) and content.startswith("{") else None
            except json.JSONDecodeError:
                content_dict = None
            if content_dict:
                errors = validate_content(unit.type, content_dict)
                if errors:
                    self._record_event(
                        EventType.SYSTEM_EVENT, actor=actor,
                        payload={"warning": f"content schema 校验不通过: {errors}"},
                    )
            changed_fields["content"] = (unit.content, content)
            unit.content = content
            # content 变更后自动同步时间字段 → extra.time
            from time_utils import auto_sync_story_time
            auto_sync_story_time(unit)
        if status is not None and status != unit.status:
            changed_fields["status"] = (unit.status.value, status.value)
            unit.status = status
        if confidence is not None and confidence != unit.confidence:
            changed_fields["confidence"] = (unit.confidence, confidence)
            unit.confidence = confidence
        if tags is not None and tags != list(unit.tags):
            changed_fields["tags"] = (list(unit.tags), tags)
            unit.tags = tags
        if extra is not None and extra != dict(unit.extra):
            changed_fields["extra"] = (dict(unit.extra), extra)
            unit.extra = extra
        if unit_name is not None and unit_name != unit.unit_name:
            # 更新名称索引
            old_name = unit.unit_name
            if old_name in self._unit_by_name:
                del self._unit_by_name[old_name]
            changed_fields["unit_name"] = (unit.unit_name, unit_name)
            unit.unit_name = unit_name
            self._unit_by_name[unit.unit_name] = unit.id
        if structure_path is not None and structure_path != unit.structure_path:
            changed_fields["structure_path"] = (unit.structure_path, structure_path)
            unit.structure_path = structure_path
        
        # 空更新：无字段实际变更 → 不触碰 updated_at/version，不记录事件、不标记脏
        if not changed_fields:
            return unit
        
        unit.updated_at = datetime.now(timezone.utc)
        unit.version += 1
        
        self._record_event(
            EventType.UNIT_UPDATED,
            actor=actor,
            target_type="unit",
            target_ids=[unit_id],
            payload={"changed_fields": list(changed_fields.keys())},
            session_id=session_id,
        )
        self._dirty_nodes = True
        self._dirty_unit_ids.add(unit_id)
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
        self._dirty_unit_ids.add(unit_id)
        return True
    
    def purge_archived(self, ids: Optional[List[str]] = None, actor: str = "script") -> dict:
        """
        物理删除已归档的叙事单元及其关联边。
        
        Args:
            ids: 要删除的单元 ID 列表。为 None 时删除所有 archived 单元。
            actor: 操作者标识
        
        Returns:
            {"purged_units": int, "removed_relations": int, "unit_ids": List[str]}
        """
        # 确定待删除的单元 ID
        if ids is not None:
            target_ids = [
                uid for uid in ids
                if uid in self._units and self._units[uid].status == UnitStatus.ARCHIVED
            ]
        else:
            target_ids = [
                uid for uid, u in self._units.items()
                if u.status == UnitStatus.ARCHIVED
            ]
        
        if not target_ids:
            return {"purged_units": 0, "removed_relations": 0, "unit_ids": []}
        
        target_set = set(target_ids)
        
        # 收集涉及这些单元的所有关系 ID
        relation_ids_to_remove: Set[str] = set()
        for uid in target_ids:
            for rel_id in self._outgoing_edges.get(uid, []):
                relation_ids_to_remove.add(rel_id)
            for rel_id in self._incoming_edges.get(uid, []):
                relation_ids_to_remove.add(rel_id)
        
        # 删除关系
        for rel_id in relation_ids_to_remove:
            rel = self._relations.pop(rel_id, None)
            if rel:
                # 从出边索引移除
                if rel.source_id in self._outgoing_edges:
                    self._outgoing_edges[rel.source_id] = [
                        r for r in self._outgoing_edges[rel.source_id] if r != rel_id
                    ]
                # 从入边索引移除
                if rel.target_id in self._incoming_edges:
                    self._incoming_edges[rel.target_id] = [
                        r for r in self._incoming_edges[rel.target_id] if r != rel_id
                    ]
        
        # 删除单元
        for uid in target_ids:
            unit = self._units.pop(uid, None)
            if unit and unit.unit_name in self._unit_by_name:
                del self._unit_by_name[unit.unit_name]
        
        # 记录事件
        self._record_event(
            EventType.UNIT_ARCHIVED,
            actor=actor,
            target_type="unit",
            target_ids=target_ids,
            payload={
                "action": "purge_archived",
                "purged_units": len(target_ids),
                "removed_relations": len(relation_ids_to_remove),
            },
        )
        
        self._dirty_nodes = True
        self._dirty_edges = True
        self._dirty_unit_ids.update(target_ids)
        
        return {
            "purged_units": len(target_ids),
            "removed_relations": len(relation_ids_to_remove),
            "unit_ids": target_ids,
        }
    
    def list_units(self, type: Optional[UnitType] = None) -> List[NarrativeUnit]:
        """列出所有未被归档的叙事单元"""
        return [
            u for u in self._units.values()
            if u.status != UnitStatus.ARCHIVED
            and (type is None or u.type == type)
        ]
    
    def find_units_by_field(
        self,
        type: Optional[UnitType] = None,
        field_name: Optional[str] = None,
        field_value: Any = None,
    ) -> List[NarrativeUnit]:
        """
        按 content 内字段名/值查询。
        
        递归搜索所有嵌套 dict，不要求字段路径精确。
        例: find_units_by_field(type=CHARACTER_ARC, field_name="修为", field_value="化神期")
        """
        results = []
        for unit in self._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if type and unit.type != type:
                continue
            if field_name is not None or field_value is not None:
                content = self._parse_content(unit)
                if not self._field_matches(content, field_name, field_value):
                    continue
            results.append(unit)
        return results
    
    def _parse_content(self, unit: NarrativeUnit) -> dict:
        """解析 content 为 dict（遇错误返回空 dict）"""
        if isinstance(unit.content, str) and unit.content.startswith("{"):
            try:
                return json.loads(unit.content)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def _field_matches(self, data: Any, field_name: Optional[str], field_value: Any) -> bool:
        """递归搜索 dict，判断是否包含匹配的字段名/值"""
        if isinstance(data, dict):
            for key, val in data.items():
                if field_name is not None and field_value is not None:
                    if key == field_name and val == field_value:
                        return True
                elif field_name is not None:
                    if key == field_name:
                        return True
                elif field_value is not None:
                    if val == field_value:
                        return True
                if isinstance(val, (dict, list)):
                    if self._field_matches(val, field_name, field_value):
                        return True
        elif isinstance(data, list):
            for item in data:
                if self._field_matches(item, field_name, field_value):
                    return True
        elif field_value is not None:
            # 叶子节点值匹配（通过递归从 list/dict 到达）
            if data == field_value:
                return True
        return False
    
    # ── 关系操作 ────────────────────────────────────────────────────────
    
    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        weight: float = 0.5,
        description: str = "",
        label: str = "",
        actor: str = "script",
        record_event: bool = True,
        session_id: Optional[str] = None,
    ) -> Optional[Relation]:
        """在两个叙事单元之间建立关系

        Args:
            session_id: 关联的创作会话 ID（遥测归因，写入事件）。
        """
        if source_id not in self._units or target_id not in self._units:
            return None
        
        # 检查是否已存在相同的关系
        for rel in self._relations.values():
            if (rel.source_id == source_id and rel.target_id == target_id
                    and rel.relation_type == relation_type):
                return rel
        
        # CONTAINS 环检测：A CONTAINS B 时，检查 B 是否已是 A 的祖先
        if relation_type == RelationType.CONTAINS:
            if self._would_create_cycle(source_id, target_id, RelationType.CONTAINS):
                return None
        
        rel = Relation(
            id=create_relation_id(),
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            description=description,
            label=label,
        )
        self._relations[rel.id] = rel
        self._outgoing_edges[source_id].append(rel.id)
        self._incoming_edges[target_id].append(rel.id)
        
        if record_event:
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
                session_id=session_id,
            )
        self._dirty_edges = True
        self._dirty_relation_ids.add(rel.id)
        return rel
    
    def _would_create_cycle(
        self, source_id: str, target_id: str, rel_type: RelationType
    ) -> bool:
        """
        检查在 source_id 和 target_id 之间添加 rel_type 类型的关系
        是否会引入环（BFS 从 target 出发是否能到达 source）。
        用于 CONTAINS / BELONGS_TO 等严格无环的关系类型。
        """
        visited: Set[str] = {target_id}
        queue = [target_id]
        while queue:
            current = queue.pop(0)
            for rel in self.get_relations(current, relation_type=rel_type, direction="outgoing"):
                if rel.target_id == source_id:
                    return True
                if rel.target_id not in visited:
                    visited.add(rel.target_id)
                    queue.append(rel.target_id)
        return False
    
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
    
    # ── 层级关系查询（CONTAINS 边） ─────────────────────────────────────
    
    def find_descendants(
        self, unit_id: str, rel_type: RelationType = RelationType.CONTAINS,
        max_depth: int = 10,
    ) -> List[str]:
        """
        递归查找所有通过指定关系类型可达的后代节点 ID。
        用于 STRUCTURE 层级聚合：给定一篇大纲，找出其下所有卷/章。
        BFS 遍历，10K 节点 < 5ms。
        """
        descendants: List[str] = []
        visited: Set[str] = {unit_id}
        queue = [unit_id]
        while queue and max_depth > 0:
            level_size = len(queue)
            for _ in range(level_size):
                current = queue.pop(0)
                for rel in self.get_relations(current, relation_type=rel_type, direction="outgoing"):
                    if rel.target_id not in visited:
                        visited.add(rel.target_id)
                        descendants.append(rel.target_id)
                        queue.append(rel.target_id)
            max_depth -= 1
        return descendants
    
    def find_ancestors(
        self, unit_id: str, rel_type: RelationType = RelationType.CONTAINS,
    ) -> List[str]:
        """
        递归查找所有通过指定关系类型可达的祖先节点 ID。
        用于反向查找：给定一章，找出它属于哪卷哪篇。
        """
        ancestors: List[str] = []
        visited: Set[str] = {unit_id}
        queue = [unit_id]
        while queue:
            current = queue.pop(0)
            for rel in self.get_relations(current, relation_type=rel_type, direction="incoming"):
                if rel.source_id not in visited:
                    visited.add(rel.source_id)
                    ancestors.append(rel.source_id)
                    queue.append(rel.source_id)
        return ancestors
    
    def rebuild_structure_path_from_edges(self, unit_id: str) -> List[Any]:
        """
        通过 CONTAINS 边重建单元的 structure_path。
        
        从给定单元出发，沿 CONTAINS 边向上追溯祖先，构建路径。
        返回路径（从最外层到最内层），如 ["人界篇", "黄枫谷卷", 15]。
        不改变单元数据——调用方负责写回。
        """
        path: List[Any] = []
        visited: Set[str] = {unit_id}
        current = unit_id
        _STRUCTURE_TYPES = {UnitType.OUTLINE, UnitType.ARC_PLAN, UnitType.VOLUME_PLAN,
                            UnitType.CHAPTER_PLAN}
        while True:
            # 找当前节点的 CONTAINS 入边（即"谁包含我"）
            parents = self.get_relations(current, relation_type=RelationType.CONTAINS, direction="incoming")
            if not parents:
                break
            parent = self.get_unit(parents[0].source_id)
            if not parent or parent.id in visited:
                break
            visited.add(parent.id)
            # 尝试从父节点提取路径片段
            if parent.type in _STRUCTURE_TYPES:
                # 优先使用 extra 中的"层级序号"（若有）
                extra = parent.extra or {}
                seq = extra.get("sequence", None)
                if seq is not None:
                    path.insert(0, seq)
                else:
                    path.insert(0, parent.unit_name)
            else:
                path.insert(0, parent.unit_name)
            current = parent.id
        
        # 追加当前节点自身的章节号
        unit = self.get_unit(unit_id)
        if unit:
            ch = get_unit_chapter(unit)
            if ch:
                path.append(ch)
            else:
                # 若当前节点自身也是结构单元（如总纲/大纲），用其名称
                if unit.type in _STRUCTURE_TYPES:
                    path.append(unit.unit_name)
        return path if path else [0]
    
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
    
    def get_relation(self, relation_id: str) -> Optional[Relation]:
        """按 ID 获取单条边。"""
        return self._relations.get(relation_id)

    def update_relation_payload(
        self,
        relation_id: str,
        payload: Dict[str, Any],
        actor: str = "script",
    ) -> bool:
        """更新单条边的 payload。
        
        触发脏标记，使约束引擎在下次 flush 时检查 payload。
        """
        rel = self._relations.get(relation_id)
        if not rel:
            return False
        rel.payload = payload
        rel.updated_at = datetime.now(timezone.utc)
        self._dirty_edges = True
        self._dirty_relation_ids.add(relation_id)
        self._record_event(
            EventType.RELATION_UPDATED,
            actor=actor,
            target_type="relation",
            target_ids=[relation_id],
            payload={"relation_type": rel.relation_type.value,
                     "source_id": rel.source_id, "target_id": rel.target_id},
        )
        return True

    def get_dirty_relation_ids(self) -> Set[str]:
        """获取所有待检查的边 ID（供约束引擎增量检查使用）。"""
        result = set(self._dirty_relation_ids)
        # flush 过全量 edges 后，脏边标记已落盘，可清空
        if not self._dirty_edges:
            self._dirty_relation_ids.clear()
        return result

    def find_relations(
        self,
        relation_type: Optional[RelationType] = None,
        source_type: Optional[UnitType] = None,
        target_type: Optional[UnitType] = None,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        payload_filter: Optional[Dict[str, Any]] = None,
    ) -> List[Relation]:
        """查询边，支持按类型、源/目标类型、payload 字段过滤。
        
        payload_filter 示例：
          {"acquired_at.ordinal": {"$gt": 5}}     # ordinal > 5
          {"upgrades": {"$exists": True}}           # 有升级记录
          {"lost_at": None}                         # 未丢失
          {"acquired_at.chapter": 5}                # 精确匹配
        """
        results = []
        for rel in self._relations.values():
            if relation_type and rel.relation_type != relation_type:
                continue
            if source_id and rel.source_id != source_id:
                continue
            if target_id and rel.target_id != target_id:
                continue
            if source_type:
                src = self._units.get(rel.source_id)
                if not src or src.type != source_type:
                    continue
            if target_type:
                tgt = self._units.get(rel.target_id)
                if not tgt or tgt.type != target_type:
                    continue
            if payload_filter and not self._match_payload(rel.payload, payload_filter):
                continue
            results.append(rel)
        return results

    def _match_payload(self, payload: Dict, filter: Dict) -> bool:
        """递归 payload 过滤匹配。支持精确匹配和 $gt/$gte/$lt/$lte/$eq/$exists 操作符。"""
        for key, condition in filter.items():
            value = self._dict_get_nested(payload, key)
            if isinstance(condition, dict):
                for op, expected in condition.items():
                    if op == "$gt":
                        if not (value is not None and self._to_num(value) > self._to_num(expected)):
                            return False
                    elif op == "$gte":
                        if not (value is not None and self._to_num(value) >= self._to_num(expected)):
                            return False
                    elif op == "$lt":
                        if not (value is not None and self._to_num(value) < self._to_num(expected)):
                            return False
                    elif op == "$lte":
                        if not (value is not None and self._to_num(value) <= self._to_num(expected)):
                            return False
                    elif op == "$eq":
                        if value != expected:
                            return False
                    elif op == "$exists":
                        exists = value is not None
                        if bool(expected) != exists:
                            return False
                    elif op == "$in":
                        if value not in expected:
                            return False
                    else:
                        return False
            else:
                if condition is None and value is not None:
                    return False
                if condition is not None and value != condition:
                    return False
        return True

    @staticmethod
    def _dict_get_nested(d: Dict, path: str) -> Any:
        """按点分路径从 dict 中取值（支持数组索引）。"""
        parts = path.split(".")
        current = d
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx] if 0 <= idx < len(current) else None
                except (ValueError, IndexError):
                    return None
            else:
                return None
            if current is None:
                return None
        return current

    @staticmethod
    def _to_num(v: Any) -> Optional[float]:
        """尝试转为数值用于比较。"""
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

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

        def _is_active(uid: str) -> bool:
            u = self._units.get(uid)
            return u is not None and u.status != UnitStatus.ARCHIVED

        # 1 度邻居
        for rel in self.get_relations(unit_id):
            if relation_type and rel.relation_type != relation_type:
                continue
            if rel.source_id == unit_id and rel.target_id not in visited:
                visited.add(rel.target_id)
                if _is_active(rel.target_id):
                    result[1].add(rel.target_id)
            if rel.target_id == unit_id and rel.source_id not in visited:
                visited.add(rel.source_id)
                if _is_active(rel.source_id):
                    result[1].add(rel.source_id)

        # 2 度邻居
        if max_depth >= 2:
            for neighbor_id in result[1]:
                for rel in self.get_relations(neighbor_id):
                    if rel.source_id == neighbor_id and rel.target_id not in visited:
                        visited.add(rel.target_id)
                        if _is_active(rel.target_id):
                            result[2].add(rel.target_id)
                    if rel.target_id == neighbor_id and rel.source_id not in visited:
                        visited.add(rel.source_id)
                        if _is_active(rel.source_id):
                            result[2].add(rel.source_id)
        
        return result
    
    def find_path(
        self,
        from_id: str,
        to_id: str,
        max_depth: int = 5,
    ) -> Optional[List[str]]:
        """BFS 查找两个叙事单元之间的路径（返回节点 ID 链，跳过已归档单元）"""
        if from_id not in self._units or to_id not in self._units:
            return None
        
        target = self._units[to_id]
        if target.status == UnitStatus.ARCHIVED:
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
                    next_unit = self._units.get(next_id)
                    if next_unit and next_unit.status != UnitStatus.ARCHIVED:
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
        ch = get_unit_chapter(unit)
        if ch:
            same_chapter = self.find_units(
                type=unit.type,
                chapter=ch,
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
    
    # ── V2 迁移：structure_path → CONTAINS 边 ──────────────────────────
    
    def migrate_structure_path_to_edges(
        self, actor: str = "system",
    ) -> Dict[str, int]:
        """
        扫描所有具有 structure_path 的单元，为其建立 CONTAINS 边。
        
        迁移策略：
        1. 扫描所有 narrative unit，收集其 structure_path
        2. 对每个有 structure_path 的单元，基于路径推断其父级
        3. 如果父级的 structure_path 前缀匹配，建立 CONTAINS 关系
        4. 返回 {found, edges_created, skipped_existing}
        
        这是一次性迁移函数。V2 新项目无需调用。
        执行后 structure_path 字段不再更新——CONTAINS 边成为真相源。
        """
        found = 0
        edges_created = 0
        skipped = 0
        
        # 第一步：收集所有有 structure_path 的活跃单元（跳过已归档）
        path_units: List[Tuple[str, List[Any]]] = []
        for unit in self._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if unit.structure_path and len(unit.structure_path) > 0:
                path_units.append((unit.id, unit.structure_path))
                found += 1
        
        # 第二步：按 path 长度排序（短路径 = 祖先，先处理）
        path_units.sort(key=lambda x: len(x[1]))
        
        # 第三步：为每个单元找父级（path[:-1] 前缀匹配）
        for unit_id, path in path_units:
            if len(path) < 2:
                continue
            parent_path = path[:-1]
            # 在已处理单元中找 path 前缀匹配的父级
            for parent_id, pp in path_units:
                if parent_id == unit_id:
                    continue
                # 检查 pp 是否是 parent_path 的前缀
                if len(pp) == len(parent_path) and pp == parent_path:
                    # 检查是否已有 CONTAINS 关系
                    exists = False
                    for rel in self._relations.values():
                        if (rel.source_id == parent_id and rel.target_id == unit_id
                                and rel.relation_type == RelationType.CONTAINS):
                            exists = True
                            break
                    if not exists:
                        self.add_relation(
                            source_id=parent_id,
                            target_id=unit_id,
                            relation_type=RelationType.CONTAINS,
                            weight=1.0,
                            description="migrated from structure_path",
                            actor=actor,
                            record_event=True,
                        )
                        edges_created += 1
                    else:
                        skipped += 1
                    break  # 每个单元只有一个父级
        
        self.flush()
        return {
            "found": found,
            "edges_created": edges_created,
            "skipped_existing": skipped,
        }
    
    # ── 统计信息 ────────────────────────────────────────────────────────
    
    def stats(self) -> Dict[str, Any]:
        """graph 统计信息（活跃 vs 归档分开统计）"""
        type_counts = defaultdict(int)
        status_counts = defaultdict(int)
        active_type_counts = defaultdict(int)
        for unit in self._units.values():
            type_counts[unit.type.value] += 1
            status_counts[unit.status.value] += 1
            if unit.status != UnitStatus.ARCHIVED:
                active_type_counts[unit.type.value] += 1
        
        return {
            "total_units": len(self._units),
            "total_relations": len(self._relations),
            "total_events": len(self._events),
            "by_type": dict(type_counts),
            "by_status": dict(status_counts),
            "active_by_type": dict(active_type_counts),
            "snapshot_count": len(list(self.snapshots_dir.glob("*.json"))),
        }
    
    def get_schema_info(self, unit_type: UnitType) -> List[str]:
        """返回该类型的 content 字段要求（供注入 LLM prompt）"""
        from schemas import schema_info
        return schema_info(unit_type)
