"""
V2 Session 层 + 编排层验证测试。
"""

import sys
import os
import tempfile
import shutil
import time

V2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "v2"))
sys.path.insert(0, V2_DIR)

from conftest import call_tool, assert_success
from graph_schema import UnitType, UnitStatus, RelationType
from graph_store import GraphStore
from session import (
    SessionManager, WritingSession, SessionPhase, SessionStatus,
    CycleType, EnergyLevel, FocusTarget, SessionAction,
)
from workspace import WorkspaceBuilder, Workspace


def test_session_lifecycle():
    """测试创作会话完整生命周期"""
    print("  [test] 会话生命周期...", end="")
    
    mgr = SessionManager("/tmp/test")
    
    # 开始会话
    session = mgr.start_session(
        focus_type=UnitType.SCENE,
        focus_unit_id="sc_test001",
        cycle_type=CycleType.EXPANSION,
    )
    assert session is not None
    assert session.status == SessionStatus.WARMING_UP
    assert session.focus.unit_id == "sc_test001"
    assert mgr.active_session is not None
    assert mgr.user_state.focus.unit_id == "sc_test001"
    
    # 记录动作
    action = session.start_action("write", "scene", "sc_test001")
    assert action.action == "write"
    assert len(session.timeline) == 1
    
    session.end_action(action, tokens=500, notes="写了第一个场景")
    assert action.tokens_generated == 500
    assert action.ended_at is not None
    
    # 暂停和恢复
    mgr.pause_session()
    assert session.status == SessionStatus.PAUSING
    
    resumed = mgr.resume_session()
    assert resumed is not None
    assert resumed.status == SessionStatus.DRAFTING
    
    # 结束会话
    mgr.end_session()
    assert mgr.active_session is None
    assert mgr.user_state.current_cycle == 2  # cycle 增加
    
    print(" PASS")


def test_cycle_type_draft_polish():
    """测试不同循环类型对模式推荐的影响"""
    print("  [test] 循环类型→模式推荐...", end="")
    
    mgr = SessionManager("/tmp/test")
    
    # 首次写作：推荐 warm
    mgr.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.EXPANSION)
    assert mgr.recommend_preheat_level() == "warm"
    mgr.end_session()
    
    # 精修：推荐 hot
    mgr.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.REFINEMENT)
    assert mgr.recommend_preheat_level() == "hot"
    mgr.end_session()
    
    # 第三次循环（cycle=3 > 1）：推荐 hot
    mgr.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.EXPANSION)
    assert mgr.user_state.current_cycle == 3
    assert mgr.recommend_preheat_level() == "hot"
    
    print(" PASS")


def test_energy_level_auto_detect():
    """测试精力水平自动推断"""
    print("  [test] 精力推断...", end="")
    
    mgr = SessionManager("/tmp/test")
    
    # 刚启动：high
    mgr.start_session(UnitType.SCENE, "sc_001")
    assert mgr.user_state.energy_level == EnergyLevel.HIGH
    mgr.end_session()
    
    # 模拟长时间会话
    mgr.start_session(UnitType.SCENE, "sc_001")
    import datetime
    mgr.user_state.current_session_start = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
    )
    assert mgr.user_state.energy_level == EnergyLevel.LOW
    
    print(" PASS")


def test_focus_shift():
    """测试焦点切换"""
    print("  [test] 焦点切换...", end="")
    
    mgr = SessionManager("/tmp/test")
    mgr.start_session(UnitType.SCENE, "sc_original")
    
    # 在会话内切换焦点
    mgr.shift_focus(UnitType.CHARACTER_ARC, "ca_new")
    assert mgr.user_state.focus.unit_id == "ca_new"
    assert mgr.user_state.focus.type == UnitType.CHARACTER_ARC
    
    # 会话焦点同步更新
    assert mgr.active_session.focus.unit_id == "ca_new"
    
    print(" PASS")


def test_intention_management():
    """测试意图管理"""
    print("  [test] 意图管理...", end="")
    
    mgr = SessionManager("/tmp/test")
    
    mgr.express_intention("想在第5章埋一把剑的伏笔", "写第3章时想到")
    mgr.express_intention("林昭的母亲可能还活着", "角色设计")
    
    unresolved = [i for i in mgr.user_state.expressed_intentions if not i.get("resolved")]
    assert len(unresolved) == 2
    
    mgr.resolve_intention("想在第5章埋一把剑的伏笔")
    unresolved = [i for i in mgr.user_state.expressed_intentions if not i.get("resolved")]
    assert len(unresolved) == 1
    
    print(" PASS")


