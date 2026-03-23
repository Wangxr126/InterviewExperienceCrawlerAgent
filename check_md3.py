import sqlite3

conn = sqlite3.connect('e:/Agent/AgentProject/wxr_agent/backend/data/local_data.db')
conn.row_factory = sqlite3.Row
curs = conn.cursor()

total = curs.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
has_md = curs.execute("SELECT COUNT(*) FROM questions WHERE answer_text LIKE '%**%' OR answer_text LIKE '%\n1.%' OR answer_text LIKE '%\n\n%'").fetchone()[0]
no_md = curs.execute("SELECT COUNT(*) FROM questions WHERE answer_text IS NOT NULL AND answer_text != '' AND answer_text NOT LIKE '%**%' AND answer_text NOT LIKE '%\n%'").fetchone()[0]
empty = curs.execute("SELECT COUNT(*) FROM questions WHERE answer_text IS NULL OR answer_text = ''").fetchone()[0]

print(f'总题目数: {total}')
print(f'有Markdown格式答案: {has_md} ({100*has_md//total}%)')
print(f'无Markdown纯文本答案: {no_md} ({100*no_md//total}%)')
print(f'无答案: {empty} ({100*empty//total}%)')

# 看最近更新的10条
print('\n最近更新的10条题目（updated_at + answer MD特征）:')
rows = curs.execute("SELECT q_id, question_text, answer_text, updated_at FROM questions WHERE answer_text IS NOT NULL AND answer_text != '' ORDER BY updated_at DESC LIMIT 10").fetchall()
for r in rows:
    at = r['answer_text'] or ''
    has_md = '**' in at or '\n' in at
    print(f'  {r["updated_at"]} | MD={has_md} | {(r["question_text"] or "")[:40]}')

conn.close()
