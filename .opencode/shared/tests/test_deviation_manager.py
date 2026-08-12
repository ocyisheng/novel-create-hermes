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
from handlers.handlers_deviation import handle_deviation_list, handle_deviation_merge


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _make_item(
    dimension: str = "character_trait",
    entity: str = "林昭",
    status: str = "pending",
    summary: str = "",
    entity_id: str = "",
    scanned_version: int = 0,
    severity: str = "info",
) -> DeviationItem:
    """创建测试用的偏差项"""
    return DeviationItem(
        id="",
        dimension=dimension,
        entity=entity,
        entity_id=entity_id,
        scanned_version=scanned_version,
        status=status,
        severity=severity,
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
        """已解决的偏差再次出现 → 保持 resolved，仅更新检测计数"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        mgr.resolve("dev_00000000")  # 假设的 ID，但实际上 ID 是生成的
        
        # 先找到实际 ID
        item = mgr.list_all()[0]
        mgr.resolve(item.id)
        assert mgr.get(item.id).status == "resolved"

        # 再次合并相同偏差 → 尊重用户判断，不重置为 pending
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", status="pending")])
        assert mgr.get(item.id).status == "resolved"
        assert mgr.get(item.id).detection_count == 2

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
        """resolved → merge same → 保持 resolved（尊重用户判断），仅更新检测计数"""
        mgr = DeviationManager(project_root)
        mgr.merge([_make_item(dimension="character_trait", entity="林昭")])
        item = mgr.list_all()[0]
        mgr.resolve(item.id)

        # 再次合并
        mgr.merge([_make_item(dimension="character_trait", entity="林昭", status="pending")])
        assert mgr.get(item.id).status == "resolved"
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


# ── 列表过滤与分页 ─────────────────────────────────────────────────────────────


class TestListFiltersAndPagination:
    def test_deviation_list_filters_severity(self, project_root):
        """按 severity 过滤偏差列表"""
        mgr = DeviationManager(project_root)
        # 创建不同 severity 的偏差
        mgr.merge([
            _make_item(dimension="character_trait", entity="林昭", severity="high", summary="高严重"),
            _make_item(dimension="plot_consistency", entity="韩致", severity="medium", summary="中严重"),
            _make_item(dimension="world_rule", entity="天道宗", severity="low", summary="低严重"),
            _make_item(dimension="character_trait", entity="陈峰", severity="high", summary="另一高严重"),
        ])
        mgr.save()

        # 过滤 high severity
        high_items = [d for d in mgr.list_all() if d.severity == "high"]
        assert len(high_items) == 2
        for item in high_items:
            assert item.severity == "high"

        # 过滤 medium severity
        medium_items = [d for d in mgr.list_all() if d.severity == "medium"]
        assert len(medium_items) == 1
        assert medium_items[0].severity == "medium"

        # 过滤 low severity
        low_items = [d for d in mgr.list_all() if d.severity == "low"]
        assert len(low_items) == 1
        assert low_items[0].severity == "low"

    def test_deviation_list_filters_dimension(self, project_root):
        """按 dimension 过滤偏差列表"""
        mgr = DeviationManager(project_root)
        mgr.merge([
            _make_item(dimension="character_trait", entity="林昭", severity="high", summary="角色偏差1"),
            _make_item(dimension="character_trait", entity="韩致", severity="medium", summary="角色偏差2"),
            _make_item(dimension="plot_consistency", entity="后山拔剑", severity="high", summary="情节偏差"),
            _make_item(dimension="world_rule", entity="天道宗", severity="low", summary="世界观偏差"),
        ])
        mgr.save()

        # 过滤 character_trait
        char_items = [d for d in mgr.list_all() if d.dimension == "character_trait"]
        assert len(char_items) == 2
        for item in char_items:
            assert item.dimension == "character_trait"

        # 过滤 plot_consistency
        plot_items = [d for d in mgr.list_all() if d.dimension == "plot_consistency"]
        assert len(plot_items) == 1
        assert plot_items[0].dimension == "plot_consistency"

        # 过滤 world_rule
        world_items = [d for d in mgr.list_all() if d.dimension == "world_rule"]
        assert len(world_items) == 1
        assert world_items[0].dimension == "world_rule"

    def test_deviation_list_filters_combined(self, project_root):
        """组合 severity + dimension 过滤"""
        mgr = DeviationManager(project_root)
        mgr.merge([
            _make_item(dimension="character_trait", entity="林昭", severity="high", summary="高+角色"),
            _make_item(dimension="character_trait", entity="韩致", severity="medium", summary="中+角色"),
            _make_item(dimension="plot_consistency", entity="后山拔剑", severity="high", summary="高+情节"),
            _make_item(dimension="world_rule", entity="天道宗", severity="low", summary="低+世界观"),
        ])
        mgr.save()

        # 高严重 + 角色维度
        filtered = [d for d in mgr.list_all() if d.severity == "high" and d.dimension == "character_trait"]
        assert len(filtered) == 1
        assert filtered[0].entity == "林昭"

        # 高严重 + 情节维度
        filtered = [d for d in mgr.list_all() if d.severity == "high" and d.dimension == "plot_consistency"]
        assert len(filtered) == 1
        assert filtered[0].entity == "后山拔剑"

    def test_deviation_pending_pagination(self, project_root):
        """待处理偏差分页：limit/offset 正确，total 为分页前总数，truncated 标志正确。

        NOTE（本次修复）：5 条 pending 使用不同 dimension 构造，避免触发
        filter_for_presentation 的"≥3 同维度折叠"规则（该规则在缺陷修复
        后已实现）——否则 5 条同维度会被折叠为 1 条聚合条目。
        """
        mgr = DeviationManager(project_root)
        # 创建 5 个 pending 偏差（跨维度，避免触发 ≥3 同维度折叠）
        dims = ["character_trait", "character_trait", "plot_consistency",
                "plot_consistency", "world_rule"]
        for i, dim in enumerate(dims):
            mgr.merge([_make_item(
                dimension=dim,
                entity=f"角色{i}",
                severity="high" if i % 2 == 0 else "medium",
                summary=f"偏差{i}",
                status="pending"
            )])
        mgr.save()

        # 第 1 页：limit=2, offset=0
        page1 = mgr.filter_for_presentation()[0:2]
        total = len(mgr.filter_for_presentation())
        assert len(page1) == 2
        assert total == 5
        assert len(page1) < total  # truncated

        # 第 2 页：limit=2, offset=2
        page2 = mgr.filter_for_presentation()[2:4]
        assert len(page2) == 2
        assert total == 5
        assert len(page2) < total  # truncated

        # 第 3 页：limit=2, offset=4
        page3 = mgr.filter_for_presentation()[4:6]
        assert len(page3) == 1
        assert total == 5
        assert len(page3) < total  # truncated (1 < 5)

        # 超出范围：offset=10
        page_empty = mgr.filter_for_presentation()[10:12]
        assert len(page_empty) == 0
        assert total == 5

    def test_filter_for_presentation_collapses_same_dimension_ge3(self, project_root):
        """filter_for_presentation 的 ≥3 同维度折叠规则（缺陷修复后实现）。

        5 条同维度 pending 应折叠为 1 条聚合条目；<3 条时原样返回。
        """
        mgr = DeviationManager(project_root)
        for i in range(5):
            mgr.merge([_make_item(
                dimension="character_trait",
                entity=f"角色{i}",
                status="pending",
            )])
        collapsed = mgr.filter_for_presentation()
        assert len(collapsed) == 1, "≥3 同维度 pending 应折叠为一条聚合条目"
        assert collapsed[0].id == "character_trait:collapse"
        assert collapsed[0].status == "pending"
        assert "5" in collapsed[0].summary  # 摘要标注条数

        # <3 条同维度：原样返回
        mgr2 = DeviationManager(project_root)
        mgr2.merge([_make_item(dimension="dim_a", entity="A", status="pending")])
        mgr2.merge([_make_item(dimension="dim_a", entity="B", status="pending")])
        mgr2.merge([_make_item(dimension="dim_b", entity="C", status="pending")])
        items = mgr2.filter_for_presentation()
        assert len(items) == 3, "各维度均 <3 条时不应折叠"

    def test_deviation_list_filters_handler(self, tmp_project):
        """handler-level: call handle_deviation_list with severity+dimension filters"""
        proj_path, store = tmp_project
        findings = [
            {"dimension": "角色一致性", "entity": "林渊", "severity": "high", "summary": "高严重"},
            {"dimension": "角色一致性", "entity": "韩致", "severity": "medium", "summary": "中严重"},
            {"dimension": "情节逻辑", "entity": "后山拔剑", "severity": "high", "summary": "高情节"},
            {"dimension": "世界观", "entity": "天道宗", "severity": "low", "summary": "低世界观"},
        ]
        handle_deviation_merge(proj_path, findings=findings)

        # Filter by severity
        result = handle_deviation_list(proj_path, severity="high")
        assert result["total"] == 2
        assert result["returned"] == 2
        assert result["truncated"] is False
        for d in result["deviations"]:
            assert d["severity"] == "high"

        # Filter by dimension
        result = handle_deviation_list(proj_path, dimension="角色一致性")
        assert result["total"] == 2
        assert result["returned"] == 2
        for d in result["deviations"]:
            assert d["dimension"] == "角色一致性"

        # Filter by both severity + dimension
        result = handle_deviation_list(proj_path, severity="high", dimension="角色一致性")
        assert result["total"] == 1
        assert result["deviations"][0]["entity"] == "林渊"

        # Non-matching filter
        result = handle_deviation_list(proj_path, severity="critical")
        assert result["total"] == 0
        assert result["deviations"] == []

        # Filter by status
        result = handle_deviation_list(proj_path, status="pending")
        assert result["total"] == 4

        result = handle_deviation_list(proj_path, status="resolved")
        assert result["total"] == 0
