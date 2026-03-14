# 对话状态管理与页面切换机制

## 一、对话保存机制

### 1.1 保存时机

**用户消息**：
- ✅ **立即保存**：用户发送消息时立即写入数据库
- 位置：`orchestrator.py` - `chat_stream()` 方法开始时
- 代码：
```python
sqlite_service.ensure_session_exists(session_id, user_id)
self._write_working(user_id, f"用户：{message}", session_id=session_id)
```

**AI 回复**：
- ✅ **流式完成后一次性保存**：不是实时保存，而是等流式响应完全结束后保存
- 位置：`orchestrator.py` - `chat_stream()` 方法的 `finally` 块
- 代码：
```python
finally:
    # 持久化完整内容
    try:
        self.interviewer.save_session(session_id)
        if full_content.strip():
            sqlite_service.patch_last_assistant_content(session_id, full_content)
    except Exception as e:
        logger.warning(f"[chat_stream] save_session 失败: {e}")
```

### 1.2 保存流程

```
用户发送消息
    ↓
立即保存用户消息到 SQLite
    ↓
开始流式响应（前端实时显示）
    ↓
累积 AI 回复内容（full_content += chunk）
    ↓
流式响应完成
    ↓
一次性保存完整 AI 回复到 SQLite
    ↓
前端标记 streaming=false
```

### 1.3 数据库表结构

**sessions 表**：
- `session_id`: 会话 ID
- `user_id`: 用户 ID
- `conversation_history`: JSON 数组，存储完整对话历史
- `created_at`: 创建时间
- `updated_at`: 最后更新时间

**conversation_history 格式**：
```json
[
  {
    "role": "user",
    "content": "用户消息内容",
    "timestamp": "2026-03-13T08:00:00Z"
  },
  {
    "role": "assistant",
    "content": "AI 回复内容",
    "timestamp": "2026-03-13T08:00:05Z",
    "thinking": [
      {"thought": "思考内容", "action": "工具调用", "observation": "观察结果"}
    ]
  }
]
```

---

## 二、页面切换机制

### 2.1 页面激活/失活监听

**前端实现**（`ChatView.vue`）：
```javascript
watch([() => props.isActive, () => props.userId], ([active, uid], [prevActive, prevUid]) => {
  // 页面激活时加载历史
  if (active && uid) {
    loadHistory()
  }
  // 页面失活时中断正在进行的请求（避免后台继续消耗资源）
  if (!active && prevActive && abortCtrl) {
    try {
      abortCtrl.abort()
    } catch (e) {
      // 忽略中断错误
    }
  }
}, { immediate: true })
```

### 2.2 页面切换时的行为

#### 场景1：从练习对话切换到其他页面

**发生的事情**：
1. ✅ `isActive` 变为 `false`
2. ✅ 触发 `abortCtrl.abort()` - 中断正在进行的流式请求
3. ✅ 前端捕获 `AbortError`，静默处理（不显示错误）
4. ✅ 移除未完成的流式消息占位符
5. ⚠️ **后端可能还在处理**：流式响应被中断，但后端可能已经完成部分内容

**代码**：
```javascript
if (err.name === 'AbortError') {
  // 用户中止（页面切换/手动停止）- 静默处理，不显示错误
  console.log('🟡 用户中止请求（页面切换或手动停止）')
  // 移除流式消息占位符
  if (streamingMsg.value) {
    messages.value = messages.value.filter(m => m !== streamingMsg.value)
    streamingMsg.value = null
  }
}
```

#### 场景2：从其他页面切换回练习对话

**发生的事情**：
1. ✅ `isActive` 变为 `true`
2. ✅ 触发 `loadHistory()` - 从后端加载历史对话
3. ✅ 后端返回最近一次会话的完整历史
4. ✅ 前端渲染所有历史消息（包括思考步骤）
5. ✅ 思考步骤默认折叠（`thinkingOpen: false`）

**代码**：
```javascript
const loadHistory = async () => {
  if (!props.userId) return
  try {
    const d = await api.getChatHistory(props.userId)
    if (d.messages?.length) {
      // 历史消息补齐字段：thinking、thinkingOpen、timestamp
      messages.value = d.messages.map(m => ({
        ...m,
        thinking: m.thinking || [],
        thinkingOpen: false,  // 默认折叠
        timestamp: m.timestamp || new Date().toISOString(),
      }))
      if (d.session_id) sessionId.value = d.session_id
      scrollToBottom()
    }
  } catch (e) { 
    console.warn('加载对话历史失败', e) 
  }
}
```

### 2.3 历史加载 API

