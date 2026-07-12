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
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

from graph_schema import NarrativeUnit, UnitType, UnitStatus, RelationType, get_unit_chapter
from graph_store import GraphStore


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
        """
        import time
        t0 = time.time()

        if name:
            results = self._entity_search(name, scope)
        elif pattern:
            results = self._regex_search(pattern, scope, case_sensitive)
        elif keyword:
            results = self._keyword_search(keyword, scope, case_sensitive)
        else:
            results = []

        results = results[:max_results]

        t1 = time.time()
        
        # 补充邻居信息
        for r in results:
            r.neighbors = self._get_neighbor_names(r.unit_id)

        return SearchResultSet(
            query=keyword or pattern or name,
            total=len(results),
            results=results,
            time_ms=round((t1 - t0) * 1000, 1),
        )

    # ── 增量分析支持 ─────────────────────────────────────────────────────

    def get_modified_units(self, since_version: int) -> List[NarrativeUnit]:
        """
        获取 version > since_version 的变更单元（用于增量分析）。
        
        与 VizIncrementalEngine.get_changed_unit_ids()（v2_graph_viz.py:977）
        相同模式，但不依赖 events.olog。
        
        - O(n_units) 而非 O(n_events)
        - unit.version 在每次 update_unit() 时自增（graph_store.py:357）
        """
        changed = []
        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if unit.version > since_version:
                changed.append(unit)
        return changed

    # ── 一致性检查 ───────────────────────────────────────────────────────

    def check_consistency(self) -> List[CheckResult]:
        """
        运行一致性检查，返回检查结果列表。
        
        输出的是供 LLM 分析的原始数据——LLM 需要判断
        "这是矛盾还是有意设计"。
        """
        results: List[CheckResult] = []
        
        # 规则 1: 已故角色仍在出场
        results.extend(self._check_archived_characters_in_scenes())
        
        # 规则 2: 角色关系不对称
        results.extend(self._check_asymmetric_relations())
        
        # 规则 3: 孤立单元（无任何关系）
        results.append(self._check_orphan_units())
        
        # 规则 4: 已归档但仍有 outgoing 关系的单元
        results.extend(self._check_archived_with_active_relations())
        
        # 规则 5: CHUNK 正文文件丢失
        results.extend(self._check_chunk_missing_file())
        
        # 规则 6: CHUNK 缺少 belongs_to_chapter
        results.append(self._check_chunk_no_chapter())
        
        return results

    # ── 内部搜索实现 ─────────────────────────────────────────────────────

    def _keyword_search(
        self,
        keyword: str,
        scope: Optional[List[UnitType]],
        case_sensitive: bool,
    ) -> List[SearchResult]:
        results: List[SearchResult] = []
        kw = keyword if case_sensitive else keyword.lower()

        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if scope and unit.type not in scope:
                continue

            score = 0.0
            name = unit.unit_name if case_sensitive else unit.unit_name.lower()
            content = unit.content if case_sensitive else unit.content.lower()
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
    ) -> List[SearchResult]:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(pattern, flags)
        except re.error:
            return []

        results: List[SearchResult] = []
        for unit in self.store._units.values():
            if unit.status == UnitStatus.ARCHIVED:
                continue
            if scope and unit.type not in scope:
                continue

            if compiled.search(unit.content) or compiled.search(unit.unit_name):
                results.append(self._make_result(unit, score=1.0))

        return results

    def _entity_search(
        self,
        name_or_id: str,
        scope: Optional[List[UnitType]],
    ) -> List[SearchResult]:
        # 1. 先按名称查找
        unit = self.store.get_unit_by_name(name_or_id)
        # 2. 名称未命中，按 ID 查找（如 wr_c0585b9b）
        if not unit:
            unit = self.store.get_unit(name_or_id)
        if not unit:
            return []

        # 主单元
        main = self._make_result(unit, score=5.0)
        results = [main]

        # 1 度邻居
        neighbors = self.store.get_neighbors(unit.id, max_depth=1).get(1, set())
        for nid in neighbors:
            n = self.store.get_unit(nid)
            if n and n.status != UnitStatus.ARCHIVED:
                if scope and n.type not in scope:
                    continue
                results.append(self._make_result(n, score=3.0))

        return results

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

            # 检查反向关系是否存在
            has_inverse = False
            for rel2 in self.store.get_relations(tgt.id, direction="outgoing"):
                if rel2.target_id == src.id and rel2.relation_type == rel.relation_type.inverse:
                    has_inverse = True
                    break
            for rel2 in self.store.get_relations(tgt.id, direction="incoming"):
                if rel2.source_id == src.id and rel2.relation_type == rel.relation_type:
                    # 检查是否有相反方向的关系
                    pass

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
            slice_info = content_dict.get("正文分片")
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
                continue  # 有 正文分片 就不检查 正文路径
            # 回退到 正文路径
            source_path = content_dict.get("正文路径", "")
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
                    if content_dict.get("章节号") is not None:
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

    # ── 工具方法 ─────────────────────────────────────────────────────────

    def _make_result(self, unit: NarrativeUnit, score: float) -> SearchResult:
        """从 NarrativeUnit 构建 SearchResult"""
        preview = unit.content[:200].replace("\n", " ") if unit.content else ""
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
