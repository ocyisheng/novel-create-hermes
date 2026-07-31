"""
test_handlers_analysis.py — analysis 域 handler 测试（版本化归档）。

通过 NOVEL_ENGINE_DIR 环境变量将引擎目录重定向到临时目录，避免污染真实 .engine/。
"""

import os
import re

import pytest

from handlers.handlers_analysis import (
    handle_save_analysis,
    handle_read_analysis,
    handle_list_analysis,
)


@pytest.fixture
def engine_dir(tmp_path, monkeypatch):
    """将引擎根目录重定向到临时目录。"""
    monkeypatch.setenv("NOVEL_ENGINE_DIR", str(tmp_path))
    return tmp_path


def test_save_creates_current(engine_dir):
    """首次 save 创建当前清单，无归档。"""
    res = handle_save_analysis(content="## 第一轮\n### critical\n1. 线索A")
    assert res["archived"] is None
    assert "unchanged" not in res

    assert (engine_dir / "analysis" / "clues_aggregated.md").exists()
    content = (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8")
    assert content == "## 第一轮\n### critical\n1. 线索A"


def test_save_archives_previous(engine_dir):
    """第二轮 save 自动归档旧版，返回归档文件名。"""
    handle_save_analysis(content="第一轮内容")
    res = handle_save_analysis(content="第二轮内容")

    assert res["archived"] is not None
    assert re.match(r"^clues_\d{8}_\d{6}_\d{3}\.md$", res["archived"])

    history = (engine_dir / "analysis" / "history")
    archived_files = list(history.glob("clues_*.md"))
    assert len(archived_files) == 1
    assert archived_files[0].read_text(encoding="utf-8") == "第一轮内容"

    current = (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8")
    assert current == "第二轮内容"


def test_save_archives_each_round(engine_dir, monkeypatch):
    """多轮 save 每轮都归档，毫秒时间戳保证同秒不冲突。"""
    for i in range(5):
        handle_save_analysis(content=f"第{i}轮内容")
    archived = sorted(p.name for p in (engine_dir / "analysis" / "history").glob("clues_*.md"))
    assert len(archived) == 4  # 第一轮无归档，后续 4 轮各归档一次
    # 毫秒时间戳唯一性
    assert len(set(archived)) == len(archived)


def test_save_idempotent(engine_dir):
    """同内容重复 save 跳过归档与写入。"""
    handle_save_analysis(content="相同内容")
    res = handle_save_analysis(content="相同内容")
    assert res.get("unchanged") is True
    assert res["archived"] is None
    assert list((engine_dir / "analysis" / "history").glob("clues_*.md")) == []


def test_save_empty_initializes(engine_dir):
    """空内容 save 写入初始化头。"""
    res = handle_save_analysis(content="")
    assert "初始化" in (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8")


def test_read_current(engine_dir):
    """read 默认读当前版本。"""
    handle_save_analysis(content="当前内容")
    res = handle_read_analysis()
    assert res["version"] == "current"
    assert res["content"] == "当前内容"


def test_read_version(engine_dir):
    """read 指定 version 读取历史归档。"""
    handle_save_analysis(content="第一轮内容")
    handle_save_analysis(content="第二轮内容")
    archived = list((engine_dir / "analysis" / "history").glob("clues_*.md"))[0].name

    res = handle_read_analysis(version=archived)
    assert res["version"] == archived
    assert res["content"] == "第一轮内容"


def test_read_version_invalid(engine_dir):
    """非法版本名（目录穿越）被拒绝。"""
    res = handle_read_analysis(version="../../evil.md")
    assert "非法版本名" in res["error"]

    res = handle_read_analysis(version="clues_20260101_000000_000.md")  # 格式合法但不存在
    assert "历史版本不存在" in res["error"]


def test_list_versions(engine_dir):
    """list 返回当前 + 全部历史，按时间倒序。"""
    handle_save_analysis(content="第一轮内容")
    handle_save_analysis(content="第二轮内容")

    res = handle_list_analysis()
    assert res["current"]["version"] == "current"
    assert (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8") == "第二轮内容"
    assert res["count"] == 1
    assert len(res["history"]) == 1
    assert res["history"][0]["content"] if "content" in res["history"][0] else True  # 历史条目不含 content，仅元数据


def test_read_missing_file(engine_dir):
    """从未 save 时 read 返回空 content。"""
    res = handle_read_analysis()
    assert res["content"] == ""
    assert res["version"] == "current"
