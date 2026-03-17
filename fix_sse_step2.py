#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复 SSE 推送中的 step 信息 - 简化版"""

with open('backend/agents/interviewer_agent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

modified = False
for i, line in enumerate(lines):
    # 查找目标行
    if "d['step'] = stream_stats.get(\"steps\", 1)" in line:
        print(f'找到目标行在第 {i+1} 行')
        print(f'原内容: {line.strip()}')
        
        # 替换为新代码
        indent = len(line) - len(line.lstrip())
        new_lines = [
            ' ' * indent + "# ✅ 优先使用 event.data 中的 step（已在 _execute_tools_async_stream 中设置）\n",
            ' ' * indent + "# 其次使用 stream_stats 中的步号\n",
            ' ' * indent + "ev_step = event.data.get('step') or stream_stats.get(\"steps\") or 1\n",
            ' ' * indent + "d['step'] = int(ev_step)\n",
        ]
        
        # 替换这一行
        lines[i] = ''.join(new_lines)
        modified = True
        print(f'新内容: {new_lines}')
        break

if modified:
    with open('backend/agents/interviewer_agent.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('✅ SSE 推送 step 修复完成！')
else:
    print('❌ 未找到目标代码')
