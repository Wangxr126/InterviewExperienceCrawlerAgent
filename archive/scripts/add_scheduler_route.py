#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""添加 scheduler API 路由到 main.py"""

with open('backend/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 查找插入位置（在 orchestrator = get_orchestrator() 之前）
insert_index = None
for i, line in enumerate(lines):
    if 'orchestrator = get_orchestrator()' in line:
        insert_index = i
        break

if insert_index is None:
    print('[ERROR] 未找到插入位置')
    exit(1)

# 检查是否已经添加
already_added = False
for line in lines[max(0, insert_index-5):insert_index]:
    if 'scheduler_api' in line or 'scheduler_router' in line:
        already_added = True
        break

if already_added:
    print('[INFO] 路由已经添加，无需重复添加')
else:
    # 插入新代码
    new_lines = [
        '\n',
        '# 添加调度器管理 API 路由\n',
        'from backend.api.scheduler_api import router as scheduler_router\n',
        'app.include_router(scheduler_router)\n',
        '\n'
    ]
    
    lines = lines[:insert_index] + new_lines + lines[insert_index:]
    
    # 写回文件
    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print('[OK] 已添加 scheduler API 路由')

# 验证
print('\n验证导入...')
try:
    import backend.main
    print('[OK] 导入成功')
except Exception as e:
    print(f'[ERROR] 导入失败: {e}')
