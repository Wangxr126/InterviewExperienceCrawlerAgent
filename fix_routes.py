#!/usr/bin/env python3
"""删除重复的 get_chat_history 路由"""

with open('backend/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到第二个 @app.get("/api/user/{user_id}/chat/history")
count = 0
second_start = -1
second_end = -1

for i, line in enumerate(lines):
    if '@app.get("/api/user/{user_id}/chat/history")' in line:
        count += 1
        if count == 2:
            second_start = i
            # 找到下一个 @app. 装饰器
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith('@app.'):
                    second_end = j
                    break
            break

if second_start >= 0 and second_end > second_start:
    print(f"找到第二个路由在行 {second_start + 1} 到 {second_end}")
    print(f"删除 {second_end - second_start} 行...")
    
    # 删除这些行
    new_lines = lines[:second_start] + lines[second_end:]
    
    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("✅ 已删除重复的 get_chat_history 函数")
else:
    print(f"❌ 未找到第二个路由 (found {count})")
