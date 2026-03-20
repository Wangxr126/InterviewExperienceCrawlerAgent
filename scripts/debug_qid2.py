import sqlite3, json, re

conn = sqlite3.connect('backend/data/local_data.db')
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', ('sess_Wangxr',)).fetchone()
hist = json.loads(row[0])
conn.close()

march16 = [m for m in hist if m.get('timestamp', '').startswith('2026-03-16')]
print('march16 msgs:', len(march16))
for m in march16[:8]:
    content = m.get('content', '') or ''
    has_qid = bool(re.search(r'\u3010q_id:', content))
    next_role = ''
    idx = hist.index(m)
    if idx + 1 < len(hist):
        next_role = hist[idx+1].get('role', '')
    print(f'  [{m.get("role")}] {m.get("timestamp","")[:19]} has_qid={has_qid} next={next_role} | {repr(content[:80])}')
