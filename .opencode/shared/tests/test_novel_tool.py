import json, os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS_DIR = os.path.join(SHARED_DIR, "tools")
V2_DIR = os.path.join(SHARED_DIR, "v2")
for _d in [SHARED_DIR, TOOLS_DIR, V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

from novel_tool import handle_request, _resolve_project, _find_novels_root, _ok, _err

# Conftest 同目录，pytest 自动加载；这里显式导入辅助函数
from conftest import json_request, call_tool, assert_success, assert_error


# ============================================================================
# 1. 基础架构测试
# ============================================================================

class TestArchitecture:
    def test_handle_request_no_operation(self):
        res = call_tool("")
        assert_error(res, "缺少 operation 字段")

    def test_handle_request_unknown_operation(self):
        res = call_tool("totally.made_up")
        assert_error(res, "未知操作: totally.made_up")

    def test_response_format_success(self):
        raw = handle_request({"operation": "graph.list_relation_types"})
        parsed = json.loads(raw)
        assert "success" in parsed
        assert parsed["success"] is True
        assert "data" in parsed

    def test_response_format_error(self):
        res = call_tool("graph.get_unit")
        assert_error(res)
        assert "error" in json.loads(handle_request({"operation": "graph.get_unit"}))

    def test_handle_graph_unknown_sub_op(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.nonexistent", project=proj_path)
        assert_error(res, "未知操作: graph.nonexistent")


# ============================================================================
# 2. Graph 读取操作
# ============================================================================

class TestGraphRead:
    def test_list_relation_types(self):
        res = call_tool("graph.list_relation_types")
        assert_success(res)
        types = res["data"]["relation_types"]
        assert len(types) >= 15
        names = [t["name"] for t in types]
        assert "PARTICIPATES_IN" in names
        assert "CAUSES" in names
        for t in types:
            assert "value" in t
            assert "inverse" in t

    def test_get_unit_by_id(self, sample_units):
        proj_path, store, units = sample_units
        uid = units["林渊"].id
        res = call_tool("graph.get_unit", project=proj_path, id=uid)
        assert_success(res)
        assert res["data"]["unit"]["name"] == "林渊"
        assert res["data"]["unit"]["type"] == "character_arc"

    def test_get_unit_by_name(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.get_unit", project=proj_path, name="林渊")
        assert_success(res)
        assert res["data"]["unit"]["name"] == "林渊"

    def test_get_unit_no_id_or_name(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.get_unit", project=proj_path)
        assert_error(res, "get_unit 需要 id 或 name")

    def test_get_unit_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.get_unit", project=proj_path, id="nonexistent_id")
        assert_success(res, None)

    def test_get_unit_non_verbose_truncates_content(self, tmp_project):
        proj_path, store = tmp_project
        from graph_schema import UnitType
        long_content = "A" * 500
        u = store.create_unit(type=UnitType.NOTE, unit_name="长内容", content=long_content, actor="novel-v2-crafter")
        store.flush()
        res = call_tool("graph.get_unit", project=proj_path, id=u.id)
        content = res["data"]["unit"]["content"]
        assert len(content) == 500

    def test_get_unit_verbose_does_not_truncate(self, tmp_project):
        # graph.get_unit 不消费 verbose（registry 未声明），不再传该未注册参数，
        # 避免 run_operation 输出"参数被静默过滤"噪音。handler 始终返回完整 content。
        proj_path, store = tmp_project
        from graph_schema import UnitType
        long_content = "A" * 500
        u = store.create_unit(type=UnitType.NOTE, unit_name="长内容", content=long_content, actor="novel-v2-crafter")
        store.flush()
        res = call_tool("graph.get_unit", project=proj_path, id=u.id)
        assert len(res["data"]["unit"]["content"]) == 500

    def test_find_unit_found(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.find_unit", project=proj_path, name="林渊")
        assert_success(res)
        assert res["data"]["id"] is not None

    def test_find_unit_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.find_unit", project=proj_path, name="不存在")
        assert_success(res, lambda d: d.get("id") is None)

    def test_find_unit_no_name(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.find_unit", project=proj_path)
        assert_success(res)
        assert "请提供 name" in res["data"].get("message", "")

    def test_search_by_keyword(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.search", project=proj_path, keyword="林渊")
        assert_success(res)
        assert res["data"]["total"] >= 1
        names = [r["unit_name"] for r in res["data"]["results"]]
        assert "林渊" in names
        # 每个结果都应携带创建/更新时间戳（供校验比对识别最新修正）
        for r in res["data"]["results"]:
            assert r.get("created_at"), f"缺少 created_at: {r}"
            assert r.get("updated_at"), f"缺少 updated_at: {r}"

    def test_search_by_name(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.search", project=proj_path, name="林渊")
        assert_success(res)
        assert res["data"]["total"] >= 1

    def test_search_by_pattern(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.search", project=proj_path, pattern="林.*", regex=True)
        assert_success(res)
        assert res["data"]["total"] >= 1

    def test_search_with_scope(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.search", project=proj_path, keyword="林渊", scope="CHARACTER_ARC")
        assert_success(res)
        for r in res["data"]["results"]:
            assert r["unit_type"] == "character_arc"

    def test_search_limit(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.search", project=proj_path, keyword="", limit=2)
        assert_success(res)
        assert len(res["data"]["results"]) <= 2

    def test_search_case_sensitive(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.search", project=proj_path, keyword="林渊", caseSensitive=True)
        assert_success(res)
        assert res["data"]["total"] >= 1

    def test_search_empty_result(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.search", project=proj_path, keyword="ZZZZ_NOT_THERE")
        assert_success(res)
        assert res["data"]["total"] == 0
        assert res["data"]["results"] == []

    def test_list_units_all(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.list_units", project=proj_path)
        assert_success(res)
        assert len(res["data"]["units"]) >= 5
        for u in res["data"]["units"]:
            assert u.get("created_at"), f"缺少 created_at: {u}"
            assert u.get("updated_at"), f"缺少 updated_at: {u}"

    def test_list_units_by_type(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.list_units", project=proj_path, type="CHARACTER_ARC")
        assert_success(res)
        for u in res["data"]["units"]:
            assert u["type"] == "character_arc"

    def test_list_units_limit(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.list_units", project=proj_path, limit=2)
        assert_success(res)
        assert len(res["data"]["units"]) == 2

    def test_stats(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.stats", project=proj_path)
        assert_success(res)
        stats = res["data"]
        assert stats["total_units"] >= 5
        assert stats["total_relations"] >= 2
        assert "by_type" in stats

    def test_get_neighbors(self, sample_units):
        proj_path, store, units = sample_units
        uid = units["林渊"].id
        res = call_tool("graph.get_neighbors", project=proj_path, id=uid)
        assert_success(res)
        names = [n["name"] for n in res["data"]["neighbors"]]
        assert "后山拔剑" in names
        for n in res["data"]["neighbors"]:
            assert n.get("created_at"), f"缺少 created_at: {n}"
            assert n.get("updated_at"), f"缺少 updated_at: {n}"

    def test_get_neighbors_no_id(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.get_neighbors", project=proj_path)
        # 必填参数校验：干净错误（无 raw TypeError traceback）
        assert_error(res, "缺少必填参数: id")

    def test_get_neighbors_with_reltype_filter(self, sample_units):
        proj_path, store, units = sample_units
        uid = units["林渊"].id
        res = call_tool("graph.get_neighbors", project=proj_path, id=uid, relType="PARTICIPATES_IN")
        assert_success(res)
        assert len(res["data"]["neighbors"]) >= 1

    def test_get_neighbors_limit(self, sample_units):
        proj_path, store, units = sample_units
        uid = units["陈峰"].id
        res = call_tool("graph.get_neighbors", project=proj_path, id=uid, limit=1)
        assert_success(res)
        assert len(res["data"]["neighbors"]) <= 1

    def test_check_consistency(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.check", project=proj_path)
        assert_success(res)
        assert isinstance(res["data"], dict)

    def test_recent_events(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.recent_events", project=proj_path)
        assert_success(res)
        assert len(res["data"]["events"]) >= 1

    def test_recent_events_limit(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.recent_events", project=proj_path, limit=3)
        assert_success(res)
        assert len(res["data"]["events"]) <= 3

    def test_get_modified_units(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.get_modified_units", project=proj_path, since_version=0)
        assert_success(res)
        assert len(res["data"]["units"]) >= 5
        for u in res["data"]["units"]:
            assert u.get("created_at"), f"缺少 created_at: {u}"
            assert u.get("updated_at"), f"缺少 updated_at: {u}"


# ============================================================================
# 3. Graph 写入操作
# ============================================================================

class TestGraphWrite:
    def test_create_unit(self, tmp_project):
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="CHARACTER_ARC", name="新角色",
                        content="测试内容", tags="主角,新标签",
                        chapter=1, actor="novel-v2-crafter")
        assert_success(res)
        assert res["data"]["id"].startswith("ca_")
        assert res["data"].get("created_at"), f"缺少 created_at: {res['data']}"
        assert res["data"].get("updated_at"), f"缺少 updated_at: {res['data']}"
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert_success(verify)
        assert verify["data"]["unit"]["name"] == "新角色"
        assert "主角" in verify["data"]["unit"]["tags"]

    def test_create_unit_default_type(self, tmp_project):
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="NOTE", name="默认笔记", actor="novel-v2-crafter")
        assert_success(res)
        assert res["data"]["id"].startswith("nt_")

    def test_create_unit_invalid_type(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="INVALID_TYPE", name="坏单元", actor="novel-v2-crafter")
        assert_error(res)

    def test_create_unit_duplicate_error_by_default(self, tmp_project):
        """handler 默认 if_exists=error：同名同类型重复创建被拒绝。"""
        proj_path, _ = tmp_project
        res1 = call_tool("graph.create_unit", project=proj_path,
                         type="CHARACTER_ARC", name="林渊", content="{}", actor="novel-v2-crafter")
        assert_success(res1)
        res2 = call_tool("graph.create_unit", project=proj_path,
                         type="CHARACTER_ARC", name="林渊", content="{}", actor="novel-v2-crafter")
        assert_error(res2)
        assert "同名" in res2["error"] or "已存在" in res2["error"]
        # 库中只有一个林渊
        units = call_tool("graph.list_units", project=proj_path,
                          unit_type="CHARACTER_ARC", actor="novel-v2-crafter")
        names = [u["name"] for u in units["data"]["units"]]
        assert names.count("林渊") == 1

    def test_create_unit_if_exists_skip_idempotent(self, tmp_project):
        """handler if_exists=skip：幂等返回已有单元，不重复创建。"""
        proj_path, _ = tmp_project
        r1 = call_tool("graph.create_unit", project=proj_path,
                       type="CHARACTER_ARC", name="幂等角色", content="{}", actor="novel-v2-crafter")
        assert_success(r1)
        r2 = call_tool("graph.create_unit", project=proj_path,
                       type="CHARACTER_ARC", name="幂等角色", content="{}",
                       actor="novel-v2-crafter", if_exists="skip")
        assert_success(r2)
        assert r2["data"]["id"] == r1["data"]["id"]
        assert r2["data"].get("skipped") is True
        units = call_tool("graph.list_units", project=proj_path,
                         unit_type="CHARACTER_ARC", actor="novel-v2-crafter")
        names = [u["name"] for u in units["data"]["units"]]
        assert names.count("幂等角色") == 1

    def test_create_unit_if_exists_create_force(self, tmp_project):
        """handler if_exists=create：强制新建，产生不同 id。"""
        proj_path, _ = tmp_project
        r1 = call_tool("graph.create_unit", project=proj_path,
                       type="CHARACTER_ARC", name="强制角色", content="{}", actor="novel-v2-crafter")
        assert_success(r1)
        r2 = call_tool("graph.create_unit", project=proj_path,
                       type="CHARACTER_ARC", name="强制角色", content="{}",
                       actor="novel-v2-crafter", if_exists="create")
        assert_success(r2)
        assert r2["data"]["id"] != r1["data"]["id"]

    def test_create_unit_if_exists_skip_archived_creates_new(self, tmp_project):
        """handler if_exists=skip：已归档单元不阻塞，允许新建。"""
        proj_path, _ = tmp_project
        r1 = call_tool("graph.create_unit", project=proj_path,
                       type="CHARACTER_ARC", name="归档角色", content="{}", actor="novel-v2-crafter")
        assert_success(r1)
        # 归档原单元
        arc = call_tool("graph.archive_unit", project=proj_path,
                        id=r1["data"]["id"], actor="novel-v2-crafter")
        assert_success(arc)
        # skip 应新建（归档不算活跃重复）
        r2 = call_tool("graph.create_unit", project=proj_path,
                       type="CHARACTER_ARC", name="归档角色", content="{}",
                       actor="novel-v2-crafter", if_exists="skip")
        assert_success(r2)
        assert r2["data"]["id"] != r1["data"]["id"]
        assert r2["data"].get("skipped") is not True

    def test_update_unit(self, sample_units):
        proj_path, store, units = sample_units
        uid = units["林渊"].id
        res = call_tool("graph.update_unit", project=proj_path,
                        id=uid, content="更新内容", name="林渊改",
                        tags="主角,剑修,更新", actor="novel-v2-crafter")
        assert_success(res)
        assert res["data"]["name"] == "林渊改"
        assert res["data"]["version"] >= 2
        assert "更新" in res["data"]["tags"]
        # 写操作响应也应携带时间戳（更新后立即可见新的 updated_at）
        assert res["data"].get("updated_at"), f"缺少 updated_at: {res['data']}"

    def test_update_unit_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.update_unit", project=proj_path,
                        id="nonexistent", content="x", actor="novel-v2-crafter")
        assert_error(res, "不存在")

    def test_archive_unit(self, sample_units):
        proj_path, store, units = sample_units
        uid = units["林渊"].id
        res = call_tool("graph.archive_unit", project=proj_path, id=uid, actor="novel-v2-crafter")
        # 信封归一化：run_operation 在成功结果上追加 status="ok"（additive），故按键断言
        assert_success(res, lambda d: d.get("archived") is True and d.get("status") == "ok")
        verify = call_tool("graph.get_unit", project=proj_path, id=uid)
        assert verify["data"]["unit"]["status"] == "archived"

    def test_archive_unit_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.archive_unit", project=proj_path, id="nonexistent", actor="novel-v2-crafter")
        assert_error(res, "不存在")

    def test_purge_archived_empty_ids_errors(self, sample_units):
        """空 ids 必须报错——防止误删全部已归档单元（历史缺陷回归测试）。"""
        proj_path, store, units = sample_units
        uid = units["林渊"].id
        res = call_tool("graph.archive_unit", project=proj_path, id=uid, actor="novel-v2-crafter")
        assert_success(res, lambda d: d.get("archived") is True)
        # 不带 ids、不带 force → 必须拒绝
        res = call_tool("graph.purge_archived", project=proj_path, actor="novel-tool")
        assert_error(res, "未指定 ids")
        # 单元仍然存在（未被误删）
        verify = call_tool("graph.get_unit", project=proj_path, id=uid)
        assert_success(verify)

    def test_purge_archived_by_ids(self, sample_units):
        """指定 ids 时只删除目标单元，其余已归档单元保留。"""
        proj_path, store, units = sample_units
        uid1 = units["林渊"].id
        uid2 = units["陈峰"].id
        for uid in (uid1, uid2):
            res = call_tool("graph.archive_unit", project=proj_path, id=uid, actor="novel-v2-crafter")
            assert_success(res, lambda d: d.get("archived") is True)
        # 定向删除 uid1
        res = call_tool("graph.purge_archived", project=proj_path, ids=uid1, actor="novel-tool")
        assert_success(res)
        assert res["data"]["purged"] == 1
        # uid1 已物理删除
        verify = call_tool("graph.get_unit", project=proj_path, id=uid1)
        assert verify["data"].get("unit") is None
        # uid2 保留
        verify2 = call_tool("graph.get_unit", project=proj_path, id=uid2)
        assert_success(verify2)

    def test_purge_archived_all_with_force(self, sample_units):
        """force=true + 空 ids 才允许全量删除。"""
        proj_path, store, units = sample_units
        uid1 = units["林渊"].id
        uid2 = units["陈峰"].id
        for uid in (uid1, uid2):
            call_tool("graph.archive_unit", project=proj_path, id=uid, actor="novel-v2-crafter")
        res = call_tool("graph.purge_archived", project=proj_path, force=True, actor="novel-tool")
        assert_success(res)
        assert res["data"]["purged"] == 2
        for uid in (uid1, uid2):
            verify = call_tool("graph.get_unit", project=proj_path, id=uid)
            assert verify["data"].get("unit") is None

    def test_add_relation(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.add_relation", project=proj_path,
                        source=units["林渊"].id, target=units["落云宗"].id,
                        type="MEMBER_OF", actor="novel-v2-crafter")
        assert_success(res)
        assert res["data"]["type"] == "member_of"

    def test_add_relation_bidirectional(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.add_relation", project=proj_path,
                        source=units["林渊"].id, target=units["落云宗"].id,
                        type="MEMBER_OF", bidirectional=True, actor="novel-v2-crafter")
        assert_success(res)
        assert "inverse_id" in res["data"]
        assert res["data"]["inverse_id"] is not None

    def test_add_relation_invalid_type(self, sample_units):
        proj_path, store, units = sample_units
        # 非法关系类型不再报错——降级为 RELATES_TO（关联容器），原始输入存为 label
        res = call_tool("graph.add_relation", project=proj_path,
                        source=units["林渊"].id, target=units["落云宗"].id,
                        type="NOT_A_TYPE", actor="novel-v2-crafter")
        assert_success(res)
        assert res["data"]["type"] == "relates_to"
        assert res["data"].get("label") == "NOT_A_TYPE"

    def test_flush(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("graph.flush", project=proj_path)
        assert_success(res, lambda d: d.get("ok") is True and "constraint_check" in d)

    def test_fix_asymmetry(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.fix_asymmetry", project=proj_path)
        assert_success(res)
        assert "created" in res["data"]
        assert "skipped" in res["data"]

    def test_batch_infer(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("graph.batch_infer", project=proj_path, actor="novel-v2-crafter")
        assert_success(res)
        assert "new_relations" in res["data"]
        assert "total_before" in res["data"]
        assert "total_after" in res["data"]

    def test_create_unit_without_content(self, tmp_project):
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="NOTE", name="空内容笔记", actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["content"] is None


# ============================================================================
# 3b. chapter_number 自动推断
# ============================================================================

class TestGraphWriteChapterNumber:
    def test_chapter_from_content_json(self, tmp_project):
        """不传 --chapter，从 content.章节号 自动推断"""
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="CHUNK", name="第5章",
                        content='{"章节号":5,"章节名":"测试"}', actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["chapter"] == 5

    def test_chapter_from_name(self, tmp_project):
        """不传 --chapter，从名称 第N章 自动推断"""
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="SCENE", name="第3章_上山", actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["chapter"] == 3

    def test_chapter_fallback_name_when_content_has_no_chapter(self, tmp_project):
        """content 有 JSON 但无 章节号 字段，回退到名称推断"""
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="CHUNK", name="第8章_测试",
                        content='{"章节名":"测试"}', actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["chapter"] == 8

    def test_chapter_explicit_overrides_all(self, tmp_project):
        """显式 --chapter 优先级高于 content.章节号 和 名称"""
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="CHUNK", name="第8章_测试",
                        content='{"章节号":5,"章节名":"测试"}',
                        chapter=7, actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["chapter"] == 7

    def test_chapter_none_when_no_info(self, tmp_project):
        """无任何章节信息时 chapter 为 None"""
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="NOTE", name="日常笔记", actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["chapter"] is None

    def test_chapter_content_non_json_ignored(self, tmp_project):
        """content 不是 JSON 时跳过 content 推断，走名称推断"""
        proj_path, store = tmp_project
        res = call_tool("graph.create_unit", project=proj_path,
                        type="CHUNK", name="第2章_赶路",
                        content="纯文本正文内容", actor="novel-v2-crafter")
        assert_success(res)
        verify = call_tool("graph.get_unit", project=proj_path, id=res["data"]["id"])
        assert verify["data"]["unit"]["chapter"] == 2


# ============================================================================
# 3c. 反序列化兼容性
# ============================================================================

class TestDeserialization:
    def test_from_dict_with_obsolete_fields(self):
        """存量 JSONL 带 belongs_to_project/belongs_to_chapter/belongs_to_volume 时不崩溃"""
        from graph_schema import NarrativeUnit
        old_data = {
            "id": "ca_legacy_001",
            "type": "character_arc",
            "unit_name": "旧角色",
            "content": "{}",
            "status": "mature",
            "confidence": 0.5,
            "tags": [],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "belongs_to_project": "旧项目名",
            "belongs_to_chapter": 5,
            "belongs_to_volume": 2,
            "version": 1,
            "extra": {},
        }
        unit = NarrativeUnit.from_dict(old_data)
        assert unit.id == "ca_legacy_001"
        assert unit.unit_name == "旧角色"
        # 已移除的字段不应导致报错
        assert unit.chapter_number is None  # old_data 中没有 chapter_number

    def test_from_dict_round_trip(self, tmp_project):
        """NarrativeUnit to_dict → from_dict 往返不丢字段"""
        proj_path, store = tmp_project
        from graph_schema import NarrativeUnit, UnitType
        original = store.create_unit(
            type=UnitType.SCENE, unit_name="第3章_测试",
            content='{"章节号":3}',
            tags=["测试"], actor="test",
        )
        d = original.to_dict()
        restored = NarrativeUnit.from_dict(d)
        assert restored.id == original.id
        assert restored.unit_name == original.unit_name
        assert restored.type == original.type
        assert restored.chapter_number == original.chapter_number
        assert restored.tags == original.tags
        assert restored.version == original.version
        assert restored.extra == original.extra


# ============================================================================
# 4. Graph 会话 / 导出 / 可视化 / 迁移
# ============================================================================

class TestGraphSessionExportViz:
    def test_start_session(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("session.start", project=proj_path,
                        type="SCENE", id=units["后山拔剑"].id)
        assert_success(res)
        assert "session_id" in res["data"]
        assert len(res["data"]["session_id"]) > 0

    def test_build_workspace_cold(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("session.build_workspace", project=proj_path,
                        id=units["后山拔剑"].id, preheat_level="cold")
        assert_success(res)
        assert "context" in res["data"]

    def test_build_workspace_warm(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("session.build_workspace", project=proj_path,
                        id=units["后山拔剑"].id, preheat_level="warm")
        assert_success(res)
        assert "context" in res["data"]

    def test_build_workspace_hot(self, sample_units):
        proj_path, store, units = sample_units
        res = call_tool("session.build_workspace", project=proj_path,
                        id=units["后山拔剑"].id, preheat_level="hot")
        assert_success(res)
        assert "context" in res["data"]

    @patch("projection_engine.ProjectionEngine.export_docs")
    def test_export_docs(self, mock_export, sample_units):
        proj_path, store, units = sample_units
        mock_export.return_value = {"doc1.md", "doc2.md"}
        res = call_tool("graph.export_docs", project=proj_path)
        assert_success(res)

    def test_export_chunks(self, tmp_project):
        proj_path, store = tmp_project
        from graph_schema import UnitType
        store.create_unit(type=UnitType.CHUNK, unit_name="第1章",
                          content="第一章正文", chapter_number=1, actor="novel-v2-crafter")
        store.flush()
        res = call_tool("graph.export_chunks", project=proj_path)
        assert_success(res)
        assert len(res["data"]["files"]) >= 1

    def test_export_chunks_no_chunks(self, tmp_project):
        proj_path, store = tmp_project
        res = call_tool("graph.export_chunks", project=proj_path)
        assert_success(res, lambda d: d.get("files") == [])

    @patch("migrate.run_migration")
    def test_migrate(self, mock_migrate, tmp_project):
        proj_path, store = tmp_project
        res = call_tool("graph.migrate", project=proj_path)
        assert_success(res, lambda d: d.get("migrated") is True)
        assert mock_migrate.called

    def test_start_session_resume(self, sample_units):
        proj_path, store, units = sample_units
        res1 = call_tool("session.start", project=proj_path,
                         type="SCENE", id=units["后山拔剑"].id)
        assert_success(res1)
        res2 = call_tool("session.start", project=proj_path,
                         type="SCENE", id=units["后山拔剑"].id)
        assert_success(res2)


# ============================================================================
# 5. Project 操作
# ============================================================================

class TestProject:
    def test_project_new_v2(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.new", name="测试小说", genre="玄幻",
                               v2=True, volumes=5, acts=3, structure="三幕")
                assert_success(res)
                assert res["data"]["v2"] is True
                proj_path = res["data"]["path"]
                assert os.path.isdir(os.path.join(proj_path, "graph"))
                assert os.path.isfile(os.path.join(proj_path, "config.yaml"))
                import yaml
                with open(os.path.join(proj_path, "config.yaml"), "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                assert cfg["项目名称"] == "测试小说"
                assert cfg["项目类型"] == "玄幻"
                assert cfg["架构"] == "v2"
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_new_v1(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.new", name="V1小说", v2=False,
                               volumes=2, acts=3, structure="三幕")
                assert_success(res)
                assert res["data"]["v2"] is False
                proj_path = res["data"]["path"]
                assert os.path.isdir(os.path.join(proj_path, "chapters"))
                assert os.path.isfile(os.path.join(proj_path, "config.yaml"))
                import yaml
                with open(os.path.join(proj_path, "config.yaml"), "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                assert "当前状态" in cfg
                assert "预期结构" in cfg
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_new_already_exists(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            os.makedirs(os.path.join(tmpdir, "已有项目"))
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.new", name="已有项目")
                assert_error(res, "已存在")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_import(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            src = os.path.join(tmpdir, "源项目")
            os.makedirs(src)
            Path(os.path.join(src, "test.txt")).write_text("hello", encoding="utf-8")
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.import", name="导入项目", source=src)
                assert_success(res)
                dst = os.path.join(tmpdir, "导入项目")
                assert os.path.isdir(dst)
                assert os.path.isfile(os.path.join(dst, "test.txt"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_import_source_not_found(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.import", name="导入项目",
                               source_path="/nonexistent/source")
                assert_error(res, "不存在")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_status(self, tmp_project):
        proj_path, store = tmp_project
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            proj_name = "状态测试"
            dst = os.path.join(tmpdir, proj_name)
            shutil.copytree(proj_path, dst)
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.status", name=proj_name)
                assert_success(res)
                assert res["data"]["name"] == proj_name
                assert res["data"]["is_v2"] is True
                assert "stats" in res["data"]
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_status_not_found(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.status", name="不存在的项目")
                assert_error(res, "不存在")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_resume(self, tmp_project):
        proj_path, store = tmp_project
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            proj_name = "续写测试"
            dst = os.path.join(tmpdir, proj_name)
            shutil.copytree(proj_path, dst)
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.resume", name=proj_name)
                assert_success(res, lambda d: d.get("ok") is True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_switch(self, tmp_project):
        proj_path, store = tmp_project
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            proj_name = "切换测试"
            dst = os.path.join(tmpdir, proj_name)
            shutil.copytree(proj_path, dst)
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.switch", name=proj_name)
                assert_success(res)
                assert res["data"]["project"] == proj_name
                ctx_path = os.path.join(os.path.dirname(TOOLS_DIR), "..", ".omo", "notepads", "novel-context.md")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_get_runtime_mode_default_release(self):
        """get_runtime_mode 默认 release；OMODE 覆盖且归一化。"""
        from handlers.handlers_project import get_runtime_mode

        saved = os.environ.get("OMODE")
        os.environ.pop("OMODE", None)
        try:
            assert get_runtime_mode() == "release"
        finally:
            if saved is not None:
                os.environ["OMODE"] = saved

        with patch.dict(os.environ, {"OMODE": "dev"}):
            assert get_runtime_mode() == "dev"
        with patch.dict(os.environ, {"OMODE": "RELEASE"}):
            assert get_runtime_mode() == "release"
        with patch.dict(os.environ, {"OMODE": "  "}):
            assert get_runtime_mode() == "release"

    def test_project_switch_writes_mode(self, tmp_project):
        """project.switch 将运行时模式写入 novel-context.md，默认 release。"""
        proj_path, store = tmp_project
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            proj_name = "切换模式测试"
            dst = os.path.join(tmpdir, proj_name)
            shutil.copytree(proj_path, dst)
            # _SHARED_DIR 经 abspath(join(X, "..", "..")) 计算 tool_root，
            # 需两级嵌套使 tool_root 落在 tmpdir
            fake_shared = os.path.join(tmpdir, "shared", "nested")
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir), \
                 patch("handlers.handlers_project._SHARED_DIR", fake_shared):
                res = call_tool("project.switch", name=proj_name)
                assert_success(res)
                assert res["data"]["mode"] == "release"
                ctx_path = os.path.join(tmpdir, ".context", "novel-context.md")
                with open(ctx_path, "r", encoding="utf-8") as f:
                    content = f.read()
                assert "__MODE__: release" in content
                assert "运行时模式：release" in content
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_switch_dry_run(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.switch", name="不存在", dryRun=True)
                assert_error(res)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_delete(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            proj_dir = os.path.join(tmpdir, "删除测试")
            os.makedirs(proj_dir)
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.delete", name="删除测试", force=True)
                assert res["data"]["deleted"] is True
                assert not os.path.isdir(proj_dir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_project_delete_no_force(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="proj_test_")
        try:
            os.makedirs(os.path.join(tmpdir, "删除测试"))
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                res = call_tool("project.delete", name="删除测试")
                assert_error(res, "force=True")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================================
# 6. Env 操作
# ============================================================================

class TestEnv:
    def test_env_check(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0")
            res = call_tool("env.check")
        assert_success(res)
        assert "python_version" in res["data"]
        assert "python_ok" in res["data"]
        assert "venv_exists" in res["data"]
        assert "deps_ok" in res["data"]

    def test_env_fix(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok")
            res = call_tool("env.fix")
        assert_success(res)

    def test_env_force(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok")
            with patch("shutil.rmtree") as mock_rmtree:
                mock_rmtree.return_value = None
                res = call_tool("env.force")
        assert_success(res)


# ============================================================================
# 7. Knowledge 操作
# ============================================================================

class TestKnowledge:
    def test_knowledge_read_missing_slug(self):
        res = call_tool("knowledge.read", project=".")
        # 必填参数校验：干净错误（无 raw TypeError traceback）
        assert_error(res, "缺少必填参数: slug")

    def test_knowledge_read_slug_not_found(self):
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="know_test_")
        try:
            from novel_tool import _find_novels_root
            with patch("novel_tool._find_novels_root", return_value=tmpdir):
                res = call_tool("knowledge.read", project=tmpdir, slug="nonexistent_book")
                assert_success(res)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_knowledge_list_books_empty(self):
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="know_test_")
        try:
            # handler uses _find_novels_root() directly (no project param), so patch it
            os.makedirs(os.path.join(tmpdir, "knowledge"), exist_ok=True)
            with patch("handlers.handlers_knowledge._find_novels_root", return_value=tmpdir):
                res = call_tool("knowledge.list_books", project=tmpdir)
                assert_success(res)
                assert res["data"]["books"] == []
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_knowledge_list_books_with_data(self):
        import tempfile, yaml
        tmpdir = tempfile.mkdtemp(prefix="know_test_")
        try:
            book_dir = os.path.join(tmpdir, "knowledge", "test-book")
            os.makedirs(book_dir)
            # Create source.yaml so KnowledgeReader recognizes it as a book
            source_yaml = {"title": "测试书籍", "author": "测试作者", "chapter_count": 5}
            with open(os.path.join(book_dir, "source.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(source_yaml, f, allow_unicode=True)
            Path(os.path.join(book_dir, "knowledge.md")).write_text("# 测试书籍内容", encoding="utf-8")
            with patch("handlers.handlers_knowledge._find_novels_root", return_value=tmpdir):
                res = call_tool("knowledge.list_books", project=tmpdir)
                assert_success(res)
                assert len(res["data"]["books"]) >= 1
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================================
# 8. Deviation 操作
# ============================================================================

class TestDeviation:
    def test_deviation_merge(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_test", "severity": "high",
                     "summary": "修为矛盾", "detail": "前文写化神后期，后文写元婴期"}]
        res = call_tool("deviation.merge", project=proj_path, findings=findings,
                        source="test", scan_version=1)
        assert_success(res)
        assert res["data"]["merged"] == 1
        assert res["data"]["total"] >= 1

    def test_deviation_merge_with_full_scan(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "情节逻辑", "entity": "后山拔剑",
                     "severity": "medium", "summary": "时间线冲突"}]
        res = call_tool("deviation.merge", project=proj_path, findings=findings,
                        full_scan_version=5)
        assert_success(res)
        assert res["data"]["full_scan_version"] == 5

    def test_deviation_list(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_1", "severity": "high",
                     "summary": "修为矛盾"}]
        call_tool("deviation.merge", project=proj_path, findings=findings, source="test")
        res = call_tool("deviation.list", project=proj_path)
        assert_success(res)
        assert len(res["data"]["deviations"]) >= 1

    def test_deviation_list_filtered(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_2", "severity": "high",
                     "summary": "修为矛盾", "status": "pending"}]
        call_tool("deviation.merge", project=proj_path, findings=findings)
        res = call_tool("deviation.list", project=proj_path, status="resolved")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 0

    def test_deviation_pending(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_3", "severity": "high",
                     "summary": "修为矛盾", "status": "pending"}]
        call_tool("deviation.merge", project=proj_path, findings=findings)
        res = call_tool("deviation.pending", project=proj_path)
        assert_success(res)
        assert len(res["data"]["deviations"]) >= 1

    def test_deviation_resolve(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_4", "severity": "high",
                     "summary": "修为矛盾"}]
        call_tool("deviation.merge", project=proj_path, findings=findings)
        list_res = call_tool("deviation.list", project=proj_path)
        did = list_res["data"]["deviations"][0]["id"]
        res = call_tool("deviation.resolve", project=proj_path, id=did)
        assert_success(res, lambda d: d.get("resolved") is True)

    def test_deviation_resolve_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("deviation.resolve", project=proj_path, id="nonexistent")
        assert_error(res, "不存在")

    def test_deviation_retain(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_5", "severity": "low",
                     "summary": "小差异"}]
        call_tool("deviation.merge", project=proj_path, findings=findings)
        list_res = call_tool("deviation.list", project=proj_path)
        did = list_res["data"]["deviations"][0]["id"]
        res = call_tool("deviation.retain", project=proj_path, id=did)
        assert_success(res, lambda d: d.get("retained") is True)

    def test_deviation_retain_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("deviation.retain", project=proj_path, id="nonexistent")
        assert_error(res, "不存在")

    def test_deviation_delete(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_6", "severity": "info",
                     "summary": "小问题"}]
        call_tool("deviation.merge", project=proj_path, findings=findings)
        list_res = call_tool("deviation.list", project=proj_path)
        did = list_res["data"]["deviations"][0]["id"]
        res = call_tool("deviation.delete", project=proj_path, id=did)
        assert_success(res, lambda d: d.get("deleted") is True)

    def test_deviation_delete_not_found(self, tmp_project):
        proj_path, _ = tmp_project
        res = call_tool("deviation.delete", project=proj_path, id="nonexistent")
        assert_error(res, "不存在")

    def test_deviation_stats(self, tmp_project):
        proj_path, store = tmp_project
        res = call_tool("deviation.stats", project=proj_path)
        assert_success(res)
        assert "total" in res["data"]
        assert "by_status" in res["data"]
        assert "by_severity" in res["data"]

    def test_deviation_stats_after_merge(self, tmp_project):
        proj_path, store = tmp_project
        findings = [{"dimension": "角色一致性", "entity": "林渊",
                     "entity_id": "ca_7", "severity": "high",
                     "summary": "修为矛盾"}]
        call_tool("deviation.merge", project=proj_path, findings=findings)
        res = call_tool("deviation.stats", project=proj_path)
        assert res["data"]["total"] >= 1

    def test_deviation_list_filters_severity(self, tmp_project):
        """按 severity 过滤偏差列表（集成测试）"""
        proj_path, store = tmp_project
        findings = [
            {"dimension": "角色一致性", "entity": "林渊", "entity_id": "ca_s1",
             "severity": "high", "summary": "高严重"},
            {"dimension": "情节逻辑", "entity": "后山拔剑", "entity_id": "sc_s1",
             "severity": "medium", "summary": "中严重"},
            {"dimension": "世界观", "entity": "天道宗", "entity_id": "wr_s1",
             "severity": "low", "summary": "低严重"},
            {"dimension": "角色一致性", "entity": "韩致", "entity_id": "ca_s2",
             "severity": "high", "summary": "另一高严重"},
        ]
        call_tool("deviation.merge", project=proj_path, findings=findings)

        # 过滤 high severity
        res = call_tool("deviation.list", project=proj_path, severity="high")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 2
        for d in res["data"]["deviations"]:
            assert d["severity"] == "high"

        # 过滤 medium severity
        res = call_tool("deviation.list", project=proj_path, severity="medium")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["severity"] == "medium"

        # 过滤 low severity
        res = call_tool("deviation.list", project=proj_path, severity="low")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["severity"] == "low"

        # 过滤不存在的 severity
        res = call_tool("deviation.list", project=proj_path, severity="critical")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 0

    def test_deviation_list_filters_dimension(self, tmp_project):
        """按 dimension 过滤偏差列表（集成测试）"""
        proj_path, store = tmp_project
        findings = [
            {"dimension": "角色一致性", "entity": "林渊", "entity_id": "ca_d1",
             "severity": "high", "summary": "角色偏差1"},
            {"dimension": "角色一致性", "entity": "韩致", "entity_id": "ca_d2",
             "severity": "medium", "summary": "角色偏差2"},
            {"dimension": "情节逻辑", "entity": "后山拔剑", "entity_id": "sc_d1",
             "severity": "high", "summary": "情节偏差"},
            {"dimension": "世界观", "entity": "天道宗", "entity_id": "wr_d1",
             "severity": "low", "summary": "世界观偏差"},
        ]
        call_tool("deviation.merge", project=proj_path, findings=findings)

        # 过滤 character_trait (角色一致性)
        res = call_tool("deviation.list", project=proj_path, dimension="角色一致性")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 2
        for d in res["data"]["deviations"]:
            assert d["dimension"] == "角色一致性"

        # 过滤 plot_consistency (情节逻辑)
        res = call_tool("deviation.list", project=proj_path, dimension="情节逻辑")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["dimension"] == "情节逻辑"

        # 过滤 world_rule (世界观)
        res = call_tool("deviation.list", project=proj_path, dimension="世界观")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["dimension"] == "世界观"

    def test_deviation_list_filters_combined(self, tmp_project):
        """组合 severity + dimension 过滤（集成测试）"""
        proj_path, store = tmp_project
        findings = [
            {"dimension": "角色一致性", "entity": "林渊", "entity_id": "ca_c1",
             "severity": "high", "summary": "高+角色"},
            {"dimension": "角色一致性", "entity": "韩致", "entity_id": "ca_c2",
             "severity": "medium", "summary": "中+角色"},
            {"dimension": "情节逻辑", "entity": "后山拔剑", "entity_id": "sc_c1",
             "severity": "high", "summary": "高+情节"},
            {"dimension": "世界观", "entity": "天道宗", "entity_id": "wr_c1",
             "severity": "low", "summary": "低+世界观"},
        ]
        call_tool("deviation.merge", project=proj_path, findings=findings)

        # 高严重 + 角色维度
        res = call_tool("deviation.list", project=proj_path, severity="high", dimension="角色一致性")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["entity"] == "林渊"

        # 高严重 + 情节维度
        res = call_tool("deviation.list", project=proj_path, severity="high", dimension="情节逻辑")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["entity"] == "后山拔剑"

        # 中严重 + 角色维度
        res = call_tool("deviation.list", project=proj_path, severity="medium", dimension="角色一致性")
        assert_success(res)
        assert len(res["data"]["deviations"]) == 1
        assert res["data"]["deviations"][0]["entity"] == "韩致"

    def test_deviation_pending_pagination(self, tmp_project):
        """待处理偏差分页：limit/offset 正确，total 为分页前总数，truncated 标志正确（集成测试）

        NOTE（本次修复）：5 条 pending 使用不同 dimension 构造，避免触发
        filter_for_presentation 的"≥3 同维度折叠"规则（缺陷修复后已实现）——
        否则 5 条同维度会被折叠为 1 条聚合条目，无法验证分页。
        """
        proj_path, store = tmp_project
        # 创建 5 个 pending 偏差（跨维度，避免触发 ≥3 同维度折叠）
        dims = ["角色一致性", "角色一致性", "情节逻辑", "情节逻辑", "世界观"]
        findings = []
        for i, dim in enumerate(dims):
            findings.append({
                "dimension": dim,
                "entity": f"角色{i}",
                "entity_id": f"ca_p{i}",
                "severity": "high" if i % 2 == 0 else "medium",
                "summary": f"偏差{i}",
                "status": "pending"
            })
        call_tool("deviation.merge", project=proj_path, findings=findings)

        # 第 1 页：limit=2, offset=0
        res1 = call_tool("deviation.pending", project=proj_path, limit=2, offset=0)
        assert_success(res1)
        data1 = res1["data"]
        assert data1["returned"] == 2
        assert data1["total"] == 5
        assert data1["truncated"] is True
        assert len(data1["deviations"]) == 2

        # 第 2 页：limit=2, offset=2
        res2 = call_tool("deviation.pending", project=proj_path, limit=2, offset=2)
        assert_success(res2)
        data2 = res2["data"]
        assert data2["returned"] == 2
        assert data2["total"] == 5
        assert data2["truncated"] is True
        assert len(data2["deviations"]) == 2

        # 第 3 页：limit=2, offset=4
        res3 = call_tool("deviation.pending", project=proj_path, limit=2, offset=4)
        assert_success(res3)
        data3 = res3["data"]
        assert data3["returned"] == 1
        assert data3["total"] == 5
        assert data3["truncated"] is True  # 1 < 5
        assert len(data3["deviations"]) == 1

        # 超出范围：offset=10
        res_empty = call_tool("deviation.pending", project=proj_path, limit=2, offset=10)
        assert_success(res_empty)
        data_empty = res_empty["data"]
        assert data_empty["returned"] == 0
        assert data_empty["total"] == 5
        assert data_empty["truncated"] is True  # len([]) < total → True

        # 验证无重叠
        ids1 = {d["id"] for d in data1["deviations"]}
        ids2 = {d["id"] for d in data2["deviations"]}
        ids3 = {d["id"] for d in data3["deviations"]}
        assert ids1.isdisjoint(ids2)
        assert ids2.isdisjoint(ids3)
        assert ids1.isdisjoint(ids3)
        assert len(ids1 | ids2 | ids3) == 5


# ============================================================================
# 11. Summary 列表分页与 total 语义
# ============================================================================


class TestSummaryListPagination:
    def test_summary_list_total_untruncated(self, tmp_project):
        """保存 25+ 条总结，验证 list_summaries 分页：total=总数，returned=limit，truncated=True，offset 分页正确"""
        proj_path, store = tmp_project

        # 创建 25 条主 Agent 会话总结
        for i in range(25):
            res = call_tool("summary.save", project=proj_path,
                          content=f"第 {i+1} 次会话总结内容",
                          session_id=f"ses_{i:03d}",
                          focus_type="SCENE",
                          focus_name=f"第{i+1}章",
                          tags="测试,分页",
                          record_type="main")
            assert_success(res)

        # 第 1 页：limit=10, offset=0
        res1 = call_tool("summary.list", project=proj_path, limit=10, offset=0, record_type="main")
        assert_success(res1)
        data1 = res1["data"]
        assert data1["total"] == 25, f"total 应为 25，实际 {data1['total']}"
        assert data1["returned"] == 10, f"returned 应为 10，实际 {data1['returned']}"
        assert data1["truncated"] is True, "第 1 页应被截断"
        assert len(data1["entries"]) == 10

        # 第 2 页：limit=10, offset=10
        res2 = call_tool("summary.list", project=proj_path, limit=10, offset=10, record_type="main")
        assert_success(res2)
        data2 = res2["data"]
        assert data2["total"] == 25, f"total 应为 25，实际 {data2['total']}"
        assert data2["returned"] == 10, f"returned 应为 10，实际 {data2['returned']}"
        assert data2["truncated"] is True, "第 2 页应被截断"
        assert len(data2["entries"]) == 10

        # 第 3 页：limit=10, offset=20
        res3 = call_tool("summary.list", project=proj_path, limit=10, offset=20, record_type="main")
        assert_success(res3)
        data3 = res3["data"]
        assert data3["total"] == 25, f"total 应为 25，实际 {data3['total']}"
        assert data3["returned"] == 5, f"returned 应为 5，实际 {data3['returned']}"
        assert data3["truncated"] is True, "truncated = returned(5) < total(25)"
        assert len(data3["entries"]) == 5

        # 验证第 1 页和第 2 页无重叠
        ids1 = {e["file"] for e in data1["entries"]}
        ids2 = {e["file"] for e in data2["entries"]}
        ids3 = {e["file"] for e in data3["entries"]}
        assert ids1.isdisjoint(ids2), "第 1 页和第 2 页不应有重叠"
        assert ids2.isdisjoint(ids3), "第 2 页和第 3 页不应有重叠"
        assert ids1.isdisjoint(ids3), "第 1 页和第 3 页不应有重叠"

        # 验证所有条目总数
        all_ids = ids1 | ids2 | ids3
        assert len(all_ids) == 25, f"所有页合并应为 25 条，实际 {len(all_ids)}"

    def test_summary_list_subagent_pagination(self, tmp_project):
        """子 Agent 总结同样支持分页"""
        proj_path, store = tmp_project

        # 创建 15 条子 Agent 总结
        for i in range(15):
            res = call_tool("summary.save", project=proj_path,
                          content=f"子 Agent 任务 {i+1} 总结",
                          record_type="subagent",
                          task_id=f"bg_{i:03d}",
                          subagent="novel-v2-crafter",
                          result="success",
                          prompt_summary=f"任务 {i+1} 提示",
                          result_summary=f"任务 {i+1} 结果")
            assert_success(res)

        # 第 1 页：limit=5
        res1 = call_tool("summary.list", project=proj_path, limit=5, offset=0, record_type="subagent")
        assert_success(res1)
        data1 = res1["data"]
        assert data1["total"] == 15
        assert data1["returned"] == 5
        assert data1["truncated"] is True

        # 第 2 页：limit=5, offset=5
        res2 = call_tool("summary.list", project=proj_path, limit=5, offset=5, record_type="subagent")
        assert_success(res2)
        data2 = res2["data"]
        assert data2["total"] == 15
        assert data2["returned"] == 5
        assert data2["truncated"] is True

        # 第 3 页：limit=5, offset=10
        res3 = call_tool("summary.list", project=proj_path, limit=5, offset=10, record_type="subagent")
        assert_success(res3)
        data3 = res3["data"]
        assert data3["total"] == 15
        assert data3["returned"] == 5
        assert data3["truncated"] is True, "truncated = returned(5) < total(15)"


# ============================================================================
# 9. 项目解析 & 错误边界
# ============================================================================

class TestProjectResolution:
    def test_resolve_project_absolute(self):
        path = _resolve_project("C:/absolute/path")
        assert path == "C:/absolute/path"

    def test_resolve_project_empty(self):
        path = _resolve_project("")
        assert path == ""

    def test_resolve_project_nonexistent(self, tmp_project):
        proj_path, _ = tmp_project
        result = _resolve_project(proj_path)
        assert result == proj_path

    def test_non_v2_project_rejected(self):
        import tempfile, yaml
        tmpdir = tempfile.mkdtemp(prefix="non_v2_")
        try:
            config = {"项目名称": "V1项目", "架构": "v1"}
            with open(os.path.join(tmpdir, "config.yaml"), "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True)
            os.makedirs(os.path.join(tmpdir, "chapters"), exist_ok=True)
            res = call_tool("graph.stats", project=tmpdir)
            assert_success(res)
            assert res["data"]["total_units"] == 0
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_graph_ops_no_project_fails(self):
        # 缺 project → 必填参数校验返回干净错误（无 traceback）
        res = call_tool("graph.stats", project="")
        assert_error(res, "缺少必填参数")


# ============================================================================
# 10. 跨域集成测试
# ============================================================================

class TestIntegration:
    def test_full_create_query_workflow(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="integration_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                # project.new
                r1 = call_tool("project.new", name="集成测试小说", genre="仙侠", v2=True)
                assert_success(r1)
                proj_path = r1["data"]["path"]

                # graph.create_unit x3
                r2 = call_tool("graph.create_unit", project=proj_path,
                              type="CHARACTER_ARC", name="叶凡",
                              content="主角", tags="主角", actor="novel-v2-crafter")
                assert_success(r2)
                vf_id = r2["data"]["id"]

                r3 = call_tool("graph.create_unit", project=proj_path,
                              type="SCENE", name="第一章-上山",
                              content="上山拜师", chapter=1, actor="novel-v2-crafter")
                assert_success(r3)
                scene_id = r3["data"]["id"]

                r4 = call_tool("graph.create_unit", project=proj_path,
                              type="WORLD_RULE", name="青云门",
                              content="修仙门派", actor="novel-v2-crafter")
                assert_success(r4)
                sect_id = r4["data"]["id"]

                # graph.add_relation
                r5 = call_tool("graph.add_relation", project=proj_path,
                              source=vf_id, target=scene_id,
                              type="PARTICIPATES_IN", actor="novel-v2-crafter")
                assert_success(r5)

                r6 = call_tool("graph.add_relation", project=proj_path,
                              source=vf_id, target=sect_id,
                              type="MEMBER_OF", actor="novel-v2-crafter")
                assert_success(r6)

                # graph.get_neighbors
                r7 = call_tool("graph.get_neighbors", project=proj_path, id=vf_id)
                assert_success(r7)
                neighbor_names = [n["name"] for n in r7["data"]["neighbors"]]
                assert "第一章-上山" in neighbor_names
                assert "青云门" in neighbor_names

                # graph.search
                r8 = call_tool("graph.search", project=proj_path, keyword="叶凡")
                assert_success(r8)
                assert r8["data"]["total"] >= 1

                # graph.stats
                r9 = call_tool("graph.stats", project=proj_path)
                assert_success(r9)
                assert r9["data"]["total_units"] >= 3
                assert r9["data"]["total_relations"] >= 2

                # graph.check
                r10 = call_tool("graph.check", project=proj_path)
                assert_success(r10)

                # graph.flush (含约束检查自动触发)
                r11 = call_tool("graph.flush", project=proj_path)
                assert_success(r11, lambda d: d.get("ok") is True and "constraint_check" in d)

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_deviation_full_workflow(self):
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp(prefix="deviation_int_")
        try:
            with patch("handlers.handlers_project.NOVELS_ROOT", tmpdir):
                r1 = call_tool("project.new", name="偏差测试", v2=True)
                assert_success(r1)
                proj_path = r1["data"]["path"]

                findings = [
                    {"dimension": "角色一致性", "entity": "林渊", "entity_id": "ca_1",
                     "severity": "high", "summary": "修为矛盾"},
                    {"dimension": "情节逻辑", "entity": "后山拔剑", "entity_id": "sc_1",
                     "severity": "medium", "summary": "时间线冲突"},
                ]

                # deviation.merge
                r2 = call_tool("deviation.merge", project=proj_path,
                              findings=findings, source="test", scan_version=1)
                assert_success(r2)
                assert r2["data"]["merged"] == 2

                # deviation.pending
                r3 = call_tool("deviation.pending", project=proj_path)
                assert_success(r3)
                assert len(r3["data"]["deviations"]) == 2

                # deviation.list
                r4 = call_tool("deviation.list", project=proj_path)
                assert_success(r4)
                assert len(r4["data"]["deviations"]) == 2

                # deviation.resolve
                did = r4["data"]["deviations"][0]["id"]
                r5 = call_tool("deviation.resolve", project=proj_path, id=did)
                assert_success(r5, lambda d: d.get("resolved") is True)

                # deviation.stats
                r6 = call_tool("deviation.stats", project=proj_path)
                assert_success(r6)
                assert r6["data"]["total"] == 2
                assert r6["data"]["by_status"]["resolved"] == 1
                assert r6["data"]["by_status"]["pending"] == 1

                # deviation.delete
                remaining = call_tool("deviation.list", project=proj_path)
                d2_id = remaining["data"]["deviations"][0]["id"]
                r7 = call_tool("deviation.delete", project=proj_path, id=d2_id)
                assert_success(r7, lambda d: d.get("deleted") is True)

                r8 = call_tool("deviation.stats", project=proj_path)
                assert r8["data"]["total"] == 1

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================================
# 13. 遥测归因：项目名规范化 + caller 默认值
# ============================================================================

class TestTelemetryAttribution:
    def test_project_basename(self):
        from novel_tool import _project_basename
        # 纯项目名
        assert _project_basename("凡人之诡影重重") == "凡人之诡影重重"
        # Windows 反斜杠完整路径
        assert _project_basename(r"C:\Users\Admin\novels\凡人之诡影重重") == "凡人之诡影重重"
        # 正斜杠路径 + 尾斜杠
        assert _project_basename("C:/Users/Admin/novels/凡人之诡影重重/") == "凡人之诡影重重"
        # 空值 / 无意义值
        assert _project_basename("") == ""
        assert _project_basename("novels") == ""
        assert _project_basename("graph") == ""

    def test_caller_defaults_orchestrator(self, tmp_project):
        """未传 caller/actor 时默认 orchestrator（编排层直接调 tool）。"""
        proj_path, _ = tmp_project
        with patch("novel_tool._record_success") as mock_record:
            call_tool("graph.stats", project=proj_path)
            args = mock_record.call_args.args
            # args: (proj_name, caller, op, canonical, duration_ms, result)
            assert args[1] == "orchestrator"

    def test_caller_prefers_explicit(self, tmp_project):
        """显式 caller 优先于 actor。"""
        proj_path, _ = tmp_project
        with patch("novel_tool._record_success") as mock_record:
            call_tool("graph.stats", project=proj_path, caller="novel-v2-crafter")
            args = mock_record.call_args.args
            assert args[1] == "novel-v2-crafter"

    def test_caller_falls_back_to_actor(self, tmp_project):
        """无 caller 时回退 actor。"""
        proj_path, _ = tmp_project
        with patch("novel_tool._record_success") as mock_record:
            call_tool("graph.stats", project=proj_path, actor="search-analysis")
            args = mock_record.call_args.args
            assert args[1] == "search-analysis"

    def test_proj_name_is_basename(self, tmp_project):
        """遥测记录的 project 是项目名而非完整路径（含尾斜杠路径也归一化）。"""
        proj_path, _ = tmp_project
        expected = os.path.basename(proj_path.rstrip(os.sep))
        with patch("novel_tool._record_success") as mock_record:
            call_tool("graph.stats", project=proj_path + os.sep)
            args = mock_record.call_args.args
            # args[0] = proj_name：应为纯项目名，不含路径分隔符
            assert args[0] == expected
            assert os.sep not in args[0].replace("\\", "/")
