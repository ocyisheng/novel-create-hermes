"""
查询层：子 Agent → 编排层的 QUERY 协议。

子 Agent 在写作过程中，如果发现缺少信息，可以通过 QUERY 指令
向编排层请求更多上下文。编排层拦截 QUERY，从 graph 查询，
将结果追加到 session 上下文。

协议格式：
    QUERY: query_type(param1="value1", param2="value2")
    
示例：
    QUERY: character_background(name="林渊")
    QUERY: scene_detail(scene_id="sc_0015")
    QUERY: world_rule(name="灵气淬体")
    QUERY: foreshadowing_status(id="F001")
    QUERY: plot_thread_summary(name="主线")
    QUERY: style_check(text="一段需要检查的文字")
    QUERY: advanced_search(keywords=["剑", "灵气"], limit=5)
"""

from __future__ import annotations

import re
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Pattern
from collections import defaultdict

from graph_schema import UnitType, UnitStatus, RelationType
from graph_store import GraphStore as GraphStoreImpl
from render_utils import summarize_content


# ── 查询类型 ──────────────────────────────────────────────────────────────

class QueryType(str, Enum):
    """子 Agent 可发出的查询类型"""
    CHARACTER_BACKGROUND = "character_background"
    SCENE_DETAIL = "scene_detail"
    WORLD_RULE = "world_rule"
    FORESHADOWING_STATUS = "foreshadowing_status"
    PLOT_THREAD_SUMMARY = "plot_thread_summary"
    STYLE_CHECK = "style_check"
    ADVANCED_SEARCH = "advanced_search"
    RECENT_CONTEXT = "recent_context"
    CHAPTER_STATUS = "chapter_status"


# ── 协议 ──────────────────────────────────────────────────────────────────

@dataclass
class QueryRequest:
    """从子 Agent 输出中解析出的查询请求"""
    query_type: QueryType
    params: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    def to_prompt_block(self, result: "QueryResult") -> str:
        """将查询结果渲染为 prompt 块（注入到 session 上下文）"""
        lines = []
        lines.append(f"[QUERY RESULT: {self.query_type.value}]")
        lines.append(f"  Request: {self.raw_text}")
        if result.error:
            lines.append(f"  Error: {result.error}")
        elif result.summary:
            lines.append(f"  {result.summary}")
        if result.content:
            lines.append("")
            lines.append(result.content)
        lines.append("")
        return "\n".join(lines)


@dataclass
class QueryResult:
    """查询结果"""
    success: bool = True
    error: str = ""
    summary: str = ""
    content: str = ""
    data: Optional[Dict[str, Any]] = None
    source_ids: List[str] = field(default_factory=list)  # 来源叙事单元 ID


# ── QUERY 解析器 ──────────────────────────────────────────────────────────

# QUERY 正则: QUERY: type(param1="val1", param2=val2)
QUERY_PATTERN: Pattern = re.compile(
    r"QUERY:\s*(\w+)"                           # type
    r"(?:\(([^)]*)\))?"                          # optional params
)

PARAM_PATTERN: Pattern = re.compile(
    r"""(\w+)\s*=\s*"([^"]*)"                    # key="value"
        |(\w+)\s*=\s*(\d+(?:\.\d+)?)             # key=number
        |(\w+)\s*=\s*\[([^\]]*)\]                # key=[list]""",
    re.VERBOSE,
)


def parse_query(text: str) -> Optional[QueryRequest]:
    """
    从文本中解析 QUERY 指令。
    
    如果文本中包含多个 QUERY，只返回第一个。
    返回 None 表示没有有效的 QUERY。
    """
    match = QUERY_PATTERN.search(text)
    if not match:
        return None
    
    type_name = match.group(1)
    params_str = match.group(2)
    
    try:
        query_type = QueryType(type_name)
    except ValueError:
        return None
    
    params = {}
    if params_str:
        for pm in PARAM_PATTERN.finditer(params_str):
            key = pm.group(1) or pm.group(3) or pm.group(5)
            value = pm.group(2) or pm.group(4) or pm.group(6)
            if value is not None:
                # 列表参数
                if pm.group(6) is not None:
                    params[key] = [v.strip().strip('"') for v in value.split(",")]
                # 数字参数
                elif pm.group(4) is not None:
                    params[key] = float(value) if "." in value else int(value)
                # 字符串参数
                else:
                    params[key] = value
    
    return QueryRequest(
        query_type=query_type,
        params=params,
        raw_text=match.group(0),
    )


