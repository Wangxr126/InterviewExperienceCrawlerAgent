#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""强制修复 main.py 编码问题"""

# 读取二进制数据
with open('backend/main.py', 'rb') as f:
    data = f.read()

# 查找并替换乱码的字节序列
# 这些是已知的乱码模式
replacements = [
    # 第146行附近的乱码
    (b'"""同步预热 LLM，供启动时及 run_xhs_worker 子进程调\xe7\x94\xa8""', 
     b'"""同步预热 LLM，供启动时及 run_xhs_worker 子进程调用"""'),
    
    # Ollama 注释
    (b'warmup_llm(timeout=120)  # Ollama 冷启动可能较\xe6\x85\xa2',
     b'warmup_llm(timeout=120)  # Ollama 冷启动可能较慢'),
    
    # 其他可能的乱码模式
    (b'\xe7\x94\xa8', b'用'),
    (b'\xe6\x85\xa2', b'慢'),
    (b'\xe7\x9a\x84', b'的'),
    (b'\xe4\xbb\x8e', b'从'),
    (b'\xe8\xaf\xbb', b'读'),
]

# 应用替换
modified = False
for old, new in replacements:
    if old in data:
        data = data.replace(old, new)
        modified = True
        print(f'替换: {old[:30]}... -> {new[:30]}...')

# 如果有修改，写回文件
if modified:
    with open('backend/main.py', 'wb') as f:
        f.write(data)
    print('\n[OK] 文件已修复')
else:
    # 如果没有找到已知模式，尝试清理所有非ASCII字符
    print('[INFO] 未找到已知乱码模式，尝试清理非法字符...')
    
    # 尝试解码并重新编码
    try:
        text = data.decode('utf-8', errors='ignore')
        # 重新编码
        data = text.encode('utf-8')
        with open('backend/main.py', 'wb') as f:
            f.write(data)
        print('[OK] 已清理非法字符')
    except Exception as e:
        print(f'[ERROR] 清理失败: {e}')

print('\n验证文件...')
try:
    with open('backend/main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    print('[OK] 文件可以正常读取')
    
    # 检查语法
    compile(content, 'backend/main.py', 'exec')
    print('[OK] Python 语法正确')
except SyntaxError as e:
    print(f'[ERROR] 语法错误: {e}')
    print(f'  行号: {e.lineno}')
    print(f'  位置: {e.offset}')
except Exception as e:
    print(f'[ERROR] {e}')
