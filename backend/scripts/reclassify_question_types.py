"""
逐条扫描 SQLite questions 表，按题干 + topic_tags 重算 question_type 并写回。

说明
----
- 与「一条 UPDATE + CASE」的 SQL 脚本不同：本脚本对每一行调用 miner_schema 中的推断链，
  与两阶段入库归一化使用同一套规则，适合全库复查与纠错。
- 默认模式会 **忽略** 当前库中的 question_type，完全按内容重算（可修正已入库但分错的小类）。
- 可选「仅规范化」模式：保留已是白名单小类的行，只修正非法值/历史大类。

运行（需已激活 NewCoderAgent 或等价环境，且加载项目 .env）：

  python -m backend.scripts.reclassify_question_types --dry-run
  python -m backend.scripts.reclassify_question_types
  python -m backend.scripts.reclassify_question_types --mode normalize --dry-run
  python -m backend.scripts.reclassify_question_types --limit 500
  python -m backend.scripts.reclassify_question_types --only-not-in-allowed

Neo4j 若单独存了 question_type，SQLite 更新后请执行：
  python -m backend.scripts.align_neo4j_question_types sync

题干去标号与按正文去重（另脚本）：
  python -m backend.scripts.maintain_question_bank all --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

from backend.agents.schemas.miner_schema import (
    ALLOWED_QUESTION_TYPES,
    recompute_question_type_from_content,
    refine_question_type_coarse_to_fine,
)
from backend.config.config import settings


def _parse_tags(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def main() -> int:
    p = argparse.ArgumentParser(description="逐题重算并写回 question_type")
    p.add_argument(
        "--mode",
        choices=("from_content", "normalize"),
        default="from_content",
        help="from_content=仅按题干+标签重算（默认）；normalize=非法/历史值才改写，已是白名单小类则保持",
    )
    p.add_argument("--dry-run", action="store_true", help="只打印将发生的变更，不写库")
    p.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0 表示全部）")
    p.add_argument(
        "--only-not-in-allowed",
        action="store_true",
        help="只处理 question_type 不在白名单内的行（仍受 --mode 影响）",
    )
    p.add_argument(
        "--csv",
        type=str,
        default="",
        help="将变更记录写入 CSV 路径（含 q_id,old,new）",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="不逐条打印，仅进度（每 1000 条）与最终汇总",
    )
    args = p.parse_args()

    db_path = settings.sqlite_db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    sql = """
        SELECT q_id, question_text, topic_tags, question_type
        FROM questions
        ORDER BY rowid
    """
    cur = conn.execute(sql)
    rows = cur.fetchall()

    total = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    changed = 0
    scanned = 0
    csv_rows: list[tuple[str, str, str]] = []

    for row in rows:
        scanned += 1
        q_id = row["q_id"]
        qtext = row["question_text"] or ""
        tags = _parse_tags(row["topic_tags"])
        current = (row["question_type"] or "").strip()

        if args.only_not_in_allowed and current in ALLOWED_QUESTION_TYPES:
            continue

        if args.mode == "from_content":
            new_type = recompute_question_type_from_content(qtext, tags)
        else:
            new_type = refine_question_type_coarse_to_fine(qtext, tags, current or "基础类")
            if new_type not in ALLOWED_QUESTION_TYPES:
                new_type = "基础-其他"

        if new_type == current:
            continue

        changed += 1
        csv_rows.append((q_id, current, new_type))
        if not args.quiet:
            print(f"[{changed}] {q_id}: {current!r} -> {new_type!r}")
        elif changed % 1000 == 0:
            print(f"... 已处理变更 {changed} 条（扫描 {scanned}/{len(rows)}）")

        if not args.dry_run:
            conn.execute(
                "UPDATE questions SET question_type = ?, updated_at = CURRENT_TIMESTAMP WHERE q_id = ?",
                (new_type, q_id),
            )
            if changed % 200 == 0:
                conn.commit()

    if not args.dry_run:
        conn.commit()

    conn.close()

    if args.csv and csv_rows:
        out_path = Path(args.csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["q_id", "question_type_old", "question_type_new"])
            w.writerows(csv_rows)

    print(
        f"\n完成：库中共 {total} 题，本轮扫描 {scanned} 行，"
        f"将变更 {changed} 条（{'dry-run 未写库' if args.dry_run else '已提交'}）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
