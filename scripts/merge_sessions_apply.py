import sqlite3, json, shutil
from datetime import datetime
from pathlib import Path

DB = 'backend/data/local_data.db'
TARGET_SID = 'sess_Wangxr'
TARGET_UID = 'Wangxr'

# 备份数据库
backup_path = f'backend/data/local_data_backup_merge_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
shutil.copy2(DB, backup_path)
print(f'[BACKUP] {backup_path}')

conn = sqlite3.connect(DB)

# 获取所有属于 Wangxr 的 session，按开始时间排序
rows = conn.execute(
    "SELECT session_id, user_id, start_time, conversation_history FROM interview_sessions "
    "WHERE user_id=? ORDER BY start_time ASC",
    (TARGET_UID,)
).fetchall()

# 收集目标 session 当前的消息
target_row = conn.execute(
    "SELECT conversation_history FROM interview_sessions WHERE session_id=?",
    (TARGET_SID,)
).fetchone()
current_hist = json.loads(target_row[0]) if target_row and target_row[0] else []

# 合并所有其他 session 的消息
all_messages = []
merged_sids = []
for sid, uid, st, hist_raw in rows:
    if sid == TARGET_SID:
        continue
    hist = json.loads(hist_raw) if hist_raw else []
    if not hist:
        continue
    for i, msg in enumerate(hist):
        if not msg.get('timestamp') and not msg.get('ts'):
            msg['timestamp'] = st
        elif msg.get('ts') and not msg.get('timestamp'):
            msg['timestamp'] = msg['ts']
    all_messages.extend(hist)
    merged_sids.append(sid)
    print(f'  + {len(hist)} msgs from {sid}')

# 加入目标 session 的消息
for msg in current_hist:
    if not msg.get('timestamp') and msg.get('ts'):
        msg['timestamp'] = msg['ts']
all_messages.extend(current_hist)

# 按 timestamp 排序
all_messages.sort(key=lambda m: m.get('timestamp') or m.get('ts') or '')

print(f'Total merged messages: {len(all_messages)}')

# 写回目标 session
conn.execute(
    "UPDATE interview_sessions SET conversation_history=?, start_time=("
    "SELECT MIN(start_time) FROM interview_sessions WHERE user_id=?"
    ") WHERE session_id=?",
    (json.dumps(all_messages, ensure_ascii=False), TARGET_UID, TARGET_SID)
)

# 删除已合并的其他 session（保留目标 session）
for sid in merged_sids:
    conn.execute("DELETE FROM interview_sessions WHERE session_id=?", (sid,))
    print(f'  - Deleted session: {sid}')

conn.commit()
conn.close()

print(f'\n[DONE] Merged {len(all_messages)} messages into {TARGET_SID}')
print(f'[DONE] Deleted {len(merged_sids)} old sessions')
print(f'[BACKUP] Original DB backed up to {backup_path}')
