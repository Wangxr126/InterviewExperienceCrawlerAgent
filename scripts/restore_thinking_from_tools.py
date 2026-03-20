import sqlite3, json, re
from datetime import datetime, timedelta

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

TOOLS_LOGS = [
    ('2026-03-17', 'backend/interviewer_logs/deepseek-reasoner/tools_20260317.jsonl'),
    ('2026-03-18', 'backend/interviewer_logs/deepseek-reasoner/tools_20260318.jsonl'),
]

# 读取所有工具调用，按 session+时间窗口分组
all_tool_calls = []
for date_str, log_path in TOOLS_LOGS:
    with open(log_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get('user_id') != 'Wangxr':
                continue
            all_tool_calls.append(rec)

print(f'Total tool calls: {len(all_tool_calls)}')

# 按时间窗口分组：同一个响应的工具调用时间差 <= 90秒
# 每组最后一个工具调用时间接近 assistant 消息时间
groups = []
current_group = []
current_sid = None
for rec in all_tool_calls:
    ts = datetime.fromisoformat(rec['timestamp'][:19])
    sid = rec.get('session_id', '')
    
    if not current_group:
        current_group = [rec]
        current_sid = sid
    else:
        prev_ts = datetime.fromisoformat(current_group[-1]['timestamp'][:19])
        # 同一 session 且时间差 <= 90秒 -> 同一组
        if sid == current_sid and (ts - prev_ts).total_seconds() <= 90:
            current_group.append(rec)
        else:
            groups.append(current_group)
            current_group = [rec]
            current_sid = sid

if current_group:
    groups.append(current_group)

print(f'Tool call groups: {len(groups)}')

# 每组转成 thinking 格式
# 每个工具调用 = 一个步骤
def group_to_thinking(group):
    steps = []
    for idx, rec in enumerate(group):
        tool_name = rec.get('tool_name', '')
        tool_input = rec.get('tool_input', {})
        # 构建简短的 thought
        if tool_name == 'recognize_intent':
            intent = tool_input.get('intent', '')
            thought = f'识别用户意图：{intent}'
        elif tool_name == 'get_question_detail':
            qid = tool_input.get('question_id', '')[:8]
            thought = f'获取题目详情（{qid}...）'
        elif tool_name == 'submit_answer':
            score = tool_input.get('score', '')
            thought = f'提交答案评分，得分：{score}/5'
        elif tool_name == 'get_next_question':
            thought = '获取下一道题目'
        elif tool_name == 'search_questions':
            thought = f'搜索相关题目'
        else:
            thought = f'执行操作：{tool_name}'
        
        # 构建工具参数（只保留非敏感字段）
        safe_args = {}
        for k, v in tool_input.items():
            if k not in ('user_answer',):  # 排除用户答案（太长）
                safe_args[k] = v
        
        steps.append({
            '__step': idx + 1,
            'thought': thought,
            'tools': [{
                'name': tool_name,
                'args': safe_args,
                'result': None,
                'observation': None,
                'observationIsJson': False,
            }]
        })
    return steps

# 为每组计算「结束时间」= 最后一个工具调用时间 + 30秒内
# 与 assistant 消息时间匹配
group_end_times = []
for group in groups:
    end_ts = datetime.fromisoformat(group[-1]['timestamp'][:19])
    sid = group[0].get('session_id', '')
    group_end_times.append((end_ts, sid, group))

# 读数据库
conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])

print(f'\nTotal msgs in DB: {len(hist)}')

updated = 0
for msg in hist:
    if msg.get('role') != 'assistant':
        continue
    if msg.get('thinking'):  # 已有thinking
        continue
    ts_str = msg.get('timestamp', '') or ''
    if not ts_str or not (ts_str.startswith('2026-03-17') or ts_str.startswith('2026-03-18')):
        continue
    
    msg_ts = datetime.fromisoformat(ts_str[:19])
    
    # 找最近的工具组（工具组结束时间在 assistant 消息之前 120秒内）
    best_group = None
    best_diff = float('inf')
    for end_ts, sid, group in group_end_times:
        diff = (msg_ts - end_ts).total_seconds()
        if 0 <= diff <= 120 and diff < best_diff:
            best_diff = diff
            best_group = group
    
    if best_group:
        thinking = group_to_thinking(best_group)
        msg['thinking'] = thinking
        updated += 1
        print(f'  +thinking ts={ts_str[:19]} tools={len(best_group)} diff={best_diff:.0f}s')

print(f'\nUpdated {updated} messages with thinking')

conn.execute(
    'UPDATE interview_sessions SET conversation_history=? WHERE session_id=?',
    (json.dumps(hist, ensure_ascii=False), TARGET_SID)
)
conn.commit()
conn.close()
print('[DONE]')
