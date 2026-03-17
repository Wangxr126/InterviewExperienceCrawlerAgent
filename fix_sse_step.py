#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复 SSE 推送中的 step 信息"""

with open('backend/agents/interviewer_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复 SSE 推送中的 step 处理
old_sse_fix = '''                sse_line = event.to_sse()
                if event.type.value == "tool_call_finish" and isinstance(sse_line, str):
                    try:
                        lines = sse_line.split('\n')
                        et = next((l[7:] for l in lines if l.startswith('event: ')), '')
                        dl = next((l[6:] for l in lines if l.startswith('data: ')), '')
                        if dl:
                            d = json.loads(dl)
                            if 'step' not in d:
                                d['step'] = stream_stats.get("steps", 1)
                            sse_line = f"event: {et}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass'''

new_sse_fix = '''                sse_line = event.to_sse()
                if event.type.value == "tool_call_finish" and isinstance(sse_line, str):
                    try:
                        lines = sse_line.split('\n')
                        et = next((l[7:] for l in lines if l.startswith('event: ')), '')
                        dl = next((l[6:] for l in lines if l.startswith('data: ')), '')
                        if dl:
                            d = json.loads(dl)
                            # ✅ 优先使用 event.data 中的 step（已在 _execute_tools_async_stream 中设置）
                            # 其次使用 stream_stats 中的步号
                            if 'step' not in d:
                                ev_step = event.data.get('step') or stream_stats.get("steps") or 1
                                d['step'] = int(ev_step)
                            sse_line = f"event: {et}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass'''

if old_sse_fix in content:
    content = content.replace(old_sse_fix, new_sse_fix)
    with open('backend/agents/interviewer_agent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('✅ SSE 推送 step 修复完成！')
else:
    print('❌ 未找到 SSE 推送代码段')
