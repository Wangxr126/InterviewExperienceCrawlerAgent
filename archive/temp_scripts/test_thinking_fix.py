#!/usr/bin/env python3
"""
诊断脚本：验证后端 thinking 事件格式是否正确
"""
import json

# 后端当前发送的格式
backend_thinking_event = {
    "type": "thinking",
    "step": 1,
    "chunk": "这是推理内容"
}

# 前端期望的格式（从 ChatView.vue 代码推断）
# 前端代码：const inner = data.data || data
# 这意味着前端期望：
# 1. data.data.chunk（嵌套格式）
# 2. 或 data.chunk（平铺格式）

print("=" * 60)
print("后端发送的 thinking 事件格式：")
print(json.dumps(backend_thinking_event, indent=2, ensure_ascii=False))

print("\n" + "=" * 60)
print("前端解析逻辑（ChatView.vue）：")
print("""
const inner = data.data || data
const chunk = data.chunk ?? data.content ?? inner?.content ?? inner?.chunk ?? inner?.reasoning_content ?? ''
""")

print("\n" + "=" * 60)
print("问题分析：")
print("✓ 后端发送：{type, step, chunk}")
print("✓ 前端期望：data.chunk 或 data.data.chunk")
print("✓ 当前匹配：YES - 前端会读到 data.chunk")
print("\n但是，让我们检查 SSE 格式...")

# SSE 格式
sse_format = """event: thinking
data: {"type":"thinking","step":1,"chunk":"这是推理内容"}

"""

print("\nSSE 格式：")
print(sse_format)

print("=" * 60)
print("前端接收到的 payload 结构：")
print("""
当前端解析 SSE 时：
1. 提取 event: thinking
2. 提取 data: {...}
3. JSON.parse(data) → payload

所以前端收到的 payload 是：
{
  "type": "thinking",
  "step": 1,
  "chunk": "这是推理内容"
}

前端代码中：
const evType = payload.type  // "thinking"
const data = payload.data || payload  // payload 本身（因为没有 .data 字段）
const chunk = data.chunk ?? ...  // ✓ 能读到 "这是推理内容"
""")

print("\n" + "=" * 60)
print("结论：格式应该是正确的！")
print("问题可能在其他地方...")
print("\n可能的问题：")
print("1. 后端没有发送 thinking 事件？")
print("2. 前端没有正确处理 thinking 事件？")
print("3. SSE 流被中断或缓冲？")
