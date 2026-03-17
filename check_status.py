import sqlite3

conn = sqlite3.connect('backend/data/local_data.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT status, COUNT(*) as cnt FROM crawl_tasks GROUP BY status ORDER BY cnt DESC")
rows = cur.fetchall()
print('当前状态分布:')
for r in rows:
    print(f'  {r["status"]}: {r["cnt"]}条')
conn.close()
