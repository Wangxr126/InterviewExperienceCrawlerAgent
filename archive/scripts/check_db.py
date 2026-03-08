import sqlite3

# 检查 local_data.db
conn = sqlite3.connect('backend/data/local_data.db')
cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('=== local_data.db 中的表 ===')
for row in cursor:
    print(f'  {row[0]}')

# 检查 crawl_tasks 表的状态
try:
    cursor = conn.execute('SELECT status, COUNT(*) as cnt FROM crawl_tasks GROUP BY status')
    print('\n=== 帖子状态统计 ===')
    for row in cursor:
        print(f'  {row[0]}: {row[1]}条')
except Exception as e:
    print(f'\n查询失败: {e}')

conn.close()
