# -*- coding: utf-8 -*-
"""
从 SQLite 题库抽取 LoRA 对比演示用案例（默认 10 条），写入 JSON，供 DSW / 前端导入。

用法（项目根目录）:
  conda activate NewCoderAgent
  python scripts/export_lora_bench_cases.py
  python scripts/export_lora_bench_cases.py --out 微调/dsw_upload/bench_cases.json

无数据库时：写出空 cases 与 meta.error，便于在云端有库后再跑。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)


def _pick_one(conn: sqlite3.Connection, sql: str, params=(), exclude: set[str] | None = None) -> dict | None:
    exclude = exclude or set()
    cur = conn.execute(sql, params)
    for row in cur:
        d = dict(row)
        qid = d.get("q_id")
        if qid and qid not in exclude:
            return d
    return None


def export_cases(db_path: str, limit: int = 10) -> dict:
    meta = {"db_path": db_path, "picked": 0, "error": None}
    cases: list[dict] = []
    used: set[str] = set()

    if not Path(db_path).is_file():
        meta["error"] = f"数据库不存在: {db_path}"
        return {"meta": meta, "cases": []}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    specs: list[tuple[str, str, tuple]] = [
        (
            "超长题干（一帖多题）",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE LENGTH(COALESCE(q.question_text,'')) > 900
            ORDER BY RANDOM() LIMIT 30
            """,
            (),
        ),
        (
            "非规整编号（含 1. 2. 但无 Q: 格式）",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.question_text LIKE '%1.%' AND q.question_text LIKE '%2.%'
              AND q.question_text NOT LIKE '%Q:%'
              AND LENGTH(q.question_text) > 120
            ORDER BY RANDOM() LIMIT 30
            """,
            (),
        ),
        (
            "图片抽取来源",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.extraction_source = 'image'
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
        (
            "有关联原帖正文",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            INNER JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE ct.raw_content IS NOT NULL AND LENGTH(TRIM(ct.raw_content)) > 300
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
        (
            "题干较短（边界/噪声）",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE LENGTH(TRIM(COALESCE(q.question_text,''))) BETWEEN 15 AND 80
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
        (
            "豆包长答案",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.answer_text IS NOT NULL AND LENGTH(q.answer_text) > 800
            ORDER BY RANDOM() LIMIT 15
            """,
            (),
        ),
        (
            "算法类",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.question_type LIKE '算法%'
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
        (
            "工程类",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.question_type LIKE '工程%'
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
        (
            "基础类",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.question_type LIKE '基础%'
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
        (
            "软技能 / 行为面",
            """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            WHERE q.question_type LIKE '软技能%' OR q.question_type LIKE '%行为%'
            ORDER BY RANDOM() LIMIT 20
            """,
            (),
        ),
    ]

    for label, sql, params in specs:
        if len(cases) >= limit:
            break
        row = _pick_one(conn, sql, params, used)
        if not row:
            continue
        qid = row["q_id"]
        used.add(qid)
        rd = dict(row)
        cases.append(
            {
                "category": label,
                "q_id": qid,
                "question_text": row["question_text"],
                "answer_text": row["answer_text"] or "",
                "raw_answer": rd.get("raw_answer") or "",
                "question_type": row["question_type"] or "",
                "difficulty": row["difficulty"] or "",
                "extraction_source": row["extraction_source"] or "",
                "source_platform": row["source_platform"] or "",
                "crawl_task_id": row["crawl_task_id"],
                "post_raw_content": row["post_raw_content"] or "",
            }
        )

    # 不足则随机补齐
    if len(cases) < limit:
        sql_fill = """
            SELECT q.q_id, q.question_text, q.answer_text, q.raw_answer, q.question_type, q.difficulty,
                   q.extraction_source, q.source_platform, q.crawl_task_id,
                   ct.raw_content AS post_raw_content
            FROM questions q
            LEFT JOIN crawl_tasks ct ON q.crawl_task_id = ct.id
            ORDER BY RANDOM() LIMIT 80
        """
        for row in conn.execute(sql_fill):
            if len(cases) >= limit:
                break
            d = dict(row)
            qid = d["q_id"]
            if qid in used:
                continue
            used.add(qid)
            cases.append(
                {
                    "category": "随机补齐",
                    "q_id": qid,
                    "question_text": d["question_text"],
                    "answer_text": d["answer_text"] or "",
                    "raw_answer": d.get("raw_answer") or "",
                    "question_type": d["question_type"] or "",
                    "difficulty": d["difficulty"] or "",
                    "extraction_source": d["extraction_source"] or "",
                    "source_platform": d.get("source_platform") or "",
                    "crawl_task_id": d["crawl_task_id"],
                    "post_raw_content": d["post_raw_content"] or "",
                }
            )

    conn.close()
    meta["picked"] = len(cases)
    return {"meta": meta, "cases": cases[:limit]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "微调" / "dsw_upload" / "bench_cases.json"))
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    try:
        from backend.config.config import settings

        db_path = settings.sqlite_db_path
    except Exception as e:
        db_path = str(ROOT / "backend" / "data" / "local_data.db")
        print("warning: 使用默认 db 路径（config 导入失败）", e)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = export_cases(db_path, limit=args.limit)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {out_path}，共 {len(data['cases'])} 条")
    if data["meta"].get("error"):
        print("提示:", data["meta"]["error"])


if __name__ == "__main__":
    main()
