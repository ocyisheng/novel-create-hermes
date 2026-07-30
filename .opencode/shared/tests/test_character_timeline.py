"""
CharacterTimelineLedger 单元测试。

验证角色时间线账本的核心行为：
- 空图 / 无 SCENE 的边界
- 单场景 / 多角色提取
- 序数排序（手动覆盖 vs 自动赋值）
- 按角色 / 按章节索引
- snapshot_before / scene_order 查询

用法:
    cd novel-create-hermes
    pytest .opencode/shared/tests/test_character_timeline.py -v
"""

import pytest

from graph_schema import UnitType, UnitStatus, RelationType
from character_timeline import (
    CharacterTimelineLedger, CharacterSnapshot, TimelineView, TimelineScene,
)
from time_utils import set_story_time


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _populate_with_scenes(store):
    """创建测试用带时间线的 SCENE 数据（含角色参与关系）"""
    # 角色
    hero = store.create_unit(
        type=UnitType.CHARACTER_ARC, unit_name="林昭",
        content='{"subtype":"主角"}', tags=["主角"], chapter_number=1, actor="test",
    )
    side = store.create_unit(
        type=UnitType.CHARACTER_ARC, unit_name="韩致",
        content='{"subtype":"反派"}', tags=["反派"], chapter_number=1, actor="test",
    )

    # 场景（按章节和时间排，含出场角色）
    s1 = store.create_unit(
        type=UnitType.SCENE, unit_name="第1章_后山练剑",
        content='{"location":"天道宗后山","time_text":"清晨","cast":[{"name":"林昭","role_status":"筑基中期"}]}',
        chapter_number=1, actor="test",
    )
    s2 = store.create_unit(
        type=UnitType.SCENE, unit_name="第1章_偶遇韩致",
        content='{"location":"山间小径","time_text":"正午","cast":[{"name":"林昭","role_status":"对峙"},{"name":"韩致","role_status":"挑衅"}]}',
        chapter_number=1, actor="test",
    )
    s3 = store.create_unit(
        type=UnitType.SCENE, unit_name="第2章_坊市冲突",
        content='{"location":"坊市","time_text":"第三日清晨","cast":[{"name":"林昭","role_status":"受伤"},{"name":"韩致","role_status":"追击"}]}',
        chapter_number=2, actor="test",
    )

    # 角色参与场景
    store.add_relation(hero.id, s1.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(hero.id, s2.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(hero.id, s3.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(side.id, s2.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(side.id, s3.id, RelationType.PARTICIPATES_IN, actor="test")

    store.flush()
    return hero, side, s1, s2, s3


# ── 边界 ──────────────────────────────────────────────────────────────────────


class TestEmptyGraph:
    def test_empty_store(self, store):
        """空图不应崩溃"""
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert view.total_scenes == 0
        assert view.scenes == []
        assert view.by_character == {}
        assert view.by_chapter == {}

    def test_no_scene_units(self, store):
        """只有角色没有场景"""
        store.create_unit(type=UnitType.CHARACTER_ARC, unit_name="林昭",
                          content="{}", actor="test")
        store.flush()
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert view.total_scenes == 0


# ── 正常构建 ──────────────────────────────────────────────────────────────────


class TestBuild:
    def test_scene_count(self, store):
        hero, side, s1, s2, s3 = _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert view.total_scenes == 3

    def test_character_index(self, store):
        hero, side, *_ = _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert "林昭" in view.by_character
        assert "韩致" in view.by_character
        assert len(view.by_character["林昭"]) == 3
        assert len(view.by_character["韩致"]) == 2

    def test_chapter_index(self, store):
        _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert 1 in view.by_chapter
        assert 2 in view.by_chapter
        assert len(view.by_chapter[1]) == 2
        assert len(view.by_chapter[2]) == 1

    def test_sort_order(self, store):
        """场景应按序数排序"""
        _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        for i in range(len(view.scenes) - 1):
            assert view.scenes[i].ordinal <= view.scenes[i + 1].ordinal, (
                f"排序错误: {view.scenes[i].unit_name}({view.scenes[i].ordinal}) 在 "
                f"{view.scenes[i+1].unit_name}({view.scenes[i+1].ordinal}) 之后"
            )

    def test_archived_skipped(self, store):
        """已归档场景应被跳过"""
        hero, side, s1, s2, s3 = _populate_with_scenes(store)
        # 归档 s3
        s3.status = UnitStatus.ARCHIVED
        store.flush()

        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert view.total_scenes == 2


# ── 序数处理 ──────────────────────────────────────────────────────────────────


class TestOrdinalHandling:
    def test_manual_ordinal_override(self, store):
        """手动设 extra.time.ordinal 的场景应正确标记"""
        hero, side, s1, *_ = _populate_with_scenes(store)
        # 手动覆盖序数（模拟闪回）
        set_story_time(s1, "清晨", ordinal=500.0, precision="override")

        from graph_store import GraphStore
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        assert view.manual_overrides >= 1
        ts = [t for t in view.scenes if t.unit_id == s1.id]
        assert len(ts) == 1
        assert ts[0].is_manual_ordinal is True
        assert ts[0].ordinal == 500.0

    def test_auto_ordinal_assignment(self, store):
        """无手动序数的场景应自动赋值"""
        _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        # 自动赋值的场景 ordinal 应为正（第1章 × 10000 起步）
        for ts in view.scenes:
            if ts.chapter > 0:
                assert ts.ordinal >= ts.chapter * 10000
                assert not ts.is_manual_ordinal

    def test_same_ordinal_sorting(self, store):
        """同序数但 precision=same 的场景按创建时间排序"""
        hero, side, s1, s2, s3 = _populate_with_scenes(store)
        set_story_time(s1, "A", ordinal=100.0, precision="same")
        set_story_time(s2, "B", ordinal=100.0, precision="same")
        set_story_time(s3, "C", ordinal=100.0, precision="exact")

        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        # exact 的 s3 应排在 same 的 s1/s2 之前
        s3_idx = next(i for i, ts in enumerate(view.scenes) if ts.unit_id == s3.id)
        s1_idx = next(i for i, ts in enumerate(view.scenes) if ts.unit_id == s1.id)
        assert s3_idx < s1_idx


# ── 查询 ──────────────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_snapshot_before(self, store):
        hero, side, s1, s2, s3 = _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        snap = ledger.get_snapshot_before(view, "林昭", chapter=2)
        # 第2章之前应有第1章的场景快照
        assert snap is not None
        assert snap.chapter < 2

    def test_get_snapshot_before_beyond_range(self, store):
        hero, side, *_ = _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        snap = ledger.get_snapshot_before(view, "林昭", chapter=0)
        # 所有场景的 chapter ≥ 1，chapter=0 之前无快照
        assert snap is None

    def test_get_snapshots(self, store):
        hero, side, *_ = _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        snaps = ledger.get_snapshots(view, "林昭")
        assert len(snaps) == 3
        assert all(isinstance(s, CharacterSnapshot) for s in snaps)

    def test_get_scene_order(self, store):
        hero, side, s1, *_ = _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        idx = ledger.get_scene_order(view, s1.id)
        assert idx >= 0

    def test_get_scene_order_missing(self, store):
        _populate_with_scenes(store)
        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        assert ledger.get_scene_order(view, "nonexistent") == -1

    def test_get_state_at_ordinal(self, store):
        hero, side, s1, s2, s3 = _populate_with_scenes(store)
        # 设置明确的序数
        set_story_time(s1, "A", ordinal=10100.5, precision="exact")
        set_story_time(s2, "B", ordinal=10200.5, precision="exact")
        set_story_time(s3, "C", ordinal=20200.5, precision="exact")

        ledger = CharacterTimelineLedger(store)
        view = ledger.build()

        # 在 s1 和 s2 之间查询（ordinal=10150）
        result = ledger.get_state_at_ordinal(view, "林昭", 10150.0)
        assert result is not None
        assert result.unit_id == s1.id

        # 在 s3 之后查询
        result = ledger.get_state_at_ordinal(view, "林昭", 99999.0)
        assert result is not None
        assert result.unit_id == s3.id

    def test_parallel_groups_count(self, store):
        hero, side, s1, s2, s3 = _populate_with_scenes(store)
        set_story_time(s1, "A", ordinal=100.0, precision="same")
        set_story_time(s2, "A", ordinal=100.0, precision="same")

        ledger = CharacterTimelineLedger(store)
        view = ledger.build()
        assert view.parallel_groups >= 1
