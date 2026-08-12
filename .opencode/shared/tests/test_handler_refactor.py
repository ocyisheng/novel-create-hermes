"""
test_handler_refactor.py — 本轮 handler/适配层重构的回归测试。

覆盖行为变更：
1. run_operation 必填参数强制校验（缺失 → 干净错误 dict，无 traceback）
2. 响应信封归一化（成功 status="ok" / 失败 status="error"，additive 保留原键）
3. cli._auto_dispatch_v2 写操作注入 actor="script"（CLI 与 tool 行为对齐）
4. 写权限门合并后行为不变（check_write_permission / check_planner_restriction）
5. handle_constraint_check 不再重复持久化（detection_count 每次 +1 而非 +2）
6. project.* 操作不再产生"参数被静默过滤"噪音
"""

import json
import os
import shutil
import tempfile
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from conftest import call_tool, assert_success, assert_error


# ============================================================================
# 1. run_operation 必填参数强制校验（DEFECT 2）
# ============================================================================

class TestRequiredParamEnforcement:
    def test_missing_required_returns_clean_error(self):
        """缺失必填参数 → 干净错误 dict（无 traceback）。"""
        from handlers import run_operation
        r = run_operation("graph.get_neighbors", project_root="/tmp/proj")
        assert "error" in r
        assert r["error"] == "缺少必填参数: id (operation=graph.get_neighbors)"
        assert r["status"] == "error"
        assert "Traceback" not in r["error"]
        assert "Traceback" not in str(r)

    def test_empty_string_required_counts_as_missing(self):
        """空字符串必填参数视为缺失。"""
        from handlers import run_operation
        r = run_operation("graph.stats", project_root="")
        assert r["error"].startswith("缺少必填参数: project_root")

    def test_none_required_counts_as_missing(self):
        """None 必填参数视为缺失。"""
        from handlers import run_operation
        r = run_operation("graph.get_unit", project_root=None, id="x")
        assert r["error"].startswith("缺少必填参数: project_root")

    def test_required_met_passes_through(self, tmp_project):
        """必填参数齐备时正常调度（不误伤 adapter 注入路径）。"""
        proj_path, _ = tmp_project
        from handlers import run_operation
        r = run_operation("graph.stats", project_root=proj_path)
        assert r["status"] == "ok"
        assert "total_units" in r

    def test_optional_params_not_enforced(self):
        """非必填参数不强制（graph.quality_check 的 layers/full 可缺省）。"""
        from handlers import OPERATION_REGISTRY
        spec = OPERATION_REGISTRY["graph.quality_check"]["params"]
        assert spec["layers"].get("required") is False
        assert spec["full"].get("required") is False


# ============================================================================
# 2. 响应信封归一化（DEFECT 3）
# ============================================================================

class TestEnvelopeNormalization:
    def test_success_stamped_ok(self):
        """成功结果被 stamp 为 status="ok"，且保留全部原有键。"""
        from handlers import run_operation
        r = run_operation("graph.list_relation_types")
        assert r["status"] == "ok"
        assert "relation_types" in r  # 原有键不被移除/重命名

    def test_error_stamped_error_and_preserves_keys(self, tmp_project):
        """错误结果被 stamp 为 status="error"，并保留原有错误附带键。"""
        proj_dir = os.path.join(tmp_project[0], "子项目")
        os.makedirs(proj_dir, exist_ok=True)
        from handlers import run_operation
        r = run_operation("project.delete", project_root=proj_dir)
        assert r["status"] == "error"
        assert "error" in r
        assert r.get("needs_force") is True  # 原有附加键保留

    def test_unknown_operation_stamped_error(self):
        from handlers import run_operation
        r = run_operation("nope.xxx")
        assert r["status"] == "error"
        assert "未知操作" in r["error"]

    def test_adapter_path_data_carries_status(self, tmp_project):
        """novel_tool 适配层路径下 data 同样携带 status 标记（additive）。"""
        proj_path, _ = tmp_project
        res = call_tool("graph.stats", project=proj_path)
        assert_success(res)
        assert res["data"]["status"] == "ok"


