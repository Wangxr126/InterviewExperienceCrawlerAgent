import sqlite3
conn = sqlite3.connect(r'E:\Agent\AgentProject\wxr_agent\backend\data\local_data.db')
rows = conn.execute("SELECT task_id FROM crawl_tasks WHERE status='fetched' LIMIT 3").fetchall()
conn.close()
for r in rows:
    print(r[0])
