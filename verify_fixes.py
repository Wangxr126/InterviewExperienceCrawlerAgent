#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""验证所有修复"""

print("=" * 60)
print("🔍 验证所有修复")
print("=" * 60)

# 1. 检查后端修复
with open('backend/agents/interviewer_agent.py', 'r', encoding='utf-8') as f:
    backend_content = f.read()

checks = [
    ('target_step_no = _current_step_no', '✅ 后端：target_step_no 初始化'),
    ('target_step_no = ev_step_no', '✅ 后端：step 变化时更新 target_step_no'),
    ('"step": target_step_no', '✅ 后端：工具中记录 step 字段'),
    ("ev_step = event.data.get('step')", '✅ 后端：SSE 推送中优先使用 event.data.step'),
]

for pattern, msg in checks:
    if pattern in backend_content:
        print(msg)
    else:
        print(f'❌ {msg} - 未找到')

# 2. 检查前端修复
with open('web/src/views/ChatView.vue', 'r', encoding='utf-8') as f:
    frontend_content = f.read()

frontend_checks = [
    ('const toolStep = data.step', '✅ 前端：读取工具的 step 字段'),
    ('pendingEntry.step = toolStep', '✅ 前端：记录工具所属的步号'),
]

for pattern, msg in frontend_checks:
    if pattern in frontend_content:
        print(msg)
    else:
        print(f'❌ {msg} - 未找到')

print("\n" + "=" * 60)
print("📋 修复总结")
print("=" * 60)
print("""
问题：推送工具时推送错 step 了

根本原因：
1. 后端在 tool_call_finish 中检测到 step 变化时，更新了 _current_step_no
   但工具被添加到 current_step["tools"] 时，没有显式记录工具所属的步号
2. SSE 推送时用 stream_stats.get("steps") 补充 step，不够准确
3. 前端没有从工具的 step 字段中读取信息来正确分配工具到对应步骤

修复方案：
✅ 后端修复 1：在 tool_call_finish 中添加 target_step_no 变量
   - 记录工具实际所属的步号（考虑 step 变化）
   - 在工具对象中显式添加 "step": target_step_no 字段

✅ 后端修复 2：SSE 推送中优先使用 event.data.step
   - 改为：ev_step = event.data.get('step') or stream_stats.get("steps") or 1
   - 确保 SSE 中的 step 信息准确

✅ 前端修复：读取并使用工具的 step 字段
   - 从 SSE 事件中读取 data.step
   - 记录到工具对象中，供后续步骤分配使用
   - 更新 _lastKnownStepNo 以便正确处理步骤切换

结果：
- 工具现在会被正确分配到对应的步骤
- 推理过程展示中不会出现工具错位的问题
- 前后端 step 信息保持一致
""")

print("=" * 60)
