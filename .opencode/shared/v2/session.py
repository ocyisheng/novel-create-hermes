"""
创作会话管理器 + 用户状态模型。

取代传统线性状态机，引入嵌套循环创作模型。
创作会话是一个有状态的、持久的、可中断的交互过程。
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from graph_schema import UnitType, UnitStatus, NarrativeUnit


# ── 枚举 ──────────────────────────────────────────────────────────────────

class SessionPhase(str, Enum):
    """创作会话的阶段（嵌套循环模型）"""
    ASSESS = "assess"                   # 评估：当前在哪儿，接下来做什么
    EXECUTE = "execute"                 # 执行：写/改/规划
    REVIEW = "review"                   # 检测：质量/一致性/问题
    SETTLE = "settle"                   # 沉淀：放一放，等待回顾


class SessionStatus(str, Enum):
    """会话生命周期状态"""
    WARMING_UP = "warming_up"           # 热身中
    DRAFTING = "drafting"               # 写作中
    PAUSING = "pausing"                 # 暂停（用户中断）
    REVIEWING = "reviewing"             # 审查中
    COOLING_DOWN = "cooling_down"       # 冷却中（沉淀期）
    COMPLETED = "completed"             # 已完成
    ABANDONED = "abandoned"             # 废弃


class CycleType(str, Enum):
    """创作循环类型"""
    IDEATION = "ideation"               # 发散构思
    EXPANSION = "expansion"             # 扩展写作
    REFINEMENT = "refinement"           # 精修润色
    PROOFING = "proofing"               # 校对质检
    PLANNING = "planning"               # 规划组织


class EnergyLevel(str, Enum):
    """预估精力水平"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── 数据类 ────────────────────────────────────────────────────────────────

@dataclass
class FocusTarget:
    """当前创作焦点"""
    type: UnitType                      # 正在处理什么类型的叙事单元
    unit_id: str                        # 目标叙事单元 ID
    sub_target: Optional[str] = None    # 可选的子目标（如具体字段）

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "unit_id": self.unit_id, "sub_target": self.sub_target}


@dataclass
class SessionAction:
    """会话中的单次动作记录"""
    action: str                         # "write" | "edit" | "review" | "query" | "create_unit" | "relate"
    target_type: str                    # "scene" | "character_arc" | etc.
    target_id: str                      # 目标叙事单元 ID
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    tokens_generated: int = 0
    notes: str = ""

    def duration_seconds(self) -> Optional[float]:
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "tokens_generated": self.tokens_generated,
            "notes": self.notes,
        }


@dataclass
class UserState:
    """
    用户状态模型。
    
    不直接注入 prompt，只用于编排层判断上下文加载策略。
    """

    # ── 当前焦点 ──
    focus: Optional[FocusTarget] = None

    # ── 写作节奏 ──
    recent_writing_days_last_7: int = 0
    avg_session_minutes: int = 45
    current_session_start: Optional[datetime] = None
    _energy_level: Optional[EnergyLevel] = None

    # ── 创作循环 ──
    current_cycle: int = 1
    current_cycle_type: CycleType = CycleType.EXPANSION

    # ── 未完成的意图 ──
    expressed_intentions: List[Dict[str, str]] = field(default_factory=list)

    # ── 当前会话引用 ──
    active_session_id: Optional[str] = None

    @property
    def energy_level(self) -> EnergyLevel:
        if self._energy_level:
            return self._energy_level
        # 自动推断
        if not self.current_session_start:
            return EnergyLevel.HIGH
        elapsed = datetime.now(timezone.utc) - self.current_session_start
        if elapsed > timedelta(hours=2):
            return EnergyLevel.LOW
        elif elapsed > timedelta(hours=1):
            return EnergyLevel.MEDIUM
        return EnergyLevel.HIGH

    @energy_level.setter
    def energy_level(self, value: EnergyLevel):
        self._energy_level = value

    def start_session(self):
        self.current_session_start = datetime.now(timezone.utc)

    def end_session(self):
        if self.current_session_start:
            elapsed = datetime.now(timezone.utc) - self.current_session_start
            # 平滑更新平均 session 时长
            self.avg_session_minutes = int(
                0.7 * self.avg_session_minutes + 0.3 * (elapsed.total_seconds() / 60)
            )
        self.current_session_start = None
        self._energy_level = None

    def add_intention(self, intention: str, context: str = ""):
        self.expressed_intentions.append({
            "intention": intention,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        })

    def resolve_intention(self, intention_text: str):
        for i in self.expressed_intentions:
            if i["intention"] == intention_text and not i.get("resolved"):
                i["resolved"] = True
                break

    def to_dict(self) -> Dict[str, Any]:
        return {
            "focus": self.focus.to_dict() if self.focus else None,
            "recent_writing_days_last_7": self.recent_writing_days_last_7,
            "avg_session_minutes": self.avg_session_minutes,
            "energy_level": self.energy_level.value,
            "current_cycle": self.current_cycle,
            "current_cycle_type": self.current_cycle_type.value,
            "expressed_intentions": [
                {k: v for k, v in i.items() if k != "resolved"}
                for i in self.expressed_intentions if not i.get("resolved")
            ],
            "active_session_id": self.active_session_id,
        }

    def to_yaml_persistable(self) -> str:
        """序列化为可写入 .omo/user_state.yaml 的 YAML"""
        import yaml
        return yaml.dump(self.to_dict(), allow_unicode=True, sort_keys=False)


