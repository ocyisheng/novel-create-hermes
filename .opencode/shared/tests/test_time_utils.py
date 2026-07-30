"""
time_utils 单元测试。

验证故事时间工具函数的核心行为：
- set/get 往返一致性
- ordinal 自动计算
- sort_by_story_time 排序正确性
- backfill 迁移逻辑
- 边界值（空 extra、缺失 key、NaN 等）

用法:
    cd novel-create-hermes
    pytest .opencode/shared/tests/test_time_utils.py -v
"""

import pytest

from graph_schema import NarrativeUnit, UnitType, UnitStatus, get_unit_chapter
from time_utils import (
    set_story_time, get_story_time, get_story_ordinal,
    get_story_label, get_story_precision,
    sort_by_story_time, compute_ordinal, backfill_story_time,
    STORY_TIME_KEY,
)


# ── 辅助 ──────────────────────────────────────────────────────────────────────


def _make_unit(name="测试单元") -> NarrativeUnit:
    return NarrativeUnit(
        id="test_id", type=UnitType.SCENE, unit_name=name,
        content='{"test": true}',
    )


# ── set / get 往返 ────────────────────────────────────────────────────────────


class TestSetGetRoundtrip:
    def test_set_and_get_roundtrip(self):
        u = _make_unit()
        set_story_time(u, "晨光初现", ordinal=42.5, precision="exact")
        st = get_story_time(u)
        assert st is not None
        assert st["label"] == "晨光初现"
        assert st["ordinal"] == 42.5
        assert st["precision"] == "exact"

    def test_get_ordinal_missing(self):
        u = _make_unit()
        assert get_story_ordinal(u) is None

    def test_get_label_missing(self):
        u = _make_unit()
        assert get_story_label(u) == ""

    def test_get_precision_default(self):
        u = _make_unit()
        assert get_story_precision(u) == "vague"

    def test_overwrite_existing(self):
        u = _make_unit()
        set_story_time(u, "A")
        set_story_time(u, "B", ordinal=99.0)
        st = get_story_time(u)
        assert st["label"] == "B"          # overwritten
        assert st["ordinal"] == 99.0
        assert "ordinal" in st             # new key added
        st2 = u.extra.get(STORY_TIME_KEY)
        assert st2 is not None


class TestComputeOrdinal:
    def test_base_case(self):
        assert compute_ordinal(5, 0) == pytest.approx(50000.5)
        assert compute_ordinal(5, 2) == pytest.approx(50200.5)
        assert compute_ordinal(1, 0) == pytest.approx(10000.5)

    def test_chapter_zero(self):
        assert compute_ordinal(0, 5) == pytest.approx(500.5)

    def test_float_precision(self):
        # 确保小数精度在合理范围
        v = compute_ordinal(100, 99)
        assert v == pytest.approx(1000000 + 9900 + 0.5)


# ── 排序 ──────────────────────────────────────────────────────────────────────


class TestSortByStoryTime:
    def test_sorted_with_ordinals(self):
        units = [_make_unit(f"unit_{i}") for i in range(3)]
        set_story_time(units[0], "C", ordinal=30.0, precision="exact")
        set_story_time(units[1], "A", ordinal=10.0, precision="exact")
        set_story_time(units[2], "B", ordinal=20.0, precision="exact")
        sorted_u = sort_by_story_time(units)
        assert [get_story_label(u) for u in sorted_u] == ["A", "B", "C"]

    def test_mixed_without_ordinals(self):
        units = [_make_unit(f"unit_{i}") for i in range(4)]
        set_story_time(units[0], "has_ord", ordinal=10.0, precision="exact")
        set_story_time(units[1], "no_ord_A", precision="vague")
        set_story_time(units[2], "has_ord2", ordinal=5.0, precision="exact")
        set_story_time(units[3], "no_ord_B", precision="vague")
        sorted_u = sort_by_story_time(units)
        labels = [get_story_label(u) for u in sorted_u]
        # 有序数的在前
        assert labels[0] == "has_ord2"
        assert labels[1] == "has_ord"
        # 无序数的在后
        assert "no_ord_A" in labels[2:]
        assert "no_ord_B" in labels[2:]

    def test_same_precision_sorting(self):
        """同 ordinal 但不同 precision 的排序"""
        units = [_make_unit(f"unit_{i}") for i in range(3)]
        set_story_time(units[0], "exact", ordinal=10.0, precision="exact")
        set_story_time(units[1], "same", ordinal=10.0, precision="same")
        set_story_time(units[2], "approx", ordinal=10.0, precision="approximate")
        sorted_u = sort_by_story_time(units)
        labels = [get_story_label(u) for u in sorted_u]
        assert labels[0] == "exact"
        assert labels[1] == "same"
        assert labels[2] == "approx"

    def test_empty_list(self):
        assert sort_by_story_time([]) == []


# ── 迁移 ──────────────────────────────────────────────────────────────────────


class TestBackfill:
    def test_backfill_with_content_time(self, store):
        """
        content 中有 '时间' 字段。
        注意：由于 create_unit 现在内部通过 auto_sync_story_time 自动同步了，
        backfill 会返回 False（因为 extra.time 已存在）。
        此验证重点：backfill 对已同步的数据不做重复操作。
        """
        from graph_schema import UnitType
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="测试场景",
            content='{"时间":"春日午后","地点":"落云宗"}',
            chapter_number=1, actor="test",
        )
        store.flush()

        # extra.time 已被 auto_sync_story_time 自动填充
        st = get_story_time(u)
        assert st is not None
        assert st["label"] == "春日午后"
        assert st["precision"] == "vague"

        # backfill 发现已有数据，返回 False（不重复写入）
        changed = backfill_story_time(u)
        assert changed is False
        assert get_story_label(u) == "春日午后"

    def test_backfill_no_time_field(self, store):
        """content 中无 '时间' 字段，返回 False"""
        from graph_schema import UnitType
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="无时间场景",
            content='{"地点":"落云宗"}',
            chapter_number=1, actor="test",
        )
        store.flush()

        changed = backfill_story_time(u)
        assert changed is False
        assert get_story_time(u) is None

    def test_backfill_already_has_time(self):
        """extra.time 已存在，不覆盖"""
        u = _make_unit()
        set_story_time(u, "已有时间", ordinal=5.0)
        changed = backfill_story_time(u)
        assert changed is False
        assert get_story_label(u) == "已有时间"

    def test_backfill_with_non_json_content(self, store):
        """非 JSON content 不会崩溃"""
        from graph_schema import UnitType
        u = store.create_unit(
            type=UnitType.NOTE, unit_name="纯文本笔记",
            content="这是一段纯粹的文本描述，不是 JSON",
            actor="test",
        )
        store.flush()
        changed = backfill_story_time(u)
        assert changed is False
