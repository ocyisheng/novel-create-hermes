"""
test_handlers_analysis.py — analysis 域 handler 测试（版本化文件 + index.json + 修复状态）。

通过 NOVEL_ENGINE_DIR 环境变量将引擎目录重定向到临时目录，避免污染真实 .engine/。
"""

import json
import os
import re

import pytest

from handlers.handlers_analysis import (
    handle_save_analysis,
    handle_read_analysis,
    handle_list_analysis,
    handle_resolve_analysis,
)


@pytest.fixture
def engine_dir(tmp_path, monkeypatch):
    """将引擎根目录重定向到临时目录。"""
    monkeypatch.setenv("NOVEL_ENGINE_DIR", str(tmp_path))
    return tmp_path


def _analysis_dir(engine_dir):
    return engine_dir / "analysis"


def _list_versioned(engine_dir):
    """根目录下的版本化清单文件。"""
    return sorted(p.name for p in _analysis_dir(engine_dir).glob("clues_*.md") if re.match(r"^clues_\d{8}_\d{6}_\d{3}\.md$", p.name))


# ── 版本化文件 + 索引 ──────────────────────────────────────────────

def test_save_creates_versioned_file(engine_dir):
    """首次 save 创建版本化文件名（clues_YYYYMMDD_HHMMSS_fff.md）并登记 index。"""
    res = handle_save_analysis(content="## 第一轮\n### critical\n1. 线索A")
    assert "unchanged" not in res
    assert re.match(r"^clues_\d{8}_\d{6}_\d{3}\.md$", res["file"])
    assert res["total"] == 1
    assert res["clues"] == []  # 无 **[类型] 组件** 格式时线索为空

    versioned = _list_versioned(engine_dir)
    assert len(versioned) == 1
    assert versioned[0] == res["file"]
    # 不再有固定 clues_aggregated.md 当前文件
    assert not (_analysis_dir(engine_dir) / "clues_aggregated.md").exists()

    content = (_analysis_dir(engine_dir) / res["file"]).read_text(encoding="utf-8")
    assert content == "## 第一轮\n### critical\n1. 线索A"

    # index.json 自动登记
    index = json.loads((_analysis_dir(engine_dir) / "index.json").read_text(encoding="utf-8"))
    assert index["total"] == 1
    assert index["entries"][0]["file"] == res["file"]
    assert index["entries"][0]["resolved"] == []


def test_save_creates_new_version_each_round(engine_dir):
    """多轮 save 每轮生成独立版本文件，不覆盖不归档，索引累计。"""
    files = []
    for i in range(5):
        res = handle_save_analysis(content=f"第{i}轮内容")
        files.append(res["file"])

    versioned = _list_versioned(engine_dir)
    assert len(versioned) == 5  # 每轮一个文件，都在根目录
    assert len(set(files)) == 5  # 毫秒时间戳唯一性
    assert versioned == sorted(files)

    index = json.loads((_analysis_dir(engine_dir) / "index.json").read_text(encoding="utf-8"))
    assert index["total"] == 5
    assert index["entries"][-1]["file"] == files[-1]  # 最新在后


def test_save_idempotent(engine_dir):
    """同内容重复 save 跳过写入，不新增版本。"""
    handle_save_analysis(content="相同内容")
    res = handle_save_analysis(content="相同内容")
    assert res.get("unchanged") is True
    assert len(_list_versioned(engine_dir)) == 1
    assert res["total"] == 1


def test_save_empty_initializes(engine_dir):
    """空内容 save 写入初始化头。"""
    res = handle_save_analysis(content="")
    assert "初始化" in (_analysis_dir(engine_dir) / res["file"]).read_text(encoding="utf-8")


# ── 线索提取 ──────────────────────────────────────────────────────

def test_save_extracts_clue_keys(engine_dir):
    """save 时从正文提取 **[类型] 组件** 线索标识到 index。"""
    content = """## 优化线索聚合分析

### critical
1. **[workflow] 编排层·创建/拆分前查重**（出现 2 次）
2. **[handler] graph_store 文件锁**（出现 2 次）

### low
1. **[schema] 键名校验**：中文键名警告
"""
    res = handle_save_analysis(content=content)
    assert res["clues"] == [
        "[workflow] 编排层·创建/拆分前查重",
        "[handler] graph_store 文件锁",
        "[schema] 键名校验",
    ]

    index = json.loads((_analysis_dir(engine_dir) / "index.json").read_text(encoding="utf-8"))
    assert index["entries"][0]["clues"] == res["clues"]


