"""
DeviationManager 单元测试。

测试覆盖：
- 创建/加载/保存状态文件
- merge 合并逻辑（去重、递增、重置）
- 状态管理（resolve/retain/delete）
- filter_for_presentation 过滤
- 统计信息
- 边界条件（空文件、不存在的文件、重复合并）

用法:
    cd novel-create-hermes
    pytest .opencode/shared/v2/tests/test_deviation_manager.py -v
"""

import os
import pytest

from deviation_manager import (
    DeviationManager,
    DeviationItem,
    DeviationState,
    ScanState,
)


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _make_item(
    dimension: str = "character_trait",
    entity: str = "林昭",
    status: str = "pending",
    summary: str = "",
    entity_id: str = "",
    scanned_version: int = 0,
) -> DeviationItem:
    """创建测试用的偏差项"""
    return DeviationItem(
        id="",
        dimension=dimension,
        entity=entity,
        entity_id=entity_id,
        scanned_version=scanned_version,
        status=status,
        severity="info",
        summary=summary or f"{entity} 的 {dimension} 偏差",
    )


# ── 基本操作 ────────────────────────────────────────────────────────────────


class TestDeviationManagerBasics:
    def test_create_new(self, project_root):
        mgr = DeviationManager(project_root)
        assert mgr.full_scan_version == 0
        assert mgr.list_all() == []

    def test_save_and_reload(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.full_scan_version = 42
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.save()

        # 创建新的实例重新读取
        mgr2 = DeviationManager(project_root)
        assert mgr2.full_scan_version == 42
        assert len(mgr2.list_all()) == 1

    def test_save_on_empty_state(self, project_root):
        """空状态保存不应报错"""
        mgr = DeviationManager(project_root)
        mgr.save()
        assert os.path.exists(mgr.state_path)

    def test_load_nonexistent_file(self, project_root):
        """读取不存在的文件应返回空状态"""
        mgr = DeviationManager(project_root)
        assert mgr.list_all() == []

    def test_load_empty_file(self, project_root):
        """读取空文件应返回空状态"""
        os.makedirs(os.path.join(project_root, "graph"), exist_ok=True)
        path = os.path.join(project_root, "graph", "deviation_state.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        mgr = DeviationManager(project_root)
        assert mgr.list_all() == []


# ── Merge 逻辑 ──────────────────────────────────────────────────────────────


class TestMerge:
    def test_merge_new_item(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        assert len(mgr.list_all()) == 1
        item = mgr.list_all()[0]
        assert item.dimension == "character_trait"
        assert item.entity == "林昭"
        assert item.detection_count == 1
        assert item.status == "pending"

    def test_merge_duplicate_increments_count(self, project_root):
        """相同 dimension + entity 的偏差应递增 detection_count"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        
        assert len(mgr.list_all()) == 1  # 不新增
        item = mgr.list_all()[0]
        assert item.detection_count == 2

    def test_merge_different_dimensions(self, project_root):
        """不同 dimension 的偏差应分别创建"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.merge([_make_item(dimension="plot_consistency", entity="林昭")])
        
        assert len(mgr.list_all()) == 2

    def test_merge_different_entities(self, project_root):
        """不同实体的偏差应分别创建"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.merge([_make_item(dimension="character_trait", entity="韩致")])
        
        assert len(mgr.list_all()) == 2

    def test_merge_resolved_comes_back(self, project_root):
        """已解决的偏差再次出现 → 重置为 pending"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.resolve("dev_00000000")  # 假设的 ID，但实际上 ID 是生成的
        
        # 先找到实际 ID
        item = mgr.list_all()[0]
        mgr.resolve(item.id)
        assert mgr.get(item.id).status == "resolved"

        # 再次合并相同偏差 → 重置为 pending
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", status="pending")])
        assert mgr.get(item.id).status == "pending"

    def test_merge_batch(self, project_root):
        """批量合并多个偏差"""
        mgr = DeviationManager(project_root)
        items = [
            _make_item(dimension="character_trait", entity="林昭"),
            _make_item(dimension="plot_consistency", entity="韩致"),
            _make_item(dimension="world_rule", entity="灵气淬体"),
        ]
        mgr.merge(items)
        assert len(mgr.list_all()) == 3

    def test_merge_idempotent_save(self, project_root):
        """重复 merge 同一条数据不应导致文件损坏"""
        mgr = DeviationManager(project_root)
        for _ in range(3):
            mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.save()

        mgr2 = DeviationManager(project_root)
        assert len(mgr2.list_all()) == 1
        assert mgr2.list_all()[0].detection_count == 3


# ── 状态管理 ────────────────────────────────────────────────────────────────


class TestStatusManagement:
    def test_resolve(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        item = mgr.list_all()[0]
        
        assert mgr.resolve(item.id) is True
        assert mgr.get(item.id).status == "resolved"

    def test_resolve_nonexistent(self, project_root):
        mgr = DeviationManager(project_root)
        assert mgr.resolve("nonexistent") is False

    def test_retain(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        item = mgr.list_all()[0]
        
        assert mgr.retain(item.id) is True
        assert mgr.get(item.id).status == "retained"

    def test_retain_nonexistent(self, project_root):
        mgr = DeviationManager(project_root)
        assert mgr.retain("nonexistent") is False

    def test_delete(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        item = mgr.list_all()[0]
        
        assert mgr.delete(item.id) is True
        assert len(mgr.list_all()) == 0

    def test_delete_nonexistent(self, project_root):
        mgr = DeviationManager(project_root)
        assert mgr.delete("nonexistent") is False

    def test_status_persistence(self, project_root):
        """状态下持久化后应保持"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        item = mgr.list_all()[0]
        mgr.resolve(item.id)
        mgr.save()

        mgr2 = DeviationManager(project_root)
        loaded = mgr2.get(item.id)
        assert loaded is not None
        assert loaded.status == "resolved"


# ── 过滤与展示 ──────────────────────────────────────────────────────────────


class TestFilterForPresentation:
    def test_filter_pending_only(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", status="pending")])
        mgr.merge([_make_item(dimension="plot_consistency", entity="韩致", status="pending")])
        item = mgr.list_all()[0]
        mgr.resolve(item.id)  # 解决一个

        pending = mgr.filter_for_presentation()
        assert len(pending) == 1  # 只应返回未解决的

    def test_filter_excludes_resolved_and_retained(self, project_root):
        mgr = DeviationManager(project_root)
        items = [
            _make_item(dimension="character_trait", entity="林昭", status="pending"),
            _make_item(dimension="plot_consistency", entity="韩致", status="pending"),
            _make_item(dimension="world_rule", entity="天道宗", status="pending"),
        ]
        mgr.merge(items)
        
        # 全部解决/保留
        all_items = mgr.list_all()
        mgr.resolve(all_items[0].id)
        mgr.retain(all_items[1].id)
        
        pending = mgr.filter_for_presentation()
        assert len(pending) == 1  # 只剩余一个 pending

    def test_filter_empty(self, project_root):
        mgr = DeviationManager(project_root)
        assert mgr.filter_for_presentation() == []


# ── 扫描版本管理 ────────────────────────────────────────────────────────────


class TestScanVersion:
    def test_default_version(self, project_root):
        mgr = DeviationManager(project_root)
        assert mgr.full_scan_version == 0

    def test_set_version(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.full_scan_version = 42
        assert mgr.full_scan_version == 42
        assert mgr._state.scan.last_scan_at != ""

    def test_version_persistence(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.full_scan_version = 100
        mgr.save()

        mgr2 = DeviationManager(project_root)
        assert mgr2.full_scan_version == 100

    def test_scanned_version_on_items(self, project_root):
        """偏差项应记录分析时的版本号"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", scanned_version=5)])
        item = mgr.list_all()[0]
        assert item.scanned_version == 5

        # 重复合并更新版本号
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", scanned_version=10)])
        assert item.scanned_version == 10
        assert item.detection_count == 2


# ── 统计 ────────────────────────────────────────────────────────────────────


class TestStats:
    def test_stats_empty(self, project_root):
        mgr = DeviationManager(project_root)
        stats = mgr.stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}
        assert stats["by_severity"] == {}

    def test_stats_with_items(self, project_root):
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", status="pending")])
        mgr.merge([_make_item(dimension="plot_consistency", entity="韩致", status="pending")])
        
        # 解决一个
        items = mgr.list_all()
        mgr.resolve(items[0].id)

        stats = mgr.stats()
        assert stats["total"] == 2
        assert stats["by_status"].get("pending", 0) == 1
        assert stats["by_status"].get("resolved", 0) == 1
        assert stats["by_dimension"].get("character_trait", 0) == 1


# ── 边界值 ──────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_merge_after_resolve_restores_pending(self, project_root):
        """resolved → merge same → pending"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        item = mgr.list_all()[0]
        mgr.resolve(item.id)

        # 再次合并
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", status="pending")])
        assert mgr.get(item.id).status == "pending"
        assert mgr.get(item.id).detection_count == 2

    def test_merge_updates_summary(self, project_root):
        """合并时新摘要应更新"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", summary="旧摘要")])
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", summary="新摘要")])
        assert mgr.list_all()[0].summary == "新摘要"

    def test_large_merge_batch(self, project_root):
        """批量合并 50 条不重复的偏差"""
        mgr = DeviationManager(project_root)
        items = []
        for i in range(50):
            items.append(_make_item(
                dimension="character_trait",
                entity=f"角色{i}",
            ))
        mgr.merge(items)
        assert len(mgr.list_all()) == 50

    def test_entity_id_matching(self, project_root):
        """按 entity_id 匹配去重"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", entity_id="ca_001")])
        # 相同 entity_id + dimension → 应去重
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", entity_id="ca_001")])
        assert len(mgr.list_all()) == 1
        assert mgr.list_all()[0].detection_count == 2