def test_user_state_persistence():
    """测试用户状态持久化（写 7 字段 → 读 7 字段，全对称）

    修复前只断言 3 个字段（恰好是 load_user_state 恢复的那 3 个），
    精确掩盖了"写 7 读 3"的半持久化不对称。
    """
    print("  [test] 状态持久化...", end="")
    
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        mgr = SessionManager(tmpdir)
        mgr.user_state.recent_writing_days_last_7 = 4
        mgr.user_state.avg_session_minutes = 30
        mgr.user_state.current_cycle = 3
        mgr.user_state.current_cycle_type = CycleType.REFINEMENT
        mgr.user_state.focus = FocusTarget(type=UnitType.SCENE, unit_id="sc_001")
        mgr.user_state.add_intention("想在第5章埋一把剑的伏笔")
        mgr.user_state.active_session_id = "ses_abcdef123456"
        
        mgr.save_user_state()
        
        # 新建一个管理器并加载
        mgr2 = SessionManager(tmpdir)
        mgr2.load_user_state()
        
        assert mgr2.user_state.recent_writing_days_last_7 == 4
        assert mgr2.user_state.avg_session_minutes == 30
        assert mgr2.user_state.current_cycle == 3
        # 修复后：僵尸字段全部读回
        assert mgr2.user_state.current_cycle_type == CycleType.REFINEMENT
        assert mgr2.user_state.focus is not None
        assert mgr2.user_state.focus.unit_id == "sc_001"
        assert len(mgr2.user_state.expressed_intentions) == 1
        assert mgr2.user_state.expressed_intentions[0]["intention"] == "想在第5章埋一把剑的伏笔"
        assert mgr2.user_state.active_session_id == "ses_abcdef123456"
        
    finally:
        shutil.rmtree(tmpdir)
    
    print(" PASS")


def test_writing_session_serialization_roundtrip():
    """WritingSession to_json/from_json 往返对称"""
    print("  [test] 会话序列化往返...", end="")
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        mgr = SessionManager(tmpdir)
        s = mgr.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.EXPANSION)
        action = s.start_action("write", "scene", "sc_001")
        s.end_action(action, tokens=500, notes="写了第一个场景")
        s.output_text = "正文内容"
        s.new_unit_ids = ["u_001"]
        s.new_relation_ids = ["r_001"]
        s.cycle_number = 3

        restored = WritingSession.from_json(s.to_json())
        assert restored.id == s.id
        assert restored.status == s.status
        assert restored.phase == s.phase
        assert restored.focus == s.focus
        assert restored.cycle_type == s.cycle_type
        assert restored.cycle_number == 3
        assert restored.created_at == s.created_at
        assert restored.updated_at == s.updated_at
        assert restored.loaded_unit_ids == s.loaded_unit_ids
        assert len(restored.timeline) == 1
        assert restored.timeline[0].action == "write"
        assert restored.timeline[0].tokens_generated == 500
        assert restored.timeline[0].started_at == action.started_at
        assert restored.output_text == "正文内容"
        assert restored.new_unit_ids == ["u_001"]
        assert restored.new_relation_ids == ["r_001"]
    finally:
        shutil.rmtree(tmpdir)
    print(" PASS")


def test_active_session_persists_across_managers():
    """活跃会话跨 SessionManager 实例恢复（session.json 快照）"""
    print("  [test] 活跃会话跨实例恢复...", end="")
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        mgr1 = SessionManager(tmpdir)
        s1 = mgr1.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.EXPANSION)
        mgr1.save_user_state()

        # 全新实例（模拟下一次 handler 调用）
        mgr2 = SessionManager(tmpdir)
        mgr2.load_user_state()
        assert mgr2.active_session is not None
        assert mgr2.active_session.id == s1.id
        assert mgr2.active_session.focus.unit_id == "sc_001"
        assert mgr2.user_state.active_session_id == s1.id
        assert mgr2.user_state.focus.unit_id == "sc_001"

        # 快照文件存在
        snapshot = os.path.join(tmpdir, ".omo", "session.json")
        assert os.path.exists(snapshot)

        # end_session 清理快照
        mgr2.end_session()
        assert not os.path.exists(snapshot)
    finally:
        shutil.rmtree(tmpdir)
    print(" PASS")


