#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复前端工具 step 分配逻辑"""

with open('web/src/views/ChatView.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 tool_call_finish 处理中，添加对工具 step 字段的处理
old_tool_finish = '''        } else {
          const obs = String(result)
          // 从 pendingToolsMap 按 FIFO 顺序取出最早匹配此工具名的占位条目
          // key 格式为 "toolName__callIndex"，按插入顺序遍历 Map 取第一个匹配的
          let pendingEntry = null
          let pendingKey = null
          for (const [k, v] of pendingToolsMap.entries()) {
            if (k.startsWith(toolName + '__')) {
              pendingEntry = v
              pendingKey = k
              break
            }
          }
          if (pendingKey) pendingToolsMap.delete(pendingKey)

          if (pendingEntry) {
            // 原地更新占位条目（它已经在 pendingStep.tools 里）
            pendingEntry.result = obs
            pendingEntry.observation = obs
            pendingEntry.observationIsJson = isObsJson(obs)
            pendingEntry._pending = false
            if (Object.keys(toolArgs || {}).length && !Object.keys(pendingEntry.args || {}).length) {
              pendingEntry.args = toolArgs
            }'''

new_tool_finish = '''        } else {
          const obs = String(result)
          // ✅ 从 SSE 事件中读取工具的 step 信息（后端已在 _execute_tools_async_stream 中设置）
          const toolStep = data.step ?? null
          
          // 从 pendingToolsMap 按 FIFO 顺序取出最早匹配此工具名的占位条目
          // key 格式为 "toolName__callIndex"，按插入顺序遍历 Map 取第一个匹配的
          let pendingEntry = null
          let pendingKey = null
          for (const [k, v] of pendingToolsMap.entries()) {
            if (k.startsWith(toolName + '__')) {
              pendingEntry = v
              pendingKey = k
              break
            }
          }
          if (pendingKey) pendingToolsMap.delete(pendingKey)

          if (pendingEntry) {
            // 原地更新占位条目（它已经在 pendingStep.tools 里）
            pendingEntry.result = obs
            pendingEntry.observation = obs
            pendingEntry.observationIsJson = isObsJson(obs)
            pendingEntry._pending = false
            // ✅ 记录工具所属的步号，供后续步骤分配使用
            if (toolStep !== null) {
              pendingEntry.step = toolStep
              _lastKnownStepNo = Math.max(_lastKnownStepNo, toolStep)
            }
            if (Object.keys(toolArgs || {}).length && !Object.keys(pendingEntry.args || {}).length) {
              pendingEntry.args = toolArgs
            }'''

if old_tool_finish in content:
    content = content.replace(old_tool_finish, new_tool_finish)
    with open('web/src/views/ChatView.vue', 'w', encoding='utf-8') as f:
        f.write(content)
    print('✅ 前端工具 step 分配逻辑修复完成！')
else:
    print('❌ 未找到目标代码段')
    print('尝试查找关键字符串...')
    if 'pendingToolsMap.entries()' in content:
        print('✓ 找到 pendingToolsMap 处理')
    if 'tool_call_finish' in content:
        print('✓ 找到 tool_call_finish 处理')
