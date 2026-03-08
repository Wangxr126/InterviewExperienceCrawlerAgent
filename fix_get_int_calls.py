"""
修复 config.py 中的 _get_int 调用
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复所有的 _get_int 调用，添加默认值 0
replacements = [
    ('_get_int("ARCHITECT_TIMEOUT") or self.llm_timeout', '_get_int("ARCHITECT_TIMEOUT", 0) or self.llm_timeout'),
    ('_get_int("INTERVIEWER_TIMEOUT") or self.llm_timeout', '_get_int("INTERVIEWER_TIMEOUT", 0) or self.llm_timeout'),
    ('_get_int("FINETUNE_LLM_TIMEOUT") or self.llm_timeout', '_get_int("FINETUNE_LLM_TIMEOUT", 0) or self.llm_timeout'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已修复 config.py 中的 _get_int 调用')
print('')
print('修复内容：')
print('  - architect_timeout: 添加默认值 0')
print('  - interviewer_timeout: 添加默认值 0')
print('  - finetune_llm_timeout: 添加默认值 0')
print('')
print('逻辑：如果配置为空或0，则使用全局 LLM_TIMEOUT')
