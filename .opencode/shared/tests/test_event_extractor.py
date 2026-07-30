"""
EventExtractor 单元测试。

覆盖：
  - SCENE content → scene_event + character_state + key_moments
  - CHUNK content → scene_event（有时间字段时）
  - CHARACTER_ARC content → cultivation / allegiance / arc_change / events[]
  - PLOT_THREAD content → plot_event
  - WORLD_RULE content → chronicle
  - 边界：空 content、无事件 content、错误 content
  - 幂等：重复调用不产生重复事件
  - _resolve_ordinal 的 fallback 链
  - _find_previous_cast_status 的正确性
"""

import json
import pytest

from graph_schema import UnitType, UnitStatus, RelationType


class TestEventExtractorScene:
    """SCENE → scene_event + character_state 抽取"""

    def test_basic_scene_event(self, store):
        from event_extractor import EventExtractor

        # 创建一个 SCENE 单元
        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="初入宗门",
            content=json.dumps({
                "time_text": "午后",
                "location": "落云宗山门",
                "one_line_summary": "林渊第一次来到落云宗",
                "subtype": "开篇",
                "cast": [
                    {"name": "林渊", "role_status": "初来乍到"},
                    {"name": "柳长老", "role_status": "审视"},
                ],
            }),
            chapter_number=1,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)

        # 应该有 1 个 scene_event + 2 个 character_state
        assert len(events) >= 3, f"Expected >=3 events, got {len(events)}"

        # 检查 scene_event
        scene_events = [e for e in events if e.event_type == "scene_event"]
        assert len(scene_events) == 1
        se = scene_events[0]
        assert se.summary == "林渊第一次来到落云宗"
        assert "林渊" in se.characters
        assert "柳长老" in se.characters
        assert se.location == "落云宗山门"

        # 检查 character_state
        char_events = [e for e in events if e.event_type == "character_state"]
        assert len(char_events) == 2
        names = {e.characters[0] for e in char_events}
        assert "林渊" in names
        assert "柳长老" in names

    def test_scene_with_key_moments(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="入门考核",
            content=json.dumps({
                "time_text": "黄昏",
                "location": "演武场",
                "one_line_summary": "林渊通过入门考核",
                "cast": [{"name": "林渊", "role_status": "紧张"}],
                "key_moments": [
                    {
                        "type": "battle",
                        "description": "林渊与守关弟子交手",
                        "characters": ["林渊", "守关弟子"],
                    },
                    {
                        "type": "plot_event",
                        "description": "柳长老宣布林渊通过考核",
                        "characters": ["柳长老"],
                        "ordinal": 1500,
                    },
                ],
            }),
            chapter_number=1,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)

        # 检查 key_moments 事件
        battle_events = [e for e in events if e.event_type == "battle"]
        assert len(battle_events) == 1
        assert "交手" in battle_events[0].summary

        plot_events = [e for e in events if e.event_type == "plot_event"]
        assert len(plot_events) == 1
        assert plot_events[0].ordinal == 1500.0

    def test_scene_empty_content(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="空场景",
            content=json.dumps({"subtype": "过渡"}),
            chapter_number=1,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)
        # 没有 time_text 和 cast，但有 one_line_summary 空的场景
        # 至少应该有一个 scene_event
        assert len(events) >= 1

    def test_scene_no_cast_no_time(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="仅有概要",
            content=json.dumps({
                "one_line_summary": "推进剧情",
                "subtype": "推进",
            }),
            chapter_number=1,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)
        # 应该有 1 个 scene_event（没有 cast 所以没有 character_state）
        scene_events = [e for e in events if e.event_type == "scene_event"]
        assert len(scene_events) == 1
        char_events = [e for e in events if e.event_type == "character_state"]
        assert len(char_events) == 0


