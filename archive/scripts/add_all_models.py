#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""添加所有缺失的请求模型定义（已归档，一次性脚本）"""

with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 定义所有模型
models_code = '''
# ══════════════════════════════════════════════════════
# 请求模型定义
# ══════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    """自由对话请求"""
    user_id: str
    message: str
    resume: Optional[str] = None
    session_id: Optional[str] = None


class SubmitAnswerRequest(BaseModel):
    """答题提交请求"""
    user_id: str
    session_id: Optional[str] = None
    question_id: Optional[str] = None
    question_text: Optional[str] = None
    user_answer: str


class EndSessionRequest(BaseModel):
    """结束会话请求"""
    user_id: str
    session_id: str


class IngestRequest(BaseModel):
    """内容采集请求"""
    url: str
    user_id: Optional[str] = None
    source_platform: Optional[str] = None


class CrawlTriggerRequest(BaseModel):
    """爬虫触发请求"""
    platform: str = "nowcoder"
    keywords: Optional[list] = None
    max_pages: int = 2
    max_notes: int = 10
    headless: bool = True
    process: bool = True

'''

# 查找插入位置（在 app = FastAPI(...) 之后）
insert_marker = 'version="3.0"\n)'
if insert_marker in content:
    insert_pos = content.find(insert_marker) + len(insert_marker)
    # 找到下一个换行
    insert_pos = content.find('\n', insert_pos) + 1
    
    # 删除旧的模型定义（如果存在）
    lines = content.split('\n')
    new_lines = []
    skip = False
    for line in lines:
        if '# 请求模型定义' in line:
            skip = True
        elif skip and ('class ' in line and 'Request' in line):
            # 跳过整个类定义
            continue
        elif skip and line and not line.startswith(' ') and not line.startswith('\t'):
            skip = False
        
        if not skip:
            new_lines.append(line)
    
    content = '\n'.join(new_lines)
    
    # 重新找到插入位置
    insert_marker = 'version="3.0"\n)'
    insert_pos = content.find(insert_marker) + len(insert_marker)
    insert_pos = content.find('\n', insert_pos) + 1
    
    # 插入模型定义
    content = content[:insert_pos] + models_code + content[insert_pos:]
    
    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('✅ 已添加所有缺失的请求模型定义')
else:
    print('❌ 找不到插入位置')
