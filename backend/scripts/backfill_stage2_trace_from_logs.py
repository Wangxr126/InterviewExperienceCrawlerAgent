"""
按 Stage2 子进程日志回填 crawl_tasks.stage2_trace_session_id。

日志模式（顺序出现）：
1) [Stage2EnrichWorker] 处理 ... task_id=TASK-XXXX
2) ✅ Trace 已保存: ... trace-s-YYYY.html
3) [Stage2EnrichWorker] 完成 task_id=TASK-XXXX ...

脚本会将步骤 2 提取到的 session_id 绑定到当前 task_id，并写回 SQLite。
"""
from __future__ import annotations

import re
from pathlib import Path
import sqlite3

from backend.services.storage import sqlite_service


TASK_START_RE = re.compile(r"task_id=(TASK-[A-Z0-9]+)")
TASK_DONE_RE = re.compile(r"完成 task_id=(TASK-[A-Z0-9]+)")
TRACE_RE = re.compile(r"trace-(s-[0-9a-zA-Z\-]+)\.(?:jsonl|html)")


def parse_log_file(log_path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    current_task_id = ""
    current_trace_id = ""

    for raw in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue

        m_start = TASK_START_RE.search(line)
        if m_start and "[Stage2EnrichWorker] 处理" in line:
            current_task_id = m_start.group(1)
            current_trace_id = ""
            continue

        m_trace = TRACE_RE.search(line)
        if m_trace and "Trace 已保存" in line:
            current_trace_id = m_trace.group(1)
            continue

        m_done = TASK_DONE_RE.search(line)
        if m_done and "[Stage2EnrichWorker] 完成" in line:
            done_tid = m_done.group(1)
            # 仅在 task_id 一致且 trace 存在时建立映射
            if current_task_id == done_tid and current_trace_id:
                mapping[done_tid] = current_trace_id

            # 清理上下文，避免串任务
            current_task_id = ""
            current_trace_id = ""

    return mapping


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    log_dir = root / "backend" / "logs" / "subprocess" / "stage2_enrich"
    if not log_dir.exists():
        print(f"[backfill] 日志目录不存在: {log_dir}")
        return

    log_files = sorted(log_dir.glob("*.log"))
    if not log_files:
        print(f"[backfill] 未发现日志文件: {log_dir}")
        return

    merged: dict[str, str] = {}
    # 旧日志在前，新日志在后；同 task_id 以最新一次为准
    for f in log_files:
        merged.update(parse_log_file(f))

    if not merged:
        print("[backfill] 未在日志中解析到 task_id -> stage2_trace_session_id 映射")
        return

    updated = 0
    skipped = 0
    missing = 0

    with sqlite_service._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for task_id, trace_id in merged.items():
            row = conn.execute(
                "SELECT stage2_trace_session_id FROM crawl_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if not row:
                missing += 1
                continue

            cur_val = (row["stage2_trace_session_id"] or "").strip()
            if cur_val == trace_id:
                skipped += 1
                continue

            conn.execute(
                "UPDATE crawl_tasks SET stage2_trace_session_id=? WHERE task_id=?",
                (trace_id, task_id),
            )
            updated += 1
        conn.commit()

    print(
        f"[backfill] 解析映射 {len(merged)} 条，更新 {updated} 条，跳过 {skipped} 条，"
        f"库中未找到 task_id {missing} 条"
    )


if __name__ == "__main__":
    main()

