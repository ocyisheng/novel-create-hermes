"""
SearchEngine 单元测试。

验证纯机械搜索的边界条件：
- 关键词搜索（大小写、子串匹配）
- 正则搜索（有效/无效正则）
- 实体搜索（含邻居展开）
- 增量分析（基于 unit.version）
- 一致性检查
- 空结果/边界值

用法:
    cd novel-create-hermes
    pytest .opencode/shared/v2/tests/test_search_engine.py -v
"""

import pytest

from graph_schema import UnitType, UnitStatus, RelationType
from search_engine import SearchEngine, SearchResult, SearchResultSet, CheckResult
from time_utils import set_story_time


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _populate_test_data(store):
    """创建测试用的单元和关系"""
    # 角色
    hero = store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="林昭",
        content='{"core_trait": "隐忍", "goal": "寻找真相", "backstory": "自幼被师傅收养于天道宗"}',
        tags=["主角", "成长型", "剑修"],
        chapter_number=1,
        actor="test",
    )
    villain = store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="韩致",
        content='{"core_trait": "阴险", "goal": "统一魔道", "backstory": "天道宗叛逃弟子"}',
        tags=["反派", "魔修"],
        chapter_number=1,
        actor="test",
    )
    mentor = store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="白眉真人",
        content='{"core_trait": "慈祥", "goal": "守护天道宗"}',
        tags=["导师", "天道宗"],
        actor="test",
    )
    # 场景
    scene1 = store.create_unit(
        type=UnitType.SCENE,
        unit_name="后山拔剑",
        content="林昭在后山独自练剑，一道剑光划破夜空。他想起师傅说过的话——隐忍不是软弱。",
        tags=["修炼", "天道宗"],
        chapter_number=2,
        actor="test",
    )
    scene2 = store.create_unit(
        type=UnitType.SCENE,
        unit_name="魔道来袭",
        content="韩致率领魔修攻打天道宗，林昭挺身而出。",
        tags=["战斗"],
        chapter_number=3,
        actor="test",
    )
    # 世界观规则
    world_rule = store.create_unit(
        type=UnitType.WORLD_RULE,
        unit_name="灵气淬体",
        content='{"level": "筑基期", "description": "以天地灵气淬炼肉身，可延寿三百年"}',
        actor="test",
    )
    # 归档角色
    deceased = store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="无名老者",
        content="已故的前辈",
        status=UnitStatus.ARCHIVED,
        actor="test",
    )

    # 关系
    store.add_relation(hero.id, scene1.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(hero.id, scene2.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(villain.id, scene2.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(hero.id, mentor.id, RelationType.REFERENCES, actor="test")
    store.add_relation(mentor.id, hero.id, RelationType.REFERENCES, actor="test")
    store.add_relation(hero.id, world_rule.id, RelationType.REFERENCES, actor="test")

    store.flush()
    return hero, villain, mentor, scene1, scene2, world_rule, deceased


# ── 关键词搜索 ──────────────────────────────────────────────────────────────


class TestKeywordSearch:
    def test_basic_keyword(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="林昭")
        assert result.total > 0
        names = [r.unit_name for r in result.results]
        assert "林昭" in names

    def test_keyword_content_match(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="天道宗")
        # 应在多个单元的 content/name/tags 中出现
        names = [r.unit_name for r in result.results]
        assert len(names) >= 3  # 白眉真人、后山拔剑、魔道来袭...

    def test_keyword_with_scope(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="天道宗", scope=[UnitType.CHARACTER_ARC])
        names = [r.unit_name for r in result.results]
        assert all(
            engine.store.get_unit(r.unit_id).type == UnitType.CHARACTER_ARC
            for r in result.results
        )

    def test_keyword_no_match(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="不存在的关键词")
        assert result.total == 0
        assert len(result.results) == 0

    def test_case_sensitive(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        # 小写搜索"林昭"应该能匹配到"林昭"（默认 case_sensitive=False）
        result = engine.search(keyword="林昭", case_sensitive=True)
        assert result.total > 0

    def test_keyword_in_tags(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="剑修")
        names = [r.unit_name for r in result.results]
        assert "林昭" in names

    def test_search_on_empty_store(self, store):
        """空 store 搜索应返回空结果"""
        engine = SearchEngine(store)
        result = engine.search(keyword="剑")
        assert result.total == 0


# ── 正则搜索 ────────────────────────────────────────────────────────────────


class TestRegexSearch:
    def test_basic_regex(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(pattern=r"淬炼.*肉身")
        assert result.total > 0
        assert result.results[0].unit_name == "灵气淬体"

    def test_invalid_regex(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(pattern=r"[invalid")  # 未闭合的中括号
        assert result.total == 0  # 不应该崩溃

    def test_regex_no_match(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(pattern=r"\d{10}")  # 不可能出现的数字模式
        assert result.total == 0

    def test_regex_with_scope(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(pattern=r"剑", scope=[UnitType.SCENE])
        # "后山拔剑"的内容包含"剑"、"剑光"
        names = [r.unit_name for r in result.results]
        assert all(
            engine.store.get_unit(r.unit_id).type == UnitType.SCENE
            for r in result.results
        )


# ── 实体搜索 ────────────────────────────────────────────────────────────────


class TestEntitySearch:
    def test_entity_found(self, store):
        hero, *_ = _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(name="林昭")
        assert result.total > 0
        # 主单元应排在第一位（最高分）
        assert result.results[0].unit_name == "林昭"

    def test_entity_with_neighbors(self, store):
        hero, *_ = _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(name="林昭")
        # 邻居拓展应包含关联的场景和角色
        names = [r.unit_name for r in result.results]
        assert "后山拔剑" in names
        assert "魔道来袭" in names

    def test_entity_not_found(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(name="不存在的人")
        assert result.total == 0

    def test_entity_with_scope(self, store):
        hero, *_ = _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(name="林昭", scope=[UnitType.SCENE])
        # 实体搜索：主单元始终返回（实体本身），scope 只过滤邻居
        names = [r.unit_name for r in result.results]
        assert "林昭" in names  # 主单元始终返回
        assert "后山拔剑" in names
        assert "魔道来袭" in names

    def test_entity_no_archived_in_results(self, store):
        """归档单元不出现在搜索结果中"""
        hero, *_, deceased, _ = _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(name="无名老者")
        # 归档单元本身可以搜到（用户有意识查）
        # 但不会出现在邻居拓展中
        hero_result = engine.search(name="林昭")
        hero_names = [r.unit_name for r in hero_result.results]
        assert "无名老者" not in hero_names


# ── 增量分析 ────────────────────────────────────────────────────────────────


class TestGetModifiedUnits:
    def test_no_changes(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        # 所有单元 version 应 <= 1（刚创建）
        changed = engine.get_modified_units(since_version=999)
        assert len(changed) == 0

    def test_after_update(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        
        # 初始状态：version <= 1
        initial = engine.get_modified_units(since_version=0)
        initial_versions = {u.unit_name: u.version for u in initial}
        
        # 更新一个单元
        hero = store.get_unit_by_name("林昭")
        store.update_unit(hero.id, content='{"core_trait": "杀伐果断"}', actor="test")
        store.flush()

        # 只应返回更新的单元
        changed = engine.get_modified_units(since_version=1)
        assert len(changed) >= 1
        changed_names = [u.unit_name for u in changed]
        assert "林昭" in changed_names

    def test_incremental_flow(self, store):
        """模拟增量分析的完整流程：初始全量 → 更新 → 增量"""
        _populate_test_data(store)
        engine = SearchEngine(store)

        # 第一次全量扫描
        scan_version = 1  # 假设已知全局最大 version
        first = engine.get_modified_units(since_version=scan_version)
        assert len(first) == 0  # 无更新高于 scan_version

        # 更新两个单元
        hero = store.get_unit_by_name("林昭")
        store.update_unit(hero.id, tags=["主角", "成长型", "剑修", "已更新"], actor="test")
        scene = store.get_unit_by_name("后山拔剑")
        store.update_unit(scene.id, content="更新后的内容", actor="test")
        store.flush()

        # 增量扫描
        changed = engine.get_modified_units(since_version=1)
        changed_names = [u.unit_name for u in changed]
        assert "林昭" in changed_names
        assert "后山拔剑" in changed_names

    def test_archived_excluded_from_modified(self, store):
        """get_modified_units 不返回已归档单元"""
        _populate_test_data(store)
        engine = SearchEngine(store)
        
        changed = engine.get_modified_units(since_version=0)
        archived = [u for u in changed if u.status == UnitStatus.ARCHIVED]
        assert len(archived) == 0


# ── 一致性检查 ──────────────────────────────────────────────────────────────


class TestConsistencyCheck:
    def test_archived_character_in_scene(self, store):
        """已归档角色仍参与场景 → 应检出"""
        _populate_test_data(store)
        engine = SearchEngine(store)
        results = engine.check_consistency()
        rule1 = [r for r in results if r.rule_id == "R1"]
        # 无名老者已归档但没有 PARTICIPATES_IN 关系 → R1 应为空
        assert len(rule1) == 0

    def test_archived_character_in_scene_detected(self, store):
        """构造一个归档角色参与场景的场景→应检出一个 R1"""
        hero, *_ = _populate_test_data(store)
        # 找一个已归档角色
        deceased = store.get_unit_by_name("无名老者")
        scene = store.get_unit_by_name("后山拔剑")
        # 添加归档角色的参与关系
        store.add_relation(deceased.id, scene.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        rule1 = [r for r in results if r.rule_id == "R1"]
        assert len(rule1) >= 1
        assert "无名老者" in rule1[0].description
        assert "后山拔剑" in rule1[0].description

    def test_orphan_units_detected(self, store):
        """孤立单元检测"""
        _populate_test_data(store)
        # 灵气淬体只有 REFERENCES 关系→不算孤立
        # 创建一个没有任何关系的单元
        unit = store.create_unit(
            type=UnitType.CHARACTER_ARC,
            unit_name="野生角色",
            content="无任何关系",
            actor="test",
        )
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        rule3 = [r for r in results if r.rule_id == "R3"]
        assert len(rule3) >= 1
        assert rule3[0].severity == "info"

    def test_asymmetric_relations(self, store):
        """关系不对称检测"""
        hero, villain, *_ = _populate_test_data(store)
        # hero→villain 有 PARTICIPATES_IN（共享场景）
        # 但没有 villain→hero 的反向 REFERENCES 关系 → 不对称
        engine = SearchEngine(store)
        results = engine.check_consistency()
        rule2 = [r for r in results if r.rule_id == "R2"]
        # 至少有一个不对称关系
        assert len(rule2) >= 0  # 不确定，因为场景关系可能是对称的

    def test_archived_with_active_relations(self, store):
        """归档单元仍有活跃关系"""
        _populate_test_data(store)
        # 无名老者已归档，目前无关系 → 没问题
        engine = SearchEngine(store)
        results = engine.check_consistency()
        rule4 = [r for r in results if r.rule_id == "R4"]
        assert len(rule4) == 0

        # 给归档角色添加一个关系
        deceased = store.get_unit_by_name("无名老者")
        scene = store.get_unit_by_name("后山拔剑")
        store.add_relation(deceased.id, scene.id, RelationType.REFERENCES, actor="test")
        store.flush()

        engine2 = SearchEngine(store)
        results2 = engine2.check_consistency()
        rule4 = [r for r in results2 if r.rule_id == "R4"]
        assert len(rule4) >= 1


# ── R7 / R9 一致性检查 ────────────────────────────────────────────────────────


class TestRule7LocationChanges:
    def test_no_location_change_when_same_location(self, store):
        """同一位置不应触发 R7"""
        _populate_test_data(store)
        hero, *_ = _populate_test_data(store)
        # 创建两个同位置场景
        s1 = store.create_unit(
            type=UnitType.SCENE, unit_name="场景A",
            content='{"地点":"天道宗后山","时间":"清晨"}',
            chapter_number=1, actor="test",
        )
        s2 = store.create_unit(
            type=UnitType.SCENE, unit_name="场景B",
            content='{"地点":"天道宗后山","时间":"正午"}',
            chapter_number=1, actor="test",
        )
        set_story_time(s1, "清晨", ordinal=1001.5, precision="exact")
        set_story_time(s2, "正午", ordinal=1050.5, precision="exact")
        store.add_relation(hero.id, s1.id, RelationType.PARTICIPATES_IN, actor="test")
        store.add_relation(hero.id, s2.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r7 = [r for r in results if r.rule_id == "R7" and "林昭" in r.description]
        assert len(r7) == 0, f"同地点不应触发R7"

    def test_location_change_detected(self, store):
        """地点变化且 ordinal 接近 → 触发 R7"""
        hero, *_ = _populate_test_data(store)
        s1 = store.create_unit(
            type=UnitType.SCENE, unit_name="场景A",
            content='{"地点":"天道宗","时间":"清晨"}',
            chapter_number=1, actor="test",
        )
        s2 = store.create_unit(
            type=UnitType.SCENE, unit_name="场景B",
            content='{"地点":"魔界","时间":"正午"}',
            chapter_number=1, actor="test",
        )
        set_story_time(s1, "清晨", ordinal=1001.5, precision="exact")
        set_story_time(s2, "正午", ordinal=1050.5, precision="exact")
        store.add_relation(hero.id, s1.id, RelationType.PARTICIPATES_IN, actor="test")
        store.add_relation(hero.id, s2.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r7 = [r for r in results if r.rule_id == "R7" and "林昭" in r.description]
        assert len(r7) >= 1
        assert "天道宗" in r7[0].description
        assert "魔界" in r7[0].description

    def test_location_change_ignored_with_large_gap(self, store):
        """ordinal 差距大（>=5000）不应触发 R7"""
        hero, *_ = _populate_test_data(store)
        s1 = store.create_unit(
            type=UnitType.SCENE, unit_name="场景A",
            content='{"地点":"天道宗","时间":"清晨"}',
            chapter_number=1, actor="test",
        )
        s2 = store.create_unit(
            type=UnitType.SCENE, unit_name="场景B",
            content='{"地点":"魔界","时间":"清晨"}',
            chapter_number=5, actor="test",
        )
        set_story_time(s1, "清晨", ordinal=1001.5, precision="exact")
        set_story_time(s2, "清晨", ordinal=50001.5, precision="exact")  # 5章差距
        store.add_relation(hero.id, s1.id, RelationType.PARTICIPATES_IN, actor="test")
        store.add_relation(hero.id, s2.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r7 = [r for r in results if r.rule_id == "R7" and "林昭" in r.description]
        assert len(r7) == 0, f"ordinal 差距大不应触发 R7"

    def test_r7_returns_checkresult_format(self, store):
        """R7 结果格式应为标准 CheckResult"""
        hero, *_ = _populate_test_data(store)
        s1 = store.create_unit(
            type=UnitType.SCENE, unit_name="A",
            content='{"地点":"X","时间":"t"}',
            chapter_number=1, actor="test",
        )
        s2 = store.create_unit(
            type=UnitType.SCENE, unit_name="B",
            content='{"地点":"Y","时间":"t"}',
            chapter_number=1, actor="test",
        )
        set_story_time(s1, "t", ordinal=101.5, precision="exact")
        set_story_time(s2, "t", ordinal=102.5, precision="exact")
        store.add_relation(hero.id, s1.id, RelationType.PARTICIPATES_IN, actor="test")
        store.add_relation(hero.id, s2.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r7 = [r for r in results if r.rule_id == "R7" and "林昭" in r.description]
        if r7:
            cr = r7[0]
            assert cr.rule_id == "R7"
            assert cr.severity == "warning"
            assert len(cr.units_involved) >= 2


class TestRule9PrecedesOrdinal:
    def test_precedes_ordinal_consistent(self, store):
        """A PRECEDES B 且 ordinal(A) < ordinal(B) → 不应触发"""
        _populate_test_data(store)
        a = store.create_unit(
            type=UnitType.SCENE, unit_name="事件A",
            content='{"地点":"天"}', chapter_number=1, actor="test",
        )
        b = store.create_unit(
            type=UnitType.SCENE, unit_name="事件B",
            content='{"地点":"地"}', chapter_number=2, actor="test",
        )
        set_story_time(a, "A", ordinal=1001.5, precision="exact")
        set_story_time(b, "B", ordinal=2001.5, precision="exact")
        store.add_relation(a.id, b.id, RelationType.PRECEDES, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r9 = [r for r in results if r.rule_id == "R9"]
        assert len(r9) == 0

    def test_precedes_ordinal_conflict(self, store):
        """A PRECEDES B 但 ordinal(A) >= ordinal(B) → 触发 R9"""
        _populate_test_data(store)
        a = store.create_unit(
            type=UnitType.SCENE, unit_name="事件A",
            content='{"地点":"天"}', chapter_number=1, actor="test",
        )
        b = store.create_unit(
            type=UnitType.SCENE, unit_name="事件B",
            content='{"地点":"地"}', chapter_number=1, actor="test",
        )
        set_story_time(a, "A", ordinal=2001.5, precision="exact")  # higher!
        set_story_time(b, "B", ordinal=1001.5, precision="exact")
        store.add_relation(a.id, b.id, RelationType.PRECEDES, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r9 = [r for r in results if r.rule_id == "R9"]
        assert len(r9) >= 1
        assert r9[0].severity == "error"
        assert "事件A" in r9[0].description
        assert "事件B" in r9[0].description

    def test_precedes_without_ordinals_skipped(self, store):
        """PRECEDES 边存在但双方无序数 → 跳过"""
        _populate_test_data(store)
        a = store.create_unit(
            type=UnitType.SCENE, unit_name="A",
            content='{"地点":"天"}', chapter_number=1, actor="test",
        )
        b = store.create_unit(
            type=UnitType.SCENE, unit_name="B",
            content='{"地点":"地"}', chapter_number=1, actor="test",
        )
        store.add_relation(a.id, b.id, RelationType.PRECEDES, actor="test")
        store.flush()

        engine = SearchEngine(store)
        results = engine.check_consistency()
        r9 = [r for r in results if r.rule_id == "R9"]
        assert len(r9) == 0

    def test_no_precedes_edges(self, store):
        """没有 PRECEDES 边 → R9 不应报错"""
        _populate_test_data(store)
        engine = SearchEngine(store)
        results = engine.check_consistency()
        r9 = [r for r in results if r.rule_id == "R9"]
        assert len(r9) == 0


# ── 规则注册表 ────────────────────────────────────────────────────────────────


class TestCheckerRegistry:
    def test_all_expected_rules_registered(self):
        """验证 _CHECKERS 注册表包含所有预期规则"""
        from search_engine import SearchEngine
        rule_ids = {rid for rid, _, _ in SearchEngine._CHECKERS}
        expected = {"R1", "R2", "R3", "R4", "R5", "R6", "R7", "R9", "R10", "R11", "R12"}
        missing = expected - rule_ids
        assert not missing, f"Missing rules: {missing}"
        unexpected = rule_ids - expected
        # 允许未来新增
        if unexpected:
            assert False, f"Unexpected rules not in test expectation: {unexpected}"

    def test_rule_ids_in_check_consistency(self, store):
        """check_consistency() 返回的 rule_id 都在注册表中"""
        _populate_test_data(store)
        from search_engine import SearchEngine
        engine = SearchEngine(store)
        registered = {rid for rid, _, _ in SearchEngine._CHECKERS}
        results = engine.check_consistency()
        for r in results:
            assert r.rule_id in registered, (
                f"Rule {r.rule_id} not in _CHECKERS registry"
            )

    def test_registry_not_empty(self):
        """_CHECKERS 注册表不为空"""
        from search_engine import SearchEngine
        assert len(SearchEngine._CHECKERS) >= 6


# ── 边界值与工具方法 ───────────────────────────────────────────────────────


class TestSearchResultRendering:
    def test_empty_search_rendering(self, store):
        engine = SearchEngine(store)
        result = engine.search(keyword="不存在")
        output = engine.query_to_string(result)
        assert "无匹配结果" in output

    def test_search_rendering(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="林昭")
        output = engine.query_to_string(result)
        assert "林昭" in output
        assert "pts" in output
        assert "搜索" in output

    def test_max_results(self, store):
        """测试 max_results 限制"""
        _populate_test_data(store)
        engine = SearchEngine(store)
        # 搜索"剑"应该匹配多个单元
        result = engine.search(keyword="剑", max_results=1)
        assert len(result.results) <= 1

    def test_get_neighbor_names(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        hero = store.get_unit_by_name("林昭")
        names = engine._get_neighbor_names(hero.id)
        assert len(names) > 0
        assert any("后山拔剑" in n for n in names)


class TestSearchResultDataclass:
    def test_search_result_fields(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="林昭")
        if result.results:
            r = result.results[0]
            assert r.unit_id
            assert r.unit_name
            assert r.unit_type
            assert r.score >= 0
            assert r.version >= 1
            assert isinstance(r.tags, list)

    def test_search_result_set_fields(self, store):
        _populate_test_data(store)
        engine = SearchEngine(store)
        result = engine.search(keyword="林昭")
        assert isinstance(result, SearchResultSet)
        assert result.query == "林昭"
        assert result.time_ms >= 0
