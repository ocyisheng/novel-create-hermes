"""
V2 查询层（QUERY 协议）验证测试。
"""

import sys
import os
import tempfile
import shutil

V2_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, V2_DIR)

from graph_schema import UnitType, UnitStatus, RelationType
from graph_store import GraphStore
from query import (
    QueryType, QueryRequest, QueryResult,
    parse_query, extract_all_queries, strip_queries,
    QueryHandlerRegistry,
)
from orchestrator import V2Orchestrator, UserIntent


def test_parse_query():
    """测试 QUERY 解析"""
    print("  [test] QUERY 解析...", end="")
    
    # 标准格式
    q = parse_query('QUERY: character_background(name="林渊")')
    assert q is not None
    assert q.query_type == QueryType.CHARACTER_BACKGROUND
    assert q.params.get("name") == "林渊"
    
    # 数字参数
    q = parse_query('QUERY: advanced_search(keywords=["剑"], limit=5)')
    assert q is not None
    assert q.query_type == QueryType.ADVANCED_SEARCH
    assert "剑" in q.params.get("keywords", [])
    assert q.params.get("limit") == 5
    
    # 无参数
    q = parse_query("QUERY: plot_thread_summary()")
    assert q is not None
    assert q.query_type == QueryType.PLOT_THREAD_SUMMARY
    assert q.params == {}
    
    # 多参数
    q = parse_query('QUERY: scene_detail(scene_id="sc_001", name="test")')
    assert q is not None
    assert q.params.get("scene_id") == "sc_001"
    assert q.params.get("name") == "test"
    
    # 无效类型
    q = parse_query("QUERY: invalid_type()")
    assert q is None
    
    # 无 QUERY
    q = parse_query("这是普通文本，不含QUERY")
    assert q is None
    
    print(" PASS")


def test_extract_queries():
    """测试从文本中提取 QUERY"""
    print("  [test] 提取 QUERY...", end="")
    
    text = """我写了这段文字。
QUERY: character_background(name="林渊")
继续写作...
QUERY: scene_detail(scene_id="sc_001")
结束。"""
    
    queries = extract_all_queries(text)
    assert len(queries) == 2
    assert queries[0].query_type == QueryType.CHARACTER_BACKGROUND
    assert queries[1].query_type == QueryType.SCENE_DETAIL
    
    # 测试 strip
    cleaned = strip_queries(text)
    assert "QUERY: character_background" not in cleaned
    assert "我写了这段文字" in cleaned
    assert "继续写作" in cleaned
    
    print(" PASS")


