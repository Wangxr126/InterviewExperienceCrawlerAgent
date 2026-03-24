# -*- coding: utf-8 -*-
import sqlite3
import os

db = r'E:\Agent\AgentProject\wxr_agent\backend\data\local_data.db'
print('exists:', os.path.exists(db))
if not os.path.exists(db):
    # 搜索db文件
    for root, dirs, files in os.walk(r'E:\Agent\AgentProject\wxr_agent\backend'):
        for f in files:
            if f.endswith('.db'):
                print('found:', os.path.join(root, f))
    exit(1)

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
print('finetune_samples count:', conn.execute('SELECT COUNT(*) FROM finetune_samples').fetchone()[0])
print('crawl_tasks processed:', conn.execute("SELECT COUNT(*) FROM crawl_tasks WHERE status='processed'").fetchone()[0])
conn.close()
print('done')
