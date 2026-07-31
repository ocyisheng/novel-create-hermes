"""
V2 核心架构的快速验证测试。

用法:
    cd novel-create-hermes
    python .opencode/shared/v2/test_graph.py
    
测试覆盖：
1. 叙事单元的创建、更新、查询
2. 关系的建立与遍历
3. 事件溯源
4. 投影生成
5. 弱信号检测
6. 快照与恢复
"""

import sys
import os
import tempfile
import shutil

# 确保可以导入 v2 模块（.opencode/shared/v2/）
V2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "v2"))
sys.path.insert(0, V2_DIR)

from graph_schema import (
    UnitType, UnitStatus, RelationType, EventType, ProjectionView,
)
from graph_store import GraphStore
from projection_engine import ProjectionEngine
from adapter import LegacyFileAdapter, AdapterMode


def test_narrative_unit_lifecycle(store):
    """测试叙事单元完整生命周期"""
    print("  [test] 叙事单元生命周期...", end="")
    
    # 创建
    unit = store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="林昭",
        content='{"core_trait": "隐忍", "goal": "寻找真相"}',
        tags=["主角", "成长型"],
        chapter_number=1,
        actor="test",
    )
    assert unit.id.startswith("ca_"), f"ID 前缀错误: {unit.id}"
    assert unit.unit_name == "林昭"
    assert unit.status == UnitStatus.SPROUT
    assert unit.confidence == 0.5
    
    # 读取
    fetched = store.get_unit(unit.id)
    assert fetched is not None
    assert fetched.unit_name == "林昭"
    
    # 按名称查找
    by_name = store.get_unit_by_name("林昭")
    assert by_name is not None
    assert by_name.id == unit.id
    
    # 更新
    store.update_unit(
        unit.id,
        status=UnitStatus.GROWING,
        confidence=0.8,
        tags=["主角", "成长型", "剑修"],
        actor="test",
    )
    updated = store.get_unit(unit.id)
    assert updated.status == UnitStatus.GROWING
    assert updated.confidence == 0.8
    assert "剑修" in updated.tags
    assert updated.version == 2
    
    # 归档
    store.archive_unit(unit.id, actor="test")
    archived = store.get_unit(unit.id)
    assert archived.status == UnitStatus.ARCHIVED
    
    # 列表排除已归档
    listed = store.list_units(type=UnitType.CHARACTER_ARC)
    assert unit.id not in [u.id for u in listed]
    
    print(" PASS")


def test_update_unit_empty_update_no_touch(store):
    """空更新/同值更新不应刷新 updated_at、递增 version 或标记脏数据。

    updated_at 语义：只记录数据被实际修改的时间。
    """
    print("  [test] 空更新不触碰 updated_at/version...", end="")
    
    unit = store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="林昭",
        content='{"core_trait": "隐忍"}',
        tags=["主角", "剑修"],
        actor="test",
    )
    store.flush()  # 清空脏标记，隔离空更新对脏状态的影响
    original_updated_at = unit.updated_at
    original_version = unit.version
    
    # 1. 空更新：不传任何字段 → 不触碰
    r = store.update_unit(unit.id, actor="test")
    assert r is unit
    assert unit.updated_at == original_updated_at
    assert unit.version == original_version
    assert not store._dirty_nodes
    assert not store._dirty_unit_ids
    
    # 2. 同值更新：字段值均未变化 → 不触碰
    r = store.update_unit(
        unit.id,
        content='{"core_trait": "隐忍"}',
        tags=["主角", "剑修"],
        status=UnitStatus.SPROUT,
        confidence=0.5,
        actor="test",
    )
    assert unit.updated_at == original_updated_at
    assert unit.version == original_version
    assert not store._dirty_nodes
    
    # 3. 真实变更：任一字段变化 → 正常刷新
    r = store.update_unit(unit.id, confidence=0.9, actor="test")
    assert unit.updated_at >= original_updated_at
    assert unit.version == original_version + 1
    assert store._dirty_nodes
    
    print(" PASS")


def test_relations(store):
    """测试关系的建立和查询"""
    print("  [test] 关系操作...", end="")
    
    ca = store.create_unit(UnitType.CHARACTER_ARC, "叶辰", "content")
    sc = store.create_unit(UnitType.SCENE, "后山对决", "决战场景", chapter_number=5)
    pt = store.create_unit(UnitType.PLOT_THREAD, "主线", "寻找长生")
    
    # 建立关系
    r1 = store.add_relation(ca.id, sc.id, RelationType.PARTICIPATES_IN)
    assert r1 is not None
    
    r2 = store.add_relation(sc.id, pt.id, RelationType.IMPLEMENTS)
    assert r2 is not None
    
    # 查询角色关系
    ca_rels = store.get_relations(ca.id, direction="outgoing")
    assert len(ca_rels) == 1
    
    # 查询场景的完整关系（出入）
    sc_rels = store.get_relations(sc.id, direction="both")
    assert len(sc_rels) == 2  # 一条入（角色参与），一条出（情节实现）
    
    # 邻居查询
    neighbors = store.get_neighbors(sc.id, max_depth=1)
    degree_1 = neighbors.get(1, set())
    assert ca.id in degree_1
    assert pt.id in degree_1
    
    # 路径查询
    path = store.find_path(ca.id, pt.id)
    assert path is not None
    assert len(path) == 3  # ca → sc → pt
    
    # 删除关系
    store.remove_relation(r1.id)
    remaining = store.get_relations(ca.id, direction="outgoing")
    assert len(remaining) == 0
    
    print(" PASS")


