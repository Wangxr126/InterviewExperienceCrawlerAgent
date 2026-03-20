import sqlite3, json

conn = sqlite3.connect('backend/data/local_data.db')

# 查所有 interview_sessions 的 session_id, user_id, start_time, msg数量
rows = conn.execute(
    'SELECT session_id, user_id, session_type, start_time, end_time, total_questions, session_meta, conversation_history FROM interview_sessions ORDER BY start_time DESC'
).fetchall()

print(f'Total sessions: {len(rows)}')
print()
for r in rows:
    sid, uid, stype, st, et, tq, meta, hist = r
    hist_len = 0
    if hist:
        try:
            hist_len = len(json.loads(hist))
        except:
            pass
    print(f'session_id={sid}')
    print(f'  user_id={uid} type={stype} start={st} end={et} questions={tq} hist_msgs={hist_len}')
    if meta:
        try:
            m = json.loads(meta)
            print(f'  meta={m}')
        except:
            print(f'  meta(raw)={repr(meta[:100])}')
    print()

conn.close()
