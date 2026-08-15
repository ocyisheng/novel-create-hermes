"""
叙事单元网络的数据模型定义。

这是 V2 架构的核心数据抽象。
取代现有三层 YAML 实体（_meta + 索引信息 + 摘要 + 完整档案）体系。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
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
    OUTLINE = "outline"                 # 总纲：全书级结构设计（本体论、七面观照、模式选择）
    ARC_PLAN = "arc_plan"               # 部大纲：跨卷级规划（覆盖部/篇两种命名约定）
    VOLUME_PLAN = "volume_plan"         # 卷大纲：卷级规划（冲突、情绪、起止状态）
    CHAPTER_PLAN = "chapter_plan"       # 章纲：章节级规划（场景序列、节奏、信息分布）
    STRUCTURE = "structure"             # [已废弃] 保留向后兼容，新代码勿用
    NARRATIVE_VOICE = "narrative_voice" # 叙述腔调：腔调谱系、叙事视角、笔法约定
    TEMPORAL_EVENT = "temporal_event"   # 时间事件：挂载到任意实体上的时间轴节点

    @classmethod
    def _missing_(cls, value: str):
        """宽松查找：先按 value（小写），再按 name（大写），都找不到返回 None。"""
        if isinstance(value, str):
            # 先按小写 value 查找
            for member in cls:
                if member.value == value.lower():
                    return member
            # 再按 name 查找（大写）
            for member in cls:
                if member.name == value.upper():
                    return member
        return None

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
            "chapter": UnitType.CHAPTER_PLAN,  # V1 分纲→V2 章纲
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
    """叙事单元之间的关系类型

    注意：此枚举用于程序化查询和一致性规则（如 CONTAINS 环检测、PRECEDES 序数校验）。
    用户想表达的中文语义标签（师徒、母子、欠人情等）存储在 Relation.label 字段中，
    不在此枚举中 —— 用户可自由输入任意标签。
    """
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
    PLANS = "plans"                     # A 规划 B（章纲规划场景）——规划意图而非结构归属
    PLANNED_BY = "planned_by"           # A 被 B 规划（PLANS 的反向）
    PARTICIPATES_IN = "participates_in" # A 参与 B（角色参与场景）
    LOCATED_AT = "located_at"           # A 位于 B（场景/角色所在地点）
    RELATES_TO = "relates_to"            # A 与 B 有关联（角色间通用容器，具体语义见 label）
    POSSESSES = "possesses"             # A 拥有 B（角色拥有物品/能力/法宝）
    POSSESSED_BY = "possessed_by"       # A 被 B 拥有（POSSESSES 的反向）
    CONTAINS = "contains"               # A 包含 B（BELONGS_TO 的反向）
    CONTROLS = "controls"               # A 控制 B（势力控制地域等）
    MEMBER_OF = "member_of"             # A 是 B 的成员（角色属于势力/组织）
    HAS_MEMBER = "has_member"           # A 拥有成员 B（MEMBER_OF 的反向）
    LOCATION_OF = "location_of"         # A 是 B 的位置（LOCATED_AT 的反向）
    CONTROLLED_BY = "controlled_by"     # A 受 B 控制（CONTROLS 的反向）
    HAS_EVENT = "has_event"             # A 有事件 B（实体 → temporal_event）
    EVENT_OF = "event_of"               # A 是 B 的事件（HAS_EVENT 的反向）
    INVOLVES = "involves"               # A 涉及角色 B（事件 → 角色参与）
    # ── type_registry 声明类型（relation_types.yaml 唯一事实来源）──
    # 漂移修复：YAML 已声明但旧枚举缺失，补齐使主代码路径与注册表一致
    # （否则 Relation.from_dict 加载此类边会因 RelationType 查找失败而丢弃）。
    CAUSED_BY = "caused_by"             # A 由 B 导致（causes 的反向，前驱事件）
    CAUSED = "caused"                   # A 是 B 的后果（causes 的另一种反向表达）
    APPLIES_TO = "applies_to"           # 此腔调适用的范围（narrative_voice → 规划/大纲）

    @classmethod
    def _missing_(cls, value: str):
        """宽松查找：小写 value 与大写 name 均可解析。"""
        for member in cls:
            if member.value == value.lower():
                return member
        for member in cls:
            if member.name == value.upper():
                return member
        return None

    @property
    def inverse(self) -> "RelationType":
        """返回逆关系类型。

        架构说明：系统采用「物化逆边」——bidirectional 创建与 fix_asymmetry
        补齐时，会在图上物理写入反向边；方向由 source_id/target_id 表达，
        Relation 数据类没有独立 direction 字段。

        - 配对类型（CONTAINS↔BELONGS_TO、PLANS↔PLANNED_BY、POSSESSES↔POSSESSED_BY 等）
          有独立的逆类型
        - 自反类型（CAUSES、RELATES_TO、PARTICIPATES_IN 等）逆 = 自身，
          双向边以同类型物化（R2 不对称检查期望此类关系双向存在）
        """
        inverses = {
            "causes": "causes",
            "precedes": "precedes",
            "contradicts": "contradicts",
            "implements": "implements",
            "inspires": "inspires",
            "refines": "refines",
            "belongs_to": "contains",
            "references": "references",
            "implies": "implies",
            "parallel": "parallel",
            "plans": "planned_by",
            "planned_by": "plans",
            "participates_in": "participates_in",
            "located_at": "location_of",
            "has_event": "event_of",
            "event_of": "has_event",
            "involves": "involves",
            "relates_to": "relates_to",
            "possesses": "possessed_by",
            "possessed_by": "possesses",
            "contains": "belongs_to",
            "controls": "controlled_by",
            "member_of": "has_member",
            "has_member": "member_of",
            "location_of": "located_at",
            "controlled_by": "controls",
            "caused_by": "causes",
            "caused": "causes",
            "applies_to": "applies_to",
        }
        name = inverses.get(self.value, self.value)
        try:
            return RelationType(name)
        except ValueError:
            return self

    @property
    def is_symmetric(self) -> bool:
        """自反类型：逆 = 自身，双向边以同类型物化（如 CAUSES、RELATES_TO）。"""
        return self.inverse == self

    @property
    def is_acyclic(self) -> bool:
        """是否为无环层级类型：加入此类边会受环检测约束。

        当前仅 CONTAINS / BELONGS_TO（互为逆的层级对）为无环类型。
        添加时需防止在同一层级森林中形成环。
        """
        return self in (RelationType.CONTAINS, RelationType.BELONGS_TO)

    @property
    def auto_reverse(self) -> str:
        """自动补反向策略（三态）。

        决定 bidirectional / fix_asymmetry 是否自动物化反向边：

        - "always"  ：对称语义或配对类型 → 建正向即物化反向。
                      A 类（同类型自翻）：CONTRADICTS/PARALLEL/RELATES_TO/PARTICIPATES_IN/INVOLVES
                      B 类（inverse 类型自翻）：MEMBER_OF/POSSESSES/CONTROLS/LOCATED_AT/HAS_EVENT/PLANS
                      及其配对反向类型
        - "optional"：默认不自动补反向，但显式 bidirectional=True 时允许（层级 CONTAINS/BELONGS_TO）
        - "never"   ：单向断言 → 禁止自动补反向（CAUSES/PRECEDES/IMPLEMENTS/REFERENCES/IMPLIES/
                      INSPIRES/REFINES），避免制造语义错误边
        """
        policies = {
            # A 类：对称语义，同类型自翻
            "contradicts": "always",
            "parallel": "always",
            "relates_to": "always",
            "participates_in": "always",
            "involves": "always",
            # B 类：配对类型，inverse 类型自翻（含反向类型本身）
            "member_of": "always",
            "has_member": "always",
            "possesses": "always",
            "possessed_by": "always",
            "controls": "always",
            "controlled_by": "always",
            "located_at": "always",
            "location_of": "always",
            "has_event": "always",
            "event_of": "always",
            "plans": "always",
            "planned_by": "always",
            # 层级：一条边足够，默认不自动补
            "contains": "optional",
            "belongs_to": "optional",
            # C 类：单向断言，禁止自翻
            "causes": "never",
            "precedes": "never",
            "implements": "never",
            "references": "never",
            "implies": "never",
            "inspires": "never",
            "refines": "never",
            "caused_by": "never",
            "caused": "never",
            "applies_to": "never",
        }
        return policies.get(self.value, "never")

    @classmethod
    def label(cls, rt: "RelationType") -> str:
        """返回关系类型的中文显示标签。"""
        labels = {
            cls.CAUSES: "导致",
            cls.PRECEDES: "先于",
            cls.CONTRADICTS: "矛盾",
            cls.IMPLEMENTS: "实现",
            cls.INSPIRES: "启发",
            cls.REFINES: "细化",
            cls.BELONGS_TO: "属于",
            cls.REFERENCES: "引用",
            cls.IMPLIES: "隐含",
            cls.PARALLEL: "并列",
            cls.PLANS: "规划",
            cls.PLANNED_BY: "被规划",
            cls.PARTICIPATES_IN: "参与",
            cls.LOCATED_AT: "位于",
            cls.HAS_EVENT: "有事件",
            cls.EVENT_OF: "所属事件",
            cls.INVOLVES: "涉及",
            cls.RELATES_TO: "关联",
            cls.POSSESSES: "拥有",
            cls.POSSESSED_BY: "被拥有",
            cls.CONTAINS: "包含",
            cls.CONTROLS: "统治",
            cls.MEMBER_OF: "成员",
            cls.HAS_MEMBER: "拥有成员",
            cls.LOCATION_OF: "所在",
            cls.CONTROLLED_BY: "受制",
            cls.CAUSED_BY: "由…导致",
            cls.CAUSED: "导致",
            cls.APPLIES_TO: "适用于",
        }
        return labels.get(rt, rt.value)

    @classmethod
    def color(cls, rt: "RelationType") -> str:
        """返回关系类型的可视化颜色。"""
        colors = {
            cls.PARTICIPATES_IN: "#5B9BD5",
            cls.CAUSES: "#FF4444",
            cls.PRECEDES: "#FFC000",
            cls.CONTRADICTS: "#FF6600",
            cls.IMPLEMENTS: "#70AD47",
            cls.BELONGS_TO: "#ED7D31",
            cls.REFERENCES: "#8888AA",
            cls.IMPLIES: "#8888AA",
            cls.PARALLEL: "#B4A7D6",
            cls.INSPIRES: "#B4A7D6",
            cls.REFINES: "#70AD47",
            cls.LOCATED_AT: "#00B0F0",
            cls.RELATES_TO: "#92D050",
            cls.POSSESSES: "#9B59B6",
            cls.POSSESSED_BY: "#9B59B6",
            cls.CONTAINS: "#ED7D31",
            cls.CONTROLS: "#FF6600",
            cls.MEMBER_OF: "#5B9BD5",
            cls.HAS_MEMBER: "#5B9BD5",
            cls.LOCATION_OF: "#00B0F0",
            cls.CONTROLLED_BY: "#FF6600",
            cls.PLANS: "#7F8C8D",
            cls.PLANNED_BY: "#7F8C8D",
            cls.CAUSED_BY: "#FF4444",
            cls.CAUSED: "#FF4444",
            cls.APPLIES_TO: "#888888",
        }
        return colors.get(rt, "#888888")

    @classmethod
    def domain(cls, rt: "RelationType") -> str:
        """返回所属域：structural / planning / entity / temporal / causal / reference

        与 type_registry 的 RelationTypeDef.domain 保持一致（relation_types.yaml 唯一事实来源）；
        此处为静态兼容视图，供无法访问注册表的纯枚举场景使用。
        """
        domains = {
            # structural：层级归属
            cls.CONTAINS: "structural",
            cls.BELONGS_TO: "structural",
            # planning：规划意图
            cls.PLANS: "planning",
            cls.PLANNED_BY: "planning",
            cls.IMPLEMENTS: "planning",
            cls.APPLIES_TO: "planning",
            # entity：实体关系（角色/势力/物品/时间事件）
            cls.PARTICIPATES_IN: "entity",
            cls.LOCATED_AT: "entity",
            cls.LOCATION_OF: "entity",
            cls.RELATES_TO: "entity",
            cls.POSSESSES: "entity",
            cls.POSSESSED_BY: "entity",
            cls.CONTROLS: "entity",
            cls.CONTROLLED_BY: "entity",
            cls.MEMBER_OF: "entity",
            cls.HAS_MEMBER: "entity",
            cls.HAS_EVENT: "entity",
            cls.EVENT_OF: "entity",
            cls.INVOLVES: "entity",
            # temporal：叙事/事件时序
            cls.PRECEDES: "temporal",
            cls.PARALLEL: "temporal",
            # causal：因果
            cls.CAUSES: "causal",
            cls.CAUSED_BY: "causal",
            cls.CAUSED: "causal",
            cls.CONTRADICTS: "causal",
            cls.IMPLIES: "causal",
            # reference：引用/启发/细化
            cls.REFERENCES: "reference",
            cls.INSPIRES: "reference",
            cls.REFINES: "reference",
        }
        return domains.get(rt, "narrative")


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


@dataclass(frozen=True)
class HierarchyInfo:
    """从 graph 结构推导的层级属性（chapter_number + structure_path）。

    由 GraphStore 注入的层级解析器计算，NarrativeUnit 的 chapter_number /
    structure_path 属性在显式缓存缺失时回退到该推导结果。
    """
    chapter_number: Optional[int] = None
    structure_path: Optional[List[Any]] = None


@dataclass
class NarrativeUnit:
    """
    叙事单元 — V2 架构的基本数据单位。
    
    取代现有架构中分散的 YAML 实体文件。
    一个叙事单元对应创作者思维中的一个"东西"——一个场景、一条弧线、一个设定。
    
    extra.time 约定（通用故事时间表示）：
        extra["time"] = {
            "label": str,            # 人类可读时间表达（如"第三日清晨"）
            "ordinal": float | None, # 可排序序数，由 CharacterTimelineLedger 自动赋值
            "precision": str,        # exact|same|day|month|year|era|relative|vague
        }
    暂存 extra 而非一等字段：Ledger 预计算排序视图，引擎层不依赖 extra 做索引。
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
    
    # 层级归属（CONTAINS 边是唯一真相源）
    # chapter_number / structure_path 是派生属性（见下方 @property）：
    # - 显式缓存（JSONL 旧数据 / create_unit 参数）优先；
    # - 缓存缺失时回退到 _hierarchy_resolver（GraphStore 注入）从图结构推导。
    # 以下私有字段不参与序列化 / 相等比较 / repr。
    _chapter_number_cache: Optional[int] = field(default=None, init=False, repr=False, compare=False)
    _structure_path_cache: Optional[List[Any]] = field(default=None, init=False, repr=False, compare=False)
    _hierarchy_resolver: Optional[Callable[[], "HierarchyInfo"]] = field(
        default=None, init=False, repr=False, compare=False,
    )
    
    # 历史版本（仅保留最新版本 + diff 链）
    version: int = 1
    
    # 扩展字段（按 type 不同有不同期望的键）
    extra: Dict[str, Any] = field(default_factory=dict)
    
    # ── 派生层级属性 ────────────────────────────────────────────────────
    
    @property
    def chapter_number(self) -> Optional[int]:
        """精确章节号：显式缓存优先，否则从 graph 结构推导。

        推导链（由 _hierarchy_resolver 提供）：自身缓存 → structure_path 缓存
        末位 → 最近的 CHAPTER_PLAN 祖先章节号。
        """
        if self._chapter_number_cache is not None:
            return self._chapter_number_cache
        info = self._resolve_hierarchy()
        return info.chapter_number if info is not None else None
    
    @chapter_number.setter
    def chapter_number(self, value: Optional[int]) -> None:
        self._chapter_number_cache = value
    
    @property
    def structure_path(self) -> Optional[List[Any]]:
        """通用结构路径：显式缓存优先，否则沿 graph 祖先链（CONTAINS 边）推导。

        示例：["人界篇", "黄枫谷卷", 15] 表示第15章，在黄枫谷卷、人界篇下。
        None 表示无层级归属（事件驱动、非线性叙事）。
        """
        if self._structure_path_cache is not None:
            return self._structure_path_cache
        info = self._resolve_hierarchy()
        return info.structure_path if info is not None else None
    
    @structure_path.setter
    def structure_path(self, value: Optional[List[Any]]) -> None:
        self._structure_path_cache = value
    
    def _resolve_hierarchy(self) -> Optional["HierarchyInfo"]:
        """调用注入的层级解析器（无解析器或 store 已释放时返回 None）。"""
        if self._hierarchy_resolver is None:
            return None
        return self._hierarchy_resolver()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        序列化到 dict（用于持久化 JSONL）。
        
        structure_path 不作为持久化字段——CONTAINS 边才是层级关系唯一真相源。
        加载时 through from_dict() 会自动从 JSONL 读取旧数据兼容。
        chapter_number 序列化派生后的值作为缓存，供旧读者兼容。
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
        result["chapter_number"] = self.chapter_number
        result["version"] = self.version
        result["extra"] = self.extra
        # 不序列化 structure_path — CONTAINS 边是唯一真相源
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NarrativeUnit":
        """从 dict 反序列化。自动忽略已废弃的旧字段以保证向后兼容。"""
        data = dict(data)
        # chapter_number / structure_path 是派生属性，不能作为构造参数；
        # 从 JSONL 读取的旧值存入私有缓存（显式值优先于图结构推导）。
        chapter_number = data.pop("chapter_number", None)
        structure_path = data.pop("structure_path", None)
        data["type"] = UnitType(data["type"])
        data["status"] = UnitStatus(data.get("status", "sprout"))
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        # 保证 content 永远是 JSON 字符串（兼容存量 dict 数据）
        if isinstance(data.get("content"), dict):
            data["content"] = json.dumps(data["content"], ensure_ascii=False)
        # 保证 unit_name 不为 None
        if data.get("unit_name") is None:
            data["unit_name"] = ""
        # 移除已废弃的旧字段（存量 JSONL 中可能还有），structure_path 保留
        for old_key in ("belongs_to_project", "belongs_to_chapter", "belongs_to_volume"):
            data.pop(old_key, None)
        unit = cls(**data)
        unit._chapter_number_cache = chapter_number
        unit._structure_path_cache = structure_path
        return unit


