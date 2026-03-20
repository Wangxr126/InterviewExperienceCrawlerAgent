import sqlite3

DB = r'E:\Agent\AgentProject\wxr_agent\backend\data\local_data.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print('=== study_records (latest 10) ===')
rows = conn.execute('SELECT question_id, score, studied_at FROM study_records ORDER BY studied_at DESC LIMIT 10').fetchall()
for r in rows:
    print(dict(r))

print()
print('=== user_tag_mastery (latest 10) ===')
rows2 = conn.execute('SELECT user_id, tag, avg_score, total_attempts, mastery_level FROM user_tag_mastery ORDER BY last_updated DESC LIMIT 10').fetchall()
for r in rows2:
    print(dict(r))

print()
print('=== questions last_score via get_latest_scores_for_questions ===')
rows3 = conn.execute('''
    SELECT sr.question_id, sr.score, sr.studied_at
    FROM study_records sr
    INNER JOIN (
        SELECT question_id, MAX(studied_at) as max_at
        FROM study_records
        GROUP BY question_id
    ) latest ON sr.question_id = latest.question_id AND sr.studied_at = latest.max_at
    LIMIT 10
''').fetchall()
for r in rows3:
    print(dict(r))

print()
print('=== questions table sample with q_id ===')
rows4 = conn.execute('SELECT q_id, question_text, difficulty FROM questions LIMIT 5').fetchall()
for r in rows4:
    print(dict(r))

conn.close()
