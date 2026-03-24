# -*- coding: utf-8 -*-
"""
从 finetune_samples + crawl_tasks 提取 10 个多样化 demo 案例
覆盖：无关帖、非格式化标号、超多题、规则标准、人工修改
"""
import sqlite3
import json
import os
import re

DB = r'E:\Agent\AgentProject\wxr_agent\backend\data\local_data.db'
OUT = r'E:\Agent\AgentProject\wxr_agent\微调\demo_cases.json'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# ── 读取所有 finetune_samples，JOIN crawl_tasks 获取完整 raw_content
rows = conn.execute("""
    SELECT 
        fs.id,
        fs.content        AS fs_content,
        fs.stage1_output,
        fs.stage2_output,
        fs.final_output,
        fs.title,
        fs.source_url,
        fs.status,
        fs.is_modified,
        ct.raw_content    AS ct_raw_content,
        ct.post_title     AS ct_title,
        ct.company,
        ct.position,
        ct.source_platform
    FROM finetune_samples fs
    LEFT JOIN crawl_tasks ct ON ct.source_url = fs.source_url
    ORDER BY fs.id
""").fetchall()

print(f"总计 {len(rows)} 条")

def parse_questions(output_text):
    if not output_text:
        return [], False
    text = output_text.strip()
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            if isinstance(data, list):
                return data, True
        except Exception:
            pass
    return [], False

def get_content(row):
    """优先用 crawl_tasks.raw_content，否则用 finetune_samples.content"""
    ct = row['ct_raw_content'] or ''
    fs = row['fs_content'] or ''
    return ct if len(ct) > len(fs) else fs

def get_title(row):
    return row['ct_title'] or row['title'] or '（无标题）'

# ── 分析每条记录
all_items = []
for row in rows:
    final = row['final_output'] or row['stage2_output'] or row['stage1_output'] or ''
    questions, ok = parse_questions(final)
    content = get_content(row)
    
    # 判断是否有非规则标号（数字+中文括号/顿号/点）
    has_irregular_numbering = bool(re.search(
        r'[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十][、。]|\d+[）)、]',
        content[:2000]
    ))
    
    item = {
        'id': row['id'],
        'title': get_title(row),
        'source_url': row['source_url'] or '',
        'company': row['company'] or '',
        'position': row['position'] or '',
        'platform': row['source_platform'] or '',
        'status': row['status'] or '',
        'is_modified': bool(row['is_modified']),
        'content': content,
        'content_len': len(content),
        'final_output': final,
        'questions_count': len(questions),
        'questions': questions,
        'parse_ok': ok,
        'has_irregular_numbering': has_irregular_numbering,
    }
    all_items.append(item)

# 打印实际内容长度分布
content_lens = sorted([x['content_len'] for x in all_items], reverse=True)
print(f"内容长度 TOP10: {content_lens[:10]}")
print(f"内容长度 median: {content_lens[len(content_lens)//2]}")

# ── 分类
cases_irrelevant    = [x for x in all_items if not x['parse_ok'] or x['questions_count'] == 0]
cases_many          = sorted([x for x in all_items if x['questions_count'] >= 8], key=lambda x: -x['questions_count'])
cases_irregular_nb  = [x for x in all_items if x['has_irregular_numbering'] and x['questions_count'] > 0]
cases_modified      = [x for x in all_items if x['is_modified'] and x['questions_count'] > 0]
cases_standard      = [x for x in all_items if x['parse_ok'] and 2 <= x['questions_count'] <= 5 and not x['is_modified']]
cases_single        = [x for x in all_items if x['questions_count'] == 1]

print(f"\n无关/空帖: {len(cases_irrelevant)}")
print(f"超多题(>=8): {len(cases_many)}")
print(f"非规则标号: {len(cases_irregular_nb)}")
print(f"人工修改: {len(cases_modified)}")
print(f"格式标准: {len(cases_standard)}")
print(f"单题: {len(cases_single)}")

# ── 选样：尽量多样化，优先内容最长（= raw_content完整）
def pick_diverse(pool, n, exclude_ids=set()):
    """从pool中选n个，排除已选id，优先内容长的"""
    candidates = [x for x in pool if x['id'] not in exclude_ids]
    # 去重标题
    seen_titles = set()
    unique = []
    for x in sorted(candidates, key=lambda x: -x['content_len']):
        t = x['title'][:30]
        if t not in seen_titles:
            seen_titles.add(t)
            unique.append(x)
    return unique[:n]

selected = []
selected_ids = set()

plan = [
    ('无关帖',      cases_irrelevant,   2),
    ('非格式化标号', cases_irregular_nb, 2),
    ('超多题',      cases_many,         2),
    ('人工修改标注', cases_modified,     2),
    ('格式规则',    cases_standard,     2),
]

for label, pool, n in plan:
    picks = pick_diverse(pool, n, selected_ids)
    for item in picks:
        item['category'] = label
        selected.append(item)
        selected_ids.add(item['id'])

# 不足10条补充
for item in sorted(all_items, key=lambda x: -x['content_len']):
    if len(selected) >= 10:
        break
    if item['id'] not in selected_ids:
        item['category'] = '补充'
        selected.append(item)
        selected_ids.add(item['id'])

selected = selected[:10]

print(f"\n=== 最终选出 {len(selected)} 个案例 ===")
for i, s in enumerate(selected):
    print(f"  [{i+1}] id={s['id']} 类型={s['category']} 题目数={s['questions_count']} 内容长={s['content_len']} 标题={s['title'][:50]}")
    if s['content']:
        print(f"       内容前100: {s['content'][:100].strip()}")

# ── 写入 JSON（完整content）
out_dir = os.path.dirname(OUT)
os.makedirs(out_dir, exist_ok=True)

demo_output = []
for i, s in enumerate(selected):
    demo_output.append({
        'case_index': i + 1,
        'category': s['category'],
        'id': s['id'],
        'title': s['title'],
        'source_url': s['source_url'],
        'company': s['company'],
        'position': s['position'],
        'platform': s['platform'],
        # content 完整保留，用于送推理
        'content': s['content'],
        'content_preview': s['content'][:300] + ('...' if len(s['content']) > 300 else ''),
        # final_output 作为「豆包/标注参考答案」
        'doubao_output': s['final_output'],
        'questions_count': s['questions_count'],
        'questions': s['questions'],
        'is_modified': s['is_modified'],
        'status': s['status'],
        'has_irregular_numbering': s['has_irregular_numbering'],
    })

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(demo_output, f, ensure_ascii=False, indent=2)

print(f"\n已写入 {len(demo_output)} 条到: {OUT}")
conn.close()
