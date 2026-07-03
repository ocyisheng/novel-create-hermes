"""
pytest conftest.py — 在测试收集前设置 sys.path 并提供共享 fixtures。

V2 目录下的 test_*.py 文件依赖同目录下的 graph_schema.py / graph_store.py 等模块。
由于 v2/__init__.py 在包导入时会尝试 from graph_schema import ...，
需要在 __init__.py 执行之前将 v2 目录加入 sys.path。
"""

import sys
import os
import tempfile
import shutil
import pytest


V2_DIR = os.path.abspath(os.path.dirname(__file__))
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)


@pytest.fixture
def project_root():
    """创建一个临时项目根目录"""
    tmpdir = tempfile.mkdtemp(prefix="v2_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def store(project_root):
    """创建一个已初始化的 GraphStore 实例"""
    from graph_store import GraphStore
    s = GraphStore(project_root)
    s.initialize()
    yield s
    try:
        s.flush()
    except Exception:
        pass