@dataclass
class WritingSession:
    """
    创作会话。
    
    每次用户启动一个创作动作（写/改/规划）时创建一个会话。
    会话持续到用户切换焦点或显式中断。
    """

    id: str
    status: SessionStatus = SessionStatus.WARMING_UP
    phase: SessionPhase = SessionPhase.ASSESS
    focus: Optional[FocusTarget] = None
    cycle_type: CycleType = CycleType.EXPANSION
    cycle_number: int = 1

    # 时间
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    paused_at: Optional[datetime] = None

    # 工作空间（session 内加载的数据快照）
    loaded_unit_ids: List[str] = field(default_factory=list)
    active_queries: List[str] = field(default_factory=list)
    session_context: Dict[str, Any] = field(default_factory=dict)
    _query_cache: Dict[str, Any] = field(default_factory=dict)  # 查询缓存（session 内重复查询复用）

    # 动作时间线
    timeline: List[SessionAction] = field(default_factory=list)

    # 产出
    output_text: str = ""
    new_unit_ids: List[str] = field(default_factory=list)
    new_relation_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = f"ses_{uuid.uuid4().hex[:12]}"

    def start_action(self, action_type: str, target_type: str, target_id: str) -> SessionAction:
        action = SessionAction(
            action=action_type,
            target_type=target_type,
            target_id=target_id,
        )
        self.timeline.append(action)
        self.updated_at = datetime.now(timezone.utc)
        self.status = SessionStatus.DRAFTING
        return action

    def end_action(self, action: SessionAction, tokens: int = 0, notes: str = ""):
        action.ended_at = datetime.now(timezone.utc)
        action.tokens_generated = tokens
        action.notes = notes
        self.updated_at = datetime.now(timezone.utc)

    def pause(self):
        self.status = SessionStatus.PAUSING
        self.paused_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def resume(self):
        self.status = SessionStatus.DRAFTING
        self.paused_at = None
        self.updated_at = datetime.now(timezone.utc)

    def complete(self):
        self.status = SessionStatus.COMPLETED
        self.updated_at = datetime.now(timezone.utc)

    def total_duration_seconds(self) -> float:
        if self.timeline:
            first = self.timeline[0].started_at
            last = self.timeline[-1].ended_at or datetime.now(timezone.utc)
            return (last - first).total_seconds()
        return 0.0

    def total_tokens(self) -> int:
        return sum(a.tokens_generated for a in self.timeline)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "phase": self.phase.value,
            "focus": self.focus.to_dict() if self.focus else None,
            "cycle_type": self.cycle_type.value,
            "cycle_number": self.cycle_number,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "loaded_unit_ids": self.loaded_unit_ids,
            "timeline": [a.to_dict() for a in self.timeline],
            "total_tokens": self.total_tokens(),
            "duration_seconds": self.total_duration_seconds(),
            "new_unit_ids": self.new_unit_ids,
        }

    def to_json(self) -> dict:
        """序列化为可持久化的 dict（与 from_json 对称，供 .omo/session.json 快照）。"""
        return {
            "id": self.id,
            "status": self.status.value,
            "phase": self.phase.value,
            "focus": self.focus.to_dict() if self.focus else None,
            "cycle_type": self.cycle_type.value,
            "cycle_number": self.cycle_number,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "loaded_unit_ids": self.loaded_unit_ids,
            "timeline": [a.to_dict() for a in self.timeline],
            "output_text": self.output_text,
            "new_unit_ids": self.new_unit_ids,
            "new_relation_ids": self.new_relation_ids,
        }

    @classmethod
    def from_json(cls, data: dict) -> "WritingSession":
        """从 to_json() 的 dict 恢复会话对象（反序列化 .omo/session.json）。"""
        s = cls(id=data["id"])
        s.status = SessionStatus(data["status"])
        s.phase = SessionPhase(data["phase"])
        if data.get("focus"):
            f = data["focus"]
            s.focus = FocusTarget(
                type=UnitType[f["type"].upper()],
                unit_id=f["unit_id"],
                sub_target=f.get("sub_target"),
            )
        s.cycle_type = CycleType(data["cycle_type"])
        s.cycle_number = data.get("cycle_number", 1)
        s.created_at = datetime.fromisoformat(data["created_at"])
        s.updated_at = datetime.fromisoformat(data["updated_at"])
        if data.get("paused_at"):
            s.paused_at = datetime.fromisoformat(data["paused_at"])
        s.loaded_unit_ids = data.get("loaded_unit_ids", [])
        s.timeline = [
            SessionAction(
                **{
                    **a,
                    "started_at": datetime.fromisoformat(a["started_at"]),
                    "ended_at": datetime.fromisoformat(a["ended_at"]) if a.get("ended_at") else None,
                }
            )
            for a in data.get("timeline", [])
        ]
        s.output_text = data.get("output_text", "")
        s.new_unit_ids = data.get("new_unit_ids", [])
        s.new_relation_ids = data.get("new_relation_ids", [])
        return s


