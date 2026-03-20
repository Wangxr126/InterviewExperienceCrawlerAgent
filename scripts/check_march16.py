import sqlite3, json

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])
conn.close()

# 找3月16日的消息
march16 = [m for m in hist if m.get('timestamp', '').startswith('2026-03-16')]
print(f'3月16日消息数: {len(march16)}')
for m in march16:
    role = m.get('role', '')
    content = m.get('content', '') or ''
    ts = m.get('timestamp', '')[:19]
    has_thinking = bool(m.get('thinking'))
    print(f'  [{role}] {ts} thinking={has_thinking} | {repr(content[:100])}')
