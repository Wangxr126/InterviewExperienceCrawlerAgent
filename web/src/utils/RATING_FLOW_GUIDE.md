# 防重复点击 + 异步评分流程 - 完整指南

## 🎯 核心问题

你遇到的问题是：**评分弹窗还没等用户点击，分数就已经弹出来了**

这是因为代码逻辑是这样的：

```javascript
// ❌ 错误的顺序
const send = async () => {
  await submitAnswer();      // 1. 提交答案
  showScoreModal();          // 2. 立即弹出分数（用户还没评分！）
};
```

---

## ✅ 正确的流程

```
用户点击发送
    ↓
[防重复] 检查是否已在发送中
    ↓
发送消息到后端（异步）
    ↓
等待 AI 回复完成
    ↓
弹出评分框 ⭐⭐⭐⭐⭐
    ↓
等待用户评分 (用户操作)
    ↓
用户点击"提交"
    ↓
异步提交评分到后端（不阻塞 UI）
    ↓
立即返回，显示分数卡片
    ↓
后台继续处理评分数据
```

---

## 📦 使用的工具

### 1. `useAsyncClick` - 防重复点击

```javascript
import { useAsyncClick } from '@/utils/useAsyncClick';

const { execute: handleSend, isLoading } = useAsyncClick(
  async () => {
    // 你的异步操作
    await sendMessage();
  },
  {
    timeout: 30000,  // 30秒超时
    onError: (error) => {
      ElMessage.error(error.message);
    },
  }
);
```

**特点：**
- ✅ 自动防重复点击
- ✅ 异步执行
- ✅ 自动管理 loading 状态
- ✅ 超时保护

### 2. `useRatingDialog` - 评分弹窗

```javascript
import { handleRatingFlow } from '@/utils/useRatingDialog';

// 弹出评分框，等待用户操作
await handleRatingFlow(async (rating, comment) => {
  // 用户评分后的回调（异步执行，不阻塞 UI）
  await submitRatingToBackend(rating, comment);
});
```

**特点：**
- ✅ 弹出评分框
- ✅ 等待用户操作
- ✅ 用户提交后异步处理
- ✅ 不阻塞 UI

---

## 🔄 完整流程示例

### 步骤 1: 定义异步操作

```javascript
// 发送消息的核心逻辑
const sendMessage = async () => {
  const text = inputText.value.trim();
  
  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: text,
    timestamp: new Date().toISOString(),
  });

  // 1️⃣ 发送消息到后端
  const response = await api.chatStream({
    user_id: props.userId,
    message: text,
  });

  // 处理流式响应...
  // (保持原有逻辑)

  // 2️⃣ AI 回复完成后，弹出评分框
  await handleRatingFlow(async (rating, comment) => {
    // 3️⃣ 用户评分后，异步提交（不阻塞 UI）
    await submitRatingToBackend(rating, comment);
  });
};
```

### 步骤 2: 使用 useAsyncClick 包装

```javascript
const { execute: handleSend, isLoading } = useAsyncClick(
  sendMessage,
  {
    timeout: 120000,
    onError: (error) => {
      ElMessage.error(error.message);
    },
  }
);
```

### 步骤 3: 在模板中使用

```vue
<template>
  <el-button 
    type="primary" 
    :loading="isLoading"
    :disabled="isLoading || !inputText.trim()"
    @click="handleSend"
  >
    {{ isLoading ? '发送中...' : '发送' }}
  </el-button>
</template>
```

---

## 🎨 时序图

```
用户                  UI                  后端
  │                   │                    │
  ├─ 点击发送 ────────>│                    │
  │                   │ [防重复检查]        │
  │                   │ [禁用按钮]          │
  │                   │                    │
  │                   ├─ 发送消息 ────────>│
  │                   │                    │ [处理中...]
  │                   │<─ 流式回复 ────────┤
  │                   │ [显示 AI 回复]      │
  │                   │                    │
  │                   │ [AI 回复完成]       │
  │                   │                    │
  │<─ 弹出评分框 ─────┤                    │
  │                   │                    │
  ├─ 选择星星 ───────>│                    │
  │                   │                    │
  ├─ 输入评论 ───────>│                    │
  │                   │                    │
  ├─ 点击提交 ───────>│                    │
  │                   │ [关闭弹窗]          │
  │                   │ [显示分数卡片]      │
  │                   │                    │
  │                   ├─ 异步提交评分 ───>│
  │                   │ (不阻塞 UI)        │ [处理中...]
  │                   │                    │
  │ (用户继续操作)     │                    │
  │                   │                    │<─ 评分已保存
  │                   │                    │
```

