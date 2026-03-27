import sqlite3

conn = sqlite3.connect('e:/Agent/AgentProject/wxr_agent/backend/data/local_data.db')
conn.row_factory = sqlite3.Row
curs = conn.cursor()

# 找有answer_text且长度>100的题目
rows = curs.execute("SELECT q_id, question_text, answer_text, raw_answer FROM questions WHERE length(answer_text) > 100 LIMIT 5").fetchall()
for r in rows:
    print('=== q_id:', r['q_id'])
    print('question:', (r['question_text'] or '')[:60])
    at = r['answer_text'] or ''
    ra = r['raw_answer'] or ''
    print('answer_text repr:', repr(at[:300]))
    print('raw_answer repr:', repr(ra[:300]))
    # 检查是否含Markdown特征
    has_md = any(c in at for c in ['**', '\\n', '\n', '##', '1.', '- '])
    print('has_markdown_features:', has_md)
    print()

conn.close()
