"""
SearchEngine — V2 纯机械搜索引擎。

定位：Tool 层的纯数据检索工具，不做任何语义理解或 LLM 推理。
职责边界：
  ✅ search(keyword="隐忍") → 返回 content 中包含"隐忍"的所有单元
  ✅ get_modified_units(version) → 返回版本号大于指定值的单元
  ❌ "这些内容中哪些是角色描述、哪些是对话"
  ❌ "判断隐忍这个特质和林昭的角色设定是否一致"

SearchEngine 是对 LLM 提问"数据在哪里"的回答，不是对"这意味着什么"的回答。

与 VizIncrementalEngine 共享增量检测模式：
  增量分析使用 unit.version 对比（graph_store.py:357 version 自增），
  不依赖 events.olog（按操作数增长，无 consumer cursor）。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

from graph_schema import NarrativeUnit, UnitType, UnitStatus, RelationType, get_unit_chapter
from graph_store import GraphStore
from time_utils import get_story_ordinal, ORDINAL_BASE

# CheckResult 的规范定义在 quality_checkers.types（超集，含 source/check_layer）。
# 此处 re-export 以保持向后兼容：from search_engine import CheckResult
from quality_checkers.types import CheckResult

# R1-R6+R9 规范实现：委托给 MechanicalChecker（单一权威）
from quality_checkers.mechanical import MechanicalChecker
from quality_checkers.types import CheckResult


# ── 数据类 ──────────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    """单个搜索结果"""
    unit_id: str
    unit_name: str
    unit_type: UnitType
    content_preview: str           # 匹配上下文摘录
    content_length: int
    chapter: Optional[int]
    volume: Optional[int]
    score: float
    tags: List[str]
    status: UnitStatus
    version: int
    neighbors: List[str] = field(default_factory=list)  # 关联单元名（供 LLM 后续分析）
    created_at: Optional[str] = None   # 单元创建时间（UTC ISO）
    updated_at: Optional[str] = None   # 单元最后修改时间（UTC ISO）


@dataclass
class SearchResultSet:
    """搜索结果集"""
    query: str
    total: int
    results: List[SearchResult]
    time_ms: float


# ── 搜索引擎 ────────────────────────────────────────────────────────────────


class SearchEngine:
    """
    V2 搜索引擎。纯数据检索，不做 LLM 推理。
    
    接收一个已初始化的 GraphStore 实例（store.initialize() 已调用）。
    """

    # NOTE: R1-R6, R9 实现已委托给 MechanicalChecker（单一权威）。
    # 仅 R7/R10-R12 保留在本文件（search_engine 独有）。
    # Do not add new duplicate rules here.
    # ── 一致性检查规则注册表 ─────────────────────────────────────────────
    # 格式: (rule_id: str, severity: str, method_name: str)
    # 新增规则只需在列表中追加，无需修改 check_consistency() 方法体。
    _CHECKERS: List[Tuple[str, str, str]] = [
        ("R1", "error",   "_check_archived_characters_in_scenes"),
        ("R3", "info",    "_check_orphan_units"),
        ("R4", "warning", "_check_archived_with_active_relations"),
        ("R5", "warning", "_check_chunk_missing_file"),
        ("R6", "info",    "_check_chunk_no_chapter"),
        ("R7", "warning", "_check_location_changes"),          # 位置变化标记 → LLM 判断瞬移
        ("R9", "error",   "_check_precedes_ordinal_conflicts"), # PRECEDES vs ordinal 纯结构冲突
        ("R10", "warning", "_check_pacing_monotony"),           # 节奏单调：同类型场景连续出现
        ("R11", "warning", "_check_density_deviation"),         # 密度偏离：CHUNK 字数超出密度预算
        ("R12", "warning", "_check_protagonist_agency"),        # 主角能动性：主角连续被动场景
    ]

    def __init__(self, store: GraphStore):
        self.store = store
        # 倒排索引：token → unit_id set
        self._name_index: Dict[str, Set[str]] = {}
        self._content_index: Dict[str, Set[str]] = {}
        self._tags_index: Dict[str, Set[str]] = {}
        self._index_built = False

    # ── 倒排索引分词与构建 ────────────────────────────────────────────────

    # 中文停用词（高频无意义字符）
    _STOP_WORDS: Set[str] = frozenset({
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
        "它", "们", "那", "这个", "那个", "什么", "怎么", "但", "而",
        "又", "或", "如果", "因为", "所以", "虽然", "但是", "可以",
        "被", "把", "让", "从", "对", "向", "与", "及", "等", "之",
    })

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """
        分词：中文按字符拆分 + 英文按空格拆分，去除停用词。
        
        不引入外部依赖（如 jieba），采用简单拆分策略。
        """
        if not text:
            return []
        
        tokens: List[str] = []
        current_english: List[str] = []
        
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                # 中文字符：先输出累积的英文 token，再输出中文字符
                if current_english:
                    word = "".join(current_english).lower()
                    if word and word not in cls._STOP_WORDS:
                        tokens.append(word)
                    current_english = []
                if char not in cls._STOP_WORDS:
                    tokens.append(char)
            elif char.isalnum():
                # 英文/数字字符：累积
                current_english.append(char)
            else:
                # 标点/空格等：输出累积的英文 token
                if current_english:
                    word = "".join(current_english).lower()
                    if word and word not in cls._STOP_WORDS:
                        tokens.append(word)
                    current_english = []
        
        # 输出最后累积的英文 token
        if current_english:
            word = "".join(current_english).lower()
            if word and word not in cls._STOP_WORDS:
                tokens.append(word)
        
        return tokens

    def _build_index(self) -> None:
        """
        构建 name/content/tags 的倒排索引。
        
        首次搜索时调用，后续复用索引。
        """
        self._name_index.clear()
        self._content_index.clear()
        self._tags_index.clear()
        
        for unit_id, unit in self.store._units.items():
            # 索引 name
            name_raw = unit.unit_name
            name_str = name_raw if isinstance(name_raw, str) else (
                json.dumps(name_raw, ensure_ascii=False) if name_raw else ""
            )
            for token in self._tokenize(name_str):
                self._name_index.setdefault(token, set()).add(unit_id)
            
            # 索引 content
            content_raw = unit.content
            content_str = content_raw if isinstance(content_raw, str) else (
                json.dumps(content_raw, ensure_ascii=False) if content_raw else ""
            )
            for token in self._tokenize(content_str):
                self._content_index.setdefault(token, set()).add(unit_id)
            
            # 索引 tags
            tags_str = " ".join(unit.tags) if unit.tags else ""
            for token in self._tokenize(tags_str):
                self._tags_index.setdefault(token, set()).add(unit_id)
        
        self._index_built = True

    # ── 统一搜索入口 ─────────────────────────────────────────────────────

    def search(
        self,
        keyword: str = "",
        pattern: str = "",
        name: str = "",
        *,
        scope: Optional[List[UnitType]] = None,
        regex: bool = False,
        case_sensitive: bool = False,
        max_results: int = 50,
        context_lines: int = 3,
        status: Optional[str] = None,     # "archived"/"mature"/"sprout"/"growing"/"frozen"/"" = default exclude archived
        chapter: Optional[int] = None,    # filter by chapter_number
        tags: Optional[List[str]] = None, # filter: ALL tags must match (AND semantics)
    ) -> SearchResultSet:
        """
        统一搜索入口。三种模式互斥：keyword > pattern > name。
        
        keyword:  遍历 _units，匹配 name/content/tags（子串匹配）
        pattern:  re.search 遍历 content（正则）
        name:     通过单元名称或 ID 查找单元 + 获取邻居
        
        过滤条件：
          scope: 只搜索指定类型的单元
          case_sensitive: 是否区分大小写（仅 keyword 模式）
          regex: 是否使用正则（仅 pattern 模式）
          status: 单元状态过滤，None/空字符串=排除 ARCHIVED（默认行为），指定值=精确匹配
          chapter: 章节号过滤，只包含 chapter_number 等于该值的单元
          tags: 标签过滤（AND 语义），只包含同时拥有所有指定标签的单元
        """
        import time
        t0 = time.time()

        if name:
            results = self._entity_search(name, scope, status, chapter, tags)
        elif pattern:
            results = self._regex_search(pattern, scope, case_sensitive, status, chapter, tags)
        elif keyword:
            results = self._keyword_search(keyword, scope, case_sensitive, status, chapter, tags)
        else:
            results = []

        total_matches = len(results)
        results = results[:max_results]

        t1 = time.time()
        
        # 补充邻居信息
        for r in results:
            r.neighbors = self._get_neighbor_names(r.unit_id)

        return SearchResultSet(
            query=keyword or pattern or name,
            total=total_matches,
            results=results,
            time_ms=round((t1 - t0) * 1000, 1),
        )

    # ── 增量分析支持 ─────────────────────────────────────────────────────

    def get_modified_units(self, since_version: int) -> List[NarrativeUnit]:
        """
        获取 version > since_version 的变更单元（用于增量分析）。
        
        委托给 GraphStore.get_modified_units()。
        保持向后兼容。
        """
        return self.store.get_modified_units(since_version)

    # ── 一致性检查 ───────────────────────────────────────────────────────

    def check_consistency(self) -> List[CheckResult]:
        """
        运行一致性检查，返回检查结果列表。
        
        遍历 _CHECKERS 注册表调用所有已注册规则。
        输出的是供 LLM 分析的原始数据——LLM 需要判断
        "这是矛盾还是有意设计"。
        
        新增规则：在类级 _CHECKERS 列表中追加即可，无需修改此方法。
        """
        results: List[CheckResult] = []
        
        for rule_id, severity, method_name in self._CHECKERS:
            method = getattr(self, method_name)
            r = method()
            if isinstance(r, list):
                results.extend(r)
            else:
                results.append(r)
        
        return results

    # ── 内部搜索实现 ─────────────────────────────────────────────────────

    def _keyword_search(
        self,
        keyword: str,
        scope: Optional[List[UnitType]],
        case_sensitive: bool,
        status: Optional[str] = None,
        chapter: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        # 确保倒排索引已构建
        if not self._index_built:
            self._build_index()
        
        results: List[SearchResult] = []
        kw = keyword if case_sensitive else keyword.lower()

        # 通过倒排索引获取候选 unit_id 集合
        candidate_ids: Optional[Set[str]] = None
        
        # 分词 keyword 用于索引查找
        kw_tokens = self._tokenize(keyword) if not case_sensitive else self._tokenize(keyword.lower())
        
        # 从 name_index、content_index 和 tags_index 获取候选
        for token in kw_tokens:
            name_matches = self._name_index.get(token, set())
            content_matches = self._content_index.get(token, set())
            tags_matches = self._tags_index.get(token, set())
            token_candidates = name_matches | content_matches | tags_matches
            
            if candidate_ids is None:
                candidate_ids = token_candidates
            else:
                # 多个 token 取并集（任一 token 命中即可）
                candidate_ids |= token_candidates
        
        # 如果索引未命中，回退到全量扫描（处理停用词过滤后的情况）
        if candidate_ids is None or not candidate_ids:
            candidate_ids = set(self.store._units.keys())

        # 只对候选集进行详细匹配
        for unit_id in candidate_ids:
            unit = self.store._units.get(unit_id)
            if not unit:
                continue
            
            # Status filter
            if status is None or status == "":
                if unit.status == UnitStatus.ARCHIVED:
                    continue
            else:
                if unit.status.value != status:
                    continue
            
            # Chapter filter
            if chapter is not None:
                if get_unit_chapter(unit) != chapter:
                    continue
            
            # Tags filter (AND semantics)
            if tags:
                unit_tags = set(unit.tags)
                if not all(tag in unit_tags for tag in tags):
                    continue
            
            if scope and unit.type not in scope:
                continue

            score = 0.0
            # 防御性：content/unit_name 可能是 None 或 dict，统一转 str
            name_raw = unit.unit_name
            content_raw = unit.content
            name_str = name_raw if isinstance(name_raw, str) else (json.dumps(name_raw, ensure_ascii=False) if name_raw else "")
            content_str = content_raw if isinstance(content_raw, str) else (json.dumps(content_raw, ensure_ascii=False) if content_raw else "")
            name = name_str if case_sensitive else name_str.lower()
            content = content_str if case_sensitive else content_str.lower()
            tags_str = " ".join(unit.tags) if case_sensitive else " ".join(unit.tags).lower()

            if kw in name:
                score += 3.0
            if kw in content:
                score += 2.0
            if kw in tags_str:
                score += 1.0

            if score > 0:
                results.append(self._make_result(unit, score))

        results.sort(key=lambda r: -r.score)
        return results

    def _regex_search(
        self,
        pattern: str,
        scope: Optional[List[UnitType]],
        case_sensitive: bool,
        status: Optional[str] = None,
        chapter: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error:
            return []

        results: List[SearchResult] = []
        for unit in self.store._units.values():
            # Status filter
            if status is None or status == "":
                if unit.status == UnitStatus.ARCHIVED:
                    continue
            else:
                if unit.status.value != status:
                    continue
            
            # Chapter filter
            if chapter is not None:
                if get_unit_chapter(unit) != chapter:
                    continue
            
            # Tags filter (AND semantics)
            if tags:
                unit_tags = set(unit.tags)
                if not all(tag in unit_tags for tag in tags):
                    continue
            
            if scope and unit.type not in scope:
                continue

            search_content_raw = unit.content
            search_name_raw = unit.unit_name
            search_content = search_content_raw if isinstance(search_content_raw, str) else (json.dumps(search_content_raw, ensure_ascii=False) if search_content_raw else "")
            search_name = search_name_raw if isinstance(search_name_raw, str) else (json.dumps(search_name_raw, ensure_ascii=False) if search_name_raw else "")
            if compiled.search(search_content) or compiled.search(search_name):
                results.append(self._make_result(unit, score=1.0))

        return results

    def _entity_search(
        self,
        name_or_id: str,
        scope: Optional[List[UnitType]],
        status: Optional[str] = None,
        chapter: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        # 1. 先按名称查找
        unit = self.store.get_unit_by_name(name_or_id)
        # 2. 名称未命中，按 ID 查找（如 wr_c0585b9b）
        if not unit:
            unit = self.store.get_unit(name_or_id)
        if not unit:
            return []

        # Apply filters to main unit
        if not self._passes_filters(unit, status, chapter, tags):
            return []

        # 主单元
        main = self._make_result(unit, score=5.0)
        results = [main]

        # 1 度邻居（get_neighbors 已排除归档单元）
        neighbors = self.store.get_neighbors(unit.id, max_depth=1).get(1, set())
        for nid in neighbors:
            n = self.store.get_unit(nid)
            if n:
                if scope and n.type not in scope:
                    continue
                if not self._passes_filters(n, status, chapter, tags):
                    continue
                results.append(self._make_result(n, score=3.0))

        return results

    def _passes_filters(
        self,
        unit: NarrativeUnit,
        status: Optional[str] = None,
        chapter: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """检查单元是否通过所有过滤条件"""
        # Status filter
        if status is None or status == "":
            if unit.status == UnitStatus.ARCHIVED:
                return False
        else:
            if unit.status.value != status:
                return False
        
        # Chapter filter
        if chapter is not None:
            if get_unit_chapter(unit) != chapter:
                return False
        
        # Tags filter (AND semantics)
        if tags:
            unit_tags = set(unit.tags)
            if not all(tag in unit_tags for tag in tags):
                return False
        
        return True

    # ── 一致性检查实现 ───────────────────────────────────────────────────

    def _check_archived_characters_in_scenes(self) -> List[CheckResult]:
        """规则 1: 已故/归档角色仍在参与场景（委托 MechanicalChecker）"""
        return MechanicalChecker(self.store)._check_archived_characters_in_scenes()

    def _check_orphan_units(self) -> CheckResult:
        """规则 3: 孤立单元（委托 MechanicalChecker）"""
        results = MechanicalChecker(self.store)._check_orphan_units()
        return results[0] if results else CheckResult(
            rule_id="R3", rule_name="孤立单元", severity="info",
            description="无孤立单元", units_involved=[],
        )

    def _check_archived_with_active_relations(self) -> List[CheckResult]:
        """规则 4: 已归档但仍有 outgoing 关系的单元（委托 MechanicalChecker）"""
        return MechanicalChecker(self.store)._check_archived_with_active_relations()

    # ── CHUNK 一致性检查 ──────────────────────────────────────────────────

    def _check_chunk_missing_file(self) -> List[CheckResult]:
        """规则 5: CHUNK 的正文文件（委托 MechanicalChecker）"""
        return MechanicalChecker(self.store)._check_chunk_missing_file()

    def _check_chunk_no_chapter(self) -> CheckResult:
        """规则 6: CHUNK content 中有章节号但 chapter_number 未同步（委托 MechanicalChecker）"""
        results = MechanicalChecker(self.store)._check_chunk_no_chapter()
        return results[0] if results else CheckResult(
            rule_id="R6", rule_name="CHUNK 章节号不一致", severity="info",
            description="CHUNK 章节状态一致", units_involved=[],
        )

    # ── R7：位置变化检测 ──────────────────────────────────────────────────

    def _check_location_changes(self) -> List[CheckResult]:
        """
        检测同一角色在相邻时间切片中的地点变化（机械标记，不下结论）。

        对于每个角色：
        1. 按 ordinal 排序该角色所有出场场景
        2. 相邻场景如果地点名称不同 + ordinal 差较小 → 标记
        3. 不做"瞬移"判断，留给 LLM
        """
        import json as _json

        results: List[CheckResult] = []

        # 建立场景基础信息索引
        scene_info: dict = {}  # scene_id → (location, ordinal, chapter, name)
        for unit in self.store._units.values():
            if unit.type != UnitType.SCENE or unit.status == UnitStatus.ARCHIVED:
                continue
            content = unit.content
            if isinstance(content, str):
                try:
                    content = _json.loads(content)
                except (_json.JSONDecodeError, ValueError):
                    content = {}
            loc = content.get("location", "") if isinstance(content, dict) else ""
            ordinal = get_story_ordinal(unit)
            ch = get_unit_chapter(unit) or 0
            scene_info[unit.id] = (loc, ordinal, ch, unit.unit_name or "?")

        # 建立角色→场景映射（通过 PARTICIPATES_IN 边）
        # 对称类型（PARTICIPATES_IN inverse==自身）：物理方向无意义，任一端是场景即视为出场
        char_scenes: dict = {}
        for rel_id, rel in self.store._relations.items():
            if rel.relation_type != RelationType.PARTICIPATES_IN:
                continue
            if rel.target_id in scene_info and rel.source_id not in scene_info:
                scene_id, char_id = rel.target_id, rel.source_id
            elif rel.source_id in scene_info and rel.target_id not in scene_info:
                scene_id, char_id = rel.source_id, rel.target_id
            else:
                continue  # 场景↔场景或非场景端点，不构成角色出场
            loc, ordinal, ch, sname = scene_info[scene_id]
            char_scenes.setdefault(char_id, []).append(
                (scene_id, loc, ordinal, ch, sname)
            )

        # 逐角色检查位置变化
        for char_id, scenes in char_scenes.items():
            char_unit = self.store.get_unit(char_id)
            if not char_unit or char_unit.type != UnitType.CHARACTER_ARC:
                continue
            char_name = char_unit.unit_name or char_id

            # 按 ordinal 排序
            scenes_sorted = sorted(scenes, key=lambda s: (
                0 if s[2] is not None else 1,
                s[2] if s[2] is not None else 0,
                s[3],
                s[4],
            ))

            for i in range(len(scenes_sorted) - 1):
                sid_a, loc_a, ord_a, ch_a, sname_a = scenes_sorted[i]
                sid_b, loc_b, ord_b, ch_b, sname_b = scenes_sorted[i + 1]

                if loc_a == loc_b or not loc_a or not loc_b:
                    continue

                # 计算间隔
                if ord_a is not None and ord_b is not None:
                    gap = ord_b - ord_a
                elif ch_a > 0 and ch_b > 0:
                    gap = (ch_b - ch_a) * ORDINAL_BASE
                else:
                    gap = 99999

                if gap < 5000:
                    results.append(CheckResult(
                        rule_name="位置变化",
                        rule_id="R7",
                        severity="warning",
                        description=f"角色「{char_name}」位置变化: {loc_a} → {loc_b}",
                        units_involved=[sid_a, sid_b, char_id],
                        detail=f"场景「{sname_a}」（ch{ch_a}, ord={ord_a}）→ "
                              f"场景「{sname_b}」（ch{ch_b}, ord={ord_b}），间隔 {gap:.1f}",
                    ))

        return results

    # ── R9：PRECEDES/ordinal 冲突 ────────────────────────────────────────

    def _check_precedes_ordinal_conflicts(self) -> List[CheckResult]:
        """检测 PRECEDES 边方向与故事时间序数排序的不一致（委托 MechanicalChecker）"""
        return MechanicalChecker(self.store)._check_precedes_ordinal_conflicts()

    # ── 工具方法 ─────────────────────────────────────────────────────────

    def _make_result(self, unit: NarrativeUnit, score: float) -> SearchResult:
        """从 NarrativeUnit 构建 SearchResult
        
        预览长度从 200→500 字符，减少"搜索后再 get_unit"的额外调用。
        完整内容仍通过 graph.get_unit 获取。
        """
        raw = unit.content if isinstance(unit.content, str) else json.dumps(unit.content, ensure_ascii=False) if unit.content else ""
        preview = raw[:500].replace("\n", " ") if raw else ""
        return SearchResult(
            unit_id=unit.id,
            unit_name=unit.unit_name,
            unit_type=unit.type,
            content_preview=preview,
            content_length=len(raw),
            chapter=get_unit_chapter(unit),
            volume=None,
            score=score,
            tags=list(unit.tags),
            status=unit.status,
            version=unit.version,
            created_at=str(unit.created_at) if unit.created_at else None,
            updated_at=str(unit.updated_at) if unit.updated_at else None,
        )

    def _get_neighbor_names(self, unit_id: str) -> List[str]:
        """获取指定单元的邻居名称"""
        names = []
        neighbors = self.store.get_neighbors(unit_id, max_depth=1).get(1, set())
        for nid in neighbors:
            n = self.store.get_unit(nid)
            if n:
                names.append(f"{n.unit_name} ({n.type.value})")
        return names[:10]  # 最多返回10个邻居

    def query_to_string(self, result_set: SearchResultSet) -> str:
        """将搜索结果渲染为可读字符串（供 LLM/CLI 消费）"""
        if not result_set.results:
            return f"搜索「{result_set.query}」无匹配结果"

        lines = [
            f"搜索「{result_set.query}」: {result_set.total} 条结果 ({result_set.time_ms}ms)",
            "",
        ]
        for i, r in enumerate(result_set.results, 1):
            ch = f"第{r.chapter}章" if r.chapter else "无章节"
            lines.append(f"  {i}. [{r.score:.0f}pts] [{r.unit_type.value}] {r.unit_name}")
            lines.append(f"      ID: {r.unit_id} | 章节: {ch} | v{r.version} | {r.status.value}")
            if r.content_preview:
                lines.append(f"      内容: {r.content_preview[:120]}...")
            if r.neighbors:
                lines.append(f"      关联: {', '.join(r.neighbors[:5])}")
            lines.append("")
        return "\n".join(lines)
    
    # ── R10-R12：节奏 / 密度 / 能动性机械检测 ─────────────────────────
    # 这些规则输出供 LLM 分析的原始信号（与 R1-R9 相同的机械定位），
    # 由 LLM 判断"这是问题还是有意设计"。

    def _check_pacing_monotony(self) -> List[CheckResult]:
        """规则 10：节奏单调——≥3 个连续场景（按章节+序数排序）共享同一 subtype。

        机械标记节奏重复的信号，不推断后果。
        """
        import json as _json

        results: List[CheckResult] = []
        scenes = []
        for unit in self.store._units.values():
            if unit.type != UnitType.SCENE or unit.status == UnitStatus.ARCHIVED:
                continue
            content = unit.content
            if isinstance(content, str) and content.startswith("{"):
                try:
                    content = _json.loads(content)
                except (_json.JSONDecodeError, ValueError):
                    content = {}
            subtype = content.get("subtype", "") if isinstance(content, dict) else ""
            if not subtype:
                continue
            scenes.append((
                get_unit_chapter(unit),
                get_story_ordinal(unit) or 0.0,
                unit.id,
                unit.unit_name or "?",
                subtype,
            ))

        if len(scenes) < 3:
            return results

        scenes.sort(key=lambda s: (s[0], s[1]))
        run = 1
        for i in range(1, len(scenes)):
            if scenes[i][4] == scenes[i - 1][4]:
                run += 1
            else:
                run = 1
            if run == 3:
                results.append(CheckResult(
                    rule_name="节奏单调",
                    rule_id="R10",
                    severity="warning",
                    description=(
                        f"连续 {run} 个场景类型均为「{scenes[i][4]}」"
                        f"（{scenes[i - run + 1][3]} → {scenes[i][3]}）"
                    ),
                    units_involved=[scenes[i][2]],
                    detail=f"场景「{scenes[i][3]}」（ch{scenes[i][0]}）与前面 {run - 1} 个场景同 subtype",
                ))
        return results

    def _check_density_deviation(self) -> List[CheckResult]:
        """规则 11：密度偏离——CHUNK 字数显著高于同类均值（>2.5× 均值）。

        样本少于 3 个 CHUNK 时不判断，避免小样本误报。
        """
        chunks = []
        for unit in self.store._units.values():
            if unit.type != UnitType.CHUNK or unit.status == UnitStatus.ARCHIVED:
                continue
            chunks.append((unit.id, unit.unit_name or "?", len(unit.content or "")))

        results: List[CheckResult] = []
        if len(chunks) < 3:
            return results
        lengths = [c[2] for c in chunks]
        mean = sum(lengths) / len(lengths)
        if mean <= 0:
            return results
        threshold = mean * 2.5
        for cid, cname, length in chunks:
            if length > threshold:
                results.append(CheckResult(
                    rule_name="密度偏离",
                    rule_id="R11",
                    severity="warning",
                    description=(
                        f"CHUNK『{cname}』字数 {length} 显著高于均值 {mean:.0f}"
                    ),
                    units_involved=[cid],
                    detail=f"密度偏离：{length} > {threshold:.0f}（{2.5}× 均值）",
                ))
        return results

    def _check_protagonist_agency(self) -> List[CheckResult]:
        """规则 12：主角能动性——主角出场 ≥3 个场景却没有任何主动关系。

        "主动关系"定义为除 PARTICIPATES_IN 之外的任意出边
        （如 CAUSES/REFERENCES/PRECEDES）。仅机械标记被动信号，不下结论。
        """
        results: List[CheckResult] = []
        for unit in self.store._units.values():
            if unit.type != UnitType.CHARACTER_ARC or unit.status == UnitStatus.ARCHIVED:
                continue
            if "主角" not in unit.tags:
                continue
            # PARTICIPATES_IN 是对称类型（inverse==自身）：物理方向无意义，
            # 单条边即可双向可达 → 用 direction="both" 采集出场场景。
            all_rels = self.store.get_relations(unit.id, direction="both")
            scene_rels = [
                r for r in all_rels if r.relation_type == RelationType.PARTICIPATES_IN
            ]
            if len(scene_rels) < 3:
                continue
            # 主动关系：方向性类型只算 char 为源端的出边（主角的行动），
            # 对称类型（RELATES_TO/CONTRADICTS 等）方向无意义，任一端关联即算。
            active_rels = [
                r for r in all_rels
                if r.relation_type != RelationType.PARTICIPATES_IN
                and (r.source_id == unit.id or r.relation_type.is_symmetric)
            ]
            if not active_rels:
                results.append(CheckResult(
                    rule_name="主角能动性不足",
                    rule_id="R12",
                    severity="warning",
                    description=(
                        f"主角『{unit.unit_name}』在 {len(scene_rels)} 个场景中出场，"
                        f"但没有任何主动关系"
                    ),
                    units_involved=[unit.id],
                    detail="连续被动：仅有 PARTICIPATES_IN 边，无 CAUSES/REFERENCES/RELATES_TO 等主动关系",
                ))
        return results
