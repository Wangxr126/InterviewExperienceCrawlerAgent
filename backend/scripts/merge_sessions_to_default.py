"""
将 SQLite 中当前默认用户的所有会话合并为 env 配置的默认 session_id。

用法（在项目根目录执行）：
  conda activate NewCoderAgent
  python -m backend.scripts.merge_sessions_to_default

会读取 .env 中的 DEFAULT_USER_ID、DEFAULT_SESSION_ID，将该用户下所有
interview_sessions 的对话历史按 start_time 合并到一条会话，并更新
study_records、episodic_log 的 session_id，最后删除其余会话行。
"""
import json
import os
import sys

# 确保项目根在 path 且 load_dotenv 已执行
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.chdir(_PROJECT_ROOT)

def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def main():
    _load_env()
    from backend.config.config import settings
    import sqlite3

    user_id = settings.default_user_id
    session_id = settings.default_session_id
    db_path = settings.sqlite_db_path

    if not os.path.isfile(db_path):
        print(f"数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row

    try:
        # 该用户下所有会话，按开始时间升序（先发生的在前）
        rows = conn.execute(
            """
            SELECT session_id, user_id, conversation_history, session_meta, start_time
            FROM interview_sessions
            WHERE user_id = ?
            ORDER BY start_time ASC
            """,
            (user_id,),
        ).fetchall()

        if not rows:
            print(f"用户 {user_id} 下暂无会话，无需合并。")
            conn.execute(
                "INSERT OR IGNORE INTO interview_sessions (session_id, user_id, session_type) VALUES (?, ?, 'practice')",
                (session_id, user_id),
            )
            conn.commit()
            print(f"已确保默认会话存在: {session_id}")
            return 0

        # 合并 conversation_history
        merged_history = []
        for row in rows:
            raw = row["conversation_history"] or "[]"
            try:
                hist = json.loads(raw)
            except json.JSONDecodeError:
                hist = []
            if isinstance(hist, list):
                merged_history.extend(hist)

        # 若默认会话已存在，保留其 session_meta（取最后一个会话的 meta 作为占位）
        existing = conn.execute(
            "SELECT session_meta FROM interview_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        session_meta = "{}"
        if existing and existing["session_meta"]:
            session_meta = existing["session_meta"]
        else:
            # 用最后一个会话的 meta 作为初始
            last_row = rows[-1]
            if last_row["session_meta"]:
                session_meta = last_row["session_meta"]

        # 确保默认会话行存在
        conn.execute(
            "INSERT OR IGNORE INTO interview_sessions (session_id, user_id, session_type) VALUES (?, ?, 'practice')",
            (session_id, user_id),
        )

        # 更新为合并后的历史
        conn.execute(
            """
            UPDATE interview_sessions
            SET conversation_history = ?, session_meta = ?
            WHERE session_id = ? AND user_id = ?
            """,
            (json.dumps(merged_history, ensure_ascii=False), session_meta, session_id, user_id),
        )

        # 把该用户下 study_records、episodic_log 的 session_id 统一为默认
        cur = conn.execute(
            "UPDATE study_records SET session_id = ? WHERE user_id = ?",
            (session_id, user_id),
        )
        study_updated = cur.rowcount
        cur = conn.execute(
            "UPDATE episodic_log SET session_id = ? WHERE user_id = ?",
            (session_id, user_id),
        )
        episodic_updated = cur.rowcount

        # 删除该用户下除默认会话外的所有会话
        cur = conn.execute(
            "DELETE FROM interview_sessions WHERE user_id = ? AND session_id != ?",
            (user_id, session_id),
        )
        deleted = cur.rowcount

        conn.commit()
        print(f"合并完成: 用户={user_id}, 默认会话={session_id}")
        print(f"  合并 {len(rows)} 条会话 -> 1 条, 共 {len(merged_history)} 条消息")
        print(f"  study_records 更新: {study_updated}, episodic_log 更新: {episodic_updated}, 删除旧会话: {deleted}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