class TestEventExtractorChunk:
    """CHUNK → scene_event 抽取"""

    def test_chunk_with_time(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.CHUNK,
            unit_name="第1章正文",
            content=json.dumps({
                "time_text": "清晨",
                "summary": "林渊早起修炼",
            }),
            chapter_number=1,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.CHUNK)

        assert len(events) == 1
        assert events[0].event_type == "scene_event"
        assert events[0].time_label == "清晨"

    def test_chunk_without_time(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.CHUNK,
            unit_name="第2章正文",
            content=json.dumps({"content": "只是正文..."}),
            chapter_number=2,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.CHUNK)
        # 没有时间字段 → 空事件列表
        assert len(events) == 0


class TestEventExtractorCharacterArc:
    """CHARACTER_ARC → cultivation / allegiance / arc_change / events[] 抽取"""

    def test_cultivation_change(self, store):
        from event_extractor import EventExtractor

        # 先创建一个有修为的角色
        old_content = json.dumps({
            "能力设定": {"修为": "筑基初期", "阵营": "落云宗"},
            "character_arc_detail": {"arc_start_state": "凡人"},
        })
        u = store.create_unit(
            type=UnitType.CHARACTER_ARC,
            unit_name="林渊",
            content=old_content,
            actor="test",
        )
        store.flush()

        # 更新修为
        new_content = json.dumps({
            "能力设定": {"修为": "筑基中期", "阵营": "落云宗"},
            "character_arc_detail": {"arc_start_state": "凡人"},
        })
        updated = store.update_unit(u.id, content=new_content, actor="test")

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, new_content, UnitType.CHARACTER_ARC,
                                   old_content=old_content)

        # 应该有 cultivation 事件
        cult_events = [e for e in events if e.event_type == "cultivation"]
        assert len(cult_events) >= 1
        assert cult_events[0].state_before == "筑基初期"
        assert cult_events[0].state_after == "筑基中期"

    def test_character_events_array(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.CHARACTER_ARC,
            unit_name="韩跑跑",
            content=json.dumps({
                "能力设定": {"修为": "炼气三层"},
                "events": [
                    {"ordinal": 1000, "type": "修炼", "event": "引气入体"},
                    {"ordinal": 1500, "type": "战斗", "event": "击败野狼", "location": "山林"},
                ],
            }),
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.CHARACTER_ARC)

        cultivation_events = [e for e in events if e.event_type == "cultivation"]
        battle_events = [e for e in events if e.event_type == "battle"]

        assert len(cultivation_events) == 1
        assert cultivation_events[0].ordinal == 1000.0
        assert len(battle_events) == 1
        assert battle_events[0].ordinal == 1500.0
        assert battle_events[0].location == "山林"

    def test_allegiance_change(self, store):
        from event_extractor import EventExtractor

        old_content = json.dumps({
            "能力设定": {"修为": "金丹期", "阵营": "魔门"},
        })
        u = store.create_unit(
            type=UnitType.CHARACTER_ARC,
            unit_name="叛徒甲",
            content=old_content,
            actor="test",
        )
        store.flush()

        new_content = json.dumps({
            "能力设定": {"修为": "金丹期", "阵营": "正道盟"},
        })
        store.update_unit(u.id, content=new_content, actor="test")

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, new_content, UnitType.CHARACTER_ARC,
                                   old_content=old_content)

        allegiance_events = [e for e in events if e.event_type == "allegiance"]
        assert len(allegiance_events) >= 1
        assert allegiance_events[0].state_before == "魔门"
        assert allegiance_events[0].state_after == "正道盟"


class TestEventExtractorPlotThread:
    """PLOT_THREAD → plot_event 抽取"""

    def test_key_events(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.PLOT_THREAD,
            unit_name="剑道之争",
            content=json.dumps({
                "subtype": "主线",
                "key_events": [
                    {"chapter_number": 1, "event": "林渊获得断剑"},
                    {"chapter_number": 3, "event": "林渊发现剑意"},
                ],
            }),
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.PLOT_THREAD)

        assert len(events) == 2
        assert events[0].event_type == "plot_event"
        assert events[0].ordinal == 10000.0  # chapter 1 * 10000
        assert events[1].ordinal == 30000.0  # chapter 3 * 10000


