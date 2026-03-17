"""
修复LLM提示词：强制使用中文回答
"""

with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在系统提示词开头添加中文要求
old_prompt_start = 'EXTRACT_SYSTEM_PROMPT = """你是面经提取专家，从面经原文中提取所有面试题，输出 JSON 数组。\n\n## 提取规则'

new_prompt_start = 'EXTRACT_SYSTEM_PROMPT = """你是面经提取专家，从面经原文中提取所有面试题，输出 JSON 数组。\n\n**重要：所有回答必须使用中文！题目、答案、分类等所有字段内容都必须用中文表达。**\n\n## 提取规则'

content = content.replace(old_prompt_start, new_prompt_start)

# 在输出格式部分强调中文
old_output = '## 输出格式\n直接输出JSON数组，不加markdown代码块。\n格式：[{"question_text":"题目","answer_text":"答案"'

new_output = '## 输出格式\n直接输出JSON数组，不加markdown代码块。**所有字段内容必须用中文。**\n格式：[{"question_text":"题目（中文）","answer_text":"答案（中文）"'

content = content.replace(old_output, new_output)

with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已修复LLM提示词')
print('修改：')
print('1. 在开头添加：所有回答必须使用中文')
print('2. 在输出格式强调：所有字段内容必须用中文')
print('3. 示例中标注（中文）')
