import re

with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 使用正则替换调用处
pattern = r'user_prompt = EXTRACT_PROMPT_TEMPLATE\.format\(\s*platform=.*?\s*company=company or "未知",\s*position=position or "未知",\s*difficulty=.*?\s*content=truncated,\s*\s*\)'

replacement = '''user_prompt = EXTRACT_PROMPT_TEMPLATE.format(
        company=company or "未知",
        position=position or "未知",
        content=truncated,
    )'''

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

if new_content != content:
    with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('[OK] 调用处已修复！')
    print('移除了 platform 和 difficulty 参数')
else:
    print('[INFO] 未找到需要修改的代码')
