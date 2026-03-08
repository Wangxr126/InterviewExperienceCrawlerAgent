#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 question_extractor.py 中的缩进问题
"""

import sys
from pathlib import Path

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = Path(__file__).parent / "backend" / "services" / "crawler" / "question_extractor.py"

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 要替换的错误代码
old_code = """        questions.append({
            # q_id 由数据库自动生成（INTEGER PRIMARY KEY AUTOINCREMENT）
                        "question_text": q_text,"""

# 正确的代码
new_code = """        # q_id 由数据库自动生成（INTEGER PRIMARY KEY AUTOINCREMENT）
        questions.append({
            "question_text": q_text,"""

# 替换
if old_code in content:
    content = content.replace(old_code, new_code)
    print("✅ 找到并修复了缩进问题")
else:
    print("⚠️ 未找到匹配的代码")
    exit(1)

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✅ 已修复 {file_path}")
print("现在重启服务即可正常保存题目")
