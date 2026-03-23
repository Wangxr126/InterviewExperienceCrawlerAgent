"""
后台子进程日志路径：按任务类型分子目录，文件名带时间戳。

根目录由环境变量 SUBPROCESS_LOG_DIR 或 settings.subprocess_log_dir 决定（见 .env.example）。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.config.config import settings


def new_subprocess_log_file(task_kind: str) -> Path:
    """
    task_kind 用于子目录与文件名前缀，建议取值：
    batch_extract | process_tasks
    """
    base = Path(settings.subprocess_log_dir)
    base.mkdir(parents=True, exist_ok=True)
    sub = base / task_kind
    sub.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return sub / f"{task_kind}_{ts}.log"