def test_session_cross_call_persistence(tmp_project):
    """跨独立调用持久化：模拟编排层真实流程（每次 handler 调用 = 全新 SessionManager）。

    修复前：start 后新调用 info/set_cycle/set_phase 全部失败——
    session 状态根本不跨调用持久化（'没有活跃会话'）。
    """
    print("  [test] 跨调用持久化（start→新调用→info/set_cycle）...", end="")
    proj_path, _store = tmp_project

    # A1. session.start（独立调用 #1）
    r1 = call_tool("session.start", project=proj_path, focus_type="SCENE", id="sc_test001")
    assert_success(r1)
    session_id = r1["data"]["session_id"]
    assert session_id.startswith("ses_")

    # A2. session.info（独立调用 #2 —— 全新 SessionManager）
    r2 = call_tool("session.info", project=proj_path)
    assert_success(r2)
    assert r2["data"]["has_session"] is True
    assert r2["data"]["session_id"] == session_id
    assert r2["data"]["updated_at"] is not None

    # A3. session.set_cycle（独立调用 #3）
    r3 = call_tool("session.set_cycle", project=proj_path, cycle_type="refinement")
    assert_success(r3)
    assert r3["data"]["cycle_type"] == "refinement"

    # A4. session.set_phase（独立调用 #4）
    r4 = call_tool("session.set_phase", project=proj_path, phase="execute")
    assert_success(r4)
    assert r4["data"]["phase"] == "execute"

    # A5. 状态确实持久化（再次 info 读到 cycle_type/phase）
    r5 = call_tool("session.info", project=proj_path)
    assert_success(r5)
    assert r5["data"]["has_session"] is True
    assert r5["data"]["cycle_type"] == "refinement"
    assert r5["data"]["session_phase"] == "execute"

    # A6. user_state.yaml 中 cycle_type/active_session_id 已写入（不再只写 3 字段）
    import yaml
    with open(os.path.join(proj_path, ".omo", "user_state.yaml"), encoding="utf-8") as f:
        y = yaml.safe_load(f)
    assert y["current_cycle_type"] == "refinement"
    assert y["active_session_id"] == session_id

    print(" PASS")


def test_session_id_flows_to_graph_events(tmp_project):
    """session_id 贯穿 graph 写操作 → 事件归因（遥测链 session 分组的数据基础）"""
    print("  [test] session_id 贯穿写链路...", end="")
    proj_path, _store = tmp_project
    sid = "ses_testchain1234"

    r = call_tool("graph.create_unit", project=proj_path, unit_type="SCENE",
                  name="测试场景", content='{"synopsis":"测试"}',
                  actor="novel-v2-crafter", session_id=sid)
    assert_success(r)
    scene_id = r["data"]["id"]

    r2 = call_tool("graph.create_unit", project=proj_path, unit_type="CHARACTER_ARC",
                   name="测试角色", content='{"角色":"主角"}',
                   actor="novel-v2-crafter", session_id=sid)
    assert_success(r2)
    char_id = r2["data"]["id"]

    r3 = call_tool("graph.update_unit", project=proj_path, id=scene_id,
                   content='{"synopsis":"测试2"}', actor="novel-v2-crafter", session_id=sid)
    assert_success(r3)

    r4 = call_tool("graph.add_relation", project=proj_path, source=char_id, target=scene_id,
                   rel_type="participates_in", actor="novel-v2-crafter", session_id=sid)
    assert_success(r4)

    r5 = call_tool("graph.recent_events", project=proj_path, limit=10)
    assert_success(r5)
    events = r5["data"]["events"]
    write_events = [e for e in events
                    if e["event_type"] in ("unit_created", "unit_updated", "relation_added")]
    assert len(write_events) >= 4, f"expected >=4 write events, got {len(write_events)}"
    assert all(e.get("session_id") == sid for e in write_events)

    print(" PASS")


