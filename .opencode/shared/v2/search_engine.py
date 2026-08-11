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
from time_utils import get_story_ordinal


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


@dataclass
class CheckResult:
    """单条一致性检查结果"""
    rule_name: str
    rule_id: str
    severity: str          # "error" | "warning" | "info"
    description: str
    units_involved: List[str]    # unit_ids
    detail: str = ""


# ── 搜索引擎 ────────────────────────────────────────────────────────────────


class SearchEngine:
    """
    V2 搜索引擎。纯数据检索，不做 LLM 推理。
    
    接收一个已初始化的 GraphStore 实例（store.initialize() 已调用）。
    """

    # NOTE: R1-R6 rule family duplicates quality_checkers/mechanical.py;
    # canonical LLM-facing entry is graph.quality_check (NarrativeQualityEngine).
    # Do not add new duplicate rules here.
    # ── 一致性检查规则注册表 ─────────────────────────────────────────────
    # 格式: (rule_id: str, severity: str, method_name: str)
    # 新增规则只需在列表中追加，无需修改 check_consistency() 方法体。
    _CHECKERS: List[Tuple[str, str, str]] = [
        ("R1", "error",   "_check_archived_characters_in_scenes"),
        ("R2", "warning", "_check_asymmetric_relations"),
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
        results: List[SearchResult] = []
        kw = keyword if case_sensitive else keyword.lower()

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
        """规则 1: 已故/归档角色仍在参与场景"""
        results = []
        for unit in self.store._units.values():
            if unit.type != UnitType.CHARACTER_ARC:
                continue
            if unit.status != UnitStatus.ARCHIVED:
                continue

            for rel in self.store.get_relations(unit.id):
                if rel.relation_type == RelationType.PARTICIPATES_IN:
                    target = self.store.get_unit(rel.target_id)
                    if target and target.type == UnitType.SCENE:
                        results.append(CheckResult(
                            rule_name="已故角色仍在出场",
                            rule_id="R1",
                            severity="error",
                            description=f"角色『{unit.unit_name}』已归档({unit.status.value})，"
                                       f"但仍在场景『{target.unit_name}』中出场",
                            units_involved=[unit.id, target.id],
                        ))
        return results

    def _check_asymmetric_relations(self) -> List[CheckResult]:
        """规则 2: 关系不对称（A→B 但 B→A）"""
        results = []
        # 构建关系索引: (source_str, target_str, type) → count
        for rel in self.store._relations.values():
            src = self.store.get_unit(rel.source_id)
            tgt = self.store.get_unit(rel.target_id)
            if not src or not tgt:
                continue
            if src.type != UnitType.CHARACTER_ARC or tgt.type != UnitType.CHARACTER_ARC:
                continue
            if src.status == UnitStatus.ARCHIVED or tgt.status == UnitStatus.ARCHIVED:
                continue  # 已归档角色的关系不对称是预期行为
            # 三态对齐：仅 always 类型期望反向存在。
            # never（单向断言 CAUSES/PRECEDES 等）不期望反向，反向存在反而是异常；
            # optional（层级 CONTAINS/BELONGS_TO）一条边足够。
            if rel.relation_type.auto_reverse != "always":
                continue

            # 检查反向关系是否存在
            has_inverse = False
            for rel2 in self.store.get_relations(tgt.id, direction="outgoing"):
                if rel2.target_id == src.id and rel2.relation_type == rel.relation_type.inverse:
                    has_inverse = True
                    break

            if not has_inverse:
                results.append(CheckResult(
                    rule_name="角色关系不对称",
                    rule_id="R2",
                    severity="warning",
                    description=f"『{src.unit_name}』→『{tgt.unit_name}』({rel.relation_type.value})，"
                               f"但反向关系不存在",
                    units_involved=[src.id, tgt.id],
                ))
        return results

    def _check_orphan_units(self) -> CheckResult:
        """规则 3: 孤立单元（没有任何关系）"""
        orphan_count = 0
        orphan_names: List[str] = []
        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            rels = self.store.get_relations(unit.id)
            if not rels:
                orphan_count += 1
                orphan_names.append(f"{unit.unit_name} ({unit.type.value})")

        detail = ""
        if orphan_names:
            detail = "孤立单元:\n" + "\n".join(f"  - {n}" for n in orphan_names[:10])
            if len(orphan_names) > 10:
                detail += f"\n  ... 等共 {len(orphan_names)} 个"

        return CheckResult(
            rule_name="孤立单元",
            rule_id="R3",
            severity="info",
            description=f"有 {orphan_count} 个单元没有任何关系",
            units_involved=[],
            detail=detail,
        )

    def _check_archived_with_active_relations(self) -> List[CheckResult]:
        """规则 4: 已归档但仍有 outgoing 关系的单元"""
        results = []
        for unit in self.store._units.values():
            if unit.status != UnitStatus.ARCHIVED:
                continue
            outgoing = self.store._outgoing_edges.get(unit.id, [])
            if outgoing:
                rel_names = []
                for rid in outgoing[:5]:
                    rel = self.store._relations.get(rid)
                    if rel:
                        tgt = self.store.get_unit(rel.target_id)
                        tn = tgt.unit_name if tgt else "?"
                        rel_names.append(f"{rel.relation_type.value}→{tn}")
                results.append(CheckResult(
                    rule_name="归档单元仍有活跃关系",
                    rule_id="R4",
                    severity="warning",
                    description=f"单元『{unit.unit_name}』({unit.type.value})已归档，"
                               f"但仍有 {len(outgoing)} 条活跃关系",
                    units_involved=[unit.id],
                    detail="关系: " + ", ".join(rel_names) if rel_names else "",
                ))
        return results

    # ── CHUNK 一致性检查 ──────────────────────────────────────────────────

    def _check_chunk_missing_file(self) -> List[CheckResult]:
        """规则 5: CHUNK 的正文文件（正文路径/正文分片）不存在"""
        results = []
        import json
        project_root = self.store.project_root
        for unit in self.store._units.values():
            if unit.type != UnitType.CHUNK:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue
            try:
                content_dict = json.loads(unit.content) if unit.content else {}
            except (json.JSONDecodeError, ValueError):
                continue
            # 优先检查 正文分片
            slice_info = content_dict.get("slice_info")
            if slice_info:
                slice_path = slice_info.get("文件", "")
                if slice_path and not (project_root / slice_path).exists():
                    results.append(CheckResult(
                        rule_name="CHUNK 分片文件丢失",
                        rule_id="R5a",
                        severity="warning",
                        description=f"CHUNK『{unit.unit_name}』的分片文件不存在: {slice_path}",
                        units_involved=[unit.id],
                    ))
                continue  # 有 slice_info 就不检查 file_path
            # 回退到 file_path
            source_path = content_dict.get("file_path", "")
            if not source_path:
                continue
            if not (project_root / source_path).exists():
                results.append(CheckResult(
                    rule_name="CHUNK 正文文件丢失",
                    rule_id="R5",
                    severity="warning",
                    description=f"CHUNK『{unit.unit_name}』的正文文件不存在: {source_path}",
                    units_involved=[unit.id],
                ))
        return results

    def _check_chunk_no_chapter(self) -> CheckResult:
        """
        规则 6: CHUNK content 中有章节号但 chapter_number 未同步。
        """
        import json
        count = 0
        names: List[str] = []
        for unit in self.store._units.values():
            if unit.type != UnitType.CHUNK:
                continue
            if unit.status == UnitStatus.ARCHIVED:
                continue
            # 仅当 content 中显式设置了章节号但 get_unit_chapter 返回 0 时才标记
            if not get_unit_chapter(unit) and unit.content:
                try:
                    content_dict = json.loads(unit.content) if isinstance(unit.content, str) else {}
                    if content_dict.get("chapter_number") is not None:
                        count += 1
                        names.append(unit.unit_name)
                except (json.JSONDecodeError, ValueError):
                    pass
        detail = ""
        if names:
            detail = "\n".join(f"  - {n}" for n in names[:10])
            if len(names) > 10:
                detail += f"\n  ... 等共 {len(names)} 个"
        return CheckResult(
            rule_name="CHUNK 章节号不一致",
            rule_id="R6",
            severity="info",
            description=f"有 {count} 个 CHUNK 的 content 含章节号但 chapter_number 未同步" if count else "CHUNK 章节状态一致",
            units_involved=[],
            detail=detail,
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
        char_scenes: dict = {}
        for rel_id, rel in self.store._relations.items():
            if rel.relation_type != RelationType.PARTICIPATES_IN:
                continue
            if rel.target_id in scene_info:
                loc, ordinal, ch, sname = scene_info[rel.target_id]
                char_scenes.setdefault(rel.source_id, []).append(
                    (rel.target_id, loc, ordinal, ch, sname)
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
                    gap = (ch_b - ch_a) * 10000
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
        """
        检测 PRECEDES 边方向与故事时间序数排序的不一致。
        纯结构检查：A PRECEDES B 但 ordinal(A) >= ordinal(B)。
        """
        results: List[CheckResult] = []

        for rel_id, rel in self.store._relations.items():
            if rel.relation_type != RelationType.PRECEDES:
                continue

            src = self.store.get_unit(rel.source_id)
            tgt = self.store.get_unit(rel.target_id)
            if not src or not tgt:
                continue

            ord_src = get_story_ordinal(src)
            ord_tgt = get_story_ordinal(tgt)
            if ord_src is None or ord_tgt is None:
                continue

            if ord_src >= ord_tgt:
                results.append(CheckResult(
                    rule_name="事件顺序冲突",
                    rule_id="R9",
                    severity="error",
                    description=f"PRECEDES 边方向与序数不一致: {src.unit_name} → {tgt.unit_name}",
                    units_involved=[rel.source_id, rel.target_id],
                    detail=f"{src.unit_name}(ord={ord_src}) PRECEDES {tgt.unit_name}(ord={ord_tgt})，"
                           f"但序数 {ord_src} >= {ord_tgt}",
                ))

        return results

    # ── 工具方法 ─────────────────────────────────────────────────────────

    def _make_result(self, unit: NarrativeUnit, score: float) -> SearchResult:
        """从 NarrativeUnit 构建 SearchResult
        
        预览长度从 200→500 字符，减少"搜索后再 get_unit"的额外调用。
        完整内容仍通过 graph.get_unit 获取。
        """
        preview = unit.content[:500].replace("\n", " ") if unit.content else ""
        return SearchResult(
            unit_id=unit.id,
            unit_name=unit.unit_name,
            unit_type=unit.type,
            content_preview=preview,
            content_length=len(unit.content) if unit.content else 0,
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
    
    # ── R10-R12：占位实现（供 _CHECKERS 注册表调用） ──────────────
    # 这些规则设计用于节奏分析和主角能动性检测，需要结合 LLM 分析。
    # 当前返回空列表作为占位，避免 check_consistency 时 AttributeError。
    # 后续可在 constraint_engine.py 中实现为 pattern 类别约束。
    
    def _check_pacing_monotony(self) -> List[CheckResult]:
        """规则 10：节奏单调检测（占位，返回空）"""
        return []
    
    def _check_density_deviation(self) -> List[CheckResult]:
        """规则 11：密度偏离检测（占位，返回空）"""
        return []
    
    def _check_protagonist_agency(self) -> List[CheckResult]:
        """规则 12：主角能动性检测（占位，返回空）"""
        return []