---

## 🚨 常见错误

### ❌ 错误 1: 没有等待用户评分

```javascript
// 错误
const send = async () => {
  await submitAnswer();
  showScoreModal();  // 立即弹出，用户还没评分！
};
```

### ✅ 正确做法

```javascript
// 正确
const send = async () => {
  await submitAnswer();
  
  // 等待用户评分
  await handleRatingFlow(async (rating, comment) => {
    // 异步提交评分
    await submitRating(rating, comment);
  });
  
  // 现在才弹出分数
  showScoreModal();
};
```

---

### ❌ 错误 2: 重复点击导致多次提交

```javascript
// 错误
const send = async () => {
  loading.value = true;
  await submitAnswer();
  loading.value = false;
};

// 用户快速点击两次 → 两条消息都被发送！
```

### ✅ 正确做法

```javascript
// 正确
const { execute: handleSend, isLoading } = useAsyncClick(
  async () => {
    await submitAnswer();
  }
);

// useAsyncClick 自动防重复，即使快速点击也只发送一次
```

---

### ❌ 错误 3: 评分提交阻塞 UI

```javascript
// 错误
const send = async () => {
  await submitAnswer();
  
  const { rating, comment } = await getRating();
  
  // 这里会阻塞 UI，用户看不到分数卡片
  await submitRating(rating, comment);
  
  showScoreModal();
};
```

### ✅ 正确做法

```javascript
// 正确
const send = async () => {
  await submitAnswer();
  
  await handleRatingFlow(async (rating, comment) => {
    // 这里是异步的，不阻塞 UI
    // 用户已经看到分数卡片了
    await submitRating(rating, comment);
  });
};
```

---

## 📋 集成清单

- [ ] 复制 `useAsyncClick.js` 到 `src/utils/`
- [ ] 复制 `useRatingDialog.js` 到 `src/utils/`
- [ ] 在 `ChatView.vue` 中导入这两个工具
- [ ] 修改 `send` 函数，使用 `useAsyncClick` 包装
- [ ] 在 AI 回复完成后调用 `handleRatingFlow`
- [ ] 在模板中使用 `isLoading` 禁用按钮
- [ ] 测试：快速点击发送按钮，确保只发送一次
- [ ] 测试：评分框弹出后，分数卡片不会立即显示

---

## 🧪 测试场景

### 场景 1: 正常流程

1. 用户输入消息
2. 点击发送
3. 等待 AI 回复
4. 弹出评分框
5. 用户评分
6. 显示分数卡片

**预期结果：** ✅ 所有步骤按顺序执行

### 场景 2: 快速重复点击

1. 用户快速点击发送按钮 5 次
2. 按钮应该被禁用

**预期结果：** ✅ 只发送一条消息，其他点击被忽略

### 场景 3: 用户取消评分

1. 弹出评分框
2. 用户点击"取消"

**预期结果：** ✅ 分数卡片不显示，但消息已保存

### 场景 4: 网络超时

1. 发送消息
2. 30秒后仍未收到回复

**预期结果：** ✅ 显示超时错误，按钮恢复可用

---

## 📞 API 参考

### useAsyncClick(asyncFn, options)

```javascript
const { execute, isLoading } = useAsyncClick(
  async () => { /* 异步操作 */ },
  {
    timeout: 30000,           // 超时时间（毫秒）
    onError: (error) => {}    // 错误回调
  }
);
```

**返回值：**
- `execute`: 执行函数
- `isLoading`: 加载状态（Ref<boolean>）

### handleRatingFlow(onRatingSubmit)

```javascript
await handleRatingFlow(async (rating, comment) => {
  // rating: 1-5 的整数
  // comment: 用户的评论文本
  await submitRating(rating, comment);
});
```

---

## 💡 最佳实践

1. **始终使用 useAsyncClick** - 防止重复点击
2. **等待用户操作** - 不要假设用户会立即操作
3. **异步处理后台任务** - 不要阻塞 UI
4. **提供清晰的反馈** - 显示 loading 状态
5. **设置合理的超时** - 防止请求卡死

---

## 🎓 总结

| 问题 | 解决方案 |
|------|--------|
| 重复点击 | `useAsyncClick` |
| 评分弹窗提前弹出 | `await handleRatingFlow()` |
| UI 被阻塞 | 异步提交评分 |
| 用户体验差 | 显示 loading 状态 |

**记住：** 异步 ≠ 并发。要等待用户操作，但不要阻塞 UI！