**后端接口**（`main.py`）：
```python
@app.get("/api/user/{user_id}/chat/history")
def get_chat_history(user_id: str):
    """获取用户最近一次对话历史，用于前端打开时自动加载"""
    session = sqlite_service.get_latest_session_for_user(user_id)
    if not session:
        return {"session_id": None, "messages": []}
    
    history = session.get("conversation_history") or []
    
    # 转为前端格式 [{role, content, timestamp}]
    messages = []
    for m in history:
        if m.get("content"):
            role = m.get("role", "user")
            content = m.get("content", "")
            
            # 用户消息：只展示用户实际输入
            if role == "user":
                content = _extract_user_display_content(content)
            
            messages.append({
                "role": role,
                "content": content,
                "timestamp": m.get("timestamp") or m.get("ts"),
                "thinking": m.get("thinking", [])
            })
    
    return {"session_id": session["session_id"], "messages": messages}
```

---

## 三、问题回答

### Q1: 对话状态是一次 query+answer 保存还是实时保存？

**答案：一次 query+answer 保存（非实时）**

- **用户消息**：发送时立即保存
- **AI 回复**：流式响应**完成后**一次性保存
- **不是实时保存**：在流式输出过程中，AI 回复只在前端显示，不写入数据库
- **保存时机**：`finally` 块中，确保即使出错也会尝试保存

**优点**：
- ✅ 减少数据库写入次数
- ✅ 保证保存的是完整内容
- ✅ 避免保存不完整的流式片段

**缺点**：
- ⚠️ 如果流式响应中断（页面切换、网络断开），AI 回复可能丢失
- ⚠️ 用户刷新页面时，正在进行的对话会丢失

### Q2: 切换到其他页面后，练习对话是否还能正常显示+展开？

**答案：✅ 可以正常显示和展开**

**验证步骤**：
1. ✅ **切换离开**：
   - 流式请求被中断（`AbortError`）
   - 未完成的消息被移除
   - 不显示错误提示

2. ✅ **切换回来**：
   - 自动调用 `loadHistory()`
   - 从后端加载最近一次会话的完整历史
   - 渲染所有消息（包括思考步骤）
   - 思考步骤默认折叠，可以手动展开

3. ✅ **思考步骤展开**：
   - 每条消息的 `thinkingOpen` 状态独立管理
   - 点击"查看推理过程"按钮可以展开/折叠
   - 切换页面后再回来，思考步骤默认折叠（`thinkingOpen: false`）

**代码验证**：
```javascript
// 历史加载时，思考步骤默认折叠
messages.value = d.messages.map(m => ({
  ...m,
  thinking: m.thinking || [],
  thinkingOpen: false,  // ✅ 默认折叠
  timestamp: m.timestamp || new Date().toISOString(),
}))

// 用户可以手动展开
<button class="thinking-toggle" @click="m.thinkingOpen = !m.thinkingOpen">
  <span>{{ m.thinkingOpen ? '收起' : '查看' }}推理过程</span>
</button>
```

---

## 四、潜在问题与改进建议

### 4.1 当前存在的问题

#### 问题1：页面切换时正在进行的对话会丢失

**现象**：
- 用户发送消息后，AI 正在流式回复
- 用户切换到其他页面（如微调标注）
- 流式请求被中断，AI 回复未保存
- 切换回来后，只能看到用户消息，AI 回复丢失

**原因**：
- 流式响应被 `abort()` 中断
- 后端的 `finally` 块可能未执行完成
- 即使执行了，`full_content` 可能不完整

**影响**：
- ⚠️ 用户体验不佳：对话不完整
- ⚠️ 数据丢失：无法恢复中断的对话

#### 问题2：刷新页面时正在进行的对话会丢失

**现象**：
- 用户发送消息后，AI 正在流式回复
- 用户刷新页面（F5 或 Ctrl+R）
- 页面重新加载，流式请求被中断
- 只能看到用户消息，AI 回复丢失

**原因**：
- 页面刷新会中断所有网络请求
- 后端可能还在处理，但前端已经断开连接
- 后端的保存逻辑在 `finally` 块中，可能未执行

#### 问题3：思考步骤在历史加载时默认折叠

**现象**：
- 切换回练习对话页面时，所有思考步骤都是折叠的
- 用户需要手动点击"查看推理过程"才能看到

**影响**：
- ⚠️ 用户体验：需要额外操作
- ⚠️ 信息可见性：思考过程不够直观

### 4.2 改进建议

#### 改进1：实现增量保存机制

**方案**：在流式响应过程中，定期保存部分内容

```python
# orchestrator.py - chat_stream()
async def chat_stream(self, user_id, message, resume, session_id):
    full_content = ""
    last_save_time = time.time()
    SAVE_INTERVAL = 5  # 每 5 秒保存一次
    
    try:
        async for event in self.interviewer.arun_stream(full_input):
            yield event.to_sse()
            
            # 累积内容
            if event.type.value == "llm_chunk":
                chunk = event.data.get("chunk") or ""
                full_content += chunk
                
                # 定期保存
                now = time.time()
                if now - last_save_time > SAVE_INTERVAL:
                    try:
                        sqlite_service.patch_last_assistant_content(
                            session_id, 
                            full_content,
                            is_partial=True  # 标记为部分内容
                        )
                        last_save_time = now
                    except Exception as e:
                        logger.warning(f"增量保存失败: {e}")
    finally:
        # 最终保存完整内容
        if full_content.strip():
            sqlite_service.patch_last_assistant_content(
                session_id, 
                full_content,
                is_partial=False  # 标记为完整内容
            )
```

