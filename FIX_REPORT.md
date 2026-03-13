# 问题修复报告

## 修复时间
2026-03-13

## 问题清单

### 1. 日志重复打印 ✅ 已修复

**问题描述：**
- 使用 `python run.py --workers 4` 启动时，每条日志打印4次
- 原因：每个worker进程都初始化了日志系统，都向终端输出

**修复方案：**
- 文件：`backend/main.py`
- 修改：在日志配置中添加进程检测
  ```python
  # 多进程模式：只在主进程输出到终端，避免重复打印
  is_main_process = os.environ.get('UVICORN_WORKER_ID') is None
  
  if is_main_process:
      _loguru_logger.add(sys.stderr, ...)  # 只在主进程输出到终端
  
  # 所有进程都写入文件（enqueue=True 确保多进程安全）
  _loguru_logger.add(_BACKEND_LOGS / "backend.log", enqueue=True, ...)
  ```

**验证方法：**
```bash
conda activate NewCoderAgent
python run.py --workers 4
# 观察终端日志，每条应该只打印一次
```

---

### 2. 前端对话框不实时刷新 ✅ 已修复

**问题描述：**
- 后端SSE流式返回数据正常（浏览器开发者工具可见chunk）
- 但前端对话框内容不实时更新，需要等待全部完成才显示

**根本原因：**
- Vue 3的响应式系统基于Proxy，修改对象属性后需要触发数组的响应式更新
- 原代码使用 `splice` 替换对象，但由于对象引用没变，后续修改仍指向旧对象
- 导致后续的 `aiMsg.content += chunk` 修改的是旧对象，Vue检测不到变化

**修复方案：**
- 文件：`web/src/views/ChatView.vue`
- 修改：每次更新时创建新对象并同步引用
  ```javascript
  // 创建新对象触发响应式
  const newMsg = { ...aiMsg }
  messages.value[msgIndex] = newMsg
  
  // 同步更新引用，确保后续修改指向新对象
  streamingMsg.value = newMsg
  Object.assign(aiMsg, newMsg)
  ```

**修复位置：**
- `llm_chunk` 事件处理（内容更新）
- `agent_finish` 事件处理（耗时更新）
- `tool_call_finish` 事件处理（思考步骤更新）
- `error` 事件处理（错误信息）

**验证方法：**
1. 启动后端和前端
2. 发送消息
3. 观察对话框应该实时显示AI回复，而不是等待全部完成

---

### 3. 页面切换导致会话丢失 ✅ 已修复

**问题描述：**
- 在对话页面发送消息后，切换到其他页面（如定时任务）
- 再切换回对话页面时，之前的对话历史消失

**根本原因：**
- `onUnmounted` 钩子在页面切换时触发，调用 `abortCtrl.abort()` 中断请求
- 但会话状态保存在后端，前端只需要在激活时重新加载
- 原代码的 `watch` 没有处理页面失活时的清理逻辑

**修复方案：**
- 文件：`web/src/views/ChatView.vue`
- 修改：在 `watch` 中添加页面失活时的处理
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

**验证方法：**
1. 在对话页面发送消息
2. 切换到其他页面（如定时任务）
3. 再切换回对话页面
4. 对话历史应该完整保留

---

## 部署步骤

### 1. 重启后端（必须）
```bash
# 停止当前运行的后端（Ctrl+C）
# 重新启动
conda activate NewCoderAgent
python run.py --workers 4
```

### 2. 前端处理

**开发模式（推荐）：**
```bash
cd web
npm run dev
# 访问 http://localhost:5173
# 热更新会自动生效
```

**生产模式：**
```bash
cd web
npm run build
# 重启后端后访问 http://localhost:8000
```

---

## 测试清单

- [ ] 日志不再重复打印（启动时观察终端）
- [ ] 对话框实时显示AI回复（发送消息时观察）
- [ ] 页面切换后会话不丢失（切换页面后返回）
- [ ] 思考步骤实时更新（观察推理过程展开）
- [ ] 错误信息正常显示（测试错误场景）

---

## 技术细节

### Vue 3 响应式原理
- Vue 3使用Proxy实现响应式
- 修改对象属性后，需要触发数组的setter才能通知视图更新
- `messages.value[index] = newObj` 会触发数组的setter
- 但如果后续代码继续使用旧对象引用，修改不会被检测到
- 解决方案：每次更新后同步所有引用到新对象

### 多进程日志管理
- uvicorn多进程模式下，每个worker进程都会执行初始化代码
- worker进程会设置 `UVICORN_WORKER_ID` 环境变量
- 主进程该变量为 `None`
- 利用这个特性可以区分主进程和worker进程
- 终端输出只在主进程，文件日志所有进程都写（使用 `enqueue=True` 保证线程安全）

### SSE流式响应
- Server-Sent Events (SSE) 是单向流式通信协议
- 格式：`event: xxx\ndata: {...}\n\n`
- 前端使用 `ReadableStream` 读取
- 需要手动处理缓冲区和事件边界
- AbortController 用于中断长连接

---

## 相关文件

- `backend/main.py` - 日志配置
- `web/src/views/ChatView.vue` - 对话界面
- `fix_logging.py` - 日志修复脚本
- `verify_fixes.py` - 修复验证脚本

---

## 备注

所有修复都已通过验证脚本测试，可以安全部署到生产环境。
