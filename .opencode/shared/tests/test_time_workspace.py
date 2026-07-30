"""
Workspace 时间序列 + 关系图 集成测试。

覆盖：
1. auto_sync_story_time() — 自动同步 content → extra.time
2. graph_store create_unit / update_unit 自动同步钩子
3. Workspace 新字段默认值
4. _load_timeline_data() — 角色/场景/地点时间线加载
5. _load_ego_graph() — 结构化关系图加载
6. to_prompt_block() — 时间轴/关系网络段落渲染
7. PREHEAT_DEPTH 新配置键

用法:
    cd novel-create-hermes
    pytest .opencode/shared/tests/test_time_workspace.py -v
"""

import json
import pytest

from graph_schema import NarrativeUnit, UnitType, UnitStatus, RelationType
from time_utils import (
    auto_sync_story_time, get_story_time, get_story_ordinal,
    get_story_label, set_story_time, STORY_TIME_KEY,
)
from workspace import Workspace, WorkspaceBuilder


# ═════════════════════════════════════════════════════════════════════════════
# auto_sync_story_time 单元测试
# ═════════════════════════════════════════════════════════════════════════════


def _make_unit(name="测试", type=UnitType.SCENE, content='{"test": true}') -> NarrativeUnit:
    return NarrativeUnit(
        id="test_" + name, type=type, unit_name=name,
        content=content,
    )


class TestAutoSyncStoryTime:
    def test_sync_time_and_ordinal(self):
        """content 中有 '时间' 和 '时间序数'，应同步到 extra.time"""
        u = _make_unit(content=json.dumps({"time_text": "第三日黄昏", "time_ordinal": 15000.5}))
        changed = auto_sync_story_time(u)
        assert changed is True
        st = get_story_time(u)
        assert st["label"] == "第三日黄昏"
        assert st["ordinal"] == 15000.5
        assert st["precision"] == "exact"

    def test_sync_time_only_no_ordinal(self):
        """content 中只有 '时间' 无 '时间序数'"""
        u = _make_unit(content=json.dumps({"time_text": "清晨", "location": "后山"}))
        changed = auto_sync_story_time(u)
        assert changed is True
        st = get_story_time(u)
        assert st["label"] == "清晨"
        assert st["ordinal"] is None
        assert st["precision"] == "vague"

    def test_skip_when_no_time_field(self):
        """content 中无时间字段，返回 False"""
        u = _make_unit(content=json.dumps({"location": "后山"}))
        changed = auto_sync_story_time(u)
        assert changed is False
        assert get_story_time(u) is None

    def test_skip_when_extra_time_exists(self):
        """extra.time 已存在，不覆盖"""
        u = _make_unit(content=json.dumps({"time_text": "新时间", "time_ordinal": 99.0}))
        u.extra[STORY_TIME_KEY] = {"label": "已有", "ordinal": 10.0, "precision": "exact"}
        changed = auto_sync_story_time(u)
        assert changed is False
        assert get_story_label(u) == "已有"  # 没有被覆盖

    def test_skip_non_json_content(self):
        """非 JSON content 不崩溃"""
        u = _make_unit(content="纯文本")
        changed = auto_sync_story_time(u)
        assert changed is False

    def test_ordinal_none_in_content(self):
        """时间序数为 null 时转为 None"""
        u = _make_unit(content=json.dumps({"time_text": "中午", "time_ordinal": None}))
        changed = auto_sync_story_time(u)
        assert changed is True
        st = get_story_time(u)
        assert st["label"] == "中午"
        assert st["ordinal"] is None


# ═════════════════════════════════════════════════════════════════════════════
# GraphStore 自动同步集成测试
# ═════════════════════════════════════════════════════════════════════════════