# ── read / list ──────────────────────────────────────────────────

def test_read_latest(engine_dir):
    """read 默认读最新版本（index 最后一条）。"""
    handle_save_analysis(content="第一轮内容")
    handle_save_analysis(content="第二轮内容")
    res = handle_read_analysis()
    assert res["content"] == "第二轮内容"
    assert res["version"] != "current"  # 版本化文件名
    assert re.match(r"^clues_\d{8}_\d{6}_\d{3}\.md$", res["version"])


def test_read_version(engine_dir):
    """read 指定 version 读取指定版本文件。"""
    r1 = handle_save_analysis(content="第一轮内容")
    r2 = handle_save_analysis(content="第二轮内容")
    assert r1["file"] != r2["file"]

    res = handle_read_analysis(version=r1["file"])
    assert res["version"] == r1["file"]
    assert res["content"] == "第一轮内容"


def test_read_current_alias(engine_dir):
    """read version=current 兼容旧调用，读最新。"""
    handle_save_analysis(content="第一轮内容")
    handle_save_analysis(content="第二轮内容")
    res = handle_read_analysis(version="current")
    assert res["content"] == "第二轮内容"


def test_read_missing_file(engine_dir):
    """从未 save 时 read 返回空 content。"""
    res = handle_read_analysis()
    assert res["content"] == ""
    assert res["version"] == "current"


def test_list_versions(engine_dir):
    """list 返回全部版本，按时间升序（最新在后），含线索与修复状态。"""
    handle_save_analysis(content="第一轮\n1. **[workflow] A**")
    handle_save_analysis(content="第二轮\n1. **[schema] B**")

    res = handle_list_analysis()
    assert res["total"] == 2
    assert len(res["entries"]) == 2
    assert res["entries"][-1]["file"] != res["entries"][0]["file"]
    assert res["entries"][-1]["clues"] == ["[schema] B"]
    assert res["resolved_count"] == 0


# ── analysis.resolve 修复状态 ────────────────────────────────────

def test_resolve_default_latest(engine_dir):
    """resolve 默认作用于最新清单，记录修复状态到 index。"""
    handle_save_analysis(content="## 清单\n1. **[workflow] 查重**（出现 2 次）")

    res = handle_resolve_analysis(clue="[workflow] 查重", note="已在 crafter prompt 增加硬约束")
    assert res["matched"] is True
    assert res["clue"] == "[workflow] 查重"
    assert len(res["resolved"]) == 1
    assert res["resolved"][0]["note"] == "已在 crafter prompt 增加硬约束"
    assert "resolved_at" in res["resolved"][0]

    index = json.loads((_analysis_dir(engine_dir) / "index.json").read_text(encoding="utf-8"))
    assert index["entries"][0]["resolved"][0]["clue"] == "[workflow] 查重"

    # read 返回 resolved 状态
    rd = handle_read_analysis()
    assert rd["resolved"][0]["clue"] == "[workflow] 查重"


def test_resolve_contains_match(engine_dir):
    """resolve 支持包含匹配（传子串命中完整线索）。"""
    handle_save_analysis(content="## 清单\n1. **[handler] graph_store._flush_edges 文件锁**")

    res = handle_resolve_analysis(clue="_flush_edges")
    assert res["matched"] is True
    assert res["clue"] == "[handler] graph_store._flush_edges 文件锁"


def test_resolve_fallback_unmatched(engine_dir):
    """clue 未命中清单线索列表时按原样记录（宽容模式），matched=False。"""
    handle_save_analysis(content="## 清单\n1. **[workflow] A线索**")

    res = handle_resolve_analysis(clue="自定义标识")
    assert res["matched"] is False
    assert res["clue"] == "自定义标识"
    assert len(res["resolved"]) == 1


