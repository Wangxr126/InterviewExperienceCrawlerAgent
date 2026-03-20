import sqlite3, json

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])
conn.close()

assistant_msgs = [m for m in hist if m.get('role') == 'assistant']
print(f'Total assistant msgs: {len(assistant_msgs)}')

has_thinking = [m for m in assistant_msgs if m.get('thinking')]
no_thinking = [m for m in assistant_msgs if not m.get('thinking')]

print(f'With thinking: {len(has_thinking)}')
print(f'Without thinking: {len(no_thinking)}')

print('\n--- With thinking (first 5) ---')
for m in has_thinking[:5]:
    thinking = m.get('thinking')
    print(f'  [{m.get("timestamp","")[:19]}] type={type(thinking).__name__} len={len(str(thinking))}')
    print(f'  preview: {repr(str(thinking)[:100])}')
    print()

print('--- Without thinking (first 5) ---')
for m in no_thinking[:5]:
    print(f'  [{m.get("timestamp","")[:19]}] content={repr(str(m.get("content",""))[:60])}')
    print(f'  keys: {list(m.keys())}')
    print()
