"""打印 questions 表中 question_type 分布（验证用）。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
from dotenv import load_dotenv

load_dotenv(project_root / ".env", override=True)

import sqlite3

from backend.agents.schemas.miner_schema import ALLOWED_QUESTION_TYPES
from backend.config.config import settings


def main() -> None:
    db = settings.sqlite_db_path
    print("sqlite_db_path:", db)
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "SELECT question_type, COUNT(*) FROM questions GROUP BY question_type ORDER BY COUNT(*) DESC"
    )
    rows = cur.fetchall()
    n_total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    conn.close()
    print("distinct question_type:", len(rows))
    not_allowed = []
    total_rows = 0
    for t, c in rows:
        total_rows += c
        ok = (t or "") in ALLOWED_QUESTION_TYPES
        flag = "OK" if ok else "!!"
        print(f"  {flag} {c:5d}  {t!r}")
        if not ok:
            not_allowed.append((t, c))
    print("sum(分组计数):", total_rows, "  COUNT(*) questions:", n_total)
    if not_allowed:
        print("\n不在白名单小类的条数合计:", sum(x[1] for x in not_allowed))


if __name__ == "__main__":
    main()
