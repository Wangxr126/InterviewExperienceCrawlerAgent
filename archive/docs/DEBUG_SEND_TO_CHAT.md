# "去对话练习"按钮调试指南

## 问题描述
点击题库浏览界面的"去对话练习"按钮时出错。

## 代码检查结果

### ✅ 事件链路完整
1. **QuestionDialog.vue** (第 52 行)
   ```vue
   <el-button type="info" @click="$emit('send-to-chat', { question })">💬 去对话练习</el-button>
   ```

2. **BrowseView.vue** (第 64 行)
   ```vue
   <QuestionDialog v-model="dialogVisible" :question="selectedQ"
                   @send-to-chat="$emit('send-to-chat', $event)" />
   ```

3. **App.vue** (第 30 行)
   ```vue
   <BrowseView v-show="currentView === 'browse'" :meta="meta"
               :is-active="currentView === 'browse'"
               @send-to-chat="onSendToChat" />
   ```

4. **App.vue** (第 72-77 行)
   ```javascript
   const onSendToChat = ({ question }) => {
     currentView.value = 'chat'
     chatViewRef.value?.prefillAndSend(
       `我想练习这道题：${question.question_text.slice(0, 50)}`
     )
   }
   ```

5. **ChatView.vue** (第 127-131 行)
   ```javascript
   const prefillAndSend = (text) => {
     inputText.value = text
     nextTick(() => send())
   }
   defineExpose({ prefillAndSend })
   ```

## 可能的问题原因

### 1. chatViewRef 未正确绑定
**检查点：** App.vue 中 ChatView 组件是否有 `ref="chatViewRef"`

**当前代码：**
```vue
<ChatView v-show="currentView === 'chat'" ref="chatViewRef"
          :user-id="userId" :is-active="currentView === 'chat'" />
```
✅ 已正确绑定

### 2. question 对象缺少 question_text 字段
**检查点：** 从数据库查询的题目是否包含 `question_text` 字段

**可能的错误：**
- `question.question_text` 为 `undefined`
- 导致 `question.question_text.slice(0, 50)` 报错：`Cannot read property 'slice' of undefined`

### 3. ChatView 组件未挂载
**检查点：** 使用 `v-show` 时，组件在首次切换前可能未完全初始化

**当前实现：** App.vue 使用 `v-show` 保持各视图状态
```vue
<ChatView v-show="currentView === 'chat'" ref="chatViewRef" ... />
```

## 调试步骤

### 步骤 1：检查浏览器控制台错误
打开浏览器开发者工具（F12），查看 Console 标签页是否有错误信息。

常见错误：
- `Cannot read property 'slice' of undefined` → question_text 字段缺失
- `Cannot read property 'prefillAndSend' of undefined` → chatViewRef 未正确绑定
- `chatViewRef.value is null` → ChatView 组件未挂载

### 步骤 2：添加调试日志
在 `App.vue` 的 `onSendToChat` 函数中添加日志：

```javascript
const onSendToChat = ({ question }) => {
  console.log('=== onSendToChat 被调用 ===')
  console.log('question:', question)
  console.log('question_text:', question?.question_text)
  console.log('chatViewRef.value:', chatViewRef.value)
  
  currentView.value = 'chat'
  
  if (!chatViewRef.value) {
    console.error('❌ chatViewRef.value 为 null')
    return
  }
  
  if (!question?.question_text) {
    console.error('❌ question.question_text 不存在')
    return
  }
  
  chatViewRef.value.prefillAndSend(
    `我想练习这道题：${question.question_text.slice(0, 50)}`
  )
}
```

### 步骤 3：检查数据库字段
查询题目数据，确认字段名称：

```python
# 在后端执行
from backend.services.sqlite_service import SQLiteService
db = SQLiteService()
questions = db.get_questions(limit=1)
print(questions[0].keys())  # 查看所有字段名
```

可能的字段名变体：
- `question_text` ✅ 正确
- `question` ❌ 错误
- `text` ❌ 错误
- `content` ❌ 错误

## 快速修复方案

### 方案 1：添加安全检查（推荐）
修改 `App.vue` 的 `onSendToChat` 函数：

```javascript
const onSendToChat = ({ question }) => {
  // 安全检查
  if (!question) {
    ElMessage.error('题目数据为空')
    return
  }
  
  if (!question.question_text) {
    ElMessage.error('题目内容缺失')
    console.error('question 对象:', question)
    return
  }
  
  currentView.value = 'chat'
  
  // 等待下一帧，确保 ChatView 已挂载
  nextTick(() => {
    if (!chatViewRef.value) {
      ElMessage.error('对话组件未就绪，请稍后再试')
      return
    }
    
    chatViewRef.value.prefillAndSend(
      `我想练习这道题：${question.question_text.slice(0, 50)}`
    )
  })
}
```

### 方案 2：使用可选链和默认值
```javascript
const onSendToChat = ({ question }) => {
  const text = question?.question_text || '未知题目'
  currentView.value = 'chat'
  nextTick(() => {
    chatViewRef.value?.prefillAndSend(
      `我想练习这道题：${text.slice(0, 50)}`
    )
  })
}
```

## 测试步骤

1. 应用上述修复方案之一
2. 重启前端开发服务器：`npm run dev`
3. 刷新浏览器页面（Ctrl+F5 强制刷新）
4. 打开浏览器控制台（F12）
5. 进入"题库浏览"页面
6. 点击任意题目
7. 在弹窗中点击"💬 去对话练习"按钮
8. 观察控制台输出和页面行为

## 预期结果

✅ **成功：**
- 页面自动切换到"练习对话"标签
- 输入框自动填充题目内容
- 自动发送消息给 AI

❌ **失败：**
- 查看控制台错误信息
- 根据错误信息定位具体问题
- 参考上述调试步骤继续排查

## 需要提供的信息

如果问题仍未解决，请提供：

1. **浏览器控制台的完整错误信息**（截图或文字）
2. **点击按钮时的调试日志输出**
3. **题目数据示例**（一条完整的 question 对象）
4. **前端版本信息**：
   - Node.js 版本：`node -v`
   - npm 版本：`npm -v`
   - Vue 版本：查看 `package.json`

## 相关文件

- `web/src/App.vue` - 主应用组件
- `web/src/views/BrowseView.vue` - 题库浏览页面
- `web/src/views/ChatView.vue` - 对话练习页面
- `web/src/components/QuestionDialog.vue` - 题目详情弹窗
