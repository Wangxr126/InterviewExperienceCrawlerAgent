import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

db_path = r'E:/Agent/AgentProject/wxr_agent/backend/data/local_data.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get recent sessions
rows = conn.execute('SELECT session_id, user_id, start_time, conversation_history FROM interview_sessions ORDER BY start_time DESC LIMIT 5').fetchall()
print(f'Total sessions (last 5): {len(rows)}')

for row in rows:
    session_id = row['session_id']
    start_time = row['start_time']
    history = json.loads(row['conversation_history'] or '[]')
    print(f'\n=== Session {session_id} | {start_time} | msgs={len(history)} ===')
    for i, msg in enumerate(history):
        role = msg.get('role', '')
        ts = msg.get('timestamp') or msg.get('ts') or ''
        thinking = msg.get('thinking')
        has_thinking = bool(thinking)
        thinking_len = len(thinking) if isinstance(thinking, list) else 0
        content_preview = (msg.get('content') or '')[:50]
        print(f'  [{i}] role={role} ts={ts[:16]} has_thinking={has_thinking} thinking_len={thinking_len} content={content_preview!r}')
        if has_thinking and isinstance(thinking, list):
            for si, step in enumerate(thinking[:3]):
                if isinstance(step, dict):
                    step_keys = list(step.keys())
                    step_val = step.get('__step')
                    tools = step.get('tools', [])
                    action = step.get('action')
                    tool_args = step.get('toolArgs')
                    obs = step.get('observation')
                    thought = (step.get('thought') or '')[:60]
                    print(f'    step[{si}]: keys={step_keys}')
                    print(f'      __step={step_val!r} action={action!r} toolArgs={bool(tool_args)} obs={bool(obs)}')
                    print(f'      tools_count={len(tools)} thought={thought!r}')
                    if tools:
                        for ti, tool in enumerate(tools[:2]):
                            if isinstance(tool, dict):
                                print(f'      tool[{ti}]: name={tool.get("name")!r} keys={list(tool.keys())}')

conn.close()
print('\nDone.')
