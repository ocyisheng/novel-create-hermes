"""
叙事单元网络的数据模型定义。

这是 V2 架构的核心数据抽象。
取代现有三层 YAML 实体（_meta + 索引信息 + 摘要 + 完整档案）体系。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict


# ── 枚举类型 ──────────────────────────────────────────────────────────────

class UnitType(str, Enum):
    """叙事单元类型 — 创作者思考时的基本单位"""
    SCENE = "scene"                     # 场景：一个时间×地点×人物组的叙事切片
    CHARACTER_ARC = "character_arc"     # 角色弧线：角色跨章节的成长轨迹
    PLOT_THREAD = "plot_thread"         # 情节线：一条完整的故事脉络
    THEMATIC_MOTIF = "thematic_motif"   # 主题意象：反复出现的象征性元素
    WORLD_RULE = "world_rule"           # 世界观规则：世界运行的核心法则
    NOTE = "note"                       # 创作笔记：作者/Agent 的备忘和灵感
    CHUNK = "chunk"                     # 正文片段：已写成的文字块
    STRUCTURE = "structure"             # 结构设计：全书整体结构、模式节奏、七面观照
    NARRATIVE_VOICE = "narrative_voice" # 叙述腔调：腔调谱系、叙事视角、笔法约定

    @classmethod
    def from_legacy_entity_type(cls, entity_type: str) -> "UnitType":
        """从现有三层YAML的 entity_type 映射到 UnitType"""
        mapping = {
            "character": UnitType.CHARACTER_ARC,
            "world_overview": UnitType.WORLD_RULE,
            "rule": UnitType.WORLD_RULE,
            "power_system": UnitType.WORLD_RULE,
            "faction": UnitType.WORLD_RULE,
            "location": UnitType.WORLD_RULE,
            "history": UnitType.WORLD_RULE,
            "culture": UnitType.WORLD_RULE,
            "economic_system": UnitType.WORLD_RULE,
            "political_system": UnitType.WORLD_RULE,
            "social_hierarchy": UnitType.WORLD_RULE,
            "plot_thread": UnitType.PLOT_THREAD,
            "chapter": UnitType.STRUCTURE,  # V1 分纲→V2 章纲（STRUCTURE 子类型=章纲）
        }
        return mapping.get(entity_type, UnitType.NOTE)


class UnitStatus(str, Enum):
    """叙事单元的生命周期状态"""
    SPROUT = "sprout"                   # 萌芽：刚被创建，内容未定
    GROWING = "growing"                 # 生长中：内容在逐步充实
    MATURE = "mature"                   # 成熟：内容已基本确定
    FROZEN = "frozen"                   # 冻结：暂时不做修改
    ARCHIVED = "archived"               # 归档：不再使用

    @classmethod
    def from_legacy_status(cls, status: str) -> "UnitStatus":
        mapping = {
            "active": UnitStatus.MATURE,
            "draft": UnitStatus.SPROUT,
            "writing": UnitStatus.GROWING,
            "complete": UnitStatus.MATURE,
            "inactive": UnitStatus.FROZEN,
            "deceased": UnitStatus.ARCHIVED,
            "departed": UnitStatus.ARCHIVED,
            "resolved": UnitStatus.ARCHIVED,
            "on_hold": UnitStatus.FROZEN,
        }
        return mapping.get(status, UnitStatus.GROWING)


class RelationType(str, Enum):
    """叙事单元之间的关系类型"""
    CAUSES = "causes"                   # A 导致 B 发生
    PRECEDES = "precedes"               # A 在时间线上先于 B
    CONTRADICTS = "contradicts"         # A 与 B 矛盾（需解决）
    IMPLEMENTS = "implements"           # A 是 B 的具体实现
    INSPIRES = "inspires"               # A 启发了 B 的创作
    REFINES = "refines"                 # A 对 B 做了精细化修订
    BELONGS_TO = "belongs_to"           # A 是 B 的一部分
    REFERENCES = "references"            # A 中提到了 B
    IMPLIES = "implies"                 # A 隐含了 B（弱关联）
    PARALLEL = "parallel"               # A 与 B 并列发生
    PARTICIPATES_IN = "participates_in" # A 参与 B（角色参与场景）
    LOCATED_AT = "located_at"           # A 位于 B（场景/角色所在地点）
    ALLIED_WITH = "allied_with"         # A 与 B 同盟（角色/势力之间）
    CONTAINS = "contains"               # A 包含 B（BELONGS_TO 的反向）
    CONTROLS = "controls"               # A 控制 B（势力控制地域等）
    MEMBER_OF = "member_of"             # A 是 B 的成员（角色属于势力/组织）
    HAS_MEMBER = "has_member"           # A 拥有成员 B（MEMBER_OF 的反向）
    LOCATION_OF = "location_of"         # A 是 B 的位置（LOCATED_AT 的反向）
    CONTROLLED_BY = "controlled_by"     # A 受 B 控制（CONTROLS 的反向）

    @property
    def inverse(self) -> "RelationType":
        inverses = {
            "causes": "caused_by",
            "precedes": "follows",
            "contradicts": "contradicted_by",
            "implements": "implemented_by",
            "inspires": "inspired_from",
            "refines": "refined_by",
            "belongs_to": "contains",
            "references": "referenced_by",
            "implies": "implied_from",
            "parallel": "parallel",
            "located_at": "location_of",
            "allied_with": "allied_with",
            "contains": "belongs_to",
            "controls": "controlled_by",
            "member_of": "has_member",
            "has_member": "member_of",
            "location_of": "located_at",
            "controlled_by": "controls",
        }
        # Return as RelationType if exists, else as string
        name = inverses.get(self.value, self.value)
        try:
            return RelationType(name)
        except ValueError:
            return self


class EventType(str, Enum):
    """事件溯源的事件类型"""
    UNIT_CREATED = "unit_created"
    UNIT_UPDATED = "unit_updated"
    UNIT_STATUS_CHANGED = "unit_status_changed"
    UNIT_ARCHIVED = "unit_archived"
    RELATION_ADDED = "relation_added"
    RELATION_REMOVED = "relation_removed"
    RELATION_UPDATED = "relation_updated"
    PROJECTION_REBUILT = "projection_rebuilt"
    BRANCH_CREATED = "branch_created"
    BRANCH_MERGED = "branch_merged"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    SYSTEM_EVENT = "system_event"


class ProjectionView(str, Enum):
    """投影视图类型"""
    OUTLINE = "outline"                 # 总纲视图
    CHAPTER_OUTLINE = "chapter_outline" # 分纲视图
    CHARACTER = "character"             # 角色档案视图
    WORLDBUILDING = "worldbuilding"     # 世界观视图
    PLOT = "plot"                       # 情节线视图
    TRACKING = "tracking"               # 追踪统计视图
    TIMELINE = "timeline"              # 时间线视图


# ── 核心数据类 ────────────────────────────────────────────────────────────

@dataclass
class NarrativeUnit:
    """
    叙事单元 — V2 架构的基本数据单位。
    
    取代现有架构中分散的 YAML 实体文件。
    一个叙事单元对应创作者思维中的一个"东西"——一个场景、一条弧线、一个设定。
    """
    id: str                               # UUID，全局唯一
    type: UnitType                        # 单元类型
    unit_name: str                        # 人类可读的名称（如"林渊后山拔剑"）
    content: str                          # 自由文本或结构化 JSON 内容
    status: UnitStatus = UnitStatus.SPROUT
    confidence: float = 0.5               # 0.0-1.0，该单元在创作者心中的确定度
    tags: List[str] = field(default_factory=list)     # 自由标签（取代封闭分类）
    
    # 元数据
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # 层级归属（CONTAINS 边是唯一真相源，以下字段为缓存/快捷字段）
    belongs_to_project: Optional[str] = None
    # 精确章节号（CONTAINS 边关系下的真实章节标号）
    chapter_number: Optional[int] = None
    # 通用结构路径，CONTAINS 边的缓存
    # 示例：["人界篇", "黄枫谷卷", 15] 表示第15章，在黄枫谷卷、人界篇下
    # 示例：[15] 仅章节号，无篇无卷
    # 示例：None 无层级归属（事件驱动、非线性叙事）
    # NOTE: structure_path 不是持久化来源——边的 CONTAINS 层级关系才是唯一真相源。
    # structure_path 可由 rebuild_structure_path_from_edges() 重新构建，仅作为缓存。
    structure_path: Optional[List[Any]] = None
    
    # 历史版本（仅保留最新版本 + diff 链）
    version: int = 1
    
    # 扩展字段（按 type 不同有不同期望的键）
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        序列化到 dict（用于持久化 JSONL）。
        
        structure_path 不作为持久化字段——CONTAINS 边才是层级关系唯一真相源。
        加载时 through from_dict() 会自动从 JSONL 读取旧数据兼容。
        """
        result = {}
        result["id"] = self.id
        result["type"] = self.type.value
        result["unit_name"] = self.unit_name
        result["content"] = self.content
        result["status"] = self.status.value
        result["confidence"] = self.confidence
        result["tags"] = self.tags
        result["created_at"] = self.created_at.isoformat()
        result["updated_at"] = self.updated_at.isoformat()
        result["belongs_to_project"] = self.belongs_to_project
        result["chapter_number"] = self.chapter_number
        result["version"] = self.version
        result["extra"] = self.extra
        # 不序列化 structure_path — CONTAINS 边是唯一真相源
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeUnit":
        """从 dict 反序列化。自动忽略已废弃的旧字段以保证向后兼容。"""
        data = dict(data)
        data["type"] = UnitType(data["type"])
        data["status"] = UnitStatus(data.get("status", "sprout"))
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        # 移除已废弃的旧字段（存量 JSONL 中可能还有），structure_path 保留
        for old_key in ("belongs_to_chapter", "belongs_to_volume"):
            data.pop(old_key, None)
        return cls(**data)


