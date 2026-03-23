"""
按日志回填 crawl_tasks.trace_session_id（Stage1）。

仅使用高置信模式：
- 出现“开始处理/处理 task_id=TASK-...”
- 紧随其后出现 trace-s-...（例如 Trace 已保存 或 /api/crawler/trace/s-...）
- 出现“完成 task_id=TASK-...”后落盘映射
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.services.storage import sqlite_service


TASK_RE = re.compile(r"task_id=(TASK-[A-Z0-9]+)")
TRACE_RE = re.compile(r"(s-[0-9]{8}-[0-9]{6}-[0-9a-zA-Z]+)")


def parse_log(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    cur_task = ""
    cur_trace = ""

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue

        if "task_id=" in line and ("开始处理" in line or "处理 " in line):
            m = TASK_RE.search(line)
            if m:
                cur_task = m.group(1)
                cur_trace = ""
            continue

        m_trace = TRACE_RE.search(line)
        if m_trace and ("Trace" in line or "/api/crawler/trace/" in line or "trace-s-" in line):
            cur_trace = m_trace.group(1)
            continue

        if "完成 task_id=" in line:
            m = TASK_RE.search(line)
            if m and cur_task == m.group(1) and cur_trace:
                mapping[cur_task] = cur_trace
            cur_task = ""
            cur_trace = ""

    return mapping


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    log_root = root / "backend" / "logs"
    if not log_root.exists():
        print(f"[backfill-stage1] 日志目录不存在: {log_root}")
        return

    files = sorted(log_root.rglob("*.log"))
    merged: dict[str, str] = {}
    for f in files:
        # Stage2 日志单独用于 stage2_trace 字段，这里跳过
        if "stage2_enrich" in str(f).lower():
            continue
        merged.update(parse_log(f))

    if not merged:
        print("[backfill-stage1] 未解析到可回填的 task_id -> trace_session_id 映射")
        return

    updated = 0
    skipped = 0
    missing = 0

    with sqlite_service._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        for task_id, trace_id in merged.items():
            row = conn.execute(
                "SELECT trace_session_id FROM crawl_tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if not row:
                missing += 1
                continue

            cur = (row["trace_session_id"] or "").strip()
            if cur == trace_id:
                skipped += 1
                continue

            conn.execute(
                "UPDATE crawl_tasks SET trace_session_id=? WHERE task_id=?",
                (trace_id, task_id),
            )
            updated += 1
        conn.commit()

    print(
        f"[backfill-stage1] 解析映射 {len(merged)} 条，更新 {updated} 条，"
        f"跳过 {skipped} 条，库中未找到 {missing} 条"
    )


if __name__ == "__main__":
    main()