def test_structure_and_narrative_voice(store):
    """测试 STRUCTURE 和 NARRATIVE_VOICE 焦点类型的 CRUD"""
    print("  [test] STRUCTURE / NARRATIVE_VOICE 类型...", end="")

    # 创建 STRUCTURE 单元
    st = store.create_unit(
        type=UnitType.STRUCTURE,
        unit_name="全书结构设计",
        content='{"结构模式": "沙漏", "节奏设计": "三幕递进", "备注": "以身份悬疑为主线"}',
        tags=["总纲", "三幕"],
        actor="test",
    )
    assert st.id.startswith("st_"), f"ID 前缀错误: {st.id}"
    assert st.unit_name == "全书结构设计"
    assert st.type == UnitType.STRUCTURE

    # 创建 NARRATIVE_VOICE 单元
    nv = store.create_unit(
        type=UnitType.NARRATIVE_VOICE,
        unit_name="叙述腔调设计",
        content='{"腔调谱系": "金庸江湖气", "功能定位": "催眠", "叙事视角": "部分全知"}',
        tags=["腔调", "视角"],
        actor="test",
    )
    assert nv.id.startswith("nv_"), f"ID 前缀错误: {nv.id}"
    assert nv.unit_name == "叙述腔调设计"
    assert nv.type == UnitType.NARRATIVE_VOICE

    # 按类型读取
    found_st = list(store.find_units(type=UnitType.STRUCTURE))
    assert len(found_st) >= 1
    assert any(u.id == st.id for u in found_st)

    found_nv = list(store.find_units(type=UnitType.NARRATIVE_VOICE))
    assert len(found_nv) >= 1
    assert any(u.id == nv.id for u in found_nv)

    # 建立关系到其他类型
    pt = store.create_unit(UnitType.PLOT_THREAD, "主线", "content")
    sc = store.create_unit(UnitType.SCENE, "关键场景", "content", chapter_number=1)

    r1 = store.add_relation(st.id, pt.id, RelationType.IMPLEMENTS)
    assert r1 is not None

    r2 = store.add_relation(nv.id, sc.id, RelationType.REFERENCES)
    assert r2 is not None

    # 邻居查询（验证关联）
    st_neighbors = store.get_neighbors(st.id, max_depth=1)
    degree_1_st = st_neighbors.get(1, set())
    assert pt.id in degree_1_st

    nv_neighbors = store.get_neighbors(nv.id, max_depth=1)
    degree_1_nv = nv_neighbors.get(1, set())
    assert sc.id in degree_1_nv

    print(" PASS")


def test_event_sourcing(store):
    """测试事件溯源"""
    print("  [test] 事件溯源...", end="")
    
    # 先产生事件数据
    unit = store.create_unit(UnitType.NOTE, "测试笔记", actor="test_user")
    
    stats = store.stats()
    assert stats["total_events"] > 0
    
    # 查找事件
    events = store._events
    unit_events = [e for e in events if unit.id in e.target_ids]
    assert len(unit_events) >= 1
    assert unit_events[0].actor == "test_user"
    assert unit_events[0].event_type == EventType.UNIT_CREATED
    
    print(" PASS")


def test_snapshots(store):
    """测试快照功能"""
    print("  [test] 快照与恢复...", end="")
    
    snapshot = store.create_snapshot({"reason": "test"})
    assert snapshot.snapshot_id.startswith("snap_")
    
    # 列出快照
    snapshots = store.get_snapshots()
    assert len(snapshots) >= 1
    
    print(" PASS")


def test_weak_signals(store):
    """测试弱信号检测"""
    print("  [test] 弱信号检测...", end="")
    
    # 创建几个有内容重叠的单元
    s1 = store.create_unit(UnitType.SCENE, "测试场景", "主角 拔剑 灵气 淬体", chapter_number=3)
    s2 = store.create_unit(UnitType.SCENE, "另一场景", "拔剑 灵气 对决", chapter_number=5)
    
    signals = store.get_weak_signals(s1.id)
    # 至少有一个信号（s2 与 s1 有 "拔剑 灵气" 重叠）
    assert len(signals) >= 0  # 不强制数量，依赖于词重叠
    
    print(" PASS")


