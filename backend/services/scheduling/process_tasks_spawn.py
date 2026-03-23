"""
启动 process_tasks 子进程（定时任务、API 恢复、main 启动恢复共用）。

与 main 解耦，避免 task_executor ↔ main 循环依赖。
子进程 stderr 追加写入 SUBPROCESS_LOG_DIR/process_tasks/ 下按时间戳命名的 .log（stdout 仍丢弃）。
启动后会挂一个 daemon 线程 wait 子进程，结束时在主进程打一条「已结束 pid=… exit=…」日志（便于与仅打印「▶ 启动」对照）。
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # backend/services/scheduling/process_tasks_spawn.py → 项目根
    return Path(__file__).resolve().parents[3]


def spawn_process_tasks_worker(batch_size: int, reason: str) -> subprocess.Popen:
    from backend.services.scheduling.subprocess_log_paths import new_subprocess_log_file

    log_path = new_subprocess_log_file("process_tasks")
    err_f = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115

    cmd = [
        sys.executable,
        "-m",
        "backend.services.scheduling.process_tasks_worker",
        "--batch-size",
        str(batch_size),
    ]
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        cmd,
        cwd=str(_project_root()),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=err_f,
        env=os.environ.copy(),
        **kwargs,
    )
    logger.info(
        "[后台子进程] ▶ 启动 process_tasks worker pid=%s reason=%s batch_size=%s 日志=%s",
        proc.pid,
        reason,
        batch_size,
        log_path,
    )

    def _log_exit_when_done(p: subprocess.Popen, pid: int, r: str, bs: int, lp: Path) -> None:
        code = p.wait()
        lvl = logging.ERROR if code else logging.INFO
        logger.log(
            lvl,
            "[后台子进程] ◼ process_tasks worker 已结束 pid=%s exit=%s reason=%s batch_size=%s 日志=%s",
            pid,
            code,
            r,
            bs,
            lp,
        )

    threading.Thread(
        target=_log_exit_when_done,
        args=(proc, proc.pid, reason, batch_size, log_path),
        daemon=True,
        name=f"process_tasks_wait_{proc.pid}",
    ).start()
    return proc
