"""
SQLite 与 Neo4j 中 Question.question_type 对齐：验证 + 写回。

验证（比对主键 q_id / id）：
  python -m backend.scripts.align_neo4j_question_types verify

将 SQLite 的 question_type 批量同步到 Neo4j（仅更新已存在的 Question 节点）：
  python -m backend.scripts.align_neo4j_question_types sync
  python -m backend.scripts.align_neo4j_question_types sync --dry-run

依赖：.env 中 Neo4j 可连；否则 verify 会提示图谱不可用。
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

from backend.agents.schemas.miner_schema import ALLOWED_QUESTION_TYPES
from backend.config.config import settings
from backend.services.storage.neo4j_service import neo4j_service


def _load_sqlite_map() -> dict[str, str]:
    conn = sqlite3.connect(settings.sqlite_db_path)
    cur = conn.execute("SELECT q_id, question_type FROM questions")
    m = {str(r[0]): (r[1] or "").strip() for r in cur.fetchall()}
    conn.close()
    return m


def _load_neo4j_map() -> dict[str, str] | None:
    if not neo4j_service.available or not neo4j_service.driver:
        return None
    q = "MATCH (q:Question) RETURN q.id AS id, q.question_type AS qt"
    out: dict[str, str] = {}
    with neo4j_service.driver.session(database=neo4j_service.db_name) as session:
        for rec in session.run(q):
            i = rec["id"]
            if i is None:
                continue
            out[str(i)] = (rec["qt"] or "").strip()
    return out


def cmd_verify() -> int:
    sqlite_map = _load_sqlite_map()
    n_sql = len(sqlite_map)
    bad_sql = sum(1 for qt in sqlite_map.values() if qt not in ALLOWED_QUESTION_TYPES)
    print(f"[SQLite] path={settings.sqlite_db_path}")
    print(f"[SQLite] questions={n_sql}  不在白名单小类={bad_sql}")

    neo_map = _load_neo4j_map()
    if neo_map is None:
        print("[Neo4j] 不可用（连接失败或未启用），跳过图谱比对。")
        return 1 if bad_sql else 0

    n_neo = len(neo_map)
    missing_in_neo = sum(1 for qid in sqlite_map if qid not in neo_map)
    extra_in_neo = sum(1 for qid in neo_map if qid not in sqlite_map)
    mismatch = 0
    for qid, sqt in sqlite_map.items():
        if qid not in neo_map:
            continue
        if neo_map[qid] != sqt:
            mismatch += 1

    print(f"[Neo4j] questions(nodes)={n_neo}")
    print(f"[对齐] SQLite 有但图中无节点: {missing_in_neo}")
    print(f"[对齐] 图中有但 SQLite 无此 q_id: {extra_in_neo}")
    print(f"[对齐] 同 id 但 question_type 不一致: {mismatch}")

    if bad_sql == 0 and mismatch == 0:
        print(
            "\n结论: SQLite 小类全部合法；与 Neo4j 中**同 q_id 节点**的 question_type 已一致。"
        )
        if missing_in_neo or extra_in_neo:
            print(
                "说明: 「SQLite 有但图中无」或「图中有但 SQLite 无」属数据覆盖范围差异，"
                "与本次类型字段对齐无关；新题入库时会写入两边。"
            )
    elif mismatch:
        print("\n建议: 运行  python -m backend.scripts.align_neo4j_question_types sync  写回图谱。")
    return 1 if bad_sql or mismatch else 0


def cmd_sync(dry_run: bool) -> int:
    sqlite_map = _load_sqlite_map()
    pairs = list(sqlite_map.items())
    if not neo4j_service.available:
        print("Neo4j 不可用，无法 sync。")
        return 1
    if dry_run:
        neo_map = _load_neo4j_map() or {}
        would_touch = sum(1 for qid, sqt in pairs if qid in neo_map and neo_map[qid] != sqt)
        print(f"[dry-run] 将尝试更新约 {would_touch} 个图中已存在且类型不一致的节点（按批写入）。")
        print(f"[dry-run] SQLite 总题数 {len(pairs)}，图中节点数 {len(neo_map)}")
        return 0
    r = neo4j_service.batch_sync_question_types(pairs, batch_size=500)
    print(f"sync 完成: batches={r['batches']} 本批 MATCH 并 SET 节点数={r['matched']}")
    print("请再运行: python -m backend.scripts.align_neo4j_question_types verify")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="比对 SQLite 与 Neo4j")
    sp = sub.add_parser("sync", help="SQLite -> Neo4j 批量写 question_type")
    sp.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.cmd == "verify":
        return cmd_verify()
    return cmd_sync(getattr(args, "dry_run", False))


if __name__ == "__main__":
    raise SystemExit(main())