def test_resolve_specific_file(engine_dir):
    """resolve 指定 file 作用于该版本清单。"""
    r1 = handle_save_analysis(content="## 第一轮\n1. **[workflow] A线索**")
    r2 = handle_save_analysis(content="## 第二轮\n1. **[workflow] A线索**（再次出现）")

    # 作用于旧版本
    res = handle_resolve_analysis(file=r1["file"], clue="[workflow] A线索")
    assert res["file"] == r1["file"]

    # 新版本独立，不受旧 resolve 影响
    rd = handle_read_analysis()  # 最新 = 第二轮
    assert rd["file"] == r2["file"]
    assert rd["resolved"] == []


def test_resolve_deduplicate(engine_dir):
    """同一线索重复 resolve 更新 resolved_at，不新增条目。"""
    handle_save_analysis(content="## 清单\n1. **[workflow] 查重**")

    handle_resolve_analysis(clue="[workflow] 查重", note="第一次")
    res = handle_resolve_analysis(clue="[workflow] 查重", note="第二次")
    assert len(res["resolved"]) == 1
    assert res["resolved"][0]["note"] == "第二次"


def test_resolve_missing_params(engine_dir):
    """resolve 缺 clue 报错。"""
    res = handle_resolve_analysis()
    assert "clue" in res["error"]

    handle_save_analysis(content="## 清单")
    res = handle_resolve_analysis(clue="x", file="clues_99999999_999999_999.md")
    assert "清单不存在" in res["error"]


def test_resolve_no_entries(engine_dir):
    """无清单时 resolve 报错。"""
    res = handle_resolve_analysis(clue="[workflow] x")
    assert "尚无改进清单" in res["error"]


def test_list_resolved_count(engine_dir):
    """list 汇总 resolved_count。"""
    handle_save_analysis(content="## 清单\n1. **[workflow] A**\n2. **[schema] B**")
    handle_resolve_analysis(clue="[workflow] A")

    res = handle_list_analysis()
    assert res["resolved_count"] == 1


# ── sources 来源元数据 ──────────────────────────────────────────────

def test_save_with_sources_writes_frontmatter(engine_dir):
    """带 sources 的 save 写入 JSON front-matter（sources/aggregated_at/total_summaries）。"""
    res = handle_save_analysis(
        content="## 清单正文",
        sources=["项目A_2026-07-27_025440.summary.md", "项目A_2026-07-29_030746.summary.md"],
    )
    assert res["total_summaries"] == 2

    raw = (_analysis_dir(engine_dir) / res["file"]).read_text(encoding="utf-8")
    assert raw.startswith("---\n")
    fm_line = raw.split("\n")[1]
    meta = json.loads(fm_line)
    assert meta["sources"] == ["项目A_2026-07-27_025440.summary.md", "项目A_2026-07-29_030746.summary.md"]
    assert meta["total_summaries"] == 2
    assert "aggregated_at" in meta
    assert raw.rstrip().endswith("## 清单正文")


def test_save_infers_project_from_sources(engine_dir):
    """project 从 sources 文件名推断，写入 front-matter 与 index。"""
    res = handle_save_analysis(
        content="## 清单正文",
        sources=["凡人之诡影重重_2026-08-01_094254_028.summary.md"],
    )
    index = json.loads((_analysis_dir(engine_dir) / "index.json").read_text(encoding="utf-8"))
    assert index["entries"][0]["project"] == "凡人之诡影重重"

    rd = handle_read_analysis()
    assert rd["project"] == "凡人之诡影重重"


def test_save_explicit_project(engine_dir):
    """显式 project 优先于 sources 推断。"""
    res = handle_save_analysis(
        content="## 清单正文",
        sources=["项目A_2026-07-27_025440.summary.md"],
        project="项目B",
    )
    rd = handle_read_analysis()
    assert rd["project"] == "项目B"


def test_read_returns_sources_metadata(engine_dir):
    """read 剥离 front-matter，返回 content + sources 元数据。"""
    src = ["项目A_2026-07-27_025440.summary.md", "项目A_2026-07-29_030746.summary.md"]
    handle_save_analysis(content="## 清单正文\n1. 线索A", sources=src)

    res = handle_read_analysis()
    assert res["content"] == "## 清单正文\n1. 线索A"
    assert res["sources"] == src
    assert res["total_summaries"] == 2
    assert res["aggregated_at"]


def test_save_idempotent_with_sources(engine_dir):
    """同 content + sources 重复 save 幂等跳过。"""
    src = ["项目A_2026-07-27_025440.summary.md"]
    handle_save_analysis(content="相同内容", sources=src)
    res = handle_save_analysis(content="相同内容", sources=src)
    assert res.get("unchanged") is True
    assert len(_list_versioned(engine_dir)) == 1


