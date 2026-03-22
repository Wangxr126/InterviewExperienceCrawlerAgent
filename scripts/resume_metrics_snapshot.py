"""一次性从 SQLite / 日志汇总简历可用指标（不落库，仅打印）。"""
from __future__ import annotations

import re
import sqlite3
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "backend" / "data" / "local_data.db"
BATCH_LOG = ROOT / "backend" / "logs" / "batch_extract.log"


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main() -> None:
    if not DB.exists():
        print(f"[skip] 数据库不存在: {DB}")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    print("=== SQLite: agent_tool_runtime_calls（每次工具调用一条，可算成功率/P95）===")
    try:
        c.execute("SELECT COUNT(*) AS n FROM agent_tool_runtime_calls")
        n = c.fetchone()["n"]
        print(f"总调用次数: {n}")
        if n:
            c.execute(
                """
                SELECT agent_name, tool_name, COUNT(*) AS cnt,
                       SUM(success) AS ok,
                       AVG(execution_time_ms) AS avg_ms
                FROM agent_tool_runtime_calls
                GROUP BY agent_name, tool_name
                ORDER BY cnt DESC
                LIMIT 25
                """
            )
            for row in c.fetchall():
                cnt, ok = row["cnt"], row["ok"] or 0
                sr = 100.0 * ok / cnt if cnt else 0
                print(
                    f"  {row['agent_name']}/{row['tool_name']}: "
                    f"n={cnt} 成功率={sr:.1f}% 平均耗时={row['avg_ms']:.0f}ms"
                )
            c.execute(
                "SELECT execution_time_ms FROM agent_tool_runtime_calls WHERE success=1 AND execution_time_ms > 0"
            )
            times = sorted(float(r[0]) for r in c.fetchall())
            if times:
                print(
                    f"  全部成功调用（混合工具）: p50={percentile(times, 50):.0f}ms "
                    f"p95={percentile(times, 95):.0f}ms max={max(times):.0f}ms"
                )
            for tool in ("stage2_enrich", "ocr_images", "submit_answer"):
                c.execute(
                    """
                    SELECT execution_time_ms FROM agent_tool_runtime_calls
                    WHERE success=1 AND tool_name=? AND execution_time_ms > 0
                    """,
                    (tool,),
                )
                tt = sorted(float(r[0]) for r in c.fetchall())
                if tt:
                    print(
                        f"  仅 {tool}: n={len(tt)} p50={percentile(tt, 50):.0f}ms "
                        f"p95={percentile(tt, 95):.0f}ms avg={statistics.mean(tt):.0f}ms"
                    )
    except sqlite3.OperationalError as e:
        print(f"  (表可能未创建) {e}")

    print("\n=== SQLite: crawl_tasks（采集/提取任务规模）===")
    for label, sql in [
        ("任务总数", "SELECT COUNT(*) FROM crawl_tasks"),
        ("按状态", "SELECT status, COUNT(*) AS n FROM crawl_tasks GROUP BY status ORDER BY n DESC"),
        (
            "done 且题数>0",
            "SELECT COUNT(*) FROM crawl_tasks WHERE status='done' AND COALESCE(questions_count,0)>0",
        ),
        (
            "平均 extract_duration_min（有记录）",
            "SELECT AVG(extract_duration_min) FROM crawl_tasks WHERE extract_duration_min IS NOT NULL AND extract_duration_min > 0",
        ),
        (
            "平均 questions_count（有题）",
            "SELECT AVG(questions_count) FROM crawl_tasks WHERE COALESCE(questions_count,0) > 0",
        ),
    ]:
        try:
            c.execute(sql)
            rows = c.fetchall()
            flat = [dict(r) for r in rows]
            print(f"  {label}: {flat}")
        except sqlite3.OperationalError as e:
            print(f"  {label}: err {e}")

    print("\n=== SQLite: questions / 学习数据 ===")
    try:
        c.execute("SELECT COUNT(*) FROM questions")
        print(f"  题库题目数: {c.fetchone()[0]}")
        c.execute(
            "SELECT COALESCE(source_platform,'(null)') AS p, COUNT(*) AS n FROM questions GROUP BY source_platform ORDER BY n DESC"
        )
        print(f"  按平台: {[dict(r) for r in c.fetchall()]}")
    except sqlite3.OperationalError as e:
        print(f"  questions: {e}")

    for tbl in ("study_records", "interview_sessions", "finetune_samples", "ingestion_logs"):
        try:
            c.execute(f"SELECT COUNT(*) FROM {tbl}")
            print(f"  {tbl}: {c.fetchone()[0]}")
        except sqlite3.OperationalError:
            pass

    try:
        c.execute("SELECT status, COUNT(*) AS n FROM stage2_pending GROUP BY status")
        print(f"  stage2_pending: {[dict(r) for r in c.fetchall()]}")
    except sqlite3.OperationalError:
        pass

    conn.close()

    print("\n=== 日志: batch_extract.log（正则粗统计，非严谨基准）===")
    if not BATCH_LOG.exists():
        print(f"  无文件: {BATCH_LOG}")
        return
    text = BATCH_LOG.read_text(encoding="utf-8", errors="replace")
    # Stage2Processor 行
    m_success = re.findall(r"本轮完成 success=(\d+) fail=(\d+)", text)
    if m_success:
        s = sum(int(a) for a, _ in m_success)
        f = sum(int(b) for _, b in m_success)
        print(f"  Stage2Processor 汇总行: 批次数={len(m_success)} success合计={s} fail合计={f}")
    # 提取失败重试
    retry = len(re.findall(r"提取失败（第", text))
    print(f"  「提取失败·重试」日志条数: {retry}")
    # Miner 执行完成
    done = len(re.findall(r"\[MinerAgent\] 执行完成", text))
    print(f"  「MinerAgent 执行完成」次数: {done}")


if __name__ == "__main__":
    main()