# ============================================================================
# 3. cli._auto_dispatch_v2 写操作 actor 注入（DEFECT 4）
# ============================================================================

class TestAutoDispatchActorInjection:
    def _dispatch(self, monkeypatch, cmd, path, **attr_overrides):
        """调用 cli._auto_dispatch_v2，捕获 run_operation 参数，返回 (captured_params, output)。"""
        import handlers
        from cli import _auto_dispatch_v2

        captured = {}

        def _fake_run_operation(op_name, **params):
            captured["op"] = op_name
            captured["params"] = params
            return {"ok": True, "status": "ok"}

        monkeypatch.setattr(handlers, "run_operation", _fake_run_operation)

        args = SimpleNamespace(v2_command=cmd, path=path)
        for k, v in attr_overrides.items():
            setattr(args, k, v)
        _auto_dispatch_v2(args)
        return captured

    def test_write_op_injects_actor_script(self, monkeypatch, tmp_project):
        """写操作（graph.remove_relation）经 _auto_dispatch_v2 → actor='script'。"""
        proj_path, _ = tmp_project
        captured = self._dispatch(monkeypatch, "graph-remove-relation", proj_path,
                                  id="rel_1", actor=None)
        assert captured["op"] == "graph.remove_relation"
        assert captured["params"]["actor"] == "script", \
            f"写操作应注入 actor='script'，实际 {captured['params']}"

    def test_explicit_actor_not_overridden(self, monkeypatch, tmp_project):
        """用户显式传 --actor 时不被覆盖。"""
        proj_path, _ = tmp_project
        captured = self._dispatch(monkeypatch, "graph-remove-relation", proj_path,
                                  id="rel_1", actor="web-ui")
        assert captured["params"]["actor"] == "web-ui"

    def test_read_op_no_actor_injected(self, monkeypatch, tmp_project):
        """读取操作（registry 未声明 actor）不注入 actor。"""
        proj_path, _ = tmp_project
        captured = self._dispatch(monkeypatch, "graph-get-modified-units", proj_path,
                                  since_version=0)
        assert captured["op"] == "graph.get_modified_units"
        assert "actor" not in captured["params"]


# ============================================================================
# 4. 写权限门合并后行为不变（DEFECT 5）
# ============================================================================

class TestWritePermissionGate:
    def test_orchestrator_blocked_with_policy_fields(self):
        from handlers._common import check_write_permission
        r = check_write_permission("orchestrator", "graph.create_unit")
        assert r is not None
        assert "error" in r
        assert r["blocked_operation"] == "graph.create_unit"
        assert "novel-writer" in r["error"]  # 修正指引

    def test_allowed_actors_pass(self):
        from handlers._common import check_write_permission
        for actor in ("novel-writer", "novel-v2-crafter", "v2-crafter",
                      "script", "fix-asymmetry", "novel-tool", "web-ui"):
            assert check_write_permission(actor, "graph.create_unit") is None, actor

    def test_unknown_actor_blocked(self):
        from handlers._common import check_write_permission
        assert check_write_permission("hacker", "graph.create_unit") is not None

    def test_planner_restriction_helper(self):
        from handlers._common import check_planner_restriction
        r = check_planner_restriction("novel-planner", "graph.archive_unit")
        assert r is not None
        assert "novel-planner" in r["error"]
        assert check_planner_restriction("novel-writer", "graph.archive_unit") is None

    def test_planner_deny_all_ops_share_template(self, tmp_project):
        """6 个全拒操作的文案统一模板（单一口径，行为不变）。"""
        from handlers._common import check_planner_restriction
        for op in ("graph.archive_unit", "graph.purge_archived", "graph.update_relation",
                   "graph.remove_relation", "graph.batch_infer", "graph.change_type"):
            r = check_planner_restriction("novel-planner", op)
            assert r is not None, op
            assert r["error"].startswith(f"novel-planner 不允许执行 {op}"), r["error"]

    def test_handler_level_behavior_unchanged(self, tmp_project):
        """handler 级行为不变：orchestrator 被拒、novel-v2-crafter 放行。"""
        proj_path, _ = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        unit_type="note", name="x", actor="orchestrator")
        assert_error(res)
        assert "不允许直接调用" in res["error"]
        res = call_tool("graph.create_unit", project=proj_path,
                        unit_type="note", name="x", actor="novel-v2-crafter")
        assert_success(res)


