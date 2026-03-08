#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复导入函数的字段名兼容性"""

with open('backend/services/finetune_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复字段名
content = content.replace(
    'content = rec.get("content", "").strip()',
    'content = (rec.get("user_content", "") or rec.get("content", "")).strip()'
)

content = content.replace(
    'llm_raw = rec.get("llm_raw", "")',
    'llm_raw = rec.get("llm_response", "") or rec.get("llm_raw", "")'
)

with open('backend/services/finetune_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("修复完成！")