**优点**：
- ✅ 即使页面切换或刷新，也能保存部分内容
- ✅ 用户可以看到中断前的对话
- ✅ 数据不会完全丢失

**缺点**：
- ⚠️ 增加数据库写入次数
- ⚠️ 需要标记内容是否完整

#### 改进2：记住思考步骤的展开状态

**方案**：使用 localStorage 记住用户的偏好

```javascript
// ChatView.vue
const loadHistory = async () => {
  const d = await api.getChatHistory(props.userId)
  if (d.messages?.length) {
    // 从 localStorage 读取用户偏好
    const thinkingPreference = localStorage.getItem('thinkingOpen')
    const defaultOpen = thinkingPreference === 'true'
    
    messages.value = d.messages.map(m => ({
      ...m,
      thinking: m.thinking || [],
      thinkingOpen: defaultOpen,  // 使用用户偏好
      timestamp: m.timestamp || new Date().toISOString(),
    }))
  }
}

// 用户切换展开状态时，保存偏好
const toggleThinking = (msg) => {
  msg.thinkingOpen = !msg.thinkingOpen
  localStorage.setItem('thinkingOpen', msg.thinkingOpen.toString())
}
```

#### 改进3：添加"恢复中断对话"功能

**方案**：检测未完成的对话，提示用户恢复

```javascript
// ChatView.vue
const loadHistory = async () => {
  const d = await api.getChatHistory(props.userId)
  if (d.messages?.length) {
    messages.value = d.messages.map(m => ({...m}))
    
    // 检测最后一条消息是否为用户消息（说明 AI 回复未完成）
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg.role === 'user') {
      ElMessageBox.confirm(
        '检测到上次对话未完成，是否继续？',
        '提示',
        {
          confirmButtonText: '继续',
          cancelButtonText: '取消',
          type: 'info'
        }
      ).then(() => {
        // 重新发送最后一条用户消息
        inputText.value = lastMsg.content
        send()
      }).catch(() => {
        // 用户选择不继续
      })
    }
  }
}
```

#### 改进4：添加对话保存状态指示器

**方案**：在 UI 上显示保存状态

```vue
<!-- ChatView.vue -->
<div class="save-status">
  <span v-if="saving">💾 保存中...</span>
  <span v-else-if="saved">✅ 已保存</span>
  <span v-else-if="saveError">⚠️ 保存失败</span>
</div>
```

---

## 五、测试验证

### 5.1 功能测试清单

- [ ] **基本对话**
  - [ ] 发送消息，AI 正常回复
  - [ ] 思考步骤正常显示
  - [ ] 流式输出流畅

- [ ] **页面切换**
  - [ ] 切换到其他页面，流式请求被中断
  - [ ] 切换回来，历史对话正常显示
  - [ ] 思考步骤可以展开/折叠

- [ ] **数据持久化**
  - [ ] 对话保存到数据库
  - [ ] 刷新页面后，历史对话仍然存在
  - [ ] 思考步骤数据完整

- [ ] **边界情况**
  - [ ] 流式响应中途切换页面
  - [ ] 流式响应中途刷新页面
  - [ ] 网络中断后恢复
  - [ ] 多个会话切换

### 5.2 性能测试

- [ ] **响应时间**
  - [ ] 首字节时间 < 1s
  - [ ] 流式输出延迟 < 100ms
  - [ ] 历史加载时间 < 500ms

- [ ] **资源占用**
  - [ ] 内存占用正常
  - [ ] CPU 占用合理
  - [ ] 数据库查询优化

---

## 六、总结

### 6.1 当前实现的优点

✅ **流式输出**：真正的 token 级流式，用户体验好  
✅ **思考步骤**：完整记录 AI 推理过程，可追溯  
✅ **数据持久化**：对话保存到 SQLite，支持历史加载  
✅ **页面切换**：自动加载历史，支持多页面切换  
✅ **错误处理**：完善的异常捕获和降级机制  

### 6.2 需要改进的地方

⚠️ **增量保存**：流式响应中断时，部分内容会丢失  
⚠️ **状态指示**：用户不知道对话是否已保存  
⚠️ **恢复机制**：无法恢复中断的对话  
⚠️ **用户偏好**：思考步骤展开状态不记忆  

### 6.3 最佳实践

1. **发送消息后不要立即切换页面**：等待 AI 回复完成
2. **定期检查保存状态**：确保对话已保存
3. **重要对话手动备份**：复制关键内容到其他地方
4. **网络不稳定时谨慎使用**：避免对话丢失

---

**最后更新时间**：2026-03-13  
**文档版本**：v1.0  
**作者**：Claude (Cursor AI Assistant)
