"""
规范化全库 topic_tags（SQLite JSON）并与 Neo4j (:Tag)+HAS_TAG 对齐。

依据：backend/services/tag_normalization.py（同义合并、缩写、去泛化词、2～4 条）。

  python -m backend.scripts.normalize_topic_tags verify
  python -m backend.scripts.normalize_topic_tags apply --dry-run
  python -m backend.scripts.normalize_topic_tags apply --quiet
  python -m backend.scripts.normalize_topic_tags apply --no-neo4j

说明
----
- 图谱构建：入库时 scheduler._save_questions → neo4j add_question，按 topic_tags 字符串
  MERGE (:Tag {name}) 并连 HAS_TAG；**无**单独 NER 流水线；Concept/link_concept 当前未被业务调用。
- 本脚本会先删每题旧 HAS_TAG 再建新边（replace_question_tags），避免「改名」后旧 Tag 仍挂着。
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

from backend.config.config import settings
from backend.services.storage.neo4j_service import neo4j_service
from backend.services.tag_normalization import normalize_topic_tags_for_question, tags_equal


def _load_rows():
    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT q_id, question_text, question_type, topic_tags FROM questions ORDER BY rowid"
    ).fetchall()
    conn.close()
    return rows


def cmd_verify() -> int:
    rows = _load_rows()
    raw_tags: dict[str, int] = {}
    for r in rows:
        try:
            arr = json.loads(r["topic_tags"] or "[]")
        except Exception:
            arr = []
        if not isinstance(arr, list):
            continue
        for t in arr:
            if not isinstance(t, str):
                continue
            k = t.strip()
            if k:
                raw_tags[k] = raw_tags.get(k, 0) + 1
    top = sorted(raw_tags.items(), key=lambda x: -x[1])[:40]
    print(f"questions: {len(rows)}  distinct raw tag strings: {len(raw_tags)}")
    print("top 40 raw tags:")
    for name, c in top:
        print(f"  {c:5d}  {name!r}")
    return 0


def cmd_apply(dry_run: bool, quiet: bool, with_neo4j: bool, csv_path: str, limit: int) -> int:
    rows = _load_rows()
    if limit > 0:
        rows = rows[:limit]
    changed = 0
    neo_ok = 0
    neo_skip = 0
    log: list[tuple[str, str, str]] = []

    conn = sqlite3.connect(settings.sqlite_db_path)
    for r in rows:
        q_id = r["q_id"]
        qtext = r["question_text"] or ""
        qtype = (r["question_type"] or "").strip()
        try:
            old = json.loads(r["topic_tags"] or "[]")
        except Exception:
            old = []
        if not isinstance(old, list):
            old = []
        old_s = [str(x) for x in old if isinstance(x, str)]
        new = normalize_topic_tags_for_question(old_s, qtext, qtype)
        if tags_equal(old_s, new):
            continue
        changed += 1
        log.append((q_id, json.dumps(old_s, ensure_ascii=False), json.dumps(new, ensure_ascii=False)))
        if not quiet and changed <= 30:
            print(f"{q_id}: {old_s} -> {new}")
        if not dry_run:
            conn.execute(
                "UPDATE questions SET topic_tags = ?, updated_at = CURRENT_TIMESTAMP WHERE q_id = ?",
                (json.dumps(new, ensure_ascii=False), q_id),
            )
            if with_neo4j and neo4j_service.available:
                if neo4j_service.replace_question_tags(q_id, new):
                    neo_ok += 1
                else:
                    neo_skip += 1
            elif with_neo4j:
                neo_skip += 1
        if not dry_run and changed % 300 == 0:
            conn.commit()

    if not dry_run:
        conn.commit()
    conn.close()

    if csv_path:
        p = Path(csv_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["q_id", "topic_tags_old", "topic_tags_new"])
            w.writerows(log)

    print(
        f"\n完成: 扫描 {len(rows)} 行, 变更 {changed} 题 "
        f"({'dry-run' if dry_run else '已写 SQLite'})"
        + (f", Neo4j 更新 {neo_ok} 题 (跳过/失败 {neo_skip})" if with_neo4j else ", 未改 Neo4j")
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="统计原始标签分布")
    sub.add_parser(
        "prune-orphan-tags",
        help="仅删除 Neo4j 中无任何 HAS_TAG 入边的 Tag 节点（需 Neo4j 可用）",
    )
    ap = sub.add_parser("apply", help="写回规范化标签")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-neo4j", action="store_true", help="只改 SQLite")
    ap.add_argument("--csv", default="", help="变更 CSV")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--prune-orphan-tags",
        action="store_true",
        help="结束后删除图中无任何 HAS_TAG 入边的 Tag 节点（慎用，需 Neo4j）",
    )
    args = p.parse_args()
    if args.cmd == "verify":
        return cmd_verify()
    if args.cmd == "prune-orphan-tags":
        if not neo4j_service.available:
            print("Neo4j 不可用")
            return 1
        q = """
        MATCH (t:Tag)
        WHERE NOT (t)<-[:HAS_TAG]-()
        WITH t LIMIT 20000
        DELETE t
        RETURN count(*) AS deleted
        """
        with neo4j_service.driver.session(database=neo4j_service.db_name) as session:
            rec = session.run(q).single()
            d = rec["deleted"] if rec else 0
        print(f"已删除孤立 Tag 节点数: {d}（本轮上限 20000，可重复执行直到为 0）")
        return 0
    rc = cmd_apply(
        dry_run=args.dry_run,
        quiet=args.quiet,
        with_neo4j=not args.no_neo4j,
        csv_path=args.csv,
        limit=args.limit,
    )
    if (
        args.cmd == "apply"
        and getattr(args, "prune_orphan_tags", False)
        and not args.dry_run
        and neo4j_service.available
        and not args.no_neo4j
    ):
        q = """
        MATCH (t:Tag)
        WHERE NOT (t)<-[:HAS_TAG]-()
        WITH t LIMIT 10000
        DELETE t
        RETURN count(*) AS deleted
        """
        with neo4j_service.driver.session(database=neo4j_service.db_name) as session:
            rec = session.run(q).single()
            d = rec["deleted"] if rec else 0
        print(f"已 prune 孤立 Tag 节点（本轮最多 10000）: {d}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