@dataclass
class Relation:
    """
    叙事单元之间的关系。
    
    取代现有架构中分散在 project_index.yaml 和各文件内部的隐式引用。
    关系是 graph 的核心——它使得"如果改这个角色会影响哪些情节线"这类
    查询成为可能，而不需要手动遍历文件。
    
    payload 约定键（约定而非新字段，无 schema 强制，写入时自由合并）：
    - 时态演化：start_chapter / end_chapter / resolve_chapter（关系生效/结束/伏笔回收章节）
    - 证据锚点：source（"auto"|"llm"|"manual"，边的产生通道）+ chapter（出处章节）
    """
    id: str                               # UUID
    source_id: str                        # 源单元 ID
    target_id: str                        # 目标单元 ID
    relation_type: RelationType           # 关系类型（枚举，用于查询/校验）
    weight: float = 0.5                   # 0.0-1.0，关系强度
    description: str = ""                 # 可选的关系描述
    label: str = ""                       # 关系语义标签（如"师徒""母子"），自由文本，不限枚举
    source_role: str = ""                 # 源端点在关系中的角色（如"师傅"），跟随端点不跟随边
    target_role: str = ""                 # 目标端点在关系中的角色（如"徒弟"），跟随端点不跟随边
    payload: Dict[str, Any] = field(default_factory=dict)  # 结构化载荷（含 schema 校验）
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """统一 label 位置：payload.label 是唯一事实来源。

        构造时若顶层 label 为空而 payload.label 非空，则回填顶层 label，
        保证内存中的 rel.label 与持久化位置一致（去重键与查询都以它为据）。
        """
        payload_label = self.payload.get("label") if isinstance(self.payload, dict) else None
        if not self.label and payload_label:
            self.label = str(payload_label)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["relation_type"] = self.relation_type.value
        result["created_at"] = self.created_at.isoformat()
        result["updated_at"] = self.updated_at.isoformat()
        # 统一 label 存储：写入 payload.label（非空时写，空时删除陈旧残留）
        payload = dict(self.payload)
        if self.label:
            payload["label"] = self.label
        else:
            payload.pop("label", None)
        result["payload"] = payload
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relation":
        """从 dict 反序列化。旧 metadata 字段已由 T1.1 迁移完成，不再兼容。"""
        data = dict(data)
        if "payload" not in data:
            data["payload"] = {}
        # 类型转换
        if "relation_type" in data and isinstance(data["relation_type"], str):
            data["relation_type"] = RelationType(data["relation_type"])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


