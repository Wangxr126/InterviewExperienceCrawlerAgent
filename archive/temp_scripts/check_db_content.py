import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('backend/data/local_data.db')
cursor = conn.cursor()

# 查看最新的10条任务的raw_content
cursor.execute('''
    SELECT task_id, post_title, LENGTH(raw_content) as content_len,
           SUBSTR(raw_content, 1, 200) as content_preview,
           status, source_url, discovered_at
    FROM crawl_tasks
    WHERE source_platform = 'nowcoder'
    ORDER BY discovered_at DESC
    LIMIT 10
''')

print('=== 最新10条任务的raw_content ===\n')
rows = cursor.fetchall()
if not rows:
    print('没有数据！')
else:
    for row in rows:
        task_id, title, content_len, preview, status, url, discovered_at = row
        print(f'任务ID: {task_id}')
        print(f'标题: {title[:50] if title else "无"}')
        print(f'URL: {url[:60]}...')
        print(f'状态: {status}')
        print(f'发现时间: {discovered_at}')
        print(f'内容长度: {content_len if content_len else 0} 字符')
        print(f'内容预览: {preview if preview else "(空)"}')
        print('-' * 100)
        print()

# 统计所有内容长度分布
cursor.execute('''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN raw_content IS NULL OR LENGTH(raw_content) = 0 THEN 1 ELSE 0 END) as empty,
        SUM(CASE WHEN raw_content IS NOT NULL AND LENGTH(raw_content) > 0 AND LENGTH(raw_content) < 200 THEN 1 ELSE 0 END) as short,
        SUM(CASE WHEN raw_content IS NOT NULL AND LENGTH(raw_content) >= 200 AND LENGTH(raw_content) < 500 THEN 1 ELSE 0 END) as medium,
        SUM(CASE WHEN raw_content IS NOT NULL AND LENGTH(raw_content) >= 500 THEN 1 ELSE 0 END) as long
    FROM crawl_tasks
    WHERE source_platform = 'nowcoder'
''')

row = cursor.fetchone()
if row and row[0] > 0:
    total, empty, short, medium, long_content = row
    
    print('\n=== 所有任务内容长度统计 ===')
    print(f'总数: {total}')
    print(f'空内容: {empty} ({empty/total*100:.1f}%)')
    print(f'短内容(<200字): {short} ({short/total*100:.1f}%)')
    print(f'中等(200-500字): {medium} ({medium/total*100:.1f}%)')
    print(f'长内容(>=500字): {long_content} ({long_content/total*100:.1f}%)')
else:
    print('\n没有任务数据')

conn.close()