@dataclass
class Relation:
    """
    叙事单元之间的关系。
    
    取代现有架构中分散在 project_index.yaml 和各文件内部的隐式引用。
    关系是 graph 的核心——它使得"如果改这个角色会影响哪些情节线"这类
    查询成为可能，而不需要手动遍历文件。
    """
    id: str                               # UUID
    source_id: str                        # 源单元 ID
    target_id: str                        # 目标单元 ID
    relation_type: RelationType           # 关系类型
    weight: float = 0.5                   # 0.0-1.0，关系强度
    description: str = ""                 # 可选的关系描述
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["relation_type"] = self.relation_type.value
        result["created_at"] = self.created_at.isoformat()
        return result


@dataclass
class Event:
    """
    事件溯源的事件记录。
    
    每次对 graph 的修改都记录为一条事件，构成完整的创作历史。
    可以回放到任意时间点、审计每次修改的来源（用户/Agent/脚本）。
    """
    event_id: str
    timestamp: datetime
    actor: str                            # "user" | "sub_agent" | "script" | 具体名称
    event_type: EventType
    target_type: Optional[str] = None     # "unit" | "relation" | "projection"
    target_ids: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None      # 关联的创作会话 ID
    parent_event_id: Optional[str] = None # 用于追踪因果链
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["event_type"] = self.event_type.value
        result["timestamp"] = self.timestamp.isoformat()
        return result


