import sqlite3, json, re
from datetime import datetime

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

THINKING_LOGS = [
    'backend/interviewer_logs/deepseek-reasoner/thinking_20260317.jsonl',
    'backend/interviewer_logs/deepseek-reasoner/thinking_20260318.jsonl',
]

# 读取所有 thinking 日志，按 timestamp 索引
# key: (user_id, timestamp[:19]) -> thinking_steps
thinking_by_ts = {}  # ts[:16] (分钟精度) -> thinking_steps

for log_path in THINKING_LOGS:
    with open(log_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get('user_id') != 'Wangxr':
                continue
            ts = rec.get('timestamp', '')[:16]  # 分钟精度
            steps = rec.get('thinking_steps', [])
            if steps:
                thinking_by_ts[ts] = steps

print(f'Loaded {len(thinking_by_ts)} thinking records from logs')
for ts, steps in list(thinking_by_ts.items())[:3]:
    print(f'  {ts}: {len(steps)} steps, thought_preview={repr(steps[0].get("thought","")[:60])}')

def convert_thinking(steps):
    """将 thinking_steps 转换为前端期望的格式"""
    result = []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        thought = step.get('thought', '') or ''
        obs = step.get('observation', '') or ''
        # 尝试从 observation 解析工具调用
        tools = []
        if obs and obs.strip().startswith('{'):
            try:
                obs_json = json.loads(obs)
                # 这是工具返回结果，但没有工具名，跳过
            except:
                pass
        result.append({
            '__step': idx + 1,
            'thought': thought,
            'tools': tools,
        })
    return result

# 读取数据库
conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])

print(f'\nTotal msgs: {len(hist)}')

# 对每条 assistant 消息，按时间戳匹配 thinking
updated = 0
for msg in hist:
    if msg.get('role') != 'assistant':
        continue
    if msg.get('thinking'):  # 已有thinking，跳过
        continue
    ts = msg.get('timestamp', '') or ''
    if not ts:
        continue
    ts_min = ts[:16]  # 分钟精度匹配
    
    if ts_min in thinking_by_ts:
        steps = thinking_by_ts[ts_min]
        msg['thinking'] = convert_thinking(steps)
        updated += 1
        print(f'  +thinking ts={ts[:19]} steps={len(steps)}')
    else:
        # 尝试前后1分钟匹配
        matched = False
        ts_dt = datetime.fromisoformat(ts[:19])
        for key_ts, steps in thinking_by_ts.items():
            key_dt = datetime.fromisoformat(key_ts + ':00')
            diff = abs((ts_dt - key_dt).total_seconds())
            if diff <= 120:  # 2分钟内
                msg['thinking'] = convert_thinking(steps)
                updated += 1
                print(f'  +thinking (fuzzy {diff:.0f}s) ts={ts[:19]} <- log_ts={key_ts}')
                matched = True
                break

print(f'\nUpdated {updated} assistant messages with thinking')

conn.execute(
    'UPDATE interview_sessions SET conversation_history=? WHERE session_id=?',
    (json.dumps(hist, ensure_ascii=False), TARGET_SID)
)
conn.commit()
conn.close()
print('[DONE]')
