"""
清理题库中的乱码题干/答案/公司名：尝试修复（NFKC、Latin1↔UTF-8、可选 ftfy），
仍不可用则删除题目；公司名异常则清空。

  python -m backend.scripts.cleanup_garbled_questions --dry-run
  python -m backend.scripts.cleanup_garbled_questions

依赖：.env 中 SQLite；Neo4j 可选（同步 company / 删节点 / 更新 text）。

可选增强：pip install ftfy（更稳的编码修复）。
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

from backend.config.config import settings
from backend.services.storage.neo4j_service import neo4j_service
from backend.scripts.maintain_question_bank import _sqlite_delete_side_tables
from backend.utils.text_garbled import (
    company_should_be_cleared,
    control_char_ratio,
    is_unusable_after_repair,
    is_unusable_answer_after_repair,
    looks_garbled,
    repair_text,
)


def main() -> int:
    p = argparse.ArgumentParser(description="清理乱码题干/公司，修复或删除")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="最多处理 N 条，0 为全部")
    p.add_argument(
        "--strict",
        action="store_true",
        help="仅处理题干/公司明显疑似乱码的行（含替换符、控制符过多、mojibake 特征等），减少大批量轻微空白/格式归一",
    )
    args = p.parse_args()

    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT q_id, question_text, answer_text, company FROM questions ORDER BY rowid"
    )
    rows = cur.fetchall()
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    n_update = 0
    n_delete = 0
    n_clear_co = 0
    to_delete: list[str] = []

    for row in rows:
        qid = row["q_id"]
        q0 = row["question_text"] or ""
        a0 = row["answer_text"] or ""
        c0 = row["company"] or ""

        q1, qc = repair_text(q0)
        if is_unusable_after_repair(q1):
            to_delete.append(qid)
            n_delete += 1
            continue

        orig_dirty = (
            looks_garbled(q0)
            or "\ufffd" in q0
            or control_char_ratio(q0) > 0.012
            or looks_garbled(c0)
            or "\ufffd" in c0
            or looks_garbled(a0)
            or "\ufffd" in (a0 or "")
        )
        # 保守模式：仅处理「原字段已疑似乱码」的行，不做全库隐形字符清洗
        if args.strict and not orig_dirty:
            continue

        a1, ac = repair_text(a0)
        if is_unusable_answer_after_repair(a1):
            a1, ac = "", True

        c1, cc = repair_text(c0)
        if company_should_be_cleared(c1):
            if c1 or c0:
                n_clear_co += 1
            c1, cc = "", True
        else:
            c1 = c1.strip()

        changed = qc or ac or cc or (q1 != q0) or (a1 != a0) or (c1 != c0)
        if not changed:
            continue
        n_update += 1
        if not args.dry_run:
            conn.execute(
                """
                UPDATE questions SET
                    question_text = ?, answer_text = ?, company = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE q_id = ?
                """,
                (q1, a1, c1, qid),
            )
            if neo4j_service.available:
                neo4j_service.update_question_text_property(qid, q1)
                neo4j_service.sync_question_company(qid, c1)

    if to_delete and not args.dry_run:
        _sqlite_delete_side_tables(conn, to_delete)
        ph = ",".join("?" * len(to_delete))
        conn.execute(f"DELETE FROM questions WHERE q_id IN ({ph})", to_delete)
        if neo4j_service.available:
            for qid in to_delete:
                neo4j_service.delete_question_by_id(qid)

    if not args.dry_run:
        conn.commit()
    conn.close()

    print(
        f"扫描 {len(rows)} 条 | 更新 {n_update} | 删除 {n_delete} | 清空/纠正公司 {n_clear_co} | dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