def test_character_background_handler():
    """测试角色背景查询处理器"""
    print("  [test] 角色背景查询...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        # 创建测试数据
        unit = store.create_unit(
            UnitType.CHARACTER_ARC, "林渊",
            '{"trait": "隐忍", "goal": "复仇"}',
            tags=["主角", "剑修"],
            actor="test",
        )
        sc1 = store.create_unit(UnitType.SCENE, "后山练剑", belongs_to_chapter=1, actor="test")
        sc2 = store.create_unit(UnitType.SCENE, "初露锋芒", belongs_to_chapter=3, actor="test")
        store.add_relation(unit.id, sc1.id, RelationType.PARTICIPATES_IN)
        store.add_relation(unit.id, sc2.id, RelationType.PARTICIPATES_IN)
        store.flush()
        
        registry = QueryHandlerRegistry(store, tmpdir)
        
        # 查询存在的角色
        req = QueryRequest(QueryType.CHARACTER_BACKGROUND, {"name": "林渊"})
        result = registry.handle(req)
        assert result.success
        assert "林渊" in result.summary
        assert result.source_ids == [unit.id]
        
        # 查询不存在的角色
        req = QueryRequest(QueryType.CHARACTER_BACKGROUND, {"name": "不存在"})
        result = registry.handle(req)
        assert not result.success
        
        # 缺少参数
        req = QueryRequest(QueryType.CHARACTER_BACKGROUND, {})
        result = registry.handle(req)
        assert not result.success
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_scene_detail_handler():
    """测试场景细节查询处理器"""
    print("  [test] 场景细节查询...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        sc = store.create_unit(
            UnitType.SCENE, "后山对决", "林渊与苏长老在后山练剑坪对决",
            belongs_to_chapter=5, actor="test",
        )
        char = store.create_unit(UnitType.CHARACTER_ARC, "林渊", actor="test")
        store.add_relation(char.id, sc.id, RelationType.PARTICIPATES_IN)
        store.flush()
        
        registry = QueryHandlerRegistry(store, tmpdir)
        
        # 按 ID 查
        req = QueryRequest(QueryType.SCENE_DETAIL, {"scene_id": sc.id})
        result = registry.handle(req)
        assert result.success
        assert "后山对决" in result.summary
        
        # 按名称查
        req = QueryRequest(QueryType.SCENE_DETAIL, {"name": "后山对决"})
        result = registry.handle(req)
        assert result.success
        
        # 显示关联角色
        assert "林渊" in result.content
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_style_check_handler():
    """测试风格检查"""
    print("  [test] 风格检查...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        registry = QueryHandlerRegistry(store, tmpdir)
        
        # 干净文本
        req = QueryRequest(QueryType.STYLE_CHECK, {"text": "林渊握紧了剑柄，指节泛白。"})
        result = registry.handle(req)
        assert result.success
        assert "通过" in result.summary
        
        # 包含语言尸体的文本
        req = QueryRequest(QueryType.STYLE_CHECK, {
            "text": "暮色从四面八方袭来，空气仿佛凝固了。"
        })
        result = registry.handle(req)
        assert result.success
        assert "语言尸体" in result.summary or "检测" in result.content
        
        # 缺少参数
        req = QueryRequest(QueryType.STYLE_CHECK, {})
        result = registry.handle(req)
        assert not result.success
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_advanced_search_handler():
    """测试高级搜索"""
    print("  [test] 高级搜索...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        store.create_unit(UnitType.CHARACTER_ARC, "林渊", "擅长剑法的隐忍主角", tags=["主角"], actor="test")
        store.create_unit(UnitType.WORLD_RULE, "灵气淬体", "九大境界的修炼体系", actor="test", 
                          extra={"境界": ["凝气", "筑基", "金丹"]})
        store.create_unit(UnitType.SCENE, "后山练剑", "林渊在后山练剑", belongs_to_chapter=1, actor="test")
        store.flush()
        
        registry = QueryHandlerRegistry(store, tmpdir)
        
        # 搜索关键词
        req = QueryRequest(QueryType.ADVANCED_SEARCH, {"keywords": ["剑", "林渊"]})
        result = registry.handle(req)
        assert result.success
        assert result.data is None  # 正常，我们没有在data字段放数据，只放在了content
        
        # 按类型筛选
        req = QueryRequest(QueryType.ADVANCED_SEARCH, {"keywords": ["剑"], "type": "character_arc"})
        result = registry.handle(req)
        assert result.success
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_plot_thread_handler():
    """测试情节线查询"""
    print("  [test] 情节线查询...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        pt = store.create_unit(UnitType.PLOT_THREAD, "主线-长生", "主角寻找长生之道", actor="test")
        sc = store.create_unit(UnitType.SCENE, "觉醒", belongs_to_chapter=1, actor="test")
        store.add_relation(sc.id, pt.id, RelationType.IMPLEMENTS)
        store.flush()
        
        registry = QueryHandlerRegistry(store, tmpdir)
        
        # 按名称
        req = QueryRequest(QueryType.PLOT_THREAD_SUMMARY, {"name": "主线-长生"})
        result = registry.handle(req)
        assert result.success
        assert "觉醒" in result.content or "1" in result.content
        
        # 列表
        req = QueryRequest(QueryType.PLOT_THREAD_SUMMARY, {})
        result = registry.handle(req)
        assert result.success
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_chapter_status_handler():
    """测试章节状态查询"""
    print("  [test] 章节状态查询...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        store = GraphStore(tmpdir)
        store.initialize()
        
        store.create_unit(UnitType.SCENE, "觉醒", belongs_to_chapter=1, actor="test")
        store.create_unit(UnitType.SCENE, "试炼", belongs_to_chapter=1, actor="test")
        store.create_unit(UnitType.SCENE, "下山", belongs_to_chapter=2, actor="test")
        store.flush()
        
        registry = QueryHandlerRegistry(store, tmpdir)
        
        # 指定章节
        req = QueryRequest(QueryType.CHAPTER_STATUS, {"number": 1})
        result = registry.handle(req)
        assert result.success
        assert "2 个场景" in result.content or "2" in result.content
        
        # 全局
        req = QueryRequest(QueryType.CHAPTER_STATUS, {})
        result = registry.handle(req)
        assert result.success
        assert "2 章" in result.content or "2" in result.content
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_orchestrator_query_integration():
    """测试编排器 QUERY 集成"""
    print("  [test] 编排器 QUERY 集成...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        orch = V2Orchestrator(tmpdir)
        
        # 创建测试数据
        orch.store.create_unit(
            UnitType.CHARACTER_ARC, "林昭",
            '{"trait": "果断"}', tags=["主角"],
            actor="test",
        )
        orch.store.flush()
        
        # 启动会话
        decision = orch.decide("写第3章")
        result = orch.execute_decision(decision)
        assert result["session"] is not None
        
        # 模拟子 Agent 返回 QUERY
        agent_response = """林昭握紧了剑。
QUERY: character_background(name="林昭")
他看向远方。"""
        
        clean_text, records = orch.process_subagent_response(agent_response)
        
        # 验证 QUERY 被处理
        assert len(records) == 1
        assert records[0]["success"]
        assert records[0]["query_type"] == "character_background"
        assert "林昭" in records[0]["summary"]
        
        # 验证正文被剥离
        assert "QUERY:" not in clean_text
        assert "林昭握紧了剑" in clean_text
        assert "他看向远方" in clean_text
        
        # 验证 session 上下文有注入
        assert orch.sessions.active_session is not None
        has_query_ctx = any(
            k.startswith("query_") for k in orch.sessions.active_session.session_context.keys()
        )
        assert has_query_ctx
        
        # 验证 get_query_prompt_block 输出
        prompt = orch.get_query_prompt_block()
        assert "上下文查询服务" in prompt
        assert "支持" in prompt
        
        # 统计
        stats = orch.get_query_stats()
        assert stats["total_queries"] == 1
        assert stats["success"] == 1
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_multiple_queries_in_one_response():
    """测试一个回复中包含多个 QUERY"""
    print("  [test] 多 QUERY 处理...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        orch = V2Orchestrator(tmpdir)
        orch.store.create_unit(UnitType.CHARACTER_ARC, "叶辰", actor="test")
        orch.store.create_unit(UnitType.SCENE, "决战", belongs_to_chapter=10, actor="test")
        orch.store.flush()
        orch.sessions.start_session(UnitType.SCENE, "sc_test")
        
        response = """叶辰拔出了剑。
QUERY: character_background(name="叶辰")
QUERY: scene_detail(name="决战")
战斗开始。"""
        
        clean_text, records = orch.process_subagent_response(response)
        assert len(records) == 2
        assert all(r["success"] for r in records)
        assert "QUERY:" not in clean_text
        
        stats = orch.get_query_stats()
        assert stats["total_queries"] == 2
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_failed_query_handling():
    """测试查询失败处理"""
    print("  [test] 查询失败处理...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        orch = V2Orchestrator(tmpdir)
        orch.sessions.start_session(UnitType.SCENE, "sc_001")
        
        response = """继续写。
QUERY: character_background(name="不存在的人")
结束。"""
        
        clean_text, records = orch.process_subagent_response(response)
        assert len(records) == 1
        assert not records[0]["success"]
        assert "不存在" in records[0].get("error", "")
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def run_all_tests():
    """运行所有 Query 层测试"""
    print("=" * 60)
    print("V2 Query 层验证测试")
    print("=" * 60)
    print()
    
    tests = [
        test_parse_query,
        test_extract_queries,
        test_character_background_handler,
        test_scene_detail_handler,
        test_style_check_handler,
        test_advanced_search_handler,
        test_plot_thread_handler,
        test_chapter_status_handler,
        test_orchestrator_query_integration,
        test_multiple_queries_in_one_response,
        test_failed_query_handling,
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