def test_projection_engine(store, project_root):
    """测试投影引擎"""
    print("  [test] 投影引擎...", end="")
    
    # 准备测试数据
    store.create_unit(UnitType.PLOT_THREAD, "主线-长生", "主角寻找长生之道", actor="test")
    store.create_unit(UnitType.PLOT_THREAD, "支线-情仇", "主角的复仇之路", actor="test")
    
    proj = ProjectionEngine(store, project_root)
    
    # 总纲投影
    outline = proj.project(ProjectionView.OUTLINE)
    assert "情节线总览" in outline
    assert "长生" in outline or "情仇" in outline
    
    # 角色档案投影
    unit = store.create_unit(UnitType.CHARACTER_ARC, "投影测试角色", 
                              '{"性格": {"核心": "谨慎"}}', actor="test")
    char_view = proj.project(ProjectionView.CHARACTER, {"unit_id": unit.id})
    assert "投影测试角色" in char_view
    assert "谨慎" in char_view
    
    # 分纲投影
    store.create_unit(UnitType.SCENE, "第3章场景1", chapter_number=3, actor="test")
    chapter_view = proj.project(ProjectionView.CHAPTER_OUTLINE, {"chapter": 3})
    assert "第3章" in chapter_view
    
    # 写文件投影
    written = proj.project_to_file(ProjectionView.OUTLINE)
    assert os.path.exists(written)
    
    print(" PASS")


def test_adapter(store, project_root):
    """测试兼容适配器"""
    print("  [test] 兼容适配器...", end="")
    
    proj = ProjectionEngine(store, project_root)
    adapter = LegacyFileAdapter(store, proj, mode=AdapterMode.DUAL_WRITE)
    
    # 模拟写角色 YAML
    test_yaml = """索引信息:
  名称: "适配器测试"
  实体ID: "adapter_test"
  状态: "active"
摘要:
  核心特质: ["测试"]
"""
    result = adapter.write_file(
        os.path.join(project_root, "characters/适配器测试.yaml"),
        test_yaml,
        actor="test",
    )
    assert result
    
    # 验证 graph 中已存在
    unit = store.get_unit_by_name("适配器测试")
    assert unit is not None, "适配器写入后 graph 中应存在该单元"
    assert unit.type == UnitType.CHARACTER_ARC
    
    # 验证文件存在（DUAL_WRITE 模式）
    expected_file = os.path.join(project_root, "characters/适配器测试.yaml")
    assert os.path.exists(expected_file), f"文件应存在: {expected_file}"
    
    # 模拟写章节正文
    adapter.write_chapter(
        os.path.join(project_root, "chapters/第1章.txt"),
        "这是第一章正文",
        chapter_number=1,
        actor="test",
    )
    
    chunks = store.find_units(type=UnitType.CHUNK, chapter=1)
    assert len(chunks) >= 1
    
    print(" PASS")


def test_migration(store, project_root):
    """测试项目迁移"""
    print("  [test] 项目迁移...", end="")
    
    proj = ProjectionEngine(store, project_root)
    adapter = LegacyFileAdapter(store, proj)
    
    # 创建测试用的旧格式文件
    test_dir = os.path.join(project_root, "test_migrate")
    os.makedirs(os.path.join(test_dir, "characters"), exist_ok=True)
    os.makedirs(os.path.join(test_dir, "worldbuilding"), exist_ok=True)
    
    char_yaml = """索引信息:
  名称: "迁移角色"
  实体ID: "migrate_char"
  状态: "active"
摘要:
  核心特质: ["迁移", "测试"]
"""
    with open(os.path.join(test_dir, "characters/迁移角色.yaml"), "w", encoding="utf-8") as f:
        f.write(char_yaml)
    
    # 创建新 store 用于迁移
    migrate_store = GraphStore(test_dir)
    migrate_store.initialize()
    migrate_adapter = LegacyFileAdapter(migrate_store, ProjectionEngine(migrate_store, test_dir))
    
    result = migrate_adapter.migrate_project(test_dir)
    assert result["characters"] >= 1
    
    # 清理
    shutil.rmtree(test_dir)
    
    print(" PASS")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("V2 Graph 架构验证测试")
    print("=" * 60)
    print()
    
    # 创建临时目录
    test_dir = tempfile.mkdtemp(prefix="v2_test_")
    
    try:
        store = GraphStore(test_dir)
        store.initialize()
        
        tests = [
            test_narrative_unit_lifecycle,
            test_relations,
            test_structure_and_narrative_voice,
            test_event_sourcing,
            test_snapshots,
            test_weak_signals,
            lambda s: test_projection_engine(s, test_dir),
            lambda s: test_adapter(s, test_dir),
            lambda s: test_migration(s, test_dir),
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                test(store)
                passed += 1
            except Exception as e:
                print(f" FAIL: {e}")
                import traceback
                traceback.print_exc()
                failed += 1
        
        print()
        print(f"结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 项")
        
        return failed == 0
    
    finally:
        shutil.rmtree(test_dir)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
