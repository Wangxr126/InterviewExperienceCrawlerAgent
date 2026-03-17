import sqlite3

conn = sqlite3.connect('E:/Agent/AgentProject/wxr_agent/backend/data/local_data.db')
conn.row_factory = sqlite3.Row

# 统计 error 任务的 error_msg 分布
print('=== error_msg 分布（Top 20）===')
rows = conn.execute("""
    SELECT error_msg, COUNT(*) as cnt
    FROM crawl_tasks
    WHERE status = 'error'
    GROUP BY error_msg
    ORDER BY cnt DESC
    LIMIT 20
""").fetchall()
for r in rows:
    print(f"  [{r['cnt']:3d}] {str(r['error_msg'])[:120]}")

print()
print('=== 最近 10 条 error 任务详情 ===')
rows2 = conn.execute("""
    SELECT task_id, url, stage, error_msg, updated_at
    FROM crawl_tasks
    WHERE status = 'error'
    ORDER BY updated_at DESC
    LIMIT 10
""").fetchall()
for r in rows2:
    print(f"  task_id={r['task_id']}")
    print(f"  stage  ={r['stage']}")
    print(f"  url    ={r['url']}")
    print(f"  error  ={str(r['error_msg'])[:200]}")
    print(f"  time   ={r['updated_at']}")
    print()

conn.close()
