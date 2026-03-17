import sqlite3
from datetime import datetime

conn = sqlite3.connect('backend/data/local_data.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 1. 重置有raw_content的可重试任务为 fetched（跳过抓取直接进LLM提取）
result = cur.execute("""
    UPDATE crawl_tasks
    SET status = 'fetched',
        error_msg = NULL,
        processed_at = ?
    WHERE status = 'error'
      AND raw_content IS NOT NULL
      AND LENGTH(raw_content) > 0
      AND (
          error_msg LIKE '%truncated%'
          OR error_msg LIKE '%429%'
          OR error_msg LIKE '%Too Many%'
          OR error_msg LIKE '%后必须紧跟%'
          OR error_msg LIKE '%正文+OCR 均无题目%'
      )
""", (now,))
print(f'重置为 fetched: {result.rowcount} 条')

# 2. 重置网络错误（无raw_content）为 pending 重新抓取
result2 = cur.execute("""
    UPDATE crawl_tasks
    SET status = 'pending',
        error_msg = NULL,
        processed_at = ?
    WHERE status = 'error'
      AND (raw_content IS NULL OR LENGTH(raw_content) = 0)
      AND (
          error_msg LIKE '%WinError%'
          OR error_msg LIKE '%远程主机%'
          OR error_msg LIKE '%ConnectionReset%'
      )
""", (now,))
print(f'重置为 pending（网络错误重新抓取）: {result2.rowcount} 条')

conn.commit()

# 验证结果
cur.execute("SELECT status, COUNT(*) as cnt FROM crawl_tasks GROUP BY status ORDER BY cnt DESC")
rows = cur.fetchall()
print()
print('重置后状态分布:')
for r in rows:
    print(f'  {r["status"]}: {r["cnt"]}条')

conn.close()
print()
print('完成！请等待下次定时任务（每2小时整点）自动处理，或手动触发。')