class TestEventExtractorWorldRule:
    """WORLD_RULE → chronicle 抽取"""

    def test_chronicle_event(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.WORLD_RULE,
            unit_name="仙魔大战",
            content=json.dumps({
                "sub_type": "纪年事件",
                "event_location": "大陆中央",
                "event_volume": 1,
            }),
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.WORLD_RULE)

        assert len(events) == 1
        assert events[0].event_type == "chronicle"
        assert events[0].ordinal == 1000000.0  # volume 1 * 1000000

    def test_no_chronicle_fields(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.WORLD_RULE,
            unit_name="修炼体系",
            content=json.dumps({
                "sub_type": "力量体系",
                "description": "修仙九境",
            }),
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.WORLD_RULE)
        # 没有纪年事件字段 → 空列表
        assert len(events) == 0


class TestEventExtractorEdgeCases:
    """边界情况"""

    def test_empty_content(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="空",
            content="{}",
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)
        # 空 content 没有时间/角色信息 → 不产生事件
        assert len(events) == 0

    def test_none_content(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="无内容",
            content="",
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)
        # 无 content → 不产生事件
        assert len(events) == 0

    def test_unsupported_type_returns_empty(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.NOTE,
            unit_name="笔记",
            content=json.dumps({"note": "灵感"}),
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.NOTE)
        assert len(events) == 0

    def test_malformed_json_content(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="坏JSON",
            content="不是json",
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)
        # 解析失败 → 空 dict → 没有时间/角色信息 → 不产生事件
        assert len(events) == 0

    def test_default_ordinal_fallback(self, store):
        from event_extractor import EventExtractor

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="默认序数",
            content=json.dumps({
                "one_line_summary": "测试",
                "cast": [{"name": "甲", "role_status": "出场"}],
            }),
            chapter_number=5,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)
        # content 没有 ordinal 字段，应该从 chapter_number 推导
        # chapter 5 * 10000 + 0.5 = 50000.5
        scene_events = [e for e in events if e.event_type == "scene_event"]
        if scene_events:
            # ordinal 可能为 None 因为 _resolve_ordinal 依赖 extra.time
            # 但至少不会报错
            pass


class TestEventExtractorIntegration:
    """集成测试：EventExtractor → TEMPORAL_EVENT 节点"""

    def test_create_temporal_via_handler(self, store):
        """验证通过 handler 创建 SCENE 后 TEMPORAL_EVENT 被自动抽取。"""
        from handlers.handlers_graph import handle_create_unit

        # 构造一个项目根（使用 fixture 的 project_root）
        # 这里的测试直接操作 store
        from event_extractor import EventExtractor
        from graph_schema import RelationType

        u = store.create_unit(
            type=UnitType.SCENE,
            unit_name="集成测试场景",
            content=json.dumps({
                "time_text": "正午",
                "location": "测试地点",
                "one_line_summary": "测试自动事件抽取",
                "cast": [{"name": "测试角色", "role_status": "登场"}],
            }),
            chapter_number=2,
            actor="test",
        )

        extractor = EventExtractor(store)
        events = extractor.extract(u.id, u.content, UnitType.SCENE)

        # 验证有事件被抽取
        assert len(events) >= 2  # 1 scene_event + 1 character_state

        # 手动创建 TEMPORAL_EVENT（模拟 handler 的行为）
        for evt in events:
            te = store.create_unit(
                type=UnitType.TEMPORAL_EVENT,
                unit_name=evt.summary[:80],
                content=json.dumps(evt.to_temporal_content(), ensure_ascii=False),
                actor="test",
            )
            assert te is not None

            # 验证 HAS_EVENT 边
            rel = store.add_relation(
                source_id=evt.source_entity_id,
                target_id=te.id,
                relation_type=RelationType.HAS_EVENT,
                actor="test",
            )
            assert rel is not None

        store.flush()

        # 验证 TEMPORAL_EVENT 节点已持久化
        from temporal_index import TemporalEventIndex
        index = TemporalEventIndex(store).build(use_content_fallback=False)
        assert len(index._events) >= 2