def test_workspace_builder_with_store():
    """测试工作空间构建（与 GraphStore 集成）"""
    print("  [test] 工作空间构建...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        # 创建测试数据
        scene = store.create_unit(
            UnitType.SCENE, "后山对决", "林渊与师父在后山练剑",
            chapter_number=5, actor="test",
        )
        char1 = store.create_unit(
            UnitType.CHARACTER_ARC, "林渊", '{"role": "主角"}',
            actor="test",
        )
        char2 = store.create_unit(
            UnitType.CHARACTER_ARC, "苏长老", '{"role": "师父"}',
            actor="test",
        )
        plot = store.create_unit(
            UnitType.PLOT_THREAD, "主线-长生", "寻找长生之道",
            actor="test",
        )
        world = store.create_unit(
            UnitType.WORLD_RULE, "灵气淬体", "九大境界",
            actor="test",
        )
        
        # 建立关系
        store.add_relation(char1.id, scene.id, RelationType.PARTICIPATES_IN)
        store.add_relation(char2.id, scene.id, RelationType.PARTICIPATES_IN)
        store.add_relation(scene.id, plot.id, RelationType.IMPLEMENTS)
        store.add_relation(scene.id, world.id, RelationType.REFERENCES)
        store.flush()
        
        # 构建工作空间
        builder = WorkspaceBuilder(store)
        ws = builder.build(scene.id, preheat_level="warm")
        
        # 验证
        assert ws.focus_unit is not None
        assert ws.focus_unit.unit_name == "后山对决"
        
        # 应该有 3 个直接关联（林渊、苏长老、主线）
        # 实际上有4个：char1, char2, plot, world
        # 但其中林渊和苏长老都是通过 PARTICIPATES_IN 关联到 scene
        # 而 scene 通过 IMPLEMENTS 关联到 plot，通过 REFERENCES 关联到 world
        
        assert len(ws.immediate_context) >= 3, f"Expected >=3 neighbors, got {len(ws.immediate_context)}"
        
        # 应该有角色信息
        char_names = [c.get("unit_name") for c in ws.character_arcs]
        assert "林渊" in char_names or any("林渊" in str(c) for c in ws.immediate_context)
        
        # 预热级别 warm 应该有情节线
        assert len(ws.plot_threads) >= 1 or any("主线" in str(c) for c in ws.immediate_context)
        
        # 验证 to_prompt_block 输出
        prompt = ws.to_prompt_block(preheat_level="warm")
        assert "后山对决" in prompt or "你正在写" in prompt
        assert "当前焦点" in prompt
        
        # 验证 cold 级别
        ws_cold = builder.build(scene.id, preheat_level="cold")
        prompt_cold = ws_cold.to_prompt_block(preheat_level="cold")
        assert len(prompt_cold) > 0
        
        # 验证 hot 级别包含弱信号
        ws_hot = builder.build(scene.id, preheat_level="hot")
        # 弱信号可能为空（测试数据词汇不重叠）
        assert ws_hot.completeness_score > 0
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_workspace_with_character_focus():
    """测试以角色为焦点时的工作空间"""
    print("  [test] 角色焦点工作空间...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        char = store.create_unit(UnitType.CHARACTER_ARC, "叶辰", 
                                  '{"trait": "果断"}', actor="test")
        sc1 = store.create_unit(UnitType.SCENE, "觉醒", chapter_number=1, actor="test")
        sc2 = store.create_unit(UnitType.SCENE, "复仇", chapter_number=5, actor="test")
        
        store.add_relation(char.id, sc1.id, RelationType.PARTICIPATES_IN)
        store.add_relation(char.id, sc2.id, RelationType.PARTICIPATES_IN)
        store.flush()
        
        builder = WorkspaceBuilder(store)
        ws = builder.build(char.id, preheat_level="warm")
        
        assert ws.focus_unit.unit_name == "叶辰"
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_preheat_recommendation():
    """测试预热级别推荐"""
    print("  [test] 预热推荐...", end="")
    
    mgr = SessionManager("/tmp/test")
    
    # 初始状态：cold
    assert mgr.recommend_preheat_level() == "cold"
    
    # 启动新会话（首次）：warm
    mgr.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.EXPANSION)
    assert mgr.recommend_preheat_level() == "warm"
    mgr.end_session()
    
    # 精修：hot
    mgr.start_session(UnitType.SCENE, "sc_001", cycle_type=CycleType.REFINEMENT)
    assert mgr.recommend_preheat_level() == "hot"
    mgr.end_session()
    
    print(" PASS")


def test_session_stats():
    """测试会话统计"""
    print("  [test] 会话统计...", end="")
    
    mgr = SessionManager("/tmp/test")
    
    # 多个会话
    for i in range(3):
        mgr.start_session(UnitType.SCENE, f"sc_{i}", cycle_type=CycleType.EXPANSION)
        action = mgr.active_session.start_action("write", "scene", f"sc_{i}")
        mgr.active_session.end_action(action, tokens=200 * (i + 1))
        mgr.end_session()
    
    stats = mgr.stats()
    assert stats["total_sessions"] == 3
    assert stats["user_state"]["cycle"] >= 3
    
    print(" PASS")


def run_all_tests():
    """运行所有 Session 层测试"""
    print("=" * 60)
    print("V2 Session 层 + 编排层验证测试")
    print("=" * 60)
    print()
    
    tests = [
        test_session_lifecycle,
        test_cycle_type_draft_polish,
        test_energy_level_auto_detect,
        test_focus_shift,
        test_intention_management,
        test_user_state_persistence,
        test_writing_session_serialization_roundtrip,
        test_active_session_persists_across_managers,
        test_session_cross_call_persistence,
        test_session_id_flows_to_graph_events,
        test_workspace_builder_with_store,
        test_workspace_with_character_focus,
        test_preheat_recommendation,
        test_session_stats,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f" FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 项")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
