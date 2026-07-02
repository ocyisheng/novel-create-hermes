"""
V2 编排集成层。

展示 SessionManager + WorkspaceBuilder + GraphStore 如何协同工作，
替代传统 P 阶段路由的意图-焦点映射模式。

这个模块不是对 novel-writer.md 的直接替换，
而是"如果用了 V2 架构，编排逻辑应该长什么样"的示范。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import json
from typing import Dict, List, Optional, Any, Tuple

from graph_schema import (
    UnitType, UnitStatus, RelationType,
)
from graph_store import GraphStore as GraphStoreImpl
from session import SessionManager, SessionPhase, CycleType, SessionAction
from workspace import WorkspaceBuilder, Workspace
from query import (
    QueryHandlerRegistry, QueryRequest, QueryResult,
    parse_query, extract_all_queries, strip_queries, QueryType,
)


class UserIntent(str, Enum):
    """用户意图分类（取代传统阶段关键词匹配）"""
    WRITE_CHAPTER = "write_chapter"
    CREATE_CHARACTER = "create_character"
    DESIGN_WORLD = "design_world"
    PLAN_PLOT = "plan_plot"
    OUTLINE_VOLUME = "outline_volume"
    OUTLINE_CHAPTER = "outline_chapter"
    SYNOPSIS = "synopsis"
    IDEATION = "ideation"
    REVIEW_QUALITY = "review_quality"
    EDIT_CHAPTER = "edit_chapter"
    EDIT_ENTITY = "edit_entity"
    EXPORT = "export"
    SEARCH = "search"
    INSPIRATION = "inspiration"
    UNKNOWN = "unknown"


@dataclass
class OrchestrationDecision:
    """
    编排决策——SessionManager 根据用户意图和当前状态，
    决定"接下来做什么"。
    """
    action: str                          # start_session | continue_session | shift_focus | end_session
    focus_type: Optional[UnitType] = None
    focus_id: Optional[str] = None
    cycle_type: CycleType = CycleType.EXPANSION
    preheat_level: str = "warm"
    mode: str = "draft"                  # draft | polish | rewrite
    session_id: Optional[str] = None
    notes: str = ""


class V2Orchestrator:
    """
    V2 编排器。
    
    将用户输入 → 叙事单元网络中的焦点 → 工作空间 → 写作会话 串联起来。
    支持子 Agent 在写作过程中通过 QUERY 指令请求更多上下文。
    """

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.store = GraphStoreImpl(str(project_root))
        self.store.initialize()
        
        self.sessions = SessionManager(str(project_root))
        self.sessions.load_user_state()
        
        self.workspace = WorkspaceBuilder(self.store)
        
        # 查询层
        self.query_registry = QueryHandlerRegistry(self.store, str(project_root))
        self._query_history: List[Dict[str, Any]] = []

    # ── 用户输入解析 ────────────────────────────────────────────────────

    def parse_intent(self, user_input: str) -> UserIntent:
        """
        解析用户意图（简易版）。
        
        真实实现会用关键词匹配 + LLM 分类。
        这里做最小原型。
        """
        input_lower = user_input.lower()
        
        # 写作意图
        if any(w in input_lower for w in ["写第", "写章", "写一", "写下一", "chapter", "第"]):
            return UserIntent.WRITE_CHAPTER
        
        # 角色
        if any(w in input_lower for w in ["角色", "人物", "主角", "配角"]):
            return UserIntent.CREATE_CHARACTER
        
        # 世界观
        if any(w in input_lower for w in ["世界观", "设定", "力量体系", "势力"]):
            return UserIntent.DESIGN_WORLD
        
        # 情节
        if any(w in input_lower for w in ["情节", "主线", "支线", "伏笔"]):
            return UserIntent.PLAN_PLOT
        
        # 分卷
        if any(w in input_lower for w in ["分卷", "卷大"]):
            return UserIntent.OUTLINE_VOLUME
        
        # 分纲
        if any(w in input_lower for w in ["分纲", "章纲", "章节大纲"]):
            return UserIntent.OUTLINE_CHAPTER
        
        # 总纲
        if any(w in input_lower for w in ["总纲", "故事框架", "大纲"]):
            return UserIntent.SYNOPSIS
        
        # 创意
        if any(w in input_lower for w in ["创意", "构思", "脑洞", "灵感"]):
            return UserIntent.IDEATION
        
        # 质量
        if any(w in input_lower for w in ["质量", "检测", "ai味", "review"]):
            return UserIntent.REVIEW_QUALITY
        
        # 编辑
        if any(w in input_lower for w in ["改", "编辑", "润色", "修订"]):
            return UserIntent.EDIT_CHAPTER
        
        # 导出
        if any(w in input_lower for w in ["导出", "export", "epub", "pdf"]):
            return UserIntent.EXPORT
        
        # 搜索
        if any(w in input_lower for w in ["搜索", "查找", "查一"]):
            return UserIntent.SEARCH
        
        # 灵感
        if "灵感" in input_lower or "记个" in input_lower or "突然想到" in input_lower:
            return UserIntent.INSPIRATION
        
        return UserIntent.UNKNOWN

    # ── 决策引擎 ────────────────────────────────────────────────────────

    def decide(self, user_input: str) -> OrchestrationDecision:
        """
        根据用户输入和当前状态，决定编排动作。
        
        这是 V2 编排的核心——取代 P 阶段路由表。
        """
        intent = self.parse_intent(user_input)
        
        # 情况1：有活跃会话 → 继续在当前焦点上工作
        if self.sessions.active_session:
            return self._decide_with_active_session(intent, user_input)
        
        # 情况2：没有活跃会话 → 启动新会话
        return self._decide_new_session(intent, user_input)

    def _decide_with_active_session(
        self, intent: UserIntent, user_input: str
    ) -> OrchestrationDecision:
        """已有活跃会话时的决策"""
        session = self.sessions.active_session
        
        # 如果意图是切换焦点
        if intent in (UserIntent.CREATE_CHARACTER, UserIntent.DESIGN_WORLD,
                       UserIntent.PLAN_PLOT, UserIntent.INSPIRATION):
            # 在当前会话中切换焦点（不结束会话）
            # 这模拟了"写着写着突然想加个角色"的自然跳跃
            return OrchestrationDecision(
                action="shift_focus",
                cycle_type=session.cycle_type,
                preheat_level=self.sessions.recommend_preheat_level(),
                mode=self.sessions.recommend_mode(),
                session_id=session.id,
                notes=f"在现有会话中切换焦点到 {intent.value}",
            )
        
        # 如果意图是质量检测 → 进入 review 阶段
        if intent == UserIntent.REVIEW_QUALITY:
            self.sessions.set_phase(SessionPhase.REVIEW)
            return OrchestrationDecision(
                action="continue_session",
                preheat_level="hot",
                mode="polish",
                session_id=session.id,
            )
        
        # 继续当前会话
        return OrchestrationDecision(
            action="continue_session",
            preheat_level=self.sessions.recommend_preheat_level(),
            mode=self.sessions.recommend_mode(),
            session_id=session.id,
        )

    def _decide_new_session(self, intent: UserIntent, user_input: str) -> OrchestrationDecision:
        """无活跃会话时决定新的焦点"""
        # 提取目标标识（从用户输入中解析）
        target_name = self._extract_target_name(user_input, intent)
        
        # 在 graph 中查找或创建目标单元
        unit_id = self._resolve_focus_unit(intent, target_name, user_input)
        
        # 确定循环类型
        if intent in (UserIntent.IDEATION,):
            cycle_type = CycleType.IDEATION
        elif intent in (UserIntent.REVIEW_QUALITY,):
            cycle_type = CycleType.PROOFING
        elif intent in (UserIntent.CREATE_CHARACTER, UserIntent.DESIGN_WORLD,
                         UserIntent.PLAN_PLOT, UserIntent.SYNOPSIS):
            cycle_type = CycleType.PLANNING
        else:
            cycle_type = CycleType.EXPANSION
        
        # 确定预热级别
        mode = self.sessions.recommend_mode()
        preheat = self.sessions.recommend_preheat_level()
        
        return OrchestrationDecision(
            action="start_session",
            focus_type=unit_id[0] if isinstance(unit_id, tuple) else UnitType.SCENE,
            focus_id=unit_id[1] if isinstance(unit_id, tuple) else unit_id,
            cycle_type=cycle_type,
            preheat_level=preheat,
            mode=mode,
        )

    def _extract_target_name(self, user_input: str, intent: UserIntent) -> str:
        """从用户输入中提取目标名称"""
        import re
        
        # 提取章节号
        ch_match = re.search(r"第\s*(\d+)\s*章", user_input)
        if ch_match:
            return f"第{ch_match.group(1)}章"
        
        # 提取角色名（在"角色"或"人物"后面）
        char_match = re.search(r"(?:角色|人物)[：:\s]*(.+?)(?:$|，|。|的)", user_input)
        if char_match and intent == UserIntent.CREATE_CHARACTER:
            return char_match.group(1).strip()
        
        return ""

    def _resolve_focus_unit(
        self, intent: UserIntent, target_name: str, user_input: str
    ) -> tuple:
        """
        解析焦点叙事单元。
        
        返回 (UnitType, unit_id) 或 (UnitType, None) 表示需要新建。
        """
        # 查重
        if target_name:
            unit = self.store.get_unit_by_name(target_name)
            if unit:
                return (unit.type, unit.id)
        
        # 根据意图决定默认类型
        type_map = {
            UserIntent.WRITE_CHAPTER: UnitType.SCENE,
            UserIntent.CREATE_CHARACTER: UnitType.CHARACTER_ARC,
            UserIntent.DESIGN_WORLD: UnitType.WORLD_RULE,
            UserIntent.PLAN_PLOT: UnitType.PLOT_THREAD,
            UserIntent.OUTLINE_VOLUME: UnitType.SCENE,
            UserIntent.OUTLINE_CHAPTER: UnitType.SCENE,
            UserIntent.SYNOPSIS: UnitType.PLOT_THREAD,
            UserIntent.IDEATION: UnitType.NOTE,
            UserIntent.EDIT_CHAPTER: UnitType.CHUNK,
            UserIntent.INSPIRATION: UnitType.NOTE,
        }
        return (type_map.get(intent, UnitType.NOTE), None)

    # ── 会话执行 ────────────────────────────────────────────────────────

    def execute_decision(self, decision: OrchestrationDecision) -> Dict[str, Any]:
        """
        执行编排决策，返回工作空间 + 会话状态。
        
        这是编排层与子 Agent 之间的接口。
        """
        result = {"decision": decision.action, "session": None, "workspace": None}
        
        if decision.action == "start_session":
            focus_type = decision.focus_type or UnitType.NOTE
            focus_id = decision.focus_id or ""
            
            # 如果 focus_id 为空，创建新的叙事单元
            if not focus_id:
                new_unit = self.store.create_unit(
                    type=focus_type,
                    unit_name=self._generate_unit_name(focus_type),
                    actor="user",
                )
                focus_id = new_unit.id
            
            session = self.sessions.start_session(
                focus_type=focus_type,
                focus_unit_id=focus_id,
                cycle_type=decision.cycle_type,
            )
            
            # 构建工作空间
            ws = self.workspace.build(
                focus_unit_id=focus_id,
                preheat_level=decision.preheat_level,
            )
            
            result["session"] = session.to_dict()
            result["workspace"] = ws.to_dict()
            result["prompt_context"] = ws.to_prompt_block(decision.preheat_level)
            
            # 持久化
            self.store.flush()
            self.sessions.save_user_state()
        
        elif decision.action == "continue_session":
            session = self.sessions.active_session
            if session and session.focus:
                ws = self.workspace.build(
                    focus_unit_id=session.focus.unit_id,
                    preheat_level=decision.preheat_level,
                )
                result["session"] = session.to_dict()
                result["workspace"] = ws.to_dict()
                result["prompt_context"] = ws.to_prompt_block(decision.preheat_level)
        
        elif decision.action == "shift_focus":
            # 在现有会话中切换焦点
            self.sessions.shift_focus(
                new_type=UnitType.CHARACTER_ARC,  # 简化处理
                new_id="",
            )
            result["notes"] = decision.notes
        
        elif decision.action == "end_session":
            self.sessions.end_session()
            result["session"] = None
        
        return result

    def _generate_unit_name(self, unit_type: UnitType) -> str:
        """为新叙事单元生成临时名称"""
        import time
        timestamp = int(time.time()) % 10000
        names = {
            UnitType.SCENE: f"场景_{timestamp}",
            UnitType.CHARACTER_ARC: f"角色_{timestamp}",
            UnitType.WORLD_RULE: f"规则_{timestamp}",
            UnitType.PLOT_THREAD: f"情节线_{timestamp}",
            UnitType.NOTE: f"笔记_{timestamp}",
            UnitType.CHUNK: f"片段_{timestamp}",
        }
        return names.get(unit_type, f"单元_{timestamp}")

    # ── 查询层（QUERY 协议） ─────────────────────────────────────────────

    def process_subagent_response(self, response_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        处理子 Agent 的返回文本。
        
        1. 提取所有 QUERY 指令
        2. 逐个执行查询
        3. 将查询结果追加到 session 上下文
        4. 返回 (剥离了QUERY的正文, 查询记录)
        """
        queries = extract_all_queries(response_text)
        clean_text = strip_queries(response_text)
        query_records = []
        
        for query in queries:
            result = self.query_registry.handle(query)
            query_record = {
                "query": query.raw_text,
                "query_type": query.query_type.value,
                "params": query.params,
                "success": result.success,
                "summary": result.summary,
                "source_ids": result.source_ids,
            }
            
            if result.success:
                # 将结果注入到 session 上下文
                prompt_block = query.to_prompt_block(result)
                if self.sessions.active_session:
                    ctx_key = f"query_{query.query_type.value}_{len(self._query_history)}"
                    self.sessions.active_session.session_context[ctx_key] = {
                        "type": query.query_type.value,
                        "query": query.raw_text,
                        "result": prompt_block,
                        "summary": result.summary,
                    }
                    query_record["injected"] = True
                else:
                    query_record["injected"] = False
            else:
                query_record["error"] = result.error
            
            self._query_history.append(query_record)
            query_records.append(query_record)
        
        if query_records:
            self.store.flush()
        
        return clean_text, query_records

    def get_session_query_context(self) -> str:
        """获取当前 session 中累积的查询结果上下文"""
        if not self.sessions.active_session:
            return ""
        
        lines = []
        for key, ctx in self.sessions.active_session.session_context.items():
            if key.startswith("query_"):
                lines.append(ctx.get("result", ""))
        
        return "\n".join(lines)

    def get_query_stats(self) -> Dict[str, Any]:
        """查询统计"""
        type_counts = {}
        success_count = 0
        fail_count = 0
        for record in self._query_history:
            qt = record["query_type"]
            type_counts[qt] = type_counts.get(qt, 0) + 1
            if record.get("success"):
                success_count += 1
            else:
                fail_count += 1
        
        return {
            "total_queries": len(self._query_history),
            "by_type": type_counts,
            "success": success_count,
            "failed": fail_count,
        }

    def get_query_prompt_block(self, preheat_level: str = "warm") -> str:
        """
        生成注入到子 Agent prompt 中的 QUERY 服务说明。
        
        告知子 Agent 可以查询哪些类型的信息。
        """
        lines = []
        lines.append("### 上下文查询服务")
        lines.append("")
        lines.append("写作过程中如果缺少信息，可以在回复中包含 QUERY 指令，")
        lines.append("编排层会自动执行查询并将结果追加到上下文。")
        lines.append("")
        
        if self.sessions.active_session and self.sessions.active_session.session_context:
            ctx = self.sessions.active_session.session_context
            query_results = {k: v for k, v in ctx.items() if k.startswith("query_")}
            if query_results:
                lines.append("已加载的查询结果:")
                for k, v in query_results.items():
                    lines.append(f"  - {v.get('summary', '')}")
                lines.append("")
        
        lines.append("支持的查询类型:")
        lines.append('  - QUERY: character_background(name="林渊")        ← 角色完整背景')
        lines.append('  - QUERY: scene_detail(scene_id="sc_0015")       ← 场景细节')
        lines.append('  - QUERY: scene_detail(name="后山对决")           ← 按名称查场景')
        lines.append('  - QUERY: world_rule(name="灵气淬体")             ← 世界观规则')
        lines.append('  - QUERY: plot_thread_summary(name="主线")       ← 情节线摘要')
        lines.append('  - QUERY: plot_thread_summary()                   ← 所有情节线列表')
        lines.append('  - QUERY: foreshadowing_status(id="F001")        ← 伏笔状态')
        lines.append('  - QUERY: foreshadowing_status()                  ← 伏笔列表')
        lines.append('  - QUERY: style_check(text="待检查的文字")        ← 风格快速检查')
        lines.append('  - QUERY: advanced_search(keywords=["剑","灵气"], limit=5)  ← 搜索')
        lines.append('  - QUERY: recent_context(chapter=5, limit=3)     ← 最近场景')
        lines.append('  - QUERY: chapter_status(number=3)                ← 章节状态')
        lines.append('  - QUERY: chapter_status()                        ← 全局概况')
        lines.append("")
        lines.append(f"已在该 session 中成功执行 {len(self._query_history)} 次查询。")
        
        return "\n".join(lines)
