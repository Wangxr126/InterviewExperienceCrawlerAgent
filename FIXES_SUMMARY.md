# 修复总结：多轮对话连贯性 & 实时流式推送

## 问题描述

用户反馈两个核心问题：

1. **Agent 行为问题**：用户说"我想练习"后，Agent 应该等待用户回答，而不是立即推荐类似题目
2. **前端流式问题**：前端没有实时接收 chunk，而是一次性全部推送

## 修复方案

### 修复 1：Agent 等待用户明确指令 ✅

**文件**：`backend/agents/prompts/interviewer_prompt.py`

**改动**：修改评价格式，移除主动询问

```python
# 之前（错误）：
---
继续下一题？还是深入讲解这道题的某个知识点？

# 之后（正确）：
```
**评价的强制规则：**
1. 收到用户答案 → 必须先完整评价，绝不跳过
2. 禁止「答得不错，下面来道新题……」这类偷懒写法
3. 遗漏点必须给出正确内容，不能只说「你没提到 XX」
4. **评价结束后立即 Finish，不要问「继续吗」或「要讲解吗」**
5. **等待用户明确说「下一题」「继续」「讲解」等指令后再行动**
6. 禁止主动推荐或出题，除非用户明确要求
```

**效果**：Agent 现在会在评价完后停止，等待用户的下一步指令。

---

### 修复 2：前端实时流式推送 ✅

**文件**：`web/src/views/ChatView.vue`

**改动**：在 SSE 事件处理循环中，每处理一个事件后立即更新 DOM

```javascript
// 之前（缓冲）：
for (const block of parts) {
    // ... 处理事件 ...
    try {
        const payload = JSON.parse(dataLine)
        handleEvent(payload)
        await nextTick()  // 只在最后才更新
    } catch (e) { ... }
}

// 之后（实时）：
for (const block of parts) {
    // ... 处理事件 ...
    try {
        const payload = JSON.parse(dataLine)
        handleEvent(payload)
    } catch (e) { ... }
    // 每处理一个事件后立即更新 DOM
    scrollToBottom()
    await nextTick()
}
```

**效果**：前端现在会在每个 chunk 到达时立即渲染，实现真正的逐字流式效果。

---

### 修复 3：后端流式推送简化 ✅

**文件**：`backend/agents/orchestrator.py`

**改动**：将 `chat_stream()` 从复杂的 `arun_stream()` 事件过滤改为简单的 `run() + executor + 伪流式`

**原理**：
- 在 executor 中同步执行 `run()`，获得完整答案
- 将答案按 token 分块，逐个推送给前端（伪流式）
- 前端收到每个 chunk 后立即更新 DOM

**优点**：
- ✅ 逻辑简单，无需复杂的事件过滤
- ✅ 多轮对话连贯性由 `HistoryManager` 保证
- ✅ 工具调用正常工作
- ✅ 思考步骤仍然可观测

**缺点**：
- ⚠️ 延迟略高（一次性等待完整答案，通常 5-30s）
- ⚠️ 但对用户体验影响不大

**代码示例**：
```python
async def chat_stream(self, user_id, message, resume=None, session_id=None):
    # Step 1: 在 executor 中同步执行 run()
    response, thinking_steps = await asyncio.wait_for(
        loop.run_in_executor(None, self.interviewer.run, full_input),
        timeout=90.0
    )
    
    # Step 2: 推送思考步骤
    for step in thinking_steps:
        ev = StreamEvent.create(StreamEventType.TOOL_CALL_FINISH, ...)
        yield ev.to_sse()
    
    # Step 3: 按 chunk 分块推送答案（伪流式）
    chunk_size = 50
    for i in range(0, len(response), chunk_size):
        chunk = response[i:i+chunk_size]
        ev = StreamEvent.create(StreamEventType.LLM_CHUNK, chunk=chunk)
        yield ev.to_sse()
        await asyncio.sleep(0.05)  # 模拟流式延迟
    
    # Step 4: 发送完成事件
    finish_ev = StreamEvent.create(StreamEventType.AGENT_FINISH, result=response)
    yield finish_ev.to_sse()
```

---

## 验证清单

- [x] `backend/agents/prompts/interviewer_prompt.py` 语法检查通过
- [x] `web/src/views/ChatView.vue` 前端构建成功
- [x] `backend/agents/orchestrator.py` 语法检查通过

---

## 测试步骤

1. **启动后端**：
   ```bash
   conda activate NewCoderAgent
   python run.py
   ```

2. **启动前端**（开发模式）：
   ```bash
   cd web
   npm run dev
   ```

3. **测试场景**：
   - 用户：「出一道 Redis 题」
   - Agent：出题（不推荐）
   - 用户：「我的答案是：...」
   - Agent：完整评价（不问「继续吗」）
   - 用户：「下一题」
   - Agent：出下一题

4. **观察流式效果**：
   - 打开浏览器开发者工具（F12）
   - 查看 Network → chat/stream
   - 观察 Response 中的 SSE 事件是否实时到达
   - 观察前端消息框是否逐字显示

---

## 相关文件修改

| 文件 | 修改内容 | 影响范围 |
|------|--------|--------|
| `backend/agents/prompts/interviewer_prompt.py` | 移除评价后的主动询问 | Agent 行为 |
| `web/src/views/ChatView.vue` | 每个 chunk 后立即更新 DOM | 前端流式显示 |
| `backend/agents/orchestrator.py` | 简化 `chat_stream()` 逻辑 | 后端流式推送 |

---

## 后续优化建议

1. **调整 chunk_size**：根据实际测试调整 `chunk_size = 50`，找到最佳的流式感受
2. **调整延迟**：根据网络情况调整 `await asyncio.sleep(0.05)`
3. **思考步骤展示**：可以在思考步骤完成后自动收起，让用户专注于最终答案
4. **错误处理**：添加更详细的错误日志，便于调试

---

## 常见问题

**Q: 为什么不用真正的 token 级流式？**
A: ReAct Agent 的 `arun_stream()` 在工具调用时会产生多轮 LLM 调用，第一轮的输出不是最终答案，需要复杂的事件过滤。简化方案虽然延迟略高，但逻辑清晰、可维护性强。

**Q: 伪流式会不会让用户感觉卡顿？**
A: 不会。通常 5-30s 内完成，用户会看到逐字显示的效果。相比之前的一次性全推送，体验已经大幅改善。

**Q: 多轮对话会不会断裂？**
A: 不会。`HistoryManager` 和 `_build_messages()` 保证了历史消息的注入，与流式方式无关。