def test_save_sources_normalize_forms(engine_dir):
    """sources 支持 JSON 数组字符串与逗号分隔字符串。"""
    r1 = handle_save_analysis(content="A", sources=json.dumps(["f1.summary.md", "f2.summary.md"]))
    assert (_analysis_dir(engine_dir) / r1["file"]).read_text(encoding="utf-8").count("f1.summary.md") == 1

    r2 = handle_save_analysis(content="B", sources="f3.summary.md,f4.summary.md")
    raw = (_analysis_dir(engine_dir) / r2["file"]).read_text(encoding="utf-8")
    assert "f3.summary.md" in raw and "f4.summary.md" in raw


def test_read_legacy_file_without_frontmatter(engine_dir):
    """无 front-matter 的旧文件 read 时 sources 为空、content 为全文。"""
    analysis_dir = _analysis_dir(engine_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "clues_aggregated.md").write_text(
        "## 旧清单（无元数据）\n1. 线索", encoding="utf-8"
    )
    res = handle_read_analysis(version="clues_aggregated.md")
    assert res["content"] == "## 旧清单（无元数据）\n1. 线索"
    assert res["sources"] == []
    assert res["total_summaries"] == 0


def test_read_yaml_legacy_frontmatter(engine_dir):
    """早期 YAML front-matter 文件仍可解析（向后兼容）。"""
    analysis_dir = _analysis_dir(engine_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "clues_aggregated.md").write_text(
        "---\nsources:\n- 旧版_2026-01-01_000000.summary.md\ntotal_summaries: 1\n---\n## YAML 旧版清单",
        encoding="utf-8",
    )
    res = handle_read_analysis(version="clues_aggregated.md")
    assert res["content"] == "## YAML 旧版清单"
    assert res["sources"] == ["旧版_2026-01-01_000000.summary.md"]
    assert res["total_summaries"] == 1


# ── 旧数据迁移 ──────────────────────────────────────────────────────

def test_rebuild_index_from_legacy(engine_dir):
    """index.json 缺失时自动扫描旧文件（history/ + clues_aggregated.md）重建索引。"""
    analysis_dir = _analysis_dir(engine_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "history").mkdir(exist_ok=True)

    # 旧版当前清单 + 旧归档
    (analysis_dir / "clues_aggregated.md").write_text(
        "---\n" + json.dumps({"sources": ["项目A_2026-07-27_025440.summary.md"], "total_summaries": 1}, ensure_ascii=False) + "\n---\n## 旧清单\n1. **[workflow] 旧线索A**",
        encoding="utf-8",
    )
    (analysis_dir / "history" / "clues_20260728_100000_000.md").write_text(
        "---\n" + json.dumps({"sources": ["项目A_2026-07-27_025440.summary.md"], "total_summaries": 1}, ensure_ascii=False) + "\n---\n## 更旧清单\n1. **[handler] 旧线索B**",
        encoding="utf-8",
    )

    res = handle_list_analysis()
    assert res["total"] == 2
    assert any(e["file"] == "clues_aggregated.md" and e["location"] == "legacy" for e in res["entries"])
    assert any(e["file"] == "clues_20260728_100000_000.md" and e["location"] == "history" for e in res["entries"])

    # 旧文件可读且线索已提取
    lr = handle_read_analysis(version="clues_aggregated.md")
    assert lr["clues"] == ["[workflow] 旧线索A"]


def test_legacy_coexists_with_new_save(engine_dir):
    """新 save 与迁移的旧数据共存，索引累计。"""
    analysis_dir = _analysis_dir(engine_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "clues_aggregated.md").write_text(
        "---\n" + json.dumps({"sources": ["项目A_2026-07-27_025440.summary.md"], "total_summaries": 1}, ensure_ascii=False) + "\n---\n## 旧清单",
        encoding="utf-8",
    )

    handle_list_analysis()  # 触发重建
    r = handle_save_analysis(content="## 新清单", sources=["项目A_2026-08-01_094254_028.summary.md"])
    assert r["total"] == 2

    rd = handle_read_analysis()  # 最新 = 新清单
    assert "新清单" in rd["content"]
