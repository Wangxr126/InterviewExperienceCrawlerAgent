import sqlite3
from pathlib import Path

db_path = Path('backend/data/local_data.db')
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# 查看最新5条爬取任务
print('=== 最新5条爬取任务的正文情况 ===\n')
cursor.execute('''
    SELECT task_id, post_title, LENGTH(raw_content) as content_len, 
           SUBSTR(raw_content, 1, 500) as content_preview,
           status, questions_count, processed_at
    FROM crawl_tasks 
    WHERE source_platform = 'nowcoder'
    ORDER BY discovered_at DESC 
    LIMIT 5
''')

for row in cursor.fetchall():
    task_id, title, content_len, preview, status, q_count, processed_at = row
    print(f'任务ID: {task_id}')
    print(f'标题: {title[:60] if title else "无"}...')
    print(f'正文长度: {content_len} 字符')
    print(f'状态: {status}')
    print(f'题目数: {q_count}')
    print(f'处理时间: {processed_at}')
    print(f'\n正文预览:')
    print(preview)
    print('=' * 100)
    print()

conn.close()
