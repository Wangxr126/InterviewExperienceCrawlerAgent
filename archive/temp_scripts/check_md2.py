import sqlite3
import json
import os

conn = sqlite3.connect('e:/Agent/AgentProject/wxr_agent/backend/data/local_data.db')
conn.row_factory = sqlite3.Row
curs = conn.cursor()

# 找有Markdown特征的答案
rows = curs.execute("SELECT q_id, question_text, answer_text, raw_answer FROM questions WHERE answer_text LIKE '%**%' OR answer_text LIKE '%\\n%' OR answer_text LIKE '%1.%' LIMIT 5").fetchall()
print(f'有Markdown特征的题目数: {len(rows)}')
for r in rows:
    print('=== q_id:', r['q_id'])
    print('answer repr:', repr((r['answer_text'] or '')[:300]))
    print()

# 总数统计
total = curs.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
has_answer = curs.execute("SELECT COUNT(*) FROM questions WHERE answer_text IS NOT NULL AND answer_text != ''").fetchone()[0]
print(f'总题目数: {total}, 有答案: {has_answer}')

# 检查Stage2日志
from backend.config.config import settings
log_path = settings.miner_two_stage_log_path
print(f'\nStage2日志路径: {log_path}')
if log_path and os.path.exists(log_path):
    size = os.path.getsize(log_path)
    print(f'日志文件大小: {size} bytes')
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f'日志行数: {len(lines)}')
    if lines:
        last = json.loads(lines[-1])
        print('最新一条 stage2_output 预览:', repr((last.get('stage2_output') or '')[:400]))
else:
    print('Stage2日志不存在或路径未配置')

conn.close()
