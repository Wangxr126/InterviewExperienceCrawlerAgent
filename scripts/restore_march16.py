import json, sqlite3, re

TOOLS_LOG = 'backend/interviewer_logs/deepseek-reasoner/tools_20260316.jsonl'
DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'

# 读取工具日志，提取含 user_answer 的 submit_answer 记录
submits = {}  # question_id -> record
with open(TOOLS_LOG, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get('user_id') != 'Wangxr':
            continue
        if rec.get('tool_name') != 'submit_answer':
            continue
        inp = rec.get('tool_input', {})
        qid = inp.get('question_id', '')
        if not qid or 'user_answer' not in inp:
            continue
        submits[qid] = {
            'timestamp': rec['timestamp'],
            'question_id': qid,
            'user_answer': inp.get('user_answer', ''),
            'score': inp.get('score', 0),
            'feedback': inp.get('feedback', ''),
            'missed_points': inp.get('missed_points', []),
            'error_points': inp.get('error_points', []),
        }

print(f'Found {len(submits)} submit records')

def extract_qid(content):
    # 格式：【q_id:xxx】
    m = re.search(r'【q_id:([a-f0-9\-]+)】', content or '')
    return m.group(1) if m else None

def build_reply(s):
    score = s['score']
    feedback = s['feedback']
    missed = s['missed_points']
    errors = s['error_points']
    lines = [f'📝 评分：{score}/5', '', f'**点评**：\n{feedback}']
    if errors:
        lines += ['', '**错误点**：']
        for e in errors:
            if isinstance(e, dict):
                lines.append(f'- ✗ {e.get("wrong","")} → 正确：{e.get("correct","")}')
            else:
                lines.append(f'- ✗ {e}')
    if missed:
        lines += ['', '**遗漏点**：']
        for m in missed:
            lines.append(f'- {m}')
    return '\n'.join(lines)

# 读取当前数据库
conn = sqlite3.connect(DB)
row = conn.execute('SELECT conversation_history FROM interview_sessions WHERE session_id=?', (TARGET_SID,)).fetchone()
hist = json.loads(row[0])
print(f'Current history: {len(hist)} msgs')

# 构建新历史：在每个3月16日用户消息后，插入对应 assistant 回复
new_hist = []
inserted = 0
i = 0
while i < len(hist):
    msg = hist[i]
    new_hist.append(msg)
    role = msg.get('role', '')
    ts = msg.get('timestamp', '')
    content = msg.get('content', '') or ''

    if role == 'user' and ts.startswith('2026-03-16'):
        qid = extract_qid(content)
        # 检查下一条是否已经是 assistant
        next_msg = hist[i+1] if i+1 < len(hist) else None
        next_is_assistant = next_msg and next_msg.get('role') == 'assistant'
        
        if qid and qid in submits and not next_is_assistant:
            s = submits[qid]
            reply_text = build_reply(s)
            assistant_msg = {
                'role': 'assistant',
                'content': reply_text,
                'timestamp': s['timestamp'],
            }
            new_hist.append(assistant_msg)
            inserted += 1
            print(f'  +reply q={qid[:8]} ts={s["timestamp"][:19]} score={s["score"]}')
    i += 1

print(f'Inserted {inserted} assistant messages')
print(f'New history: {len(new_hist)} msgs')

# 按时间排序
new_hist.sort(key=lambda m: m.get('timestamp') or m.get('ts') or '')

conn.execute(
    'UPDATE interview_sessions SET conversation_history=? WHERE session_id=?',
    (json.dumps(new_hist, ensure_ascii=False), TARGET_SID)
)
conn.commit()
conn.close()
print('[DONE]')
