# useAsyncClick - 防重复点击 + 异步执行

## 📦 功能特性

✅ **防止重复点击** - 异步执行期间自动禁用按钮  
✅ **超时保护** - 可配置超时时间，防止操作卡死  
✅ **错误处理** - 统一的错误捕获和回调  
✅ **Vue 3 Composition API** - 完美支持 `<script setup>`  
✅ **TypeScript 友好** - 完整的类型支持（可选）

---

## 🚀 快速开始

### 1. 基础用法

```vue
<template>
  <button @click="handleSubmit" :disabled="isLoading">
    {{ isLoading ? '提交中...' : '提交' }}
  </button>
</template>

<script setup>
import { useAsyncClick } from '@/utils/useAsyncClick';

const submitData = async () => {
  await fetch('/api/submit', { method: 'POST' });
};

const { execute: handleSubmit, isLoading } = useAsyncClick(submitData);
</script>
```

### 2. 带错误处理

```vue
<script setup>
import { useAsyncClick } from '@/utils/useAsyncClick';
import { ElMessage } from 'element-plus';

const { execute: handleSubmit, isLoading } = useAsyncClick(
  async () => {
    const res = await fetch('/api/submit', { method: 'POST' });
    if (!res.ok) throw new Error('提交失败');
  },
  {
    timeout: 20000, // 20秒超时
    onError: (error) => {
      ElMessage.error(error.message);
    },
  }
);
</script>
```

### 3. 表单提交

```vue
<template>
  <form @submit.prevent="handleSubmit">
    <input v-model="form.name" :disabled="isLoading" />
    <button type="submit" :disabled="isLoading">
      {{ isLoading ? '提交中...' : '提交' }}
    </button>
  </form>
</template>

<script setup>
import { ref } from 'vue';
import { useAsyncClick } from '@/utils/useAsyncClick';

const form = ref({ name: '' });

const { execute: handleSubmit, isLoading } = useAsyncClick(async () => {
  await fetch('/api/submit', {
    method: 'POST',
    body: JSON.stringify(form.value),
  });
});
</script>
```

---

## 📖 API 文档

### useAsyncClick(asyncFn, options)

#### 参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `asyncFn` | `Function` | ✅ | - | 要执行的异步函数 |
| `options` | `Object` | ❌ | `{}` | 配置选项 |
| `options.timeout` | `Number` | ❌ | `30000` | 超时时间（毫秒） |
| `options.onError` | `Function` | ❌ | - | 错误回调函数 |

#### 返回值

| 属性 | 类型 | 说明 |
|------|------|------|
| `execute` | `Function` | 执行函数，调用它来触发异步操作 |
| `isLoading` | `Ref<Boolean>` | 加载状态，`true` 表示正在执行 |

---

## 🎯 使用场景

### 场景 1: 防止表单重复提交

```vue
<script setup>
const { execute: handleSubmit, isLoading } = useAsyncClick(async () => {
  await submitForm();
});
</script>
```

### 场景 2: 防止按钮重复点击

```vue
<script setup>
const { execute: handleDelete, isLoading } = useAsyncClick(async () => {
  await deleteItem(id);
});
</script>
```

### 场景 3: 多个独立按钮

```vue
<script setup>
const { execute: handleAction1, isLoading: loading1 } = useAsyncClick(action1);
const { execute: handleAction2, isLoading: loading2 } = useAsyncClick(action2);
</script>

<template>
  <button @click="handleAction1" :disabled="loading1">操作1</button>
  <button @click="handleAction2" :disabled="loading2">操作2</button>
</template>
```

---

## ⚠️ 注意事项

1. **必须使用 `execute` 函数**  
   不要直接调用 `asyncFn`，而是调用返回的 `execute` 函数

   ```javascript
   // ❌ 错误
   const { isLoading } = useAsyncClick(myAsyncFn);
   myAsyncFn(); // 不会触发防重复逻辑

   // ✅ 正确
   const { execute, isLoading } = useAsyncClick(myAsyncFn);
   execute(); // 会触发防重复逻辑
   ```

2. **`isLoading` 是响应式的**  
   可以直接在模板中使用，无需 `.value`

   ```vue
   <template>
     <!-- ✅ 正确 -->
     <button :disabled="isLoading">提交</button>
   </template>
   ```

3. **超时不会中断异步操作**  
   超时只是改变 `isLoading` 状态，实际的异步操作仍会继续执行

4. **错误会被自动捕获**  
   不需要在 `asyncFn` 中手动 `try-catch`，错误会传递给 `onError`

---

## 🔧 高级用法

### 自定义超时时间

```javascript
const { execute, isLoading } = useAsyncClick(myAsyncFn, {
  timeout: 60000, // 60秒
});
```

### 全局错误处理

```javascript
// utils/useAsyncClick.js
export function useAsyncClick(asyncFn, options = {}) {
  const defaultOptions = {
    timeout: 30000,
    onError: (error) => {
      // 全局错误处理
      console.error('操作失败:', error);
      ElMessage.error(error.message);
    },
  };

  // 合并配置
  const finalOptions = { ...defaultOptions, ...options };
  // ... 其余代码
}
```

---

## 📝 完整示例

查看 `src/components/AsyncClickDemo.vue` 获取完整的可运行示例。

---

## 🤝 对比其他方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| **useAsyncClick** | 可复用、代码整洁、支持超时 | 需要额外文件 |
| 手动 `isLoading` | 简单直接 | 每个按钮都要写一遍 |
| `useRef` 标记 | 无需响应式 | 用户看不到加载状态 |

---

## 📄 License

MIT
