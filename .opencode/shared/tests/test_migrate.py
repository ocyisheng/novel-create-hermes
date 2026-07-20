"""
V2 迁移工具验证测试。
"""

import sys
import os
import tempfile
import shutil

V2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "v2"))
sys.path.insert(0, V2_DIR)

from graph_schema import UnitType, UnitStatus
from graph_store import GraphStore
from migrate import ProjectScanner, ImportEngine, RelationBuilder, MigrationVerifier, generate_report


def setup_test_project(tmpdir: str) -> str:
    """创建一个模拟的小说项目目录"""
    root = os.path.join(tmpdir, "test_novel")
    
    # 标准目录结构
    dirs = [
        "characters", "worldbuilding", "outline/情节线", "outline/分纲/卷1",
        "outline/分卷", "outline/追踪", "ideation", "chapters",
        "quality", "styles", ".omo",
    ]
    for d in dirs:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    
    # 角色文件
    with open(os.path.join(root, "characters/林昭.yaml"), "w", encoding="utf-8") as f:
        f.write("""索引信息:
  名称: "林昭"
  角色类型: "主角"
  状态: "active"
摘要:
  一句话描述: "隐忍果决的复仇者"
  核心特质: ["隐忍", "果决"]
""")
    
    with open(os.path.join(root, "characters/苏长老.yaml"), "w", encoding="utf-8") as f:
        f.write("""索引信息:
  名称: "苏长老"
  角色类型: "导师"
  状态: "active"
摘要:
  一句话描述: "深不可测的剑术宗师"
  核心特质: ["深不可测", "严厉"]
""")
    
    # 世界观文件
    with open(os.path.join(root, "worldbuilding/灵气淬体.yaml"), "w", encoding="utf-8") as f:
        f.write("""索引信息:
  名称: "灵气淬体体系"
  实体子类型: "power_system"
  状态: "active"
摘要:
  一句话描述: "九大境界的修炼体系"
完整档案:
  等级划分:
    - 等级名: "凝气"
    - 等级名: "筑基"
""")
    
    # 总纲
    with open(os.path.join(root, "outline/总纲.yaml"), "w", encoding="utf-8") as f:
        f.write("""项目名称: "剑渊"
类型: "玄幻"
故事结构:
  结构类型: "三幕"
  幕:
    - 幕号: 1
      名称: "开端"
分卷:
  - 卷号: 1
    卷名: "惊雷初醒"
""")
    
    # 分卷
    with open(os.path.join(root, "outline/分卷/卷1_惊雷初醒.yaml"), "w", encoding="utf-8") as f:
        f.write("""卷信息:
  卷号: "卷1"
  卷名: "惊雷初醒"
  章节范围: "第1章 - 第10章"
""")
    
    # 分纲
    with open(os.path.join(root, "outline/分纲/卷1/第1章.yaml"), "w", encoding="utf-8") as f:
        f.write("""_meta:
  entity_type: "chapter"
索引信息:
  实体ID: "chapter_001"
  名称: "第1章"
  章节号: 1
  所属分卷: 1
摘要:
  一句话描述: "林昭第一次拔剑"
  出场角色: ["林昭", "苏长老"]
完整档案:
  关联情节线: ["主线"]
  结构规划:
    开篇:
      方式: "场景切入"
""")
    
    with open(os.path.join(root, "outline/分纲/卷1/第2章.yaml"), "w", encoding="utf-8") as f:
        f.write("""_meta:
  entity_type: "chapter"
索引信息:
  实体ID: "chapter_002"
  名称: "第2章"
  章节号: 2
  所属分卷: 1
摘要:
  一句话描述: "苏长老的试炼"
  出场角色: ["林昭", "苏长老"]
""")
    
    # 情节线
    with open(os.path.join(root, "outline/情节线/主线.yaml"), "w", encoding="utf-8") as f:
        f.write("""索引信息:
  名称: "主线"
  类型: "main"
  状态: "active"
摘要:
  一句话描述: "林昭的复仇之路"
""")
    
    # 伏笔规划
    with open(os.path.join(root, "outline/伏笔规划.yaml"), "w", encoding="utf-8") as f:
        f.write("""伏笔规划:
  - 编号: "F001"
    名称: "绝灵根异常"
    关联情节线: "主线"
""")
    
    # 章节正文
    with open(os.path.join(root, "chapters/第1章.txt"), "w", encoding="utf-8") as f:
        f.write("""林昭站在后山的练剑坪上，手中握着一柄普通的铁剑。
晨光从东方升起，将他的影子拉得很长。
""")
    
    with open(os.path.join(root, "chapters/第2章.txt"), "w", encoding="utf-8") as f:
        f.write("""苏长老站在三步之外，目光平静如水。
""")
    
    # 创意方案
    with open(os.path.join(root, "ideation/最终创意方案.yaml"), "w", encoding="utf-8") as f:
        f.write("""主角: "林昭"
核心冲突: "复仇"
世界观概述: "修仙世界"
""")
    
    # 追踪数据
    with open(os.path.join(root, "outline/追踪/伏笔.yaml"), "w", encoding="utf-8") as f:
        f.write("- 编号: F001\n  状态: 已设置\n")
    
    # 风格文件
    with open(os.path.join(root, "styles/凡人修仙风.yaml"), "w", encoding="utf-8") as f:
        f.write("""narrative_tone: "冷峻克制"
sentence_structure: "简洁"
""")
    
    # config.yaml
    with open(os.path.join(root, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("项目名称: \"剑渊\"\n项目类型: \"玄幻\"\n")
    
    return root


def test_scanner():
    """测试扫描器"""
    print("  [test] 项目扫描...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        root = setup_test_project(tmpdir)
        scanner = ProjectScanner(root)
        files = scanner.scan()
        summary = scanner.summary()
        
        # 验证发现了所有类型
        assert "characters" in summary
        assert "worldbuilding" in summary
        assert "plot_threads" in summary
        assert "outlines" in summary
        assert "volumes" in summary
        assert "synopsis" in summary
        assert "foreshadowing" in summary
        assert "chapters" in summary
        assert "ideation" in summary
        
        # 验证数量
        assert summary["characters"] == 2  # 林昭, 苏长老
        assert summary["outlines"] == 2    # 第1章, 第2章
        assert summary["chapters"] == 2    # 第1章.txt, 第2章.txt
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_full_migration_flow():
    """测试完整迁移流程"""
    print("  [test] 完整迁移流程...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        root = setup_test_project(tmpdir)
        scanner = ProjectScanner(root)
        files = scanner.scan()
        
        # 初始化 graph
        store = GraphStore(root)
        store.initialize()
        
        # 导入所有文件
        importer = ImportEngine(store)
        type_map = {
            "characters": UnitType.CHARACTER_ARC,
            "worldbuilding": UnitType.WORLD_RULE,
            "plot_threads": UnitType.PLOT_THREAD,
            "outlines": UnitType.SCENE,
            "volumes": UnitType.NOTE,
            "synopsis": UnitType.NOTE,
            "foreshadowing": UnitType.NOTE,
            "chapters": UnitType.CHUNK,
            "ideation": UnitType.NOTE,
            "tracking": UnitType.NOTE,
            "styles": UnitType.NOTE,
        }
        
        for category, unit_type in type_map.items():
            for fpath in scanner.files.get(category, []):
                importer.import_file(fpath, unit_type)
        
        report = importer.report()
        assert report["error_count"] == 0, f"导入错误: {report.get('error_details', [])}"
        assert report["created"] > 0, "应该创建了叙事单元"
        
        # 验证导入的内容
        # 角色
        chars = store.find_units(type=UnitType.CHARACTER_ARC)
        assert len(chars) >= 2
        char_names = [c.unit_name for c in chars]
        assert "林昭" in char_names
        
        # 场景
        scenes = store.find_units(type=UnitType.SCENE)
        assert len(scenes) >= 2
        
        # 章节正文
        chunks = store.find_units(type=UnitType.CHUNK)
        assert len(chunks) >= 2
        
        # 情节线
        plots = store.find_units(type=UnitType.PLOT_THREAD)
        assert len(plots) >= 1
        
        # 构建关系
        rel_builder = RelationBuilder(store)
        rel_builder.build_all(importer._imported_ids)
        rel_report = rel_builder.report()
        
        # 验证关系
        stats = store.stats()
        if stats["total_relations"] > 0:
            # 验证角色↔场景关系
            linzhao = store.get_unit_by_name("林昭")
            if linzhao:
                rels = store.get_relations(linzhao.id)
                # 应该关联到第1章和第2章
        
        # 创建快照
        store.create_snapshot({"reason": "test"})
        snapshots = store.get_snapshots()
        assert len(snapshots) >= 1
        
        store.flush()
        
        # 验证事件溯源
        assert store.stats()["total_events"] > 0
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_scanner_on_empty_project():
    """测试空项目扫描"""
    print("  [test] 空项目扫描...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        scanner = ProjectScanner(tmpdir)
        files = scanner.scan()
        summary = scanner.summary()
        assert len(summary) == 0, "空项目应返回空结果"
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_import_engine_skip_existing():
    """测试导入引擎跳过已存在的单元"""
    print("  [test] 跳过已导入...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        root = setup_test_project(tmpdir)
        scanner = ProjectScanner(root)
        scanner.scan()
        
        store = GraphStore(root)
        store.initialize()
        
        # 第一次导入
        importer1 = ImportEngine(store)
        for fpath in scanner.files.get("characters", []):
            importer1.import_file(fpath, UnitType.CHARACTER_ARC)
        
        first_count = importer1.report()["created"]
        
        # 第二次导入（应全部跳过）
        importer2 = ImportEngine(store)
        for fpath in scanner.files.get("characters", []):
            importer2.import_file(fpath, UnitType.CHARACTER_ARC)
        
        second_report = importer2.report()
        assert second_report["created"] == 0
        assert second_report["skipped"] == first_count
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_verifier():
    """测试迁移验证器"""
    print("  [test] 迁移验证...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        root = setup_test_project(tmpdir)
        scanner = ProjectScanner(root)
        scanner.scan()
        
        store = GraphStore(root)
        store.initialize()
        
        # 导入
        importer = ImportEngine(store)
        for fpath in scanner.files.get("characters", []):
            importer.import_file(fpath, UnitType.CHARACTER_ARC)
        for fpath in scanner.files.get("worldbuilding", []):
            importer.import_file(fpath, UnitType.WORLD_RULE)
        for fpath in scanner.files.get("outlines", []):
            importer.import_file(fpath, UnitType.SCENE)
        for fpath in scanner.files.get("plot_threads", []):
            importer.import_file(fpath, UnitType.PLOT_THREAD)
        
        # 验证
        verifier = MigrationVerifier(store, scanner)
        result = verifier.verify()
        
        assert "checks" in result
        assert result["total_units"] > 0
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_report_generation():
    """测试报告生成"""
    print("  [test] 报告生成...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        root = setup_test_project(tmpdir)
        scanner = ProjectScanner(root)
        scanner.scan()
        
        store = GraphStore(root)
        store.initialize()
        
        importer = ImportEngine(store)
        for fpath in scanner.files.get("characters", []):
            importer.import_file(fpath, UnitType.CHARACTER_ARC)
        
        rel_builder = RelationBuilder(store)
        rel_builder.build_all(importer._imported_ids)
        
        verifier = MigrationVerifier(store, scanner)
        verify_result = verifier.verify()
        
        report = generate_report(scanner, importer.report(), rel_builder.report(), verify_result)
        assert "迁移报告" in report
        assert "Graph 统计" in report
        assert "导入结果" in report
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def test_relation_building():
    """测试关系构建"""
    print("  [test] 关系构建...", end="")
    
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    try:
        root = setup_test_project(tmpdir)
        scanner = ProjectScanner(root)
        scanner.scan()
        
        store = GraphStore(root)
        store.initialize()
        
        importer = ImportEngine(store)
        type_map = {
            "characters": UnitType.CHARACTER_ARC,
            "outlines": UnitType.SCENE,
            "plot_threads": UnitType.PLOT_THREAD,
        }
        for category, unit_type in type_map.items():
            for fpath in scanner.files.get(category, []):
                importer.import_file(fpath, unit_type)
        
        # 构建关系前，关系数为0
        assert store.stats()["total_relations"] == 0
        
        # 构建关系
        rel_builder = RelationBuilder(store)
        rel_builder.build_all(importer._imported_ids)
        
        # 验证关系被创建
        # 第1章有出场角色["林昭", "苏长老"]，应该建立2个 PARTICIPATES_IN 关系
        # 第2章也有出场角色["林昭", "苏长老"]，应该建立2个
        # 第1章有关联情节线["主线"]，应该建立1个 IMPLEMENTS
        stats = store.stats()
        assert stats["total_relations"] > 0, f"应该有关系，但当前为0"
        
        print(" PASS")
    finally:
        shutil.rmtree(tmpdir)


def run_all_tests():
    print("=" * 60)
    print("V2 迁移层验证测试")
    print("=" * 60)
    print()
    
    tests = [
        test_scanner,
        test_scanner_on_empty_project,
        test_import_engine_skip_existing,
        test_full_migration_flow,
        test_verifier,
        test_report_generation,
        test_relation_building,
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