@dataclass
class Event:
    """
    事件溯源的事件记录（append-only 审计日志，非可回放日志）。

    每次对 graph 的修改都追加一条事件，构成完整的创作历史，用于
    审计每次修改的来源（用户/Agent/脚本）与时间线追踪。

    注意：events.olog 是仅追加的调试/审计日志，没有消费游标，也不支持
    "回放到任意时间点"——状态恢复请使用 graph/snapshots/ 下的快照。
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
    获取单元的章节号，回退链：chapter_number（派生属性）→ structure_path 末位 → 0。
    用于排序和分组。
    """
    ch = unit.chapter_number
    if ch is not None:
        return ch
    if unit._structure_path_cache and len(unit._structure_path_cache) > 0:
        last = unit._structure_path_cache[-1]
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
        UnitType.OUTLINE: "ol",
        UnitType.ARC_PLAN: "ap",
        UnitType.VOLUME_PLAN: "vp",
        UnitType.CHAPTER_PLAN: "cp",
        UnitType.STRUCTURE: "st",           # 废弃，保留向后兼容
        UnitType.NARRATIVE_VOICE: "nv",
        UnitType.TEMPORAL_EVENT: "te",
    }
    prefix = prefix_map.get(unit_type, "xx") if unit_type else "xx"
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{short_uuid}"


def create_relation_id() -> str:
    return f"rel_{uuid.uuid4().hex[:12]}"


def create_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"
