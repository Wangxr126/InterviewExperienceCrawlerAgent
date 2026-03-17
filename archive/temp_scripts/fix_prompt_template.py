"""
修改提示词模板，明确要求LLM填充公司和岗位字段
"""

with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换提示词模板
old_template = '''EXTRACT_PROMPT_TEMPLATE = """## 面经原文
{content}

## 任务
从上面原文提取所有面试题，输出JSON数组。公司：{company}，岗位：{position}"""'''

new_template = '''EXTRACT_PROMPT_TEMPLATE = """## 面经原文
{content}

## 任务
从上面原文提取所有面试题，输出JSON数组。

**重要信息**：
- 公司：{company}
- 岗位：{position}

**要求**：
1. 每道题目的company字段必须填写：{company}
2. 每道题目的position字段必须填写：{position}
3. 如果原文中提到其他公司或岗位，以原文为准
4. 所有内容必须用中文"""'''

content = content.replace(old_template, new_template)

with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已修改提示词模板')
print('修改：')
print('1. 明确标注公司和岗位信息')
print('2. 要求每道题目必须填写company和position字段')
print('3. 强调所有内容用中文')
