import sqlite3, json

conn = sqlite3.connect('backend/data/local_data.db')

# 重点看 session-auto 和 sess_Wangxr 这两个大会话的 assistant 消息结构
for target_sid in ['session-auto', 'sess_Wangxr', 'sess_fixed']:
    rows = conn.execute(
        'SELECT conversation_history FROM interview_sessions WHERE session_id=?',
        (target_sid,)
    ).fetchone()
    if not rows:
        print(f'{target_sid}: NOT FOUND')
        continue
    hist = json.loads(rows[0])
    print(f'\n=== {target_sid} ({len(hist)} msgs) ===')
    for i, msg in enumerate(hist):
        if msg.get('role') == 'assistant':
            keys = list(msg.keys())
            has_thinking = 'thinking' in msg
            has_think_content = 'think_content' in msg
            content_preview = str(msg.get('content',''))[:60]
            print(f'  [msg {i}] keys={keys}')
            print(f'           has_thinking={has_thinking} has_think_content={has_think_content}')
            print(f'           content preview: {repr(content_preview)}')
            if has_thinking:
                t = msg['thinking']
                print(f'           thinking len={len(t)}')

conn.close()
