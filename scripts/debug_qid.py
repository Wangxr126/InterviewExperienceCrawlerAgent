import json, sqlite3, re

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])
conn.close()

# 打印3月16日的用户消息，看q_id格式
march16_users = [m for m in hist if m.get('role')=='user' and m.get('timestamp','').startswith('2026-03-16')]
print(f'3月16日用户消息: {len(march16_users)}')
for m in march16_users[:5]:
    print(f'  ts={m["timestamp"][:19]}')
    print(f'  content={repr(m.get("content","")[:200])}')
    print()
