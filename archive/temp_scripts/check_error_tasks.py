import sqlite3

conn = sqlite3.connect('backend/data/local_data.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 查看3条「其他」错误的具体内容
cur.execute("""
    SELECT task_id, source_url, error_msg, 
           raw_content IS NOT NULL as has_raw,
           LENGTH(COALESCE(raw_content,'')) as raw_len
    FROM crawl_tasks
    WHERE status = 'error'
      AND error_msg NOT LIKE '%truncated%'
      AND error_msg NOT LIKE '%429%'
      AND error_msg NOT LIKE '%Too Many%'
      AND error_msg NOT LIKE '%后必须紧跟%'
      AND error_msg NOT LIKE '%太短%'
      AND error_msg NOT LIKE '%内容和图片均为空%'
      AND error_msg IS NOT NULL
      AND error_msg != ''
""")
rows = cur.fetchall()
print('3条其他错误详情:')
for r in rows:
    print(f'  url={str(r["source_url"])[:70]}')
    print(f'  has_raw={r["has_raw"]} raw_len={r["raw_len"]}')
    print(f'  err={r["error_msg"]}')
    print()

conn.close()
