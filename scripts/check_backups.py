import sqlite3, json

dbs = [
    'archive/old_db/db_backup_20260317_094019.db',
    'backend/data/local_data_backup_merge_20260318_122648.db',
    'backend/data/local_data_backup_20260318_095158.db',
]

for db_path in dbs:
    print(f'\n{'='*60}')
    print(f'DB: {db_path}')
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT session_id, user_id, start_time FROM interview_sessions WHERE user_id='Wangxr' ORDER BY start_time"
        ).fetchall()
        print(f'Wangxr sessions: {len(rows)}')
        for sid, uid, st in rows:
            hist_row = conn.execute(
                'SELECT conversation_history FROM interview_sessions WHERE session_id=?', (sid,)
            ).fetchone()
            hist = json.loads(hist_row[0]) if hist_row and hist_row[0] else []
            march16 = [m for m in hist if m.get('timestamp','').startswith('2026-03-16')]
            assistant_march16 = [m for m in march16 if m.get('role')=='assistant']
            print(f'  {sid}: total={len(hist)}, march16={len(march16)}, assistant_march16={len(assistant_march16)}')
            for m in assistant_march16[:3]:
                print(f'    [{m["role"]}] {m.get("timestamp","")[:19]} | {repr(str(m.get("content",""))[:80])}')
        conn.close()
    except Exception as e:
        print(f'ERROR: {e}')
