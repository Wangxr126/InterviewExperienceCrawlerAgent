import sqlite3

conn = sqlite3.connect('backend/data/local_data.db')
conn.row_factory = sqlite3.Row

print('=== 最近 5 条 error 任务详情 ===')
rows = conn.execute(
    "SELECT task_id, source_url, source_platform, error_msg, processed_at "
    "FROM crawl_tasks WHERE status='error' ORDER BY processed_at DESC LIMIT 5"
).fetchall()
for r in rows:
    print('task_id:', r['task_id'])
    print('platform:', r['source_platform'])
    print('url:', (r['source_url'] or '')[:80])
    print('error:', str(r['error_msg'] or '')[:300])
    print('time:', r['processed_at'])
    print()

conn.close()
