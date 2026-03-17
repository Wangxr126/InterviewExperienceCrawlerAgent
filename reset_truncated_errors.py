import sqlite3

conn = sqlite3.connect('backend/data/local_data.db')
conn.row_factory = sqlite3.Row

# 只重置 truncated 错误的任务（有 raw_content 的才能重置为 fetched）
cur = conn.execute("""
    UPDATE crawl_tasks
    SET status='fetched', error_msg=NULL
    WHERE status='error'
      AND error_msg = 'name ''truncated'' is not defined'
      AND raw_content IS NOT NULL
      AND trim(raw_content) != ''
""")
conn.commit()
print(f'重置为 fetched: {cur.rowcount} 条')

# 没有 raw_content 的重置为 pending，需要重新抓取
cur2 = conn.execute("""
    UPDATE crawl_tasks
    SET status='pending', error_msg=NULL
    WHERE status='error'
      AND error_msg = 'name ''truncated'' is not defined'
      AND (raw_content IS NULL OR trim(raw_content) = '')
""")
conn.commit()
print(f'重置为 pending: {cur2.rowcount} 条')

# 验证
row = conn.execute("SELECT COUNT(*) as c FROM crawl_tasks WHERE error_msg = 'name ''truncated'' is not defined'").fetchone()
print(f'剩余 truncated error: {row["c"]} 条')

row2 = conn.execute("SELECT COUNT(*) as c FROM crawl_tasks WHERE status='error'").fetchone()
print(f'当前 error 总数: {row2["c"]} 条')

row3 = conn.execute("SELECT COUNT(*) as c FROM crawl_tasks WHERE status='fetched'").fetchone()
print(f'当前 fetched 总数（待处理）: {row3["c"]} 条')

conn.close()