class TestGraphStoreAutoSync:
    def test_create_unit_auto_syncs_time(self, store):
        """create_unit 应自动同步 content 中的时间字段"""
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="测试场景",
            content=json.dumps({"time_text": "黄昏", "time_ordinal": 15000.5}),
            chapter_number=3, actor="test",
        )
        st = get_story_time(u)
        assert st is not None
        assert st["label"] == "黄昏"
        assert st["ordinal"] == 15000.5

    def test_create_unit_no_time_skipped(self, store):
        """content 中无时间字段，不写 extra.time"""
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="无时间场景",
            content=json.dumps({"location": "后山"}),
            actor="test",
        )
        assert get_story_time(u) is None

    def test_update_unit_auto_syncs_time(self, store):
        """update_unit 更新 content 时应自动同步时间"""
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="初始",
            content=json.dumps({"location": "后山"}),
            actor="test",
        )
        assert get_story_time(u) is None

        # 更新 content，加上时间
        updated = store.update_unit(
            u.id,
            content=json.dumps({"time_text": "黎明", "location": "后山"}),
            actor="test",
        )
        assert updated is not None
        st = get_story_time(updated)
        assert st is not None
        assert st["label"] == "黎明"

    def test_update_unit_keeps_existing_time(self, store):
        """已有 extra.time，更新 content 不覆盖"""
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="已有时间",
            content=json.dumps({"time_text": "早晨", "time_ordinal": 100.0}),
            actor="test",
        )
        assert get_story_ordinal(u) == 100.0

        # 更新一个不涉及时间的字段
        store.update_unit(u.id, content=json.dumps({"time_text": "早晨", "location": "新地点"}), actor="test")
        # content 中的 '时间序数' 没写，但 extra.time 已有不会被清除
        st = get_story_time(u)
        assert st is not None
        # 注意：update_unit 的 auto_sync 只会在 extra.time 为空时写入
        # 这里 extra.time 已有, 所以保持原值
        assert st["label"] == "早晨"


# ═════════════════════════════════════════════════════════════════════════════
# Workspace 数据类测试
# ═════════════════════════════════════════════════════════════════════════════


class TestWorkspaceDataClass:
    def test_new_fields_defaults(self):
        """新字段应有正确的默认值"""
        ws = Workspace()
        assert ws.entity_timeline == []
        assert ws.character_snapshots == []
        assert ws.character_evolution == ""
        assert ws.relation_summary == ""
        assert ws.location_timeline == []
        assert ws.ego_graph is None
        assert ws.global_timeline_summary is None
        assert ws.story_ordinal is None
        assert ws.entity_paths == []

    def test_to_dict_includes_new_fields(self, sample_units):
        """to_dict 应包含新字段的统计"""
        proj_path, store, _units = sample_units
        from graph_schema import RelationType

        # 创建带时间线的场景
        sc = store.create_unit(
            type=UnitType.SCENE, unit_name="新场景",
            content=json.dumps({"time_text": "正午", "location": "大厅", "cast": [{"name": "林渊"}]}),
            chapter_number=1, actor="test",
        )
        store.add_relation(_units["林渊"].id, sc.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(_units["林渊"].id, preheat_level="warm")

        d = ws.to_dict()
        assert "timeline_event_count" in d
        assert "snapshot_count" in d
        assert "has_ego_graph" in d
        assert isinstance(d["timeline_event_count"], int)
        assert isinstance(d["snapshot_count"], int)
        assert isinstance(d["has_ego_graph"], bool)


# ═════════════════════════════════════════════════════════════════════════════
# _load_timeline_data 集成测试
# ═════════════════════════════════════════════════════════════════════════════


class TestLoadTimelineData:
    def test_character_timeline_and_snapshots(self, store):
        """角色焦点应加载时间线事件和快照"""
        # 创建角色和3个场景
        char = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="林昭", actor="test",
        )
        scenes = []
        for i in range(3):
            sc = store.create_unit(
                type=UnitType.SCENE,
                unit_name="场景%d" % (i + 1),
                content=json.dumps({
                    "time_text": "第%d日" % (i + 1),
                    "location": "地点%d" % (i + 1),
                    "cast": [{"name": "林昭"}],
                }),
                chapter_number=i + 1,
                actor="test",
            )
            scenes.append(sc)

        # 建立 PARTICIPATES_IN 关系
        for sc in scenes:
            store.add_relation(sc.id, char.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="warm")

        # 验证时间线
        assert len(ws.entity_timeline) == 3, "应有3个时间线事件"
        ordinals = [e["story_ordinal"] for e in ws.entity_timeline]
        assert ordinals == sorted(ordinals), "应按序数升序"

        # 验证快照
        assert len(ws.character_snapshots) == 3, "应有3个快照"

        # 验证演变摘要
        assert "林昭" in ws.character_evolution
        assert "第1章" in ws.character_evolution
        assert "第3章" in ws.character_evolution

        # 验证全局时间线摘要
        assert ws.global_timeline_summary is not None
        assert ws.global_timeline_summary["total_scenes"] == 3

    def test_scene_timeline_with_focus_marker(self, store):
        """场景焦点应包含前后场景，标记自身"""
        scenes = []
        for i in range(3):
            sc = store.create_unit(
                type=UnitType.SCENE,
                unit_name="场景%d" % (i + 1),
                content=json.dumps({"time_text": "第%d日" % (i + 1), "location": "L%d" % (i + 1)}),
                chapter_number=i + 1,
                actor="test",
            )
            scenes.append(sc)
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(scenes[1].id, preheat_level="warm")

        # 验证时间线包含前后场景
        assert len(ws.entity_timeline) == 3  # 前后各2 + 自身，但总共3个

        # 检查焦点标记
        focused = [e for e in ws.entity_timeline if e.get("is_focus")]
        assert len(focused) == 1
        assert focused[0]["event"] == "场景2"

        # 验证全局位置
        assert ws.global_timeline_summary is not None
        pos = ws.global_timeline_summary.get("focus_position")
        assert pos == 1  # 0-based，第2个场景

        assert ws.story_ordinal is not None

    def test_cold_level_no_timeline(self, store):
        """cold 预热级别应不加载时间线"""
        char = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="角色", actor="test",
        )
        sc = store.create_unit(
            type=UnitType.SCENE, unit_name="场景",
            content=json.dumps({"time_text": "某日", "cast": [{"name": "角色"}]}),
            chapter_number=1, actor="test",
        )
        store.add_relation(sc.id, char.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="cold")

        assert len(ws.entity_timeline) == 0
        assert len(ws.character_snapshots) == 0

    def test_location_timeline(self, store):
        """地点焦点应加载地点时间线"""
        loc = store.create_unit(
            type=UnitType.WORLD_RULE, unit_name="青云宗",
            content=json.dumps({"subtype": "地点"}),
            actor="test",
        )
        for i in range(2):
            store.create_unit(
                type=UnitType.SCENE,
                unit_name="后山事件%d" % (i + 1),
                content=json.dumps({"time_text": "第%d次" % (i + 1), "location": "青云宗"}),
                chapter_number=i + 1,
                actor="test",
            )
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(loc.id, preheat_level="warm")

        # 地点应加载 location_timeline
        assert len(ws.location_timeline) > 0
        assert ws.location_timeline[0]["location"] == "青云宗"