# ── 会话管理器 ────────────────────────────────────────────────────────────

class SessionManager:
    """
    创作会话管理器。
    
    管理用户状态和活跃会话，决策上下文加载策略。
    这是 V2 编排层的核心——取代现有 P 阶段路由。
    """

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.user_state = UserState()
        self.active_session: Optional[WritingSession] = None
        self._session_history: List[WritingSession] = []
        self._hooks: Dict[str, List[Callable]] = {
            "session_start": [],
            "session_end": [],
            "phase_change": [],
            "focus_change": [],
            "action_complete": [],
        }

    # ── 会话生命周期 ─────────────────────────────────────────────────────

    def start_session(
        self,
        focus_type: UnitType,
        focus_unit_id: str,
        cycle_type: CycleType = CycleType.EXPANSION,
        sub_target: Optional[str] = None,
    ) -> WritingSession:
        """开始一个新的创作会话"""
        self._save_current_session_if_active()

        session = WritingSession(
            id=f"ses_{uuid.uuid4().hex[:12]}",
            focus=FocusTarget(type=focus_type, unit_id=focus_unit_id, sub_target=sub_target),
            cycle_type=cycle_type,
            cycle_number=self.user_state.current_cycle,
        )
        self.active_session = session
        self.user_state.active_session_id = session.id
        self.user_state.focus = session.focus
        self.user_state.start_session()

        self._trigger_hooks("session_start", session)
        return session

    def end_session(self, notes: str = ""):
        """结束当前会话"""
        if not self.active_session:
            return
        self.active_session.complete()
        self._session_history.append(self.active_session)
        self.user_state.end_session()
        self.user_state.active_session_id = None
        self.user_state.current_cycle += 1

        self._trigger_hooks("session_end", self.active_session)
        self.active_session = None
        self._remove_session_snapshot()

    def pause_session(self):
        """暂停当前会话"""
        if self.active_session:
            self.active_session.pause()
            self._trigger_hooks("session_end", self.active_session)

    def resume_session(self) -> Optional[WritingSession]:
        """恢复上次暂停的会话"""
        if self.active_session and self.active_session.status == SessionStatus.PAUSING:
            self.active_session.resume()
            self.user_state.start_session()
            self._trigger_hooks("session_start", self.active_session)
            return self.active_session
        return None

    # ── 焦点管理 ─────────────────────────────────────────────────────────

    def shift_focus(self, new_type: UnitType, new_id: str, sub_target: Optional[str] = None):
        """
        切换焦点。
        
        如果当前有活跃会话，记录焦点切换（但保留会话）。
        这模拟了"写一章时突然想到要加个角色"的自然跳跃。
        """
        old_focus = self.user_state.focus
        self.user_state.focus = FocusTarget(type=new_type, unit_id=new_id, sub_target=sub_target)

        if self.active_session:
            self.active_session.focus = self.user_state.focus
            self.active_session.updated_at = datetime.now(timezone.utc)

        self._trigger_hooks("focus_change", {"old": old_focus, "new": self.user_state.focus})

    # ── 阶段和循环 ────────────────────────────────────────────────────────

    def set_phase(self, phase: SessionPhase):
        """设置当前会话的阶段"""
        if self.active_session:
            self.active_session.phase = phase
            self.active_session.updated_at = datetime.now(timezone.utc)
            self._trigger_hooks("phase_change", phase)

    def set_cycle_type(self, cycle_type: CycleType):
        """设置当前循环类型"""
        if self.active_session:
            self.active_session.cycle_type = cycle_type
        self.user_state.current_cycle_type = cycle_type

    # ── 动作记录 ─────────────────────────────────────────────────────────

    def record_action(self, action: SessionAction):
        """将会话中的一个动作记录到时间线"""
        if self.active_session:
            self.active_session.timeline.append(action)
            self.active_session.updated_at = datetime.now(timezone.utc)
            self._trigger_hooks("action_complete", action)

    # ── 意图管理 ─────────────────────────────────────────────────────────

    def express_intention(self, intention: str, context: str = ""):
        self.user_state.add_intention(intention, context)

    def resolve_intention(self, intention_text: str):
        self.user_state.resolve_intention(intention_text)

    # ── 上下文推荐（给编排层的信号） ──────────────────────────────────────

    def recommend_preheat_level(self) -> str:
        """
        根据当前用户状态和焦点类型，推荐数据预热级别。
        
        返回 "cold" | "warm" | "hot"
        
        优先级规则（由编排层 novel-writer.md 定义）：
        1. 有活跃会话 → 使用本方法的返回值
        2. 无活跃会话 → 使用路由表默认值
        """
        if not self.active_session:
            return "cold"

        focus_type = self.active_session.focus.type if self.active_session.focus else None

        # NOTE 类型：最小上下文，无需预热
        if focus_type == UnitType.NOTE:
            return "cold"

        # 修订循环（多轮迭代）→ 需要全量上下文
        if self.user_state.current_cycle > 1:
            return "hot"

        # 低精力 → 少加载数据，减轻认知负担
        if self.user_state.energy_level == EnergyLevel.LOW:
            return "cold"

        # 按 cycle_type 调整预热级别
        cycle_map = {
            CycleType.EXPANSION: "warm",
            CycleType.REFINEMENT: "hot",
            CycleType.PROOFING: "warm",
            CycleType.PLANNING: "warm",
            CycleType.IDEATION: "cold",
        }
        return cycle_map.get(self.active_session.cycle_type, "warm")

    # ── 钩子系统 ─────────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable):
        """注册事件钩子"""
        if event in self._hooks:
            self._hooks[event].append(callback)

    def _trigger_hooks(self, event: str, data: Any = None):
        for hook in self._hooks.get(event, []):
            try:
                hook(data)
            except Exception:
                pass

    # ── 持久化 ───────────────────────────────────────────────────────────

    def save_user_state(self):
        """将用户状态写入 .omo/user_state.yaml；活跃会话快照原子写入 .omo/session.json。

        修复半持久化不对称：写 7 字段 → 读 7 字段（focus/cycle_type/energy/
        intentions/active_session_id 全部可恢复，energy 重新推断）。
        session.json 采用临时文件 + rename 原子写，与 GraphStore 写 JSONL 同机制——
        多章并行写时串行排队，杜绝半写文件。
        """
        state_dir = self.project_root / ".omo"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "user_state.yaml"
        with open(state_path, "w", encoding="utf-8") as f:
            f.write(self.user_state.to_yaml_persistable())

        if self.active_session:
            self._write_session_snapshot()
        else:
            self._remove_session_snapshot()

    def load_user_state(self):
        """从 .omo/user_state.yaml 加载用户状态；从 .omo/session.json 恢复活跃会话。"""
        state_path = self.project_root / ".omo" / "user_state.yaml"
        if not state_path.exists():
            # YAML 缺失时仍尝试恢复会话快照（快照独立于用户状态）
            self._load_session_snapshot()
            return
        import yaml
        with open(state_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data:
            if data.get("recent_writing_days_last_7") is not None:
                self.user_state.recent_writing_days_last_7 = data["recent_writing_days_last_7"]
            if data.get("avg_session_minutes") is not None:
                self.user_state.avg_session_minutes = data["avg_session_minutes"]
            if data.get("current_cycle") is not None:
                self.user_state.current_cycle = data["current_cycle"]
            if data.get("current_cycle_type"):
                self.user_state.current_cycle_type = CycleType(data["current_cycle_type"])
            if data.get("expressed_intentions"):
                self.user_state.expressed_intentions = data["expressed_intentions"]
            if data.get("focus"):
                f = data["focus"]
                self.user_state.focus = FocusTarget(
                    type=UnitType[f["type"].upper()],
                    unit_id=f["unit_id"],
                    sub_target=f.get("sub_target"),
                )
            if data.get("active_session_id"):
                self.user_state.active_session_id = data["active_session_id"]
        # 恢复活跃会话（session.json 为准，覆盖 YAML 中的指针）
        self._load_session_snapshot()

    def _write_session_snapshot(self):
        """原子写入活跃会话快照到 .omo/session.json（临时文件 + rename）。"""
        state_dir = self.project_root / ".omo"
        state_dir.mkdir(parents=True, exist_ok=True)
        session_path = state_dir / "session.json"
        tmp = session_path.with_suffix(".json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.active_session.to_json(), f, ensure_ascii=False, indent=2)
            tmp.replace(session_path)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    def _remove_session_snapshot(self):
        """清理 .omo/session.json（会话结束/归档时）。"""
        session_path = self.project_root / ".omo" / "session.json"
        if session_path.exists():
            session_path.unlink(missing_ok=True)

    def _load_session_snapshot(self):
        """从 .omo/session.json 恢复活跃会话（跨调用持久化的关键）。

        快照损坏/字段缺失时降级为无会话并清理快照，不阻塞主流程。
        """
        session_path = self.project_root / ".omo" / "session.json"
        if not session_path.exists():
            return
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                sess_data = json.load(f)
            if sess_data.get("id"):
                self.active_session = WritingSession.from_json(sess_data)
                self.user_state.active_session_id = sess_data["id"]
                if self.active_session.focus:
                    self.user_state.focus = self.active_session.focus
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            self.active_session = None
            self._remove_session_snapshot()

    # ── 统计 ─────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        return {
            "active_session": self.active_session.to_dict() if self.active_session else None,
            "user_state": {
                "cycle": self.user_state.current_cycle,
                "cycle_type": self.user_state.current_cycle_type.value,
                "energy": self.user_state.energy_level.value,
                "unresolved_intentions": sum(
                    1 for i in self.user_state.expressed_intentions if not i.get("resolved")
                ),
            },
            "total_sessions": len(self._session_history),
            "avg_session_duration_minutes": (
                sum(s.total_duration_seconds() for s in self._session_history) / 60
                / max(len(self._session_history), 1)
            ),
        }

    def _save_current_session_if_active(self):
        """如果当前有活跃会话，先保存到历史"""
        if self.active_session and self.active_session.status not in (
            SessionStatus.COMPLETED, SessionStatus.ABANDONED
        ):
            self.active_session.complete()
            self._session_history.append(self.active_session)
        if self.active_session:
            # 旧会话归档后清理快照（新会话会重新写入）
            self._remove_session_snapshot()
