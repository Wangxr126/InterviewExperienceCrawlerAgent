#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 main.py 编码问题 - 简化版"""

# 读取文件（尝试多种编码）
content = None
for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
    try:
        with open('backend/main.py', 'r', encoding=encoding, errors='ignore') as f:
            content = f.read()
        print(f'使用 {encoding} 编码读取成功')
        break
    except:
        continue

if not content:
    print('无法读取文件')
    exit(1)

# 查找并修复第146行附近的问题
lines = content.split('\n')
print(f'总行数: {len(lines)}')

# 修复已知问题行
fixed = False
for i in range(140, min(155, len(lines))):
    line = lines[i]
    if '"""同步预热 LLM' in line and '调' in line and not line.endswith('"""'):
        lines[i] = '    """同步预热 LLM，供启动时及 run_xhs_worker 子进程调用"""'
        print(f'修复第 {i+1} 行')
        fixed = True
    elif 'Ollama 冷启动可能较' in line and not line.endswith('慢'):
        lines[i] = '    warmup_llm(timeout=120)  # Ollama 冷启动可能较慢'
        print(f'修复第 {i+1} 行')
        fixed = True
    elif '"""启动时打印各 Agent 使用' in line and not line.endswith('"""'):
        lines[i] = '    """启动时打印各 Agent 使用的 LLM 和参数（从 settings 读取，不直接读 env）"""'
        print(f'修复第 {i+1} 行')
        fixed = True

# 写回文件
content = '\n'.join(lines)
with open('backend/main.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

if fixed:
    print('[OK] 编码问题已修复')
else:
    print('[INFO] 未发现需要修复的问题')
