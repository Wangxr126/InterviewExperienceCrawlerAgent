import sqlite3

conn = sqlite3.connect('E:/Agent/AgentProject/wxr_agent/backend/data/local_data.db')
conn.row_factory = sqlite3.Row

# 看一条有 raw_content 的 error 任务的完整 error_msg
rows = conn.execute("""
    SELECT id, task_id, error_msg, raw_content, source_url, post_title, source_platform
    FROM crawl_tasks
    WHERE status='error' AND error_msg LIKE '%truncated%'
    LIMIT 3
""").fetchall()

for r in rows:
    d = dict(r)
    print(f"=== id={d['id']} platform={d['source_platform']} ===")
    print(f"title: {d.get('post_title','')}")
    print(f"error_msg: {d.get('error_msg','')}")
    content = d.get('raw_content') or ''
    print(f"raw_content length: {len(content)}")
    print(f"raw_content[:500]: {content[:500]}")
    print()

# 看一条无 raw_content 的 error 任务
rows2 = conn.execute("""
    SELECT id, task_id, error_msg, source_url, post_title, source_platform
    FROM crawl_tasks
    WHERE status='error' AND (raw_content IS NULL OR raw_content='')
    LIMIT 3
""").fetchall()
print('=== error 任务（无 raw_content）===')
for r in rows2:
    d = dict(r)
    print(f"  id={d['id']} platform={d['source_platform']} error_msg={d.get('error_msg','')}")

conn.close()
