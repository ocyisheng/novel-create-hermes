"""
ConstraintEngine 回归测试。

测试覆盖：
- 长生命周期引擎（daemon 中复用的 GraphStore/ConstraintEngine）的偏差写入
  不得覆盖外部（deviation.* handler）对 deviation_state.yaml 的新写入。

缺陷背景：
ConstraintEngine._get_deviation_manager() 曾缓存 DeviationManager 实例；
daemon 中引擎跨请求复用，缓存实例的内存状态与磁盘脱节。graph.flush 的
post_flush 钩子 → run_incremental → merge_from_check_results 无条件 save()，
用缓存旧状态整体覆盖新状态——导致 handler 的 merge/resolve（707 条/已解决）
被后续 flush 回滚（706 条/全 pending）。修复：每次调用新建实例（从磁盘加载）。

用法:
    cd novel-create-hermes
    pytest .opencode/shared/tests/test_constraint_engine.py -v
"""

import pytest

from deviation_manager import DeviationManager, DeviationItem


def _make_item(dimension: str, entity: str, summary: str = "") -> DeviationItem:
    """创建测试用偏差项（id 留空，由 merge 自动生成）。"""
    return DeviationItem(
        id="",
        dimension=dimension,
        entity=entity,
        severity="warning" if dimension == "plot_consistency" else "info",
        summary=summary or f"{entity} 的 {dimension} 偏差",
    )


class TestConstraintEngineDeviationStaleness:
    """回归：引擎不得用缓存旧状态覆盖外部写入的偏差状态。"""

    def test_run_incremental_preserves_external_writes(self, project_root):
        """约束检查重跑后，外部 handler 的 merge/resolve 结果必须保留。

        旧实现：引擎第一次 run_incremental 时缓存空状态实例，外部写入
        2 条偏差（1 条 resolved）后再次 run_incremental → 空状态整体覆盖
        → 2 条全部丢失。新实现：每次从磁盘加载 → 外部写入保留。
        """
        from graph_store import GraphStore
        from constraint_engine import ConstraintEngine

        store = GraphStore(project_root)
        store.initialize()
        engine = ConstraintEngine(store)
        engine.register_with_store()  # 模拟 daemon 中注册的常驻引擎

        # 1) 首次触发：引擎在此获取（旧代码缓存）自己的 DeviationManager
        engine.run_incremental()

        # 2) 外部写者（模拟 deviation.merge + resolve handler）：2 条，解决 1 条
        mgr = DeviationManager(project_root)
        mgr.merge([
            _make_item("character_trait", "林昭"),
            _make_item("plot_consistency", "韩致"),
        ])
        mgr.save()
        resolved_id = mgr.list_all()[0].id
        pending_id = mgr.list_all()[1].id
        mgr.resolve(resolved_id)
        mgr.save()

        # 3) 再次触发约束检查（模拟后续 graph.flush → post_flush 钩子）
        engine.run_incremental()

        fresh = DeviationManager(project_root)
        stats = fresh.stats()
        assert stats["total"] == 2, f"外部写入被约束引擎覆盖: {stats}"
        assert fresh.get(resolved_id).status == "resolved", "resolved 状态被回滚"
        assert fresh.get(pending_id).status == "pending", "pending 状态被改动"

    def test_flush_post_hook_preserves_external_writes(self, project_root):
        """经 graph.flush 的 post_flush 钩子重跑约束检查后，外部写入仍保留。"""
        from graph_store import GraphStore
        from graph_schema import UnitType
        from constraint_engine import ConstraintEngine

        store = GraphStore(project_root)
        store.initialize()
        engine = ConstraintEngine(store)
        engine.register_with_store()

        # 1) 首次 flush：引擎注册钩子并初始化（旧代码在此缓存空状态实例）
        store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="陈峰",
            content='{"角色":"配角"}', tags=[], actor="test",
        )
        store.flush()

        # 2) 外部写者：merge 2 条，解决 1 条
        mgr = DeviationManager(project_root)
        mgr.merge([
            _make_item("character_trait", "林昭"),
            _make_item("plot_consistency", "韩致"),
        ])
        mgr.save()
        resolved_id = mgr.list_all()[0].id
        pending_id = mgr.list_all()[1].id
        mgr.resolve(resolved_id)
        mgr.save()

        # 3) 再次 flush → post_flush 钩子 → run_incremental（触发覆盖缺陷的路径）
        store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="韩致",
            content='{"角色":"主角","修为":"化神期"}', tags=["主角"], actor="test",
        )
        store.flush()

        fresh = DeviationManager(project_root)
        stats = fresh.stats()
        assert stats["total"] >= 2, f"外部写入被 flush 钩子覆盖: {stats}"
        assert fresh.get(resolved_id).status == "resolved", "resolved 状态被回滚"
        assert fresh.get(pending_id).status == "pending", "pending 状态被改动"
