import sqlite3, json

conn = sqlite3.connect('backend/data/local_data.db')
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', ('sess_Wangxr',)).fetchone()
hist = json.loads(row[0])
conn.close()

print(f'Total msgs: {len(hist)}')
by_date = {}
for m in hist:
    ts = m.get('timestamp', '') or ''
    date = ts[:10] if ts else 'unknown'
    by_date[date] = by_date.get(date, 0) + 1
for d in sorted(by_date):
    print(f'  {d}: {by_date[d]} msgs')

print('\nFirst 3 msgs:')
for m in hist[:3]:
    print(f'  [{m.get("role")}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:80])}')
print('Last 3 msgs:')
for m in hist[-3:]:
    print(f'  [{m.get("role")}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:80])}')