# ============================================================================
# 5. handle_constraint_check 不再重复持久化（DEFECT 6）
# ============================================================================

class TestConstraintCheckNoDoublePersist:
    def _violating_project(self, tmp_project):
        """创建触发 age_monotonic 偏差的角色单元。"""
        proj_path, store = tmp_project
        from graph_schema import UnitType
        store.create_unit(
            type=UnitType.CHARACTER_ARC, unit_name="林渊",
            content=json.dumps({
                "subtype": "主角",
                "events": [
                    {"ordinal": 1, "age": 20, "location": "落云宗", "type": "修炼"},
                    {"ordinal": 2, "age": 10, "location": "落云宗", "type": "修炼"},
                ],
            }, ensure_ascii=False),
            actor="test",
        )
        store.flush()
        return proj_path

    def test_detection_count_increments_once_per_check(self, tmp_project):
        """两次手动全量检查 → detection_count 各 +1（修复前每次 +2）。"""
        proj_path = self._violating_project(tmp_project)
        from handlers import run_operation
        from deviation_manager import DeviationManager

        r1 = run_operation("constraint.check", project_root=proj_path, full=True)
        assert r1["status"] == "ok"
        assert r1["checked"] is True

        dm1 = DeviationManager(proj_path)
        items1 = dm1.list_all()
        assert items1, "应产生约束偏差"
        assert all(d.detection_count == 1 for d in items1), \
            f"第一次检查后 detection_count 应为 1，实际 {[d.detection_count for d in items1]}"

        r2 = run_operation("constraint.check", project_root=proj_path, full=True)
        assert r2["status"] == "ok"

        dm2 = DeviationManager(proj_path)
        items2 = dm2.list_all()
        assert all(d.detection_count == 2 for d in items2), \
            f"第二次检查后 detection_count 应为 2（每次 +1），实际 {[d.detection_count for d in items2]}"


# ============================================================================
# 6. project.* 操作无"参数被静默过滤"噪音（DEFECT 8a）
# ============================================================================

class TestNoSpuriousParamFilterWarnings:
    def _project_dir(self):
        return tempfile.mkdtemp(prefix="novels_root_")

    def test_project_ops_no_filter_warning(self):
        """project.* 操作不再触发 run_operation 的"参数被静默过滤"警告。"""
        tmpdir = self._project_dir()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # 任何 UserWarning → 失败
                with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                    r = call_tool("project.new", name="无噪音小说", genre="玄幻", v2=True)
                    assert_success(r)
                    proj_path = r["data"]["path"]

                    r2 = call_tool("project.status", name="无噪音小说")
                    assert_success(r2)

                    r3 = call_tool("project.import", name="导入噪音源",
                                   source_path=os.path.join(tmpdir, "不存在"))
                    assert_error(r3, "不存在")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_canonical_params_drop_alias_consumed_keys(self):
        """别名消费的源键不再同时经基础映射残留。"""
        from novel_tool import _build_canonical_params
        tmpdir = self._project_dir()
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                p = _build_canonical_params("project.new",
                                            {"operation": "project.new", "name": "小说", "genre": "仙侠"})
                assert "name" not in p
                assert p["project_root"] == os.path.join(tmpdir, "小说")
                assert p["genre"] == "仙侠"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
