"""
engine_log.py — 引擎结构化日志统一写入基类。

telemetry（调用级遥测）与 daemon（进程级事件日志）共用的按天分片写入器。
两个存储保持分离（schema 不同，不合并文件），只在「写入机制」层面统一。

约定：
- 按天分片: .engine/{subdir}/{prefix}{YYYY-MM-DD}{ext}
- 惰性创建：首次写入时才建目录/文件（模块 import 不产生文件）
- 跨天自动轮转：日期变化时关闭旧文件、打开新文件
- 写入失败静默：日志失败不影响主流程（遥测/守护进程均为非关键路径）
- 线程安全：daemon 模式使用线程池（最多 4 worker），写入需加锁
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


def resolve_engine_root() -> str:
    """解析 .engine/ 目录路径（工具根目录下）。

    engine_log.py 位于 shared/v2/ 下，工具根目录在上溯 3 级。
    读取端（_read_engine_telemetry 等）与写入端统一由此解析。
    """
    current = Path(__file__).resolve().parent  # shared/v2/
    shared = current.parent                      # shared/
    opencode = shared.parent                     # .opencode/
    tool_root = opencode.parent                  # novel-create-hermes/
    engine_root = tool_root / ".engine"
    engine_root.mkdir(parents=True, exist_ok=True)
    return str(engine_root)


class EngineLogWriter:
    """按天分片的结构化日志写入器（全局单例使用）。

    子类只需：
    - 构造时传入 subdir / prefix / ext
    - 调用 self.write(entry: dict) 写入一条记录
    - 进程退出时调用 self.close()

    所有写操作失败静默（不抛异常），保证日志不影响主流程。
    """

    def __init__(self, subdir: str, prefix: str = "", ext: str = ".ndjson"):
        self._subdir = subdir
        self._prefix = prefix
        self._ext = ext
        self._log_dir: Optional[str] = None
        self._log_file = None
        self._current_date: Optional[str] = None
        self._lock = threading.RLock()  # daemon 线程池并发写入需要

    def _ensure_dir(self) -> str:
        """惰性创建日志目录，返回目录路径。"""
        if self._log_dir:
            return self._log_dir
        engine_root = resolve_engine_root()
        self._log_dir = os.path.join(engine_root, self._subdir)
        os.makedirs(self._log_dir, exist_ok=True)
        return self._log_dir

    def _date_stamped_path(self) -> tuple[str, str]:
        """返回 (今日日期, 今日分片文件路径)。"""
        d = self._ensure_dir()
        today = datetime.now().strftime("%Y-%m-%d")
        return today, os.path.join(d, f"{self._prefix}{today}{self._ext}")

    def _rotate(self, new_date: str):
        """跨天时关闭旧文件，打开新文件。"""
        with self._lock:
            # 直接关闭文件句柄，不调用 self.close()：
            # TelemetryRecorder 覆写了 close() 为 flush()+close()，若在此调用
            # 会触发 flush → write → _rotate 的递归（_current_date 在 close()
            # 之后才赋值，重入的 write 再次判定日期不匹配），直到 RecursionError，
            # 回卷时每层都会把同一条记录再写一遍（实测单条膨胀 240~248 份）。
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
                self._log_file = None
            self._current_date = new_date
            _, path = self._date_stamped_path()
            try:
                self._log_file = open(path, "a", encoding="utf-8")
            except OSError:
                self._log_file = None

    def write(self, entry: dict):
        """写入一条记录。跨天自动轮转；任何失败静默，不影响主流程。"""
        with self._lock:
            try:
                today, _ = self._date_stamped_path()
                if today != self._current_date:
                    self._rotate(today)
                if not self._log_file:
                    return
                self._log_file.write(
                    json.dumps(entry, ensure_ascii=False, default=str) + "\n")
                self._log_file.flush()
            except Exception:
                pass

    def close(self):
        """关闭日志文件（幂等）。"""
        with self._lock:
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
                self._log_file = None
