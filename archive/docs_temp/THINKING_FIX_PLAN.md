#!/usr/bin/env python3
"""
修复方案：在后端直接从 LLM 响应中提取 reasoning_content
并生成 thinking 事件
"""

# 问题分析：
# 1. hello-agents 的 arun_stream() 没有正确转发 reasoning_content
# 2. DeepSeek API 返回的 reasoning_content 在 message.content 中
# 3. 我们需要在后端拦截并提取

# 解决方案：
# 1. 在 orchestrator.chat_stream() 中，监听 llm_chunk 事件
# 2. 检查是否包含 reasoning_content
# 3. 如果有，生成 thinking 事件

# 代码位置：backend/agents/orchestrator.py 第 920-950 行

# 修复前的代码：
"""
reasoning_chunk = ""
if event.type.value == "thinking":
    reasoning_chunk = (
        event.data.get("content")
        or event.data.get("reasoning")
        or event.data.get("reasoning_content")
        or ""
    )
"""

# 修复后的代码应该：
"""
# 1. 从任何事件中提取 reasoning_content
reasoning_chunk = event.data.get("reasoning_content") or ""

# 2. 特别处理 llm_chunk 事件
if event.type.value == "llm_chunk":
    # DeepSeek 在 llm_chunk 中可能包含 reasoning_content
    reasoning_chunk = event.data.get("reasoning_content") or ""

# 3. 如果有 reasoning_content，生成 thinking 事件
if reasoning_chunk and isinstance(reasoning_chunk, str) and reasoning_chunk.strip():
    # 生成 thinking 事件
    ...
"""

print("修复方案已准备好")
print("\n关键修改点：")
print("1. 在 orchestrator.chat_stream() 中添加对 reasoning_content 的监听")
print("2. 从 llm_chunk 事件中提取 reasoning_content")
print("3. 生成 thinking 类型的 SSE 事件")
print("\n预期效果：")
print("✓ 前端能接收到 thinking 事件")
print("✓ 前端能显示每步的推理过程")
