import sqlite3, json

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])

cleaned = []
skipped = []

for m in hist:
    role = m.get('role', '')
    content = m.get('content', '') or ''
    
    # 跳过 assistant 消息中的工具调用 JSON（旧格式 [{"name":...}]）
    if role == 'assistant' and content.strip().startswith('[{"name"') :
        skipped.append(('TOOL_JSON', m.get('timestamp','')[:19], content[:60]))
        continue
    
    # 跳过 DSML 格式工具调用
    if role == 'assistant' and content.startswith('<|') :
        skipped.append(('DSML', m.get('timestamp','')[:19], content[:60]))
        continue
    
    # 跳过生成中占位
    if role == 'assistant' and content.strip() in ('（生成中...）', '(生成中...)', '') :
        skipped.append(('PLACEHOLDER', m.get('timestamp','')[:19], content[:60]))
        continue
    
    cleaned.append(m)

print(f'Original: {len(hist)} msgs')
print(f'After clean: {len(cleaned)} msgs')
print(f'Skipped: {len(skipped)}')
for reason, ts, preview in skipped:
    print(f'  [{reason}] {ts} {repr(preview)}')

conn.execute(
    'UPDATE interview_sessions SET conversation_history=? WHERE session_id=?',
    (json.dumps(cleaned, ensure_ascii=False), TARGET_SID)
)
conn.commit()
conn.close()
print('\n[DONE] Database updated.')
