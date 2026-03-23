""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"), override=True)

from backend.services.storage.sqlite_service import sqlite_service
import sqlite3

with sqlite_service._get_conn() as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT task_id, source_url, questions_count FROM crawl_tasks WHERE source_url IS NOT NULL AND source_url != ''"
    ).fetchall()
    updated = 0
    for r in rows:
        actual = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE source_url=?", (r["source_url"],)
        ).fetchone()[0]
        if actual != r["questions_count"] and actual > 0:
            conn.execute(
                "UPDATE crawl_tasks SET questions_count=? WHERE task_id=?",
                (actual, r["task_id"])
            )
            updated += 1
    conn.commit()
    print(f"已检查 {len(rows)} 条，修复 {updated} 条 crawl_tasks.questions_count")
""