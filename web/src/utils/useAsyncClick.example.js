/**
 * useAsyncClick 使用示例
 */

// ============ 示例 1: 基础用法 ============
import { useAsyncClick } from '@/utils/useAsyncClick';

export default {
  setup() {
    // 定义异步操作
    const submitForm = async () => {
      const response = await fetch('/api/submit', {
        method: 'POST',
        body: JSON.stringify({ /* 数据 */ }),
      });
      return response.json();
    };

    // 使用 Composable
    const { execute, isLoading } = useAsyncClick(submitForm);

    return {
      handleSubmit: execute,
      isLoading,
    };
  },
};

// 模板中使用
// <button @click="handleSubmit" :disabled="isLoading">
//   {{ isLoading ? '提交中...' : '提交' }}
// </button>


// ============ 示例 2: 带错误处理 ============
const { execute, isLoading } = useAsyncClick(
  async () => {
    await someAsyncOperation();
  },
  {
    timeout: 20000, // 20秒超时
    onError: (error) => {
      console.error('操作失败:', error.message);
      // 可以在这里显示错误提示
      ElMessage.error(error.message);
    },
  }
);


// ============ 示例 3: 在 Vue 组件中的完整示例 ============
import { ref } from 'vue';
import { useAsyncClick } from '@/utils/useAsyncClick';
import { ElMessage } from 'element-plus';

export default {
  name: 'MyComponent',
  setup() {
    const formData = ref({
      name: '',
      email: '',
    });

    // 定义异步提交函数
    const submitData = async () => {
      // 这里是你的异步操作
      const response = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData.value),
      });

      if (!response.ok) {
        throw new Error('提交失败');
      }

      return response.json();
    };

    // 使用 useAsyncClick
    const { execute: handleSubmit, isLoading } = useAsyncClick(submitData, {
      timeout: 30000,
      onError: (error) => {
        ElMessage.error(`操作失败: ${error.message}`);
      },
    });

    return {
      formData,
      handleSubmit,
      isLoading,
    };
  },
};

// 模板
// <template>
//   <form @submit.prevent="handleSubmit">
//     <input v-model="formData.name" placeholder="名字" />
//     <input v-model="formData.email" placeholder="邮箱" />
//     <button :disabled="isLoading" type="submit">
//       {{ isLoading ? '提交中...' : '提交' }}
//     </button>
//   </form>
// </template>


// ============ 示例 4: 在 Composition API 中使用 ============
import { defineComponent, ref } from 'vue';
import { useAsyncClick } from '@/utils/useAsyncClick';

export default defineComponent({
  setup() {
    const count = ref(0);

    const { execute: handleClick, isLoading } = useAsyncClick(async () => {
      // 模拟异步操作
      await new Promise(resolve => setTimeout(resolve, 2000));
      count.value++;
    });

    return {
      count,
      handleClick,
      isLoading,
    };
  },
});

// 模板
// <template>
//   <div>
//     <p>点击次数: {{ count }}</p>
//     <button @click="handleClick" :disabled="isLoading">
//       {{ isLoading ? '处理中...' : '点击我' }}
//     </button>
//   </div>
// </template>