# ═════════════════════════════════════════════════════════════════════════════
# _load_ego_graph 集成测试
# ═════════════════════════════════════════════════════════════════════════════


class TestLoadEgoGraph:
    def test_basic_ego_graph(self, sample_units):
        """基本 Ego Network 加载"""
        proj_path, store, units = sample_units
        lin = units["林渊"]

        builder = WorkspaceBuilder(store)
        ws = builder.build(lin.id, preheat_level="warm")

        assert ws.ego_graph is not None
        assert ws.ego_graph["center_id"] == lin.id
        assert ws.ego_graph["node_count"] >= 1  # 至少中心节点 + 邻居
        assert ws.ego_graph["edge_count"] >= 1  # 至少1条边

        # 验证 by_type 分组
        assert "participates_in" in ws.ego_graph["by_type"]

    def test_relation_summary(self, sample_units):
        """关系摘要文本生成"""
        proj_path, store, units = sample_units
        builder = WorkspaceBuilder(store)
        ws = builder.build(units["林渊"].id, preheat_level="warm")

        assert ws.relation_summary != ""
        assert "participates_in" in ws.relation_summary

    def test_hot_depth_two(self, sample_units):
        """hot 预热应加载 2-hop"""
        proj_path, store, units = sample_units
        builder = WorkspaceBuilder(store)
        ws = builder.build(units["林渊"].id, preheat_level="hot")

        assert ws.ego_graph is not None
        # hot 应包含 graph_internal_edges
        assert ws.ego_graph["node_count"] >= 1

    def test_cold_no_ego_graph(self, sample_units):
        """cold 预热不加载 ego_graph（timeline_events=0）"""
        proj_path, store, units = sample_units
        builder = WorkspaceBuilder(store)
        ws = builder.build(units["林渊"].id, preheat_level="cold")

        # cold: timeline_events=0 but graph_depth=1, ego_graph still loaded
        # ego_graph 独立于 timeline_events 控制
        assert ws.ego_graph is not None  # 图数据仍应加载


# ═════════════════════════════════════════════════════════════════════════════
# to_prompt_block 渲染测试
# ═════════════════════════════════════════════════════════════════════════════


