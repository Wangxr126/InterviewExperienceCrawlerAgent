# 修复日志：流式输出 + 评分提前问题

## 问题 1：前端没有流式输出

**现象**：整个答案一次性显示，没有逐字流式效果

**根本原因**：后端使用 `StreamEvent.to_sse()` 返回的格式可能不符合前端期望的 SSE 标准格式

**修复方案**：
- **文件**：`backend/agents/orchestrator.py` 第 700-730 行
- **改动**：直接生成标准 SSE 格式 `data: {...}\n\n`，而不依赖 `StreamEvent.to_sse()`

**修改前**：
```python
from hello_agents.core.streaming import StreamEvent, StreamEventType
ev = StreamEvent.create(StreamEventType.LLM_CHUNK, ...)
yield ev.to_sse()
```

**修改后**：
```python
payload = {
    "type": "llm_chunk",
    "data": {"chunk": chunk}
}
yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
```

**效果**：
- ✅ 前端能正确解析 SSE 事件
- ✅ 答案逐字流式显示
- ✅ 思考步骤、完成事件也能正确推送

---

## 问题 2：评分提前了（还没回答就给分）

**现象**：用户说「我想练习这道题：...」，AI 直接给出了评分 2/10，而不是先出题

**根本原因**：AI 误解了用户意图
- 用户说「我想练习这道题」 = **请求出题**
- AI 错误地理解为 = **用户在回答题目**

**修复方案**：
- **文件**：`backend/agents/prompts/interviewer_prompt.py`
- **改动**：在 prompt 中明确区分「请求出题」vs「提交答案」

**修改前**：
```
重要区分：
- 「换个问法考我」「换一道」→ 是请求，不是答案！
- 「我的答案是：xxx」「直接作答内容」→ 才是答案，需要评价
```

**修改后**：
```
重要区分（必须严格执行）：
- 「我想练习这道题：xxx」「来道关于 xxx 的题」→ 是请求出题，不是答案！应走 C2
- 「换个问法考我」「换一道」→ 是请求，不是答案！应走 C
- 「我的答案是：xxx」「直接作答内容」「HTTP 404 表示...」→ 才是答案，需要评价
- 「这道题的答案是...」「我认为...」「根据我的理解...」→ 这些也是答案，需要评价

禁止：看到「我想练习」就直接评分，必须先出题，等用户真正回答后再评价
```

**效果**：
- ✅ AI 正确识别「我想练习这道题」为出题请求
- ✅ 先出题，等用户回答后再评价
- ✅ 避免误判

---

## 验证步骤

1. **重启后端**：
   ```powershell
   conda activate NewCoderAgent
   python run.py
   ```

2. **测试流式输出**：
   - 发送消息：「出一道 Redis 面试题」
   - 观察：答案应该逐字显示，而不是一次性出现

3. **测试评分时机**：
   - 发送消息：「我想练习这道题：Redis 和 Memcached 的区别」
   - 观察：AI 应该先出题，而不是直接评分
   - 然后回答题目，观察 AI 是否正确评价

---

## 相关文件

- `backend/agents/orchestrator.py` - SSE 格式修复
- `backend/agents/prompts/interviewer_prompt.py` - 意图识别修复
- `web/src/views/ChatView.vue` - 前端 SSE 解析（无需修改）

