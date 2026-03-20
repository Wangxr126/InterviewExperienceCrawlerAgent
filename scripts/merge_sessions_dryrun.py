import sqlite3, json
from datetime import datetime

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'
TARGET_UID = 'Wangxr'

conn = sqlite3.connect(DB)

# 获取所有属于 Wangxr 的 session，按开始时间排序
rows = conn.execute(
    "SELECT session_id, user_id, start_time, conversation_history FROM interview_sessions "
    "WHERE user_id=? ORDER BY start_time ASC",
    (TARGET_UID,)
).fetchall()

print(f'Found {len(rows)} sessions for user {TARGET_UID}:')
for r in rows:
    hist = json.loads(r[3]) if r[3] else []
    print(f'  {r[0]} start={r[2]} msgs={len(hist)}')

# 收集目标 session 当前的消息
target_row = conn.execute(
    "SELECT conversation_history FROM interview_sessions WHERE session_id=?",
    (TARGET_SID,)
).fetchone()
current_hist = json.loads(target_row[0]) if target_row and target_row[0] else []
print(f'\nTarget session {TARGET_SID} currently has {len(current_hist)} messages')

# 合并所有其他 session 的消息到目标 session（按时间排序）
all_messages = []
for sid, uid, st, hist_raw in rows:
    if sid == TARGET_SID:
        continue
    hist = json.loads(hist_raw) if hist_raw else []
    if not hist:
        continue
    # 给没有 timestamp 的消息补上 session 的 start_time 作为近似时间戳
    for i, msg in enumerate(hist):
        if not msg.get('timestamp') and not msg.get('ts'):
            msg['timestamp'] = st
        elif msg.get('ts') and not msg.get('timestamp'):
            msg['timestamp'] = msg['ts']
    all_messages.extend(hist)
    print(f'  + {len(hist)} msgs from {sid}')

# 加上目标 session 自己的消息
for msg in current_hist:
    if not msg.get('timestamp') and msg.get('ts'):
        msg['timestamp'] = msg['ts']
all_messages.extend(current_hist)

# 按 timestamp 排序
def sort_key(m):
    ts = m.get('timestamp') or m.get('ts') or ''
    return ts

all_messages.sort(key=sort_key)

print(f'\nTotal merged messages: {len(all_messages)}')

# 预览前几条和后几条
print('\nFirst 3 messages:')
for m in all_messages[:3]:
    print(f'  role={m.get("role")} ts={m.get("timestamp","")[:19]} content={repr(str(m.get("content",""))[:60])}')
print('Last 3 messages:')
for m in all_messages[-3:]:
    print(f'  role={m.get("role")} ts={m.get("timestamp","")[:19]} content={repr(str(m.get("content",""))[:60])}')

conn.close()
print('\n[DRY RUN] No changes made. Run merge_sessions_apply.py to apply.')