# ── Graph 快照（用于定期归档） ──────────────────────────────────────────────

@dataclass
class GraphSnapshot:
    """Graph 在某个时间点的完整状态快照"""
    snapshot_id: str
    timestamp: datetime
    units: List[NarrativeUnit]
    relations: List[Relation]
    last_event_id: str                    # 该快照对应的最后一条事件 ID
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "units": [u.to_dict() for u in self.units],
            "relations": [r.to_dict() for r in self.relations],
            "last_event_id": self.last_event_id,
            "metadata": self.metadata,
        }


# ── 查询帮助函数 ──────────────────────────────────────────────────────────


def get_unit_chapter(unit: NarrativeUnit) -> int:
    """
    获取单元的章节号，回退链：chapter_number → structure_path 末位 → 0。
    用于排序和分组。
    """
    if unit.chapter_number is not None:
        return unit.chapter_number
    if unit.structure_path and len(unit.structure_path) > 0:
        last = unit.structure_path[-1]
        if isinstance(last, int):
            return last
    return 0


def get_unit_chapter_label(unit: NarrativeUnit) -> str:
    """获取章节显示标签（如 '第3章'），无章节时返回 '?'"""
    ch = get_unit_chapter(unit)
    return f"第{ch}章" if ch else "?"


def create_unit_id(unit_type: Optional[UnitType] = None) -> str:
    """生成全局唯一的叙事单元 ID（人类可读前缀 + UUID 短码）"""
    prefix_map = {
        UnitType.SCENE: "sc",
        UnitType.CHARACTER_ARC: "ca",
        UnitType.PLOT_THREAD: "pt",
        UnitType.THEMATIC_MOTIF: "tm",
        UnitType.WORLD_RULE: "wr",
        UnitType.NOTE: "nt",
        UnitType.CHUNK: "ck",
        UnitType.STRUCTURE: "st",
        UnitType.NARRATIVE_VOICE: "nv",
    }
    prefix = prefix_map.get(unit_type, "xx") if unit_type else "xx"
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{short_uuid}"


def create_relation_id() -> str:
    return f"rel_{uuid.uuid4().hex[:12]}"


def create_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"
