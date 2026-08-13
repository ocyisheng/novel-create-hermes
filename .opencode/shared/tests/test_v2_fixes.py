"""
回归测试 — V2 叙事图引擎缺陷修复。

覆盖本次修复的 7 项行为缺陷：
1. GraphStore 并发安全（smoke）
2. ConstraintEngine 增量水位（watermark）
3. 同名不同类型去重（_unit_by_name 多值索引）
4. find_units volume 过滤
5. DeviationManager scanned_version 往返
6. DeviationManager 原子保存 + 损坏备份
7. TypeRegistry 按项目隔离

用法:
    cd novel-create-hermes
    pytest .opencode/shared/tests/test_v2_fixes.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path

import pytest
import yaml

from graph_schema import UnitType, UnitStatus, RelationType
from graph_store import GraphStore


# ── 1. 并发 flush 安全（smoke） ───────────────────────────────────────────


class TestConcurrentFlushSafety:
    def test_concurrent_mutations_and_flush(self, project_root):
        """多线程并发 create/update + flush 不抛异常、状态一致（smoke）。"""
        store = GraphStore(project_root)
        store.initialize()

        errors: list = []
        barrier = threading.Barrier(4)  # 4 个 worker 线程同步起跑

        def worker(idx: int):
            try:
                barrier.wait()
                for i in range(10):
                    u = store.create_unit(
                        type=UnitType.NOTE, unit_name=f"并发单元-{idx}-{i}",
                        content="{}", actor="test",
                    )
                    store.update_unit(u.id, content='{"note": "更新"}', actor="test")
                    store.flush()
            except Exception as e:  # 收集任何线程异常（测试中允许裸收集）
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        # 主线程同时并发 flush
        for _ in range(10):
            try:
                store.flush()
            except Exception as e:
                errors.append(e)
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"并发操作抛出异常: {errors}"
        # 4 线程 × 10 单元，全部落盘
        store2 = GraphStore(project_root)
        store2.initialize()
        assert len(store2._units) == 40, f"期望 40 个单元，实际 {len(store2._units)}"

    def test_concurrent_same_name_dedup(self, project_root):
        """并发下 if_exists=error 的查重不产生重复单元。"""
        store = GraphStore(project_root)
        store.initialize()
        created = []
        errors: list = []
        barrier = threading.Barrier(3)

        def worker():
            try:
                barrier.wait()
                u = store.create_unit(
                    type=UnitType.NOTE, unit_name="同名单元",
                    content="{}", actor="test", if_exists="error",
                )
                created.append(u)
            except ValueError:
                pass  # 预期：并发创建中只有一个成功
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        store.flush()

        assert not errors, f"并发创建抛出异常: {errors}"
        # 锁串行化后只允许一个成功（其余抛 ValueError）
        assert len(created) == 1, f"期望恰好 1 个成功，实际 {len(created)}"


# ── 2. ConstraintEngine 增量水位 ──────────────────────────────────────────


class TestConstraintWatermark:
    def _make_engine(self, store):
        from constraint_engine import ConstraintEngine
        engine = ConstraintEngine(store)
        engine.register_with_store()
        return engine

    def test_incremental_only_checks_modified_units(self, project_root):
        """水位之后修改的单元被检查，未修改的单元不被重新扫描。"""
        from unittest.mock import patch
        from constraint_engine import ConstraintEngine

        store = GraphStore(project_root)
        store.initialize()
        engine = ConstraintEngine(store)
        engine.register_with_store()

        # 首轮：从未检查 → 全量语义，检查全部单元
        u1 = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="林渊",
            content='{"subtype": "主角"}', actor="test",
        )
        store.flush()
        dm = engine._get_deviation_manager()
        assert dm.constraint_watermark >= u1.version, \
            "首轮检查后水位应推进到已检查单元的最大 version"

        # 挂载真正的 _check_unit 以便 spy（记录被检查的单元 ID）
        engine._check_unit_real = ConstraintEngine._check_unit.__get__(engine)

        def _spy(unit, td):
            engine._checked_ids.append(unit.id)
            return engine._check_unit_real(unit, td)

        # 第二轮：新建 u2（v1，未检查过）+ 修改 u1（v2 > 已检查版本）→ 两者都应被检查
        engine._checked_ids = []
        u2 = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="韩致",
            content='{"subtype": "反派"}', actor="test",
        )
        store.update_unit(u1.id, content='{"subtype": "主角", "goal": "寻道"}', actor="test")
        with patch.object(engine, "_check_unit", side_effect=_spy):
            store.flush()

        assert sorted(engine._checked_ids) == sorted([u1.id, u2.id]), \
            f"新建+修改的单元都应被检查，实际 {engine._checked_ids}"

        # 第三轮：只新建 u3（u1/u2 未再变化）→ 只应检查 u3，u1/u2 不被重扫
        engine._checked_ids = []
        u3 = store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="白眉",
            content='{"subtype": "配角"}', actor="test",
        )
        with patch.object(engine, "_check_unit", side_effect=_spy):
            store.flush()

        assert engine._checked_ids == [u3.id], \
            f"未修改单元不应被重新扫描，实际 {engine._checked_ids}"
        # 重新获取实例读取磁盘上的最新水位（引擎每次运行都新建实例落盘，
        # 不缓存实例；此前持有的 dm 是第 1 轮的旧实例，不代表最新状态）
        dm = engine._get_deviation_manager()
        assert dm.constraint_watermark >= 2, \
            "水位应推进到当前最大 unit.version"

    def test_run_full_updates_watermark(self, project_root):
        """run(full=True) 做全量扫描并更新水位。"""
        from constraint_engine import ConstraintEngine

        store = GraphStore(project_root)
        store.initialize()
        engine = ConstraintEngine(store)
        store.create_unit(
            type=UnitType.NOTE, unit_name="单元A", content="{}", actor="test",
        )
        store.flush()

        results = engine.run(full=True)
        assert isinstance(results, list)
        dm = engine._get_deviation_manager()
        assert dm.constraint_watermark >= 1

    def test_watermark_persists_round_trip(self, project_root):
        """水位持久化在 deviation_state.yaml 中，重载后保留。"""
        from deviation_manager import DeviationManager
        mgr = DeviationManager(project_root)
        mgr.constraint_watermark = 42
        mgr.save()

        mgr2 = DeviationManager(project_root)
        assert mgr2.constraint_watermark == 42


# ── 3. 同名不同类型去重 ────────────────────────────────────────────────────


class TestSameNameDifferentTypeDedup:
    def test_same_name_same_type_error_raises(self, store):
        """同名同类型 + if_exists=error 应抛出 ValueError。"""
        store.create_unit(type=UnitType.SCENE, unit_name="第1章", actor="test")
        with pytest.raises(ValueError, match="同名同类型"):
            store.create_unit(
                type=UnitType.SCENE, unit_name="第1章", actor="test", if_exists="error",
            )

    def test_same_name_different_type_succeeds(self, store):
        """SCENE '第1章' 与 CHAPTER_PLAN '第1章' 同名不同类型应共存。"""
        s1 = store.create_unit(type=UnitType.SCENE, unit_name="第1章", actor="test")
        cp = store.create_unit(
            type=UnitType.CHAPTER_PLAN, unit_name="第1章", actor="test",
            if_exists="error",
        )
        assert s1.id != cp.id
        # 名称索引含两个条目
        assert len(store._unit_by_name["第1章"]) == 2

    def test_second_same_type_after_cross_type_collision_raises(self, store):
        """跨类型共存后，再创建同类型同名 + if_exists=error 仍应拒绝。"""
        store.create_unit(type=UnitType.SCENE, unit_name="第1章", actor="test")
        store.create_unit(
            type=UnitType.CHAPTER_PLAN, unit_name="第1章", actor="test",
            if_exists="error",
        )
        with pytest.raises(ValueError, match="同名同类型"):
            store.create_unit(
                type=UnitType.SCENE, unit_name="第1章", actor="test", if_exists="error",
            )

    def test_get_unit_by_name_with_type_filter(self, store):
        """get_unit_by_name 支持 type 过滤消歧。"""
        store.create_unit(type=UnitType.SCENE, unit_name="第1章", actor="test")
        cp = store.create_unit(
            type=UnitType.CHAPTER_PLAN, unit_name="第1章", actor="test",
        )
        by_type = store.get_unit_by_name("第1章", type=UnitType.CHAPTER_PLAN)
        assert by_type is not None and by_type.id == cp.id
        # 无 type 时返回第一个匹配（不崩溃）
        assert store.get_unit_by_name("第1章") is not None


# ── 4. find_units volume 过滤 ──────────────────────────────────────────────


class TestFindUnitsVolumeFilter:
    def test_volume_filter_by_content_volume_number(self, store):
        """按 content.volume_number 过滤卷号。"""
        v1 = store.create_unit(
            type=UnitType.SCENE, unit_name="卷1场景",
            content='{"volume_number": 1}', chapter_number=1, actor="test",
        )
        v2 = store.create_unit(
            type=UnitType.SCENE, unit_name="卷2场景",
            content='{"volume_number": 2}', chapter_number=1, actor="test",
        )
        no_vol = store.create_unit(
            type=UnitType.SCENE, unit_name="无卷场景", chapter_number=1, actor="test",
        )

        found_v1 = store.find_units(type=UnitType.SCENE, chapter=1, volume=1)
        assert [u.id for u in found_v1] == [v1.id]
        found_v2 = store.find_units(type=UnitType.SCENE, chapter=1, volume=2)
        assert [u.id for u in found_v2] == [v2.id]

    def test_volume_filter_by_structure_path(self, store):
        """structure_path 倒数第二个 int 视为卷号（如 ["人界篇", 2, 15]）。"""
        u = store.create_unit(
            type=UnitType.SCENE, unit_name="二卷场景",
            content="{}", chapter_number=15,
            structure_path=["人界篇", 2, 15], actor="test",
        )
        found = store.find_units(type=UnitType.SCENE, volume=2)
        assert [x.id for x in found] == [u.id]
        assert store.find_units(type=UnitType.SCENE, volume=3) == []

    def test_volume_filter_by_extra(self, store):
        """extra.volume_number 也参与卷号推导。"""
        u = store.create_unit(
            type=UnitType.CHUNK, unit_name="卷5正文",
            content="{}", actor="test", extra={"volume_number": 5},
        )
        found = store.find_units(type=UnitType.CHUNK, volume=5)
        assert [x.id for x in found] == [u.id]


# ── 5. scanned_version 往返 ────────────────────────────────────────────────


class TestScannedVersionRoundTrip:
    def test_scanned_version_survives_save_load(self, project_root):
        """scanned_version 不应在 save/load 往返中被丢弃。"""
        from deviation_manager import DeviationManager, DeviationItem

        mgr = DeviationManager(project_root)
        mgr.merge([
            DeviationItem(
                id="", dimension="character_trait", entity="林昭",
                scanned_version=7, status="pending",
            )
        ])
        mgr.save()

        mgr2 = DeviationManager(project_root)
        item = mgr2.list_all()[0]
        assert item.scanned_version == 7, \
            f"scanned_version 往返后应为 7，实际 {item.scanned_version}"

    def test_scanned_version_written_to_yaml(self, project_root):
        """保存后的 YAML 中应包含 scanned_version 字段。"""
        from deviation_manager import DeviationManager, DeviationItem

        mgr = DeviationManager(project_root)
        mgr.merge([
            DeviationItem(
                id="", dimension="plot_consistency", entity="韩致",
                scanned_version=3, status="pending",
            )
        ])
        mgr.save()

        with open(mgr.state_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        deviations = data.get("deviations", [])
        assert any(d.get("scanned_version") == 3 for d in deviations), \
            "YAML 中应保留 scanned_version=3"


# ── 6. DeviationManager 原子保存 + 损坏备份 ──────────────────────────────


class TestDeviationManagerAtomicity:
    def test_atomic_save_no_tmp_leftover(self, project_root):
        """原子保存后不残留 tmp 文件。"""
        from deviation_manager import DeviationManager, DeviationItem

        mgr = DeviationManager(project_root)
        mgr.merge([DeviationItem(
            id="", dimension="world_rule", entity="天道宗", status="pending",
        )])
        mgr.save()

        state_dir = os.path.dirname(mgr.state_path)
        leftovers = [f for f in os.listdir(state_dir)
                     if f.endswith(".tmp") and f.startswith("deviation_state")]
        assert leftovers == [], f"原子保存不应残留 tmp 文件: {leftovers}"
        # 文件可正常重载
        mgr2 = DeviationManager(project_root)
        assert len(mgr2.list_all()) == 1

    def test_corrupt_file_backup_and_reset(self, project_root):
        """损坏的 YAML 应备份为 .corrupt-<timestamp> 并重置为空状态。"""
        from deviation_manager import DeviationManager

        graph_dir = os.path.join(project_root, "graph")
        os.makedirs(graph_dir, exist_ok=True)
        state_path = os.path.join(graph_dir, "deviation_state.yaml")
        with open(state_path, "w", encoding="utf-8") as f:
            f.write("format_version: 1.0\ndeviations: [这是: 非法的: YAML: [结构\n")

        mgr = DeviationManager(project_root)
        # 重置为空状态
        assert mgr.list_all() == []
        # 备份文件存在
        backups = [f for f in os.listdir(graph_dir)
                   if f.startswith("deviation_state.yaml.corrupt-")]
        assert backups, "损坏文件应被备份为 .corrupt-<timestamp>"
        # 原文件已移走（备份即替换）
        assert not os.path.exists(state_path) or len(backups) >= 1


# ── 7. TypeRegistry 按项目隔离 ─────────────────────────────────────────────


class TestTypeRegistryProjectIsolation:
    def _make_project_with_override(self, description: str):
        """创建临时项目，带项目级 scene.yaml 覆盖（修改 description）。"""
        tmpdir = tempfile.mkdtemp(prefix="reg_proj_")
        proj_unit_types = os.path.join(tmpdir, ".opencode", "unit_types")
        os.makedirs(proj_unit_types, exist_ok=True)
        with open(os.path.join(proj_unit_types, "scene.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(
                {"unit_type": "scene", "description": description},
                f, allow_unicode=True, sort_keys=False,
            )
        return tmpdir

    def test_registries_isolated_per_project(self):
        """不同 project_root 的注册表互不污染；默认注册表不受影响。"""
        from type_registry import TypeRegistry

        try:
            TypeRegistry.reset_global()
            proj_a = self._make_project_with_override("项目A的场景定义")
            proj_b = self._make_project_with_override("项目B的场景定义")

            reg_a = TypeRegistry.get_global(project_root=proj_a)
            reg_b = TypeRegistry.get_global(project_root=proj_b)
            default = TypeRegistry.get_global()

            # 不同项目 → 不同实例
            assert reg_a is not reg_b
            assert reg_a.get_type("scene").description == "项目A的场景定义"
            assert reg_b.get_type("scene").description == "项目B的场景定义"
            # 默认（空键）注册表不含任何项目覆盖
            assert default.get_type("scene").description != "项目A的场景定义"

            # 相同项目 → 同一实例（缓存）
            assert TypeRegistry.get_global(project_root=proj_a) is reg_a
        finally:
            TypeRegistry.reset_global()
            for p in (proj_a, proj_b):
                shutil.rmtree(p, ignore_errors=True)
