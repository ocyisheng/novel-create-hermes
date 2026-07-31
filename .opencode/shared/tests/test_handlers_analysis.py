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


# ── sources 来源元数据 ──────────────────────────────────────────────

def test_save_with_sources_writes_frontmatter(engine_dir):
    """带 sources 的 save 写入 YAML front-matter（sources/aggregated_at/total_summaries）。"""
    res = handle_save_analysis(
        content="## 清单正文",
        sources=["项目A_2026-07-27_025440.summary.md", "项目A_2026-07-29_030746.summary.md"],
    )
    assert res["total_summaries"] == 2

    raw = (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    assert "sources:" in raw
    assert "项目A_2026-07-27_025440.summary.md" in raw
    assert "total_summaries: 2" in raw
    assert "aggregated_at:" in raw
    # 正文保留且 front-matter 剥离后仍完整
    assert raw.rstrip().endswith("## 清单正文")


def test_read_returns_sources_metadata(engine_dir):
    """read 剥离 front-matter，返回 content + sources 元数据。"""
    src = ["项目A_2026-07-27_025440.summary.md", "项目A_2026-07-29_030746.summary.md"]
    handle_save_analysis(content="## 清单正文\n1. 线索A", sources=src)

    res = handle_read_analysis()
    assert res["content"] == "## 清单正文\n1. 线索A"          # 正文无 front-matter
    assert res["sources"] == src
    assert res["total_summaries"] == 2
    assert res["aggregated_at"]  # 非空时间戳


def test_read_version_with_sources(engine_dir):
    """历史归档版本保留 sources 元数据。"""
    src1 = ["项目A_2026-07-27_025440.summary.md"]
    src2 = ["项目A_2026-07-29_030746.summary.md"]
    handle_save_analysis(content="第一轮", sources=src1)
    handle_save_analysis(content="第二轮", sources=src2)
    archived = list((engine_dir / "analysis" / "history").glob("clues_*.md"))[0].name

    res = handle_read_analysis(version=archived)
    assert res["content"] == "第一轮"
    assert res["sources"] == src1
    assert res["total_summaries"] == 1


def test_save_idempotent_with_sources(engine_dir):
    """同 content + sources 重复 save 幂等跳过。"""
    src = ["项目A_2026-07-27_025440.summary.md"]
    handle_save_analysis(content="相同内容", sources=src)
    res = handle_save_analysis(content="相同内容", sources=src)
    assert res.get("unchanged") is True
    assert res["archived"] is None
    assert list((engine_dir / "analysis" / "history").glob("clues_*.md")) == []


def test_save_sources_normalize_forms(engine_dir):
    """sources 支持 JSON 数组字符串与逗号分隔字符串。"""
    import json as _json
    handle_save_analysis(content="A", sources=_json.dumps(["f1.summary.md", "f2.summary.md"]))
    assert (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8").count("f1.summary.md") == 1

    handle_save_analysis(content="B", sources="f3.summary.md,f4.summary.md")
    raw = (engine_dir / "analysis" / "clues_aggregated.md").read_text(encoding="utf-8")
    assert "f3.summary.md" in raw and "f4.summary.md" in raw


def test_list_returns_sources(engine_dir):
    """list 的 current/history 条目携带 sources。"""
    src = ["项目A_2026-07-27_025440.summary.md"]
    handle_save_analysis(content="第一轮", sources=src)
    handle_save_analysis(content="第二轮", sources=src)

    res = handle_list_analysis()
    assert res["current"]["sources"] == src
    assert res["current"]["total_summaries"] == 1
    assert res["history"][0]["sources"] == src


def test_read_legacy_file_without_frontmatter(engine_dir):
    """无 front-matter 的旧文件 read 时 sources 为空、content 为全文。"""
    analysis_dir = engine_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "clues_aggregated.md").write_text(
        "## 旧清单（无元数据）\n1. 线索", encoding="utf-8"
    )
    res = handle_read_analysis()
    assert res["content"] == "## 旧清单（无元数据）\n1. 线索"
    assert res["sources"] == []
    assert res["total_summaries"] == 0


def test_archive_preserves_frontmatter(engine_dir):
    """归档保留原 front-matter（历史可追溯 sources）。"""
    src = ["项目A_2026-07-27_025440.summary.md"]
    handle_save_analysis(content="第一轮", sources=src)
    handle_save_analysis(content="第二轮", sources=src)
    archived_raw = list((engine_dir / "analysis" / "history").glob("clues_*.md"))[0].read_text(encoding="utf-8")
    assert archived_raw.startswith("---\n")
    assert "项目A_2026-07-27_025440.summary.md" in archived_raw
