import sys, json
sys.path.insert(0, 'e:/Agent/AgentProject/wxr_agent')

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path='e:/Agent/AgentProject/wxr_agent/.env', override=True)

from backend.services.storage.sqlite_service import sqlite_service

# 详查 sess_Wangxr
s = sqlite_service.get_session('sess_Wangxr')
print('session_id:', s.get('session_id'))
print('user_id:', s.get('user_id'))
hist = s.get('conversation_history', [])
print('message count:', len(hist))
print()
for i, m in enumerate(hist):
    role = m.get('role')
    content = str(m.get('content', ''))
    thinking = m.get('thinking', [])
    print(f'[{i}] role={role}')
    print(f'     content ({len(content)} chars): {content[:200]!r}')
    print(f'     thinking_steps: {len(thinking)}')
    print()

# 模拟 get_chat_history 的过滤逻辑
print('=== 模拟 get_chat_history 过滤 ===')
import re

def _extract_user_display_content(content):
    if not content or "[用户消息]" not in content:
        return content or ""
    idx = content.find("[用户消息]")
    after = content[idx + len("[用户消息]"):].lstrip("\n\r")
    return after if after else content

def _strip_internal_markers_for_display(content):
    if not content:
        return content
    return re.sub(r'\u3010q_id:[^\u3011]+\u3011', '', content).replace('  ', ' ').strip()

messages = []
for m in hist:
    if m.get('content'):
        role = m.get('role', 'user')
        content = m.get('content', '')
        if role == 'user':
            content = _extract_user_display_content(content)
            content = _strip_internal_markers_for_display(content)
        print(f'role={role} | filtered_content ({len(content)} chars): {content[:100]!r}')
        if content:  # 只有非空才加入
            messages.append({'role': role, 'content': content})

print(f'\n最终返回消息数: {len(messages)}')
