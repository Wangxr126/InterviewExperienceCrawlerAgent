# 模拟后端 get_chat_history 的处理逻辑，验证旧数据清理效果
import sqlite3, json, re
from datetime import datetime
import time

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])
conn.close()

base_time = time.time()
messages = []
dsml_count = 0
nul_count = 0
empty_skipped = 0

for idx, m in enumerate(hist):
    content = m.get('content', '') or ''
    role = m.get('role', 'user')
    
    # NUL THINKING 清理
    if '\x00THINKING\x00' in content:
        content = content.replace('\x00THINKING\x00', '')
        nul_count += 1
    
    # DSML 置空
    if role == 'assistant' and content.startswith('<|'):
        content = ''
        dsml_count += 1
    
    if not content and role != 'assistant':
        empty_skipped += 1
        continue
    
    timestamp = m.get('timestamp') or m.get('ts')
    if not timestamp:
        timestamp = datetime.fromtimestamp(base_time - (len(hist) - idx) * 60).isoformat()
    
    msg = {'role': role, 'content': content, 'timestamp': timestamp}
    if m.get('thinking'):
        msg['thinking'] = m['thinking']
    messages.append(msg)

print(f'Total input msgs: {len(hist)}')
print(f'Total output msgs: {len(messages)}')
print(f'NUL tokens cleaned: {nul_count}')
print(f'DSML msgs blanked: {dsml_count}')
print(f'Empty user msgs skipped: {empty_skipped}')
print(f'Assistant with thinking: {sum(1 for m in messages if m.get("role")=="assistant" and m.get("thinking"))}')
print()
print('First 5 messages:')
for m in messages[:5]:
    print(f'  [{m["role"]}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:80])}')
print('Last 5 messages:')
for m in messages[-5:]:
    print(f'  [{m["role"]}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:80])}')
