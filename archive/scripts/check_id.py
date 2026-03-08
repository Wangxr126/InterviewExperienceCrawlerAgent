import sqlite3

conn = sqlite3.connect('backend/data/local_data.db')
conn.row_factory = sqlite3.Row

# 检查表结构
cursor = conn.execute('PRAGMA table_info(crawl_tasks)')
columns = cursor.fetchall()
print("crawl_tasks 表结构:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

print("\n" + "="*50 + "\n")

# 检查前5条记录
cursor = conn.execute('SELECT id, task_id, post_title FROM crawl_tasks ORDER BY id ASC LIMIT 5')
rows = cursor.fetchall()
print("前5条记录:")
for r in rows:
    row_dict = dict(r)
    title = row_dict.get('post_title', '无标题')
    if title and len(title) > 30:
        title = title[:30] + '...'
    print(f"  id={row_dict['id']}, task_id={row_dict['task_id']}, title={title}")

conn.close()
