#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""添加 preview-log API 端点"""

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 export 函数的位置
import re
pattern = r'(@app\.post\("/api/finetune/export"\).*?return _ft\.export_labeled\(\))'
match = re.search(pattern, content, re.DOTALL)

if match:
    # 在 export 函数后添加新端点
    new_endpoint = '''


@app.post("/api/finetune/preview-log")
async def finetune_preview_log(body: dict):
    """
    预览日志文件前N条记录
    body: {log_path, limit}
    """
    log_path = body.get("log_path", "")
    limit = body.get("limit", 10)
    if not log_path:
        raise HTTPException(status_code=400, detail="log_path 不能为空")
    return _ft.preview_log_file(log_path, limit)'''
    
    # 在匹配位置后插入
    insert_pos = match.end()
    new_content = content[:insert_pos] + new_endpoint + content[insert_pos:]
    
    with open('backend/main.py', 'w', encoding='utf-8', newline='\n') as f:
        f.write(new_content)
    
    print('API endpoint added successfully')
else:
    print('Pattern not found')
