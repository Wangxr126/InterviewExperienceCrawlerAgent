"""
题库维护：题干去标号、按正文去重、可选同步 Neo4j 题干。

1) 去掉题干前缀 (7) / 7. / Q1: 等（SQLite + Neo4j.text）
2) 按「规范化题干」去重：同一文本只保留一条（优先答案更长，其次更早 created_at），删除其余
3) 类型纠错请另跑：python -m backend.scripts.reclassify_question_types
   Neo4j question_type：python -m backend.scripts.align_neo4j_question_types sync

示例（项目根、已加载 .env）：

  python -m backend.scripts.maintain_question_bank strip --dry-run
  python -m backend.scripts.maintain_question_bank strip
  python -m backend.scripts.maintain_question_bank dedupe --dry-run
  python -m backend.scripts.maintain_question_bank dedupe
  python -m backend.scripts.maintain_question_bank all --dry-run
  python -m backend.scripts.maintain_question_bank all

说明：修改题干后 Neo4j 向量 embedding 不会自动重算；若依赖向量检索，需后续批量重嵌入（另议）。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

from backend.config.config import settings
from backend.services.storage.neo4j_service import neo4j_service
from backend.utils.question_text_cleanup import (
    normalize_text_for_dedupe,
    strip_question_enumeration,
)


def _sqlite_delete_side_tables(conn: sqlite3.Connection, q_ids: list[str]) -> None:
    if not q_ids:
        return
    ph = ",".join("?" * len(q_ids))
    conn.execute(f"DELETE FROM study_records WHERE question_id IN ({ph})", q_ids)
    conn.execute(f"DELETE FROM user_notes WHERE question_id IN ({ph})", q_ids)
    conn.execute(f"DELETE FROM episodic_log WHERE question_id IN ({ph})", q_ids)
    conn.execute(f"DELETE FROM ingestion_logs WHERE question_id IN ({ph})", q_ids)


def cmd_strip(conn: sqlite3.Connection, dry_run: bool) -> int:
    cur = conn.execute(
        "SELECT q_id, question_text FROM questions ORDER BY rowid"
    )
    rows = cur.fetchall()
    n = 0
    for q_id, old in rows:
        old = old or ""
        new = strip_question_enumeration(old)
        if new == old:
            continue
        n += 1
        if not dry_run:
            conn.execute(
                "UPDATE questions SET question_text = ?, updated_at = CURRENT_TIMESTAMP WHERE q_id = ?",
                (new, q_id),
            )
            if neo4j_service.available:
                neo4j_service.update_question_text_property(q_id, new)
    print(f"[strip] 将更新题干 {n} 条（总扫描 {len(rows)}） dry_run={dry_run}")
    return 0


def cmd_dedupe(conn: sqlite3.Connection, dry_run: bool) -> int:
    cur = conn.execute(
        """
        SELECT q_id, question_text, answer_text, created_at
        FROM questions
        ORDER BY created_at ASC
        """
    )
    rows = cur.fetchall()
    groups: dict[str, list[tuple]] = defaultdict(list)
    for q_id, qtext, ans, created in rows:
        key = normalize_text_for_dedupe(qtext or "")
        if not key:
            continue
        alen = len((ans or "").strip())
        groups[key].append((q_id, qtext, alen, created or ""))

    to_delete: list[str] = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        # 保留：答案更长优先，其次 created_at 更早（items 已按 created_at ASC）
        items_sorted = sorted(items, key=lambda x: (-(x[2] or 0), x[3]))
        keeper = items_sorted[0][0]
        for dead_qid, *_ in items_sorted[1:]:
            to_delete.append(dead_qid)

    print(
        f"[dedupe] 重复组数={sum(1 for g in groups.values() if len(g) > 1)} "
        f"将删除题目 {len(to_delete)} 条 dry_run={dry_run}"
    )
    if dry_run and to_delete[:15]:
        print("  示例将删 q_id:", to_delete[:15])

    if not dry_run and to_delete:
        _sqlite_delete_side_tables(conn, to_delete)
        ph = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM questions WHERE q_id IN ({ph})", to_delete)
        if neo4j_service.available:
            for qid in to_delete:
                neo4j_service.delete_question_by_id(qid)
    return 0


def cmd_all(conn: sqlite3.Connection, dry_run: bool) -> int:
    cmd_strip(conn, dry_run)
    if not dry_run:
        conn.commit()
    cmd_dedupe(conn, dry_run)
    if not dry_run:
        conn.commit()
    print(
        "\n后续建议：\n"
        "  python -m backend.scripts.reclassify_question_types --quiet\n"
        "  python -m backend.scripts.align_neo4j_question_types sync\n"
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="题库：去题干标号 + 正文去重")
    p.add_argument("cmd", choices=("strip", "dedupe", "all"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    conn = sqlite3.connect(settings.sqlite_db_path)
    try:
        if args.cmd == "strip":
            r = cmd_strip(conn, args.dry_run)
        elif args.cmd == "dedupe":
            r = cmd_dedupe(conn, args.dry_run)
        else:
            r = cmd_all(conn, args.dry_run)
        if not args.dry_run:
            conn.commit()
        return r
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
