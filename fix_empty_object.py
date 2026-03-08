import re

with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到并替换空对象处理逻辑
old_code = '''    # 0. 检测「帖子与面经无关」
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("reason") == "帖子与面经无关":
            return [], "unrelated"
    except json.JSONDecodeError:
        pass'''

new_code = '''    # 0. 检测「帖子与面经无关」或空对象
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("reason") == "帖子与面经无关":
                return [], "unrelated"
            # 处理空对象 {} 的情况（LLM有时返回空对象表示无题目）
            if not data:
                logger.info("LLM 返回空对象 {}，判定为无题目")
                return [], "empty"
    except json.JSONDecodeError:
        pass'''

if old_code in content:
    content = content.replace(old_code, new_code)
    
    with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已添加空对象 {} 的处理逻辑')
else:
    print('[WARN] 未找到目标代码')

# 同时优化提示词，更明确地要求返回格式
print('\n正在优化提示词...')

old_prompt = '''## 输出格式
直接输出JSON数组，不加markdown代码块。
格式：[{"question_text":"题目","answer_text":"答案","difficulty":"easy/medium/hard","question_type":"分类","topic_tags":["标签"],"company":"","position":""}]
无关帖子输出：{"reason":"帖子与面经无关"}
无题目输出：[]'''

new_prompt = '''## 输出格式
直接输出JSON数组，不加markdown代码块。
格式：[{"question_text":"题目","answer_text":"答案","difficulty":"easy/medium/hard","question_type":"分类","topic_tags":["标签"],"company":"","position":""}]

特殊情况：
- 完全无关帖子（广告/吐槽）：{"reason":"帖子与面经无关"}
- 无题目但相关：[]（空数组，不要返回空对象{}）'''

if old_prompt in content:
    content = content.replace(old_prompt, new_prompt)
    
    with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已优化提示词格式说明')
else:
    print('[WARN] 提示词未找到')

print('\n修复完成！主要改进：')
print('1. 添加了对空对象 {} 的处理（判定为 empty）')
print('2. 优化提示词，明确要求无题目时返回 [] 而不是 {}')
print('3. 添加日志记录，便于调试')
