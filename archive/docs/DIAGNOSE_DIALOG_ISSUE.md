# 去对话练习按钮问题诊断

## 问题现象
点击"💬 去对话练习"按钮后：
1. 弹出了一个不相关的对话框（"你对Agent怎么看..."）
2. 没有跳转到练习对话页面
3. 没有自动填充题目内容

## 可能的原因

### 1. 事件冒泡导致触发了其他对话框
从截图看，弹出的对话框似乎是微调标注页面的预览对话框，可能是：
- 事件冒泡到了父元素
- 有全局的事件监听器拦截了点击
- 对话框的 z-index 层级问题

### 2. 按钮点击事件被其他代码拦截
可能有其他代码监听了按钮点击事件并阻止了默认行为。

## 立即修复方案

### 方案 1：阻止事件冒泡（推荐）

修改 `QuestionDialog.vue` 中的按钮，添加 `.stop` 修饰符：

```vue
<el-button type="info" @click.stop="handleSendToChat">💬 去对话练习</el-button>
```

### 方案 2：检查对话框是否正确关闭

在 `handleSendToChat` 方法中，先关闭当前对话框：

```javascript
const handleSendToChat = () => {
  console.log('🔵 QuestionDialog: 触发 send-to-chat 事件')
  console.log('🔵 question:', props.question)
  
  // 先关闭当前对话框
  visible.value = false
  
  // 延迟触发事件，确保对话框已关闭
  setTimeout(() => {
    emit('send-to-chat', { question: props.question })
  }, 100)
}
```

### 方案 3：检查是否有全局点击监听器

检查 `App.vue` 或其他全局组件是否有 `@click` 监听器。

## 测试步骤

1. 打开浏览器开发者工具（F12）
2. 切换到 Console 标签页
3. 在 Console 中输入以下代码来监听所有点击事件：

```javascript
document.addEventListener('click', (e) => {
  console.log('全局点击事件:', e.target, e.currentTarget)
}, true)
```

4. 然后点击"去对话练习"按钮
5. 查看控制台输出，看看点击事件的传播路径

## 快速诊断命令

在浏览器控制台执行：

```javascript
// 检查是否有多个对话框
console.log('对话框数量:', document.querySelectorAll('.el-dialog').length)

// 检查对话框的 z-index
document.querySelectorAll('.el-dialog').forEach((el, i) => {
  console.log(`对话框 ${i}:`, el.querySelector('.el-dialog__title')?.textContent, 'z-index:', window.getComputedStyle(el).zIndex)
})
```

## 我现在要应用的修复

我将同时应用方案 1 和方案 2，确保：
1. 阻止事件冒泡
2. 先关闭当前对话框再触发事件
3. 添加更详细的调试日志