def extract_all_queries(text: str) -> List[QueryRequest]:
    """从文本中提取所有 QUERY 指令"""
    queries = []
    for match in QUERY_PATTERN.finditer(text):
        parsed = parse_query(match.group(0))
        if parsed:
            queries.append(parsed)
    return queries


def strip_queries(text: str) -> str:
    """从文本中移除 QUERY 指令（只保留正文）"""
    return QUERY_PATTERN.sub("", text).strip()


# ── 查询处理器 ────────────────────────────────────────────────────────────

QueryHandler = Callable[[QueryRequest, GraphStoreImpl, str], QueryResult]


class QueryHandlerRegistry:
    """
    查询处理器注册表。
    
    每种 QueryType 对应一个处理函数。
    处理函数接收 QueryRequest + GraphStore + project_root，
    返回 QueryResult。
    """

    def __init__(self, store: GraphStoreImpl, project_root: str):
        self.store = store
        self.project_root = project_root
        self._handlers: Dict[QueryType, QueryHandler] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._register_defaults()

    def register(self, query_type: QueryType, handler: QueryHandler):
        """注册自定义处理器"""
        self._handlers[query_type] = handler

    def handle(self, request: QueryRequest, session=None) -> QueryResult:
        """执行查询（支持 session 级缓存）"""
        # 生成缓存键
        import json as _json
        cache_key = f"{request.query_type.value}:{_json.dumps(request.params, sort_keys=True, ensure_ascii=False)}"
        
        # session 缓存命中
        if session and hasattr(session, '_query_cache') and cache_key in session._query_cache:
            self._cache_hits += 1
            return session._query_cache[cache_key]
        
        self._cache_misses += 1
        handler = self._handlers.get(request.query_type)
        if not handler:
            return QueryResult(
                success=False,
                error=f"未注册的查询类型: {request.query_type.value}",
            )
        try:
            result = handler(request, self.store, self.project_root)
            # 写入 session 缓存
            if session and hasattr(session, '_query_cache'):
                session._query_cache[cache_key] = result
            return result
        except Exception as e:
            return QueryResult(
                success=False,
                error=f"查询执行失败: {e}",
            )

    def cache_stats(self) -> dict:
        return {"hits": self._cache_hits, "misses": self._cache_misses}

    def _register_defaults(self):
        """注册默认处理器"""
        self._handlers = {
            QueryType.CHARACTER_BACKGROUND: _handle_character_background,
            QueryType.SCENE_DETAIL: _handle_scene_detail,
            QueryType.WORLD_RULE: _handle_world_rule,
            QueryType.FORESHADOWING_STATUS: _handle_foreshadowing_status,
            QueryType.PLOT_THREAD_SUMMARY: _handle_plot_thread_summary,
            QueryType.STYLE_CHECK: _handle_style_check,
            QueryType.ADVANCED_SEARCH: _handle_advanced_search,
            QueryType.RECENT_CONTEXT: _handle_recent_context,
            QueryType.CHAPTER_STATUS: _handle_chapter_status,
        }


# ── 各查询类型的实现 ─────────────────────────────────────────────────────

