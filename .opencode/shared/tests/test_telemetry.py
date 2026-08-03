"""
test_telemetry.py — 遥测读时归一化 + project 透传测试。

覆盖:
- project_basename() 规范化（Windows/正斜杠/尾斜杠/空值）
- _read_engine_telemetry 对历史污染 project 字段的读时归一化
- _read_project_telemetry 回退路径归一化
- usage_analyzer._collect_subagent_traces 归一化
- novel_tool analyze.telemetry 的 project 参数透传过滤
"""

import json
import os
import sys
from datetime import datetime, timezone

import pytest

SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2_DIR = os.path.join(SHARED_DIR, "v2")
TOOLS_DIR = os.path.join(SHARED_DIR, "tools")
for _d in [SHARED_DIR, V2_DIR, TOOLS_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

from conftest import json_request, call_tool, assert_success


def _write_ndjson(path, records):
    """写 NDJSON 文件（每条 dict 一行）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _mk_record(project, op="graph.stats", success=True, caller="orchestrator", ts="2026-07-01T00:00:00+00:00"):
    return {
        "ts": ts,
        "project": project,
        "caller": caller,
        "op": op,
        "success": success,
        "duration_ms": 10.0,
        "result_size": 10,
        "unit_count": 0,
        "relation_count": 0,
        "params": {},
    }


# ============================================================================
# 1. project_basename 规范化
# ============================================================================

class TestProjectBasename:
    def test_plain_name(self):
        from telemetry import project_basename
        assert project_basename("凡人之诡影重重") == "凡人之诡影重重"

    def test_windows_backslash_path(self):
        from telemetry import project_basename
        assert project_basename(r"C:\Users\Admin\Desktop\novels\凡人之诡影重重") == "凡人之诡影重重"

    def test_posix_path_trailing_slash(self):
        from telemetry import project_basename
        assert project_basename("C:/Users/Admin/novels/凡人之诡影重重/") == "凡人之诡影重重"

    def test_empty_and_special(self):
        from telemetry import project_basename
        assert project_basename("") == ""
        assert project_basename("novels") == ""
        assert project_basename("graph") == ""
        assert project_basename(None) == ""

    def test_basename_does_not_collapse_nested(self):
        from telemetry import project_basename
        # 多级目录只取最后一级
        assert project_basename("/a/b/c/项目X") == "项目X"


# ============================================================================
# 2. _read_engine_telemetry 读时归一化
# ============================================================================

class TestReadEngineTelemetry:
    def test_filter_matches_polluted_historical(self, tmp_path, monkeypatch):
        """历史完整路径记录通过项目名过滤也能命中。"""
        import telemetry
        monkeypatch.setattr(telemetry, "_resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-07.ndjson"), [
            _mk_record(r"C:\Users\Admin\Desktop\novels\凡人之诡影重重"),
            _mk_record("凡人之诡影重重"),
            _mk_record("另一个项目"),
        ])

        entries = telemetry._read_engine_telemetry("凡人之诡影重重")
        assert len(entries) == 2
        # 返回的 project 字段已归一化为纯项目名
        assert all(e["project"] == "凡人之诡影重重" for e in entries)

    def test_no_filter_returns_all_normalized(self, tmp_path, monkeypatch):
        import telemetry
        monkeypatch.setattr(telemetry, "_resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-07.ndjson"), [
            _mk_record(r"C:\path\项目A"),
            _mk_record("项目B/"),
        ])

        entries = telemetry._read_engine_telemetry()
        assert len(entries) == 2
        projects = {e["project"] for e in entries}
        assert projects == {"项目A", "项目B"}

    def test_full_path_filter_also_matches(self, tmp_path, monkeypatch):
        """调用方传完整路径过滤时同样归一化后匹配。"""
        import telemetry
        monkeypatch.setattr(telemetry, "_resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-07.ndjson"), [
            _mk_record("凡人之诡影重重"),
        ])

        entries = telemetry._read_engine_telemetry(r"C:\Users\Admin\novels\凡人之诡影重重")
        assert len(entries) == 1


# ============================================================================
# 3. _read_project_telemetry 回退路径归一化
# ============================================================================

class TestReadProjectTelemetry:
    def test_fallback_normalizes_project(self, tmp_path):
        import telemetry
        # 旧格式: {project_root}/graph/telemetry.ndjson
        graph_dir = tmp_path / "graph"
        graph_dir.mkdir(exist_ok=True)
        _write_ndjson(str(graph_dir / "telemetry.ndjson"), [
            _mk_record(r"C:\old\path\项目X"),
            {"ts": "2026-07-01T00:00:00+00:00", "op": "graph.stats", "success": True},  # 无 project
        ])

        entries = telemetry._read_project_telemetry(str(tmp_path))
        assert len(entries) == 2
        assert entries[0]["project"] == "项目X"  # 污染路径归一化
        assert entries[1]["project"] == os.path.basename(str(tmp_path))  # 缺失补 basename


# ============================================================================
# 4. usage_analyzer._collect_subagent_traces 归一化
# ============================================================================

class TestCollectSubagentTraces:
    def test_project_filter_normalized(self, tmp_path, monkeypatch):
        from usage_analyzer import _collect_subagent_traces
        monkeypatch.setattr("usage_analyzer._resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "subagents", "2026-07.ndjson"), [
            {"id": "1", "project": r"C:\Users\Admin\novels\项目A", "subagent": "novel-v2-crafter", "result": "success"},
            {"id": "2", "project": "项目A", "subagent": "explore", "result": "success"},
            {"id": "3", "project": "项目B", "subagent": "explore", "result": "failed"},
        ])

        res = _collect_subagent_traces("项目A")
        assert res["total_traces"] == 2
        assert res["success_count"] == 2


# ============================================================================
# 5. novel_tool analyze.telemetry project 参数透传
# ============================================================================

class TestAnalyzeTelemetryPassthrough:
    def test_project_filter_reaches_handler(self, tmp_path, monkeypatch):
        """analyze.telemetry 的 project 参数透传到 handler 并过滤。"""
        import engine_log
        import telemetry
        from telemetry import close_all
        from novel_tool import handle_request
        close_all()  # 重置遥测单例，避免缓存旧 engine root
        monkeypatch.setattr(engine_log, "resolve_engine_root", lambda: str(tmp_path))
        monkeypatch.setattr(telemetry, "_resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-07.ndjson"), [
            _mk_record("凡人之诡影重重"),
            _mk_record("凡人之诡影重重", success=False),
            _mk_record("另一个项目"),
        ])

        raw = handle_request(json_request("analyze.telemetry", project="凡人之诡影重重"))
        res = json.loads(raw)
        assert res["success"] is True
        data = res["data"]
        assert data["total_calls"] == 2  # 只统计该项目
        assert data["failure_count"] == 1

    def test_no_project_returns_all(self, tmp_path, monkeypatch):
        import engine_log
        import telemetry
        from telemetry import close_all
        from novel_tool import handle_request
        close_all()  # 重置遥测单例，避免缓存旧 engine root
        monkeypatch.setattr(engine_log, "resolve_engine_root", lambda: str(tmp_path))
        monkeypatch.setattr(telemetry, "_resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-07.ndjson"), [
            _mk_record("项目A"),
            _mk_record("项目B"),
        ])

        raw = handle_request(json_request("analyze.telemetry"))
        res = json.loads(raw)
        assert_success(res)
        assert res["data"]["total_calls"] == 2


# ============================================================================
# 6. 按天分片（EngineLogWriter 统一写入机制）
# ============================================================================

class TestDailySharding:
    def test_recorder_writes_daily_shard(self, tmp_path, monkeypatch):
        """遥测写入 {YYYY-MM-DD}.ndjson 而非月度文件。"""
        import engine_log
        from telemetry import TelemetryRecorder
        monkeypatch.setattr(engine_log, "resolve_engine_root", lambda: str(tmp_path))
        rec = TelemetryRecorder()
        try:
            rec.record(operation="graph.stats", params={"project": "项目A"},
                       success=True, duration_ms=5.0, project="项目A", caller="orchestrator")
        finally:
            rec.close()

        today = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(str(tmp_path), "telemetry", f"{today}.ndjson")
        assert os.path.isfile(path), f"应按天分片: {path}"
        with open(path, encoding="utf-8") as f:
            line = f.readline().strip()
        assert line, "应写入一条记录"
        entry = json.loads(line)
        assert entry["op"] == "graph.stats"
        assert entry["project"] == "项目A"
        assert entry["success"] is True

    def test_no_duplicate_records_on_first_flush(self, tmp_path, monkeypatch):
        """新 recorder 首次写入不膨胀（回归：_rotate 递归导致单条重复写入 240+ 份）。"""
        import engine_log
        from telemetry import TelemetryRecorder
        monkeypatch.setattr(engine_log, "resolve_engine_root", lambda: str(tmp_path))
        rec = TelemetryRecorder()
        try:
            for i in range(5):
                rec.record(operation=f"op.{i}", params={"n": i},
                           success=True, duration_ms=1.0, project="P", caller="test")
        finally:
            rec.close()

        today = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(str(tmp_path), "telemetry", f"{today}.ndjson")
        with open(path, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 5, f"应恰好 5 条，实际 {len(lines)} 条"
        ops = [json.loads(l)["op"] for l in lines]
        assert ops == ["op.0", "op.1", "op.2", "op.3", "op.4"]

    def test_legacy_monthly_files_still_readable(self, tmp_path, monkeypatch):
        """历史月度分片文件仍可被读取（消费端兼容）。"""
        import telemetry
        monkeypatch.setattr(telemetry, "_resolve_engine_root", lambda: str(tmp_path))
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-06.ndjson"), [
            _mk_record("项目A", ts="2026-06-01T00:00:00+00:00"),
        ])
        _write_ndjson(os.path.join(str(tmp_path), "telemetry", "2026-07.ndjson"), [
            _mk_record("项目B", ts="2026-07-01T00:00:00+00:00"),
        ])

        entries = telemetry._read_engine_telemetry()
        assert len(entries) == 2
        projects = {e["project"] for e in entries}
        assert projects == {"项目A", "项目B"}


# ============================================================================
# 7. daemon 模式遥测缺口修复（_daemon_handle_request 记录遥测）
# ============================================================================

class TestDaemonRecordsTelemetry:
    def test_daemon_success_records_telemetry(self, tmp_path, monkeypatch):
        """daemon 成功请求也写入遥测（修复缺口）。"""
        import engine_log
        import handlers
        from telemetry import close_all
        from novel_tool import _daemon_handle_request
        close_all()  # 重置单例，确保新 recorder 使用 tmp_path
        monkeypatch.setattr(engine_log, "resolve_engine_root", lambda: str(tmp_path))
        monkeypatch.setattr(handlers, "run_operation",
                            lambda op, **kw: {"ok": True, "data": "x"})

        try:
            raw = _daemon_handle_request(json_request("graph.stats", project="凡人之诡影重重"))
            res = json.loads(raw)
            assert res["success"] is True

            today = datetime.now().strftime("%Y-%m-%d")
            path = os.path.join(str(tmp_path), "telemetry", f"{today}.ndjson")
            assert os.path.isfile(path), f"daemon 请求应写入遥测: {path}"
            with open(path, encoding="utf-8") as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
            assert lines, "应至少有一条遥测记录"
            entry = json.loads(lines[-1])
            assert entry["op"] == "graph.stats"
            assert entry["success"] is True
            assert entry["project"] == "凡人之诡影重重"
        finally:
            close_all()  # 关闭文件句柄，避免 Windows tmp 清理失败

    def test_daemon_failure_records_telemetry(self, tmp_path, monkeypatch):
        """daemon 失败请求也写入遥测（错误归因）。"""
        import engine_log
        import handlers
        from telemetry import close_all
        from novel_tool import _daemon_handle_request
        close_all()
        monkeypatch.setattr(engine_log, "resolve_engine_root", lambda: str(tmp_path))
        monkeypatch.setattr(handlers, "run_operation",
                            lambda op, **kw: {"error": "boom"})

        try:
            raw = _daemon_handle_request(json_request("graph.stats", project="项目X"))
            res = json.loads(raw)
            assert res["success"] is False

            today = datetime.now().strftime("%Y-%m-%d")
            path = os.path.join(str(tmp_path), "telemetry", f"{today}.ndjson")
            with open(path, encoding="utf-8") as f:
                lines = [l for l in f.read().splitlines() if l.strip()]
            entry = json.loads(lines[-1])
            assert entry["op"] == "graph.stats"
            assert entry["success"] is False
            assert entry["error"]["type"] == "runtime_error"
        finally:
            close_all()