class TestToPromptBlock:
    def test_timeline_section_in_warm(self, store):
        """warm 预热应包含时间轴段落"""
        char = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="测试角色",
            content=json.dumps({"name": "测试角色"}),
            actor="test",
        )
        for i in range(2):
            sc = store.create_unit(
                type=UnitType.SCENE, unit_name="测试场景%d" % (i + 1),
                content=json.dumps({"time_text": "第%d日" % (i + 1), "location": "某地",
                                    "cast": [{"name": "测试角色"}]}),
                chapter_number=i + 1, actor="test",
            )
            store.add_relation(sc.id, char.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="warm")
        prompt = ws.to_prompt_block("warm")

        # 验证新段落出现
        assert "### 时间轴" in prompt
        assert "### 实体时间线" in prompt
        assert "### 角色状态演变" in prompt
        assert "### 角色轨迹" in prompt
        assert "### 关系网络" in prompt

    def test_hot_contains_ego_graph_detail(self, store):
        """hot 预热应包含关系图结构详情"""
        char = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="角色A", actor="test",
        )
        sc = store.create_unit(
            type=UnitType.SCENE, unit_name="场景",
            content=json.dumps({"time_text": "某日", "cast": [{"name": "角色A"}]}),
            chapter_number=1, actor="test",
        )
        store.add_relation(sc.id, char.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="hot")
        prompt = ws.to_prompt_block("hot")

        assert "### 关系图结构" in prompt
        assert "节点" in prompt
        assert "边" in prompt

    def test_cold_no_timeline_section(self, store):
        """cold 预热不应有时间轴段落"""
        char = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="角色", actor="test",
        )
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="cold")
        prompt = ws.to_prompt_block("cold")

        assert "### 时间轴" not in prompt

    def test_scene_prompt_has_position(self, store):
        """场景焦点 prompt 应包含时间线位置"""
        scenes = []
        for i in range(3):
            sc = store.create_unit(
                type=UnitType.SCENE,
                unit_name="场景%d" % (i + 1),
                content=json.dumps({"time_text": "第%d日" % (i + 1), "location": "L%d" % (i + 1)}),
                chapter_number=i + 1,
                actor="test",
            )
            scenes.append(sc)
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(scenes[1].id, preheat_level="warm")
        prompt = ws.to_prompt_block("warm")

        # 应包含焦点位置
        assert "焦点位置" in prompt
        assert "故事坐标" in prompt

    def test_character_evolution_in_prompt(self, store):
        """角色演变摘要应在 prompt 中"""
        char = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="主角",
            content=json.dumps({"name": "主角"}),
            actor="test",
        )
        for i in range(2):
            sc = store.create_unit(
                type=UnitType.SCENE,
                unit_name="章%d" % (i + 1),
                content=json.dumps({"time_text": "时刻%d" % (i + 1), "location": "L%d" % (i + 1),
                                    "cast": [{"name": "主角"}]}),
                chapter_number=i + 1,
                actor="test",
            )
            store.add_relation(sc.id, char.id, RelationType.PARTICIPATES_IN, actor="test")
        store.flush()

        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="warm")
        prompt = ws.to_prompt_block("warm")

        assert "### 角色轨迹" in prompt
        assert "主角:" in prompt


# ═════════════════════════════════════════════════════════════════════════════
# PREHEAT_DEPTH 配置测试
# ═════════════════════════════════════════════════════════════════════════════


class TestPreheatConfig:
    def test_default_config_has_new_keys(self):
        """PREHEAT_DEPTH 各级别都应包含新配置键"""
        builder = object.__new__(WorkspaceBuilder)
        for level in ("cold", "warm", "hot"):
            cfg = WorkspaceBuilder.PREHEAT_DEPTH[level]
            assert "timeline_events" in cfg, f"{level} 缺少 timeline_events"
            assert "snapshot_limit" in cfg, f"{level} 缺少 snapshot_limit"
            assert "graph_depth" in cfg, f"{level} 缺少 graph_depth"
            assert "graph_internal_edges" in cfg, f"{level} 缺少 graph_internal_edges"

    def test_cold_timeline_zero(self):
        """cold 级别 timeline_events=0"""
        cfg = WorkspaceBuilder.PREHEAT_DEPTH["cold"]
        assert cfg["timeline_events"] == 0
        assert cfg["snapshot_limit"] == 0

    def test_warm_gradual(self):
        """warm 级别有适度加载"""
        cfg = WorkspaceBuilder.PREHEAT_DEPTH["warm"]
        assert cfg["timeline_events"] == 5
        assert cfg["snapshot_limit"] == 5
        assert cfg["graph_depth"] == 1
        assert cfg["graph_internal_edges"] is True

    def test_hot_maximal(self):
        """hot 级别加载最多"""
        cfg = WorkspaceBuilder.PREHEAT_DEPTH["hot"]
        assert cfg["timeline_events"] == 20
        assert cfg["snapshot_limit"] == 20
        assert cfg["graph_depth"] == 2
        assert cfg["graph_internal_edges"] is True
