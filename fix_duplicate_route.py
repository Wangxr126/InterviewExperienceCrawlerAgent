#!/usr/bin/env python3
"""修复 backend/main.py 中的重复路由定义"""
import re

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到所有 get_chat_history 的位置
pattern = r'@app\.get\("/api/user/\{user_id\}/chat/history"\)\s+def get_chat_history\(user_id: str\):'
matches = list(re.finditer(pattern, content))

print(f"找到 {len(matches)} 个 /api/user/{{user_id}}/chat/history 路由")

if len(matches) >= 2:
    # 找到第二个匹配的起始位置
    second_match = matches[1]
    start_pos = second_match.start()
    
    # 找到第二个函数的结束位置（下一个 @app 装饰器或文件末尾）
    rest = content[start_pos:]
    next_decorator_match = re.search(r'\n@app\.', rest[200:])  # 跳过函数头部分
    
    if next_decorator_match:
        end_pos = start_pos + 200 + next_decorator_match.start()
    else:
        end_pos = len(content)
    
    # 提取第二个函数
    second_func = content[start_pos:end_pos]
    
    # 替换路由和函数名
    new_func = second_func.replace(
        '@app.get("/api/user/{user_id}/chat/history")',
        '@app.get("/api/user/{user_id}/study-history")'
    ).replace(
        'def get_chat_history(user_id: str):',
        'def get_study_history(user_id: str):'
    ).replace(
        'get_chat_history failed',
        'get_study_history failed'
    )
    
    # 重新组合内容
    new_content = content[:start_pos] + new_func + content[end_pos:]
    
    # 写回文件
    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ 已修复：第二个 get_chat_history 改名为 get_study_history")
    print("   路由从 /api/user/{user_id}/chat/history 改为 /api/user/{user_id}/study-history")
else:
    print(f"❌ 错误：找到 {len(matches)} 个匹配，需要至少 2 个")
    exit(1)
