#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 main.py 中的编码问题"""

import chardet

# 检测文件编码
with open('backend/main.py', 'rb') as f:
    raw_data = f.read()
    result = chardet.detect(raw_data)
    print(f"检测到的编码: {result['encoding']}, 置信度: {result['confidence']}")

# 尝试用检测到的编码读取
try:
    content = raw_data.decode(result['encoding'])
except:
    # 如果失败，尝试 gbk
    try:
        content = raw_data.decode('gbk')
        print("使用 GBK 编码读取成功")
    except:
        # 最后尝试 latin1（不会失败）
        content = raw_data.decode('latin1')
        print("使用 Latin1 编码读取")

# 修复已知的乱码注释
fixes = [
    ('"""同步预热 LLM，供启动时及 run_xhs_worker 子进程调�?""', '"""同步预热 LLM，供启动时及 run_xhs_worker 子进程调用"""'),
    ('warmup_llm(timeout=120)  # Ollama 冷启动可能较�?', 'warmup_llm(timeout=120)  # Ollama 冷启动可能较慢'),
    ('"""启动时打印各 Agent 使用�?LLM 和参数（�?settings 读取，不直接�?env�?""', '"""启动时打印各 Agent 使用的 LLM 和参数（从 settings 读取，不直接读 env）"""'),
    ('║  API 地址  ：http://localhost:8000', '║  API 地址  ：http://localhost:8000                   ║'),
]

for old, new in fixes:
    if old in content:
        content = content.replace(old, new)
        print(f"✓ 修复: {old[:50]}...")

# 以 UTF-8 编码写回
with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n[OK] main.py 编码问题已修复")
