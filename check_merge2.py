import json
import sqlite3

# 从日志拿最新含Markdown的记录，找对应q_id看数据库
log_path = 'e:/Agent/AgentProject/wxr_agent/微调/llm_logs/miner_two_stage_log.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f'日志总行数: {len(lines)}')
print(f'最新记录时间: {json.loads(lines[-1]).get("ts")}')
print(f'最早记录时间: {json.loads(lines[0]).get("ts")}')
print()

# 找含Markdown的记录
md_records = []
for line in lines:
    rec = json.loads(line)
    s2 = rec.get('stage2_output', '')
    if s2 and '**' in s2:
        md_records.append(rec)

print(f'含Markdown的记录数: {len(md_records)}')
if md_records:
    sample = md_records[-1]
    print(f'最新Markdown记录时间: {sample.get("ts")}')
    print(f'source: {sample.get("source")}')
    print(f'source_url: {sample.get("source_url", "")[:80]}')
    
    # 从stage2_output里找q_id
    s2_out = sample.get('stage2_output', '')
    try:
        s2_list = json.loads(s2_out)
        print(f'stage2_output题目数: {len(s2_list)}')
        first = s2_list[0] if s2_list else {}
        qt = first.get('question_text', '')[:50]
        print(f'第一题题干: {qt}')
        at = first.get('answer_text', '')
        print(f'answer_text含**:{"**" in at}, 含\\n:{chr(10) in at}')
        
        # 用question_text去数据库查
        conn = sqlite3.connect('e:/Agent/AgentProject/wxr_agent/backend/data/local_data.db')
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT q_id, answer_text, updated_at FROM questions WHERE question_text LIKE ? LIMIT 1',
                           (f'%{qt[:20]}%',)).fetchone()
        if row:
            print(f'\n数据库中找到: q_id={row["q_id"]}')
            print(f'updated_at: {row["updated_at"]}')
            db_at = row['answer_text'] or ''
            print(f'DB answer_text含**:{"**" in db_at}, 含\\n:{chr(10) in db_at}')
            print(f'DB answer_text repr: {repr(db_at[:200])}')
        else:
            print(f'数据库未找到该题目（题干: {qt}）')
        conn.close()
    except Exception as e:
        print(f'解析失败: {e}')