def _handle_character_background(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """查询角色完整背景"""
    name = req.params.get("name", "")
    if not name:
        return QueryResult(success=False, error="缺少参数: name")
    
    unit = store.get_unit_by_name(name)
    if not unit:
        return QueryResult(success=False, error=f"角色不存在: {name}")
    
    # 获取关联场景
    related_scenes = []
    for rel in store.get_relations(unit.id, direction="incoming"):
        source = store.get_unit(rel.source_id)
        if source and source.type == UnitType.SCENE:
            related_scenes.append(f"  - {source.unit_name} (ch.{source.belongs_to_chapter})")
    
    # 获取关联情节线
    related_plots = []
    for rel in store.get_relations(unit.id, direction="outgoing"):
        target = store.get_unit(rel.target_id)
        if target and target.type == UnitType.PLOT_THREAD:
            related_plots.append(f"  - {target.unit_name}")
    
    parts = [f"角色档案: {name}"]
    parts.append(f"状态: {unit.status.value}")
    parts.append(f"确信度: {unit.confidence:.1f}")
    if unit.tags:
        parts.append(f"标签: {', '.join(unit.tags)}")
    if unit.content:
        try:
            content_dict = json.loads(unit.content) if isinstance(unit.content, str) else unit.content
            if isinstance(content_dict, dict):
                preview = summarize_content(content_dict)
            else:
                preview = str(content_dict)[:300]
        except (json.JSONDecodeError, ValueError):
            preview = unit.content[:300]
        parts.append(f"内容:\n{preview}")
    if related_scenes:
        parts.append("出场章节:")
        parts.extend(related_scenes)
    if related_plots:
        parts.append("关联情节线:")
        parts.extend(related_plots)
    
    return QueryResult(
        summary=f"角色『{name}』: {unit.status.value}, 关联 {len(related_scenes)} 个场景, {len(related_plots)} 条情节线",
        content="\n".join(parts),
        source_ids=[unit.id],
    )


def _handle_scene_detail(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """查询场景细节"""
    scene_id = req.params.get("scene_id", "")
    name = req.params.get("name", "")
    
    unit = None
    if scene_id:
        unit = store.get_unit(scene_id)
    elif name:
        unit = store.get_unit_by_name(name)
    
    if not unit:
        return QueryResult(success=False, error=f"场景不存在: {scene_id or name}")
    if unit.type != UnitType.SCENE:
        return QueryResult(success=False, error=f"不是场景类型: {unit.type.value}")
    
    # 获取关联信息
    neighbors_1 = store.get_neighbors(unit.id, max_depth=1).get(1, set())
    neighbor_names = []
    for nid in neighbors_1:
        n = store.get_unit(nid)
        if n:
            neighbor_names.append(f"{n.unit_name} ({n.type.value})")
    
    parts = [f"场景: {unit.unit_name}"]
    if unit.belongs_to_chapter:
        parts.append(f"章节: 第{unit.belongs_to_chapter}章")
    parts.append(f"状态: {unit.status.value}")
    if unit.content:
        try:
            content_dict = json.loads(unit.content) if isinstance(unit.content, str) else unit.content
            if isinstance(content_dict, dict):
                preview = summarize_content(content_dict)
            else:
                preview = str(content_dict)[:300]
        except (json.JSONDecodeError, ValueError):
            preview = unit.content[:300]
        parts.append(f"内容:\n{preview}")
    if neighbor_names:
        parts.append(f"关联: {', '.join(neighbor_names)}")
    
    return QueryResult(
        summary=f"场景『{unit.unit_name}』: 第{unit.belongs_to_chapter or '?'}章, {len(neighbors_1)} 个关联",
        content="\n".join(parts),
        source_ids=[unit.id],
    )


def _handle_world_rule(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """查询世界观规则"""
    name = req.params.get("name", "")
    if not name:
        return QueryResult(success=False, error="缺少参数: name")
    
    unit = store.get_unit_by_name(name)
    if not unit:
        return QueryResult(success=False, error=f"未找到世界观规则: {name}")
    
    parts = [f"世界观规则: {unit.unit_name}"]
    parts.append(f"状态: {unit.status.value}")
    if unit.content:
        try:
            content_dict = json.loads(unit.content) if isinstance(unit.content, str) else unit.content
            if isinstance(content_dict, dict):
                preview = summarize_content(content_dict)
            else:
                preview = str(content_dict)[:300]
        except (json.JSONDecodeError, ValueError):
            preview = unit.content[:300]
        parts.append(f"内容:\n{preview}")
    
    return QueryResult(
        summary=f"世界观规则: {unit.unit_name}",
        content="\n".join(parts),
        source_ids=[unit.id],
    )


def _handle_foreshadowing_status(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """查询伏笔状态"""
    fb_id = req.params.get("id", "")
    if fb_id:
        # 查特定伏笔（NOTE 类型，名称含伏笔编号）
        all_notes = store.find_units(type=UnitType.NOTE)
        for note in all_notes:
            if fb_id in note.unit_name or "伏笔" in note.unit_name:
                return QueryResult(
                    summary=f"伏笔: {note.unit_name}",
                    content=note.content[:500] if note.content else "（空）",
                    source_ids=[note.id],
                )
        return QueryResult(success=False, error=f"伏笔不存在: {fb_id}")
    
    # 列出所有未归档的伏笔笔记
    all_notes = store.find_units(type=UnitType.NOTE)
    foreshadowings = [n for n in all_notes if "伏笔" in n.tags or "foreshadow" in n.unit_name.lower()]
    
    if not foreshadowings:
        return QueryResult(summary="当前没有伏笔记录", content="（无）")
    
    parts = [f"伏笔列表 ({len(foreshadowings)} 条):"]
    for fb in foreshadowings:
        parts.append(f"  - {fb.unit_name} [{fb.status.value}]")
    
    return QueryResult(
        summary=f"共 {len(foreshadowings)} 条伏笔",
        content="\n".join(parts),
        source_ids=[n.id for n in foreshadowings],
    )


def _handle_plot_thread_summary(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """查询情节线摘要"""
    name = req.params.get("name", "")
    
    if name:
        unit = store.get_unit_by_name(name)
        if not unit:
            return QueryResult(success=False, error=f"情节线不存在: {name}")
        
        # 找到关联场景
        related = []
        for rel in store.get_relations(unit.id, direction="incoming"):
            source = store.get_unit(rel.source_id)
            if source and source.type == UnitType.SCENE:
                related.append(source)
        
        parts = [f"情节线: {unit.unit_name}"]
        parts.append(f"状态: {unit.status.value}")
        if unit.content:
            try:
                content_dict = json.loads(unit.content) if isinstance(unit.content, str) else unit.content
                if isinstance(content_dict, dict):
                    preview = summarize_content(content_dict)
                else:
                    preview = str(content_dict)[:300]
            except (json.JSONDecodeError, ValueError):
                preview = unit.content[:300]
            parts.append(f"摘要: {preview}")
        if related:
            parts.append(f"关联场景 ({len(related)}):")
            for r in sorted(related, key=lambda x: x.belongs_to_chapter or 0):
                parts.append(f"  - 第{r.belongs_to_chapter or '?'}章: {r.unit_name}")
        
        return QueryResult(
            summary=f"情节线『{name}』: {unit.status.value}, {len(related)} 个场景",
            content="\n".join(parts),
            source_ids=[unit.id],
        )
    
    # 列出所有情节线
    plots = store.find_units(type=UnitType.PLOT_THREAD)
    if not plots:
        return QueryResult(summary="当前没有情节线", content="（无）")
    
    parts = [f"情节线列表 ({len(plots)} 条):"]
    for p in plots:
        # 找到关联场景数
        rels = store.get_relations(p.id, direction="incoming")
        scene_count = len([r for r in rels if store.get_unit(r.source_id) 
                          and store.get_unit(r.source_id).type == UnitType.SCENE])
        parts.append(f"  - {p.unit_name} [{p.status.value}] ({scene_count} 场景)")
    
    return QueryResult(
        summary=f"共 {len(plots)} 条情节线",
        content="\n".join(parts),
        source_ids=[p.id for p in plots],
    )


def _handle_style_check(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """
    风格一致性快速检查。
    
    简易实现：检查文本中是否包含常见的 AI 语言尸体。
    完整实现应加载活跃风格文件进行 7 维度对比。
    """
    text = req.params.get("text", "")
    if not text:
        return QueryResult(success=False, error="缺少参数: text")
    
    # 语言尸体关键词（权威列表见 skills/novel-quality/references/cliches.md）
    CLICHES = [
        "暮色从四面八方", "空气仿佛凝固", "时间仿佛停止",
        "一股莫名的", "不知为何", "心中涌起一股",
        "眼神中闪过一丝", "嘴角露出一抹", "深吸一口气",
        "整个世界都", "命运的车轮",
    ]
    
    findings = []
    for cliche in CLICHES:
        if cliche in text:
            findings.append(f"  ⚠️ 检测到语言尸体: 「{cliche}」")
    
    if not findings:
        return QueryResult(
            summary="✅ 风格快速检查通过",
            content="未检测到明显语言尸体。",
        )
    
    return QueryResult(
        summary=f"⚠️ 检测到 {len(findings)} 处可能的语言尸体",
        content="风格快速检查发现以下问题:\n" + "\n".join(findings),
    )


def _handle_advanced_search(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """高级搜索：按关键词、类型、章节搜索叙事单元"""
    keywords = req.params.get("keywords", [])
    unit_type = req.params.get("type", "")
    chapter = req.params.get("chapter", 0)
    limit = req.params.get("limit", 10)
    
    if isinstance(keywords, str):
        keywords = [keywords]
    if isinstance(limit, str):
        limit = int(limit)
    if isinstance(chapter, str):
        chapter = int(chapter)
    
    results = []
    for unit in store._units.values():
        if unit.status == UnitStatus.ARCHIVED:
            continue
        if unit_type and unit.type.value != unit_type:
            continue
        if chapter and unit.belongs_to_chapter != chapter:
            continue
        
        score = 0
        for kw in keywords:
            if kw.lower() in unit.unit_name.lower():
                score += 3
            if kw.lower() in unit.content.lower():
                score += 2
            if kw.lower() in str(unit.tags).lower():
                score += 1
        
        if score > 0:
            results.append((score, unit))
    
    results.sort(key=lambda x: -x[0])
    results = results[:int(limit)]
    
    if not results:
        return QueryResult(summary="未找到匹配结果", content="（无）")
    
    parts = [f"搜索结果 ({len(results)} 条):"]
    for score, unit in results:
        ch = f"ch.{unit.belongs_to_chapter}" if unit.belongs_to_chapter else "?"
        preview = unit.unit_name[:50]
        parts.append(f"  [{score}pts] [{unit.type.value}] {preview} ({ch})")
    
    return QueryResult(
        summary=f"找到 {len(results)} 条相关结果",
        content="\n".join(parts),
        source_ids=[u.id for _, u in results],
    )


def _handle_recent_context(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """最近上下文查询"""
    chapter = req.params.get("chapter", 0)
    limit = req.params.get("limit", 5)
    if isinstance(limit, str):
        limit = int(limit)
    if isinstance(chapter, str):
        chapter = int(chapter)
    
    if chapter:
        scenes = store.find_units(type=UnitType.SCENE, chapter=chapter)
    else:
        all_scenes = store.find_units(type=UnitType.SCENE)
        all_scenes.sort(key=lambda u: (u.belongs_to_chapter or 0, u.created_at))
        scenes = all_scenes[-int(limit):]
    
    if not scenes:
        return QueryResult(summary="没有找到场景", content="（无）")
    
    parts = [f"最近场景 ({len(scenes)}):"]
    for s in scenes:
        chars = []
        for rel in store.get_relations(s.id, direction="incoming"):
            source = store.get_unit(rel.source_id)
            if source and source.type == UnitType.CHARACTER_ARC:
                chars.append(source.unit_name)
        char_info = f" [角色: {', '.join(chars[:3])}]" if chars else ""
        parts.append(f"  - 第{s.belongs_to_chapter or '?'}章: {s.unit_name}{char_info}")
    
    return QueryResult(
        summary=f"最近 {len(scenes)} 个场景",
        content="\n".join(parts),
        source_ids=[s.id for s in scenes],
    )


def _handle_chapter_status(
    req: QueryRequest, store: GraphStoreImpl, project_root: str
) -> QueryResult:
    """查询章节状态"""
    chapter = req.params.get("number", 0)
    if isinstance(chapter, str):
        chapter = int(chapter) if chapter else 0
    
    scenes = store.find_units(type=UnitType.SCENE, chapter=chapter) if chapter else []
    chunks = store.find_units(type=UnitType.CHUNK, chapter=chapter) if chapter else []
    characters_in_chapter = set()
    
    for s in scenes:
        for rel in store.get_relations(s.id, direction="incoming"):
            source = store.get_unit(rel.source_id)
            if source and source.type == UnitType.CHARACTER_ARC:
                characters_in_chapter.add(source.unit_name)
    
    parts = []
    if chapter:
        parts.append(f"第{chapter}章 状态:")
        parts.append(f"  场景数: {len(scenes)}")
        parts.append(f"  正文片段: {len(chunks)}")
        parts.append(f"  涉及角色: {', '.join(sorted(characters_in_chapter)) if characters_in_chapter else '无'}")
    else:
        # 全局章节概况
        all_scenes = store.find_units(type=UnitType.SCENE)
        chapters = defaultdict(list)
        for s in all_scenes:
            ch = s.belongs_to_chapter or 0
            chapters[ch].append(s)
        
        parts.append(f"全局概况 ({len(chapters)} 章有内容):")
        for ch in sorted(chapters.keys()):
            parts.append(f"  第{ch}章: {len(chapters[ch])} 个场景")
    
    return QueryResult(
        summary=f"章节状态: {chapter if chapter else '全局'}",
        content="\n".join(parts),
    )
