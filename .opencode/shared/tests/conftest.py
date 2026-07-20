"""
pytest conftest — 统一测试配置。

在测试收集前设置 sys.path，使各模块可从 shared/tests/ 导入 v2/、tools/ 等。
提供所有测试文件共享的 fixtures 和辅助函数。
"""

import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

# ── sys.path 统一设置 ──────────────────────────────────────
# shared/tests/ 下的测试文件需要导入 v2/ 和 tools/ 中的模块
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2_DIR = os.path.join(SHARED_DIR, "v2")
TOOLS_DIR = os.path.join(SHARED_DIR, "tools")
for _d in [SHARED_DIR, V2_DIR, TOOLS_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)


# ── 共享辅助函数 ─────────────────────────────────────────────

def json_request(op: str, **kwargs) -> dict:
    """构建一个 novel-tool 风格的请求 dict。"""
    d = {"operation": op}
    d.update(kwargs)
    return d


def call_tool(op: str, **kwargs) -> dict:
    """调用 handle_request 并解析 JSON 结果。"""
    from novel_tool import handle_request
    raw = handle_request(json_request(op, **kwargs))
    return json.loads(raw)


def assert_success(res: dict, data_check=None):
    assert res.get("success") is True, f"Expected success, got: {res}"
    if data_check is not None:
        if callable(data_check):
            data_check(res["data"])
        else:
            assert res["data"] == data_check, f"Data mismatch: {res['data']} != {data_check}"


def assert_error(res: dict, msg_contain=None):
    assert res.get("success") is False, f"Expected error, got: {res}"
    if msg_contain:
        assert msg_contain in res.get("error", ""), f"Error '{res.get('error')}' does not contain '{msg_contain}'"


# ── 共享 Fixtures ─────────────────────────────────────────────

@pytest.fixture
def project_root():
    """创建一个临时项目根目录（供 GraphStore 测试使用）。"""
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def store(project_root):
    """创建一个已初始化的 GraphStore 实例。"""
    from graph_store import GraphStore
    s = GraphStore(project_root)
    s.initialize()
    yield s
    try:
        s.flush()
    except Exception:
        pass


@pytest.fixture
def tmp_project():
    """创建一个完整的临时 V2 项目目录（含 config.yaml + 已初始化 GraphStore）。"""
    tmpdir = tempfile.mkdtemp(prefix="novel_tool_test_")
    graph_dir = os.path.join(tmpdir, "graph")
    os.makedirs(graph_dir, exist_ok=True)
    for fn in ["nodes.jsonl", "edges.jsonl"]:
        Path(os.path.join(graph_dir, fn)).touch()

    config = {
        "项目名称": "测试项目",
        "项目类型": "测试",
        "活跃风格": "通俗网文风",
        "架构": "v2",
        "状态": "进行中",
        "创建时间": "2026-01-01",
        "最后编辑": "2026-01-01",
    }
    with open(os.path.join(tmpdir, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    from graph_store import GraphStore
    store = GraphStore(str(tmpdir))
    store.initialize()
    store.flush()

    yield tmpdir, store

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_units(tmp_project):
    """创建若干示例叙事单元供查询测试使用。"""
    proj_path, store = tmp_project
    from graph_schema import UnitType
    c1 = store.create_unit(type=UnitType.CHARACTER_ARC, unit_name="林渊",
                           content='{"角色":"主角","修为":"化神期"}', tags=["主角", "剑修"], actor="test")
    c2 = store.create_unit(type=UnitType.CHARACTER_ARC, unit_name="陈峰",
                           content='{"角色":"主角","职业":"CEO"}', tags=["主角", "商战"], actor="test")
    sc = store.create_unit(type=UnitType.SCENE, unit_name="后山拔剑",
                           content='{"地点":"落云宗"}', tags=["关键场景"], actor="test")
    pt = store.create_unit(type=UnitType.PLOT_THREAD, unit_name="主线-剑道之争",
                           content='{"类型":"主线"}', tags=["主线"], actor="test")
    wr = store.create_unit(type=UnitType.WORLD_RULE, unit_name="落云宗",
                           content='{"子类型":"势力"}', tags=["宗门"], actor="test")
    nt = store.create_unit(type=UnitType.NOTE, unit_name="测试笔记",
                           content='{"note":"备忘"}', actor="test")
    from graph_schema import RelationType
    store.add_relation(c1.id, sc.id, RelationType.PARTICIPATES_IN, actor="test")
    store.add_relation(c2.id, sc.id, RelationType.PARTICIPATES_IN, actor="test")
    store.flush()
    return proj_path, store, {"林渊": c1, "陈峰": c2, "后山拔剑": sc, "主线": pt, "落云宗": wr, "笔记": nt}
