#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复时间戳格式问题"""

with open('backend/services/finetune_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复时间戳
content = content.replace(
    'ts = rec.get("ts", now_beijing_str().isoformat(timespec="seconds"))',
    'ts = rec.get("ts", now_beijing_str())'
)

with open('backend/services/finetune_service.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("修复完成！")
