# 会话持久化修复总结

## 问题描述

用户反馈：点击其他页面再返回当前页面后，正在执行的最新对话消失了。

## 根本原因

1. **前端问题**：页面切换时 `loadHistory()` 会重新从后端加载历史，但正在流式输出的消息还没保存到后端，导致被清空
2. **后端问题**：hello_agents 的 `arun_stream()` 只在流式**完成后**才调用 `add_message` 并触发自动保存，如果流式被中断（页面切换），消息根本没有被添加到历史中

## 解决方案（双重保障）

### 方案A：前端保留流式消息（立即生效）

**文件**：`web/src/views/ChatView.vue`

**修改**：在 `loadHistory()` 中保留正在流式输出的消息

```javascript
const loadHistory = async () => {
  // ...
  // 🔧 保留正在流式输出的消息，避免被 loadHistory 清空
  const streamingMessages = messages.value.filter(m => m.streaming)
  
  if (d.messages?.length) {
    messages.value = d.messages.map(m => ({...}))
    
    // 将流式消息追加回来（保持在最后）
    if (streamingMessages.length > 0) {
      messages.value.push(...streamingMessages)
    }
  }
}
```

**效果**：用户切换页面再回来，正在输出的消息仍然保留在界面上

### 方案B：后端流式过程中定期保存（真正的断电续传）

**文件**：`backend/agents/orchestrator.py`

**修改**：在 `chat_stream()` 方法中增加三个保存点

1. **流式开始前**：先保存用户消息
```python
# 流式开始前先保存用户消息（确保至少用户问题被保存）
from hello_agents.core.message import Message
self.interviewer.add_message(Message(full_input, "user"))
self.interviewer.save_session(session_id)
```

2. **流式过程中**：每 50 个 chunk 或每 5 秒保存一次
```python
if chunk_count % 50 == 0 or (current_time - last_save_time) >= 5:
    sqlite_service.patch_last_assistant_content(session_id, full_content)
```

3. **流式完成后**：最终保存完整内容（原有逻辑）

**效果**：
- 即使页面切换、浏览器崩溃、进程重启，用户的问题和 AI 的部分回复都已保存
- 刷新页面后能看到之前的对话历史（包括被中断的部分）

## hello_agents 的断电续传能力

hello_agents 框架提供的会话持久化功能：

- **核心能力**：将完整会话序列化保存（消息历史、工具调用结果、元数据）
- **自动保存**：每 N 条消息触发一次（项目配置为 `auto_save_interval=2`）
- **原子写入**：保证不会产生损坏文件
- **一致性检查**：恢复时检查 LLM 模型、工具 Schema 是否变化

**项目配置**（`backend/agents/interviewer_agent.py`）：
```python
auto_save_enabled=True,
auto_save_interval=2,  # 每2条消息保存一次
```

**但是**：自动保存依赖 `add_message()` 被调用，而 `arun_stream()` 只在流式完成时才调用 `add_message`，所以流式被中断时自动保存不会触发。

## 测试方法

1. 启动后端：`python run.py`
2. 启动前端：`cd web && npm run dev`
3. 发送一条消息，等待 AI 开始回复
4. **在 AI 回复过程中**切换到其他页面（如"题库浏览"）
5. 等待 3-5 秒后切回"练习对话"页面
6. **预期结果**：
   - 正在输出的消息仍然显示（方案A）
   - 刷新浏览器后，能看到之前的对话历史（方案B）

## 技术细节

- **前端修复**：纯 UI 层面，不依赖后端，立即生效
- **后端修复**：利用 `sqlite_service.patch_last_assistant_content()` 在流式过程中更新数据库
- **两者结合**：前端保证用户体验（消息不消失），后端保证数据持久化（刷新后能恢复）
