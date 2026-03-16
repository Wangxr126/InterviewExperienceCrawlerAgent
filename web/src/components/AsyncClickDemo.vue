<template>
  <div class="async-button-demo">
    <!-- 示例 1: 基础按钮 -->
    <div class="demo-section">
      <h3>示例 1: 基础异步按钮</h3>
      <button 
        @click="handleBasicClick" 
        :disabled="basicLoading"
        class="btn btn-primary"
      >
        {{ basicLoading ? '处理中...' : '点击提交' }}
      </button>
      <p v-if="basicResult" class="result">✅ {{ basicResult }}</p>
    </div>

    <!-- 示例 2: 带错误处理的按钮 -->
    <div class="demo-section">
      <h3>示例 2: 带错误处理</h3>
      <button 
        @click="handleWithError" 
        :disabled="errorLoading"
        class="btn btn-warning"
      >
        {{ errorLoading ? '处理中...' : '可能失败的操作' }}
      </button>
      <p v-if="errorMessage" class="error">❌ {{ errorMessage }}</p>
    </div>

    <!-- 示例 3: 表单提交 -->
    <div class="demo-section">
      <h3>示例 3: 表单提交</h3>
      <form @submit.prevent="handleFormSubmit">
        <input 
          v-model="formData.name" 
          placeholder="输入名字"
          :disabled="formLoading"
        />
        <input 
          v-model="formData.email" 
          placeholder="输入邮箱"
          :disabled="formLoading"
        />
        <button 
          type="submit" 
          :disabled="formLoading"
          class="btn btn-success"
        >
          {{ formLoading ? '提交中...' : '提交表单' }}
        </button>
      </form>
      <p v-if="formResult" class="result">✅ {{ formResult }}</p>
    </div>

    <!-- 示例 4: 多个按钮独立控制 -->
    <div class="demo-section">
      <h3>示例 4: 多个独立按钮</h3>
      <button 
        @click="handleAction1" 
        :disabled="action1Loading"
        class="btn btn-info"
      >
        {{ action1Loading ? '操作1中...' : '操作1' }}
      </button>
      <button 
        @click="handleAction2" 
        :disabled="action2Loading"
        class="btn btn-info"
      >
        {{ action2Loading ? '操作2中...' : '操作2' }}
      </button>
      <p v-if="action1Result" class="result">✅ {{ action1Result }}</p>
      <p v-if="action2Result" class="result">✅ {{ action2Result }}</p>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue';
import { useAsyncClick } from '@/utils/useAsyncClick';

export default {
  name: 'AsyncClickDemo',
  setup() {
    // ========== 示例 1: 基础用法 ==========
    const basicResult = ref('');
    const { execute: handleBasicClick, isLoading: basicLoading } = useAsyncClick(
      async () => {
        await new Promise(resolve => setTimeout(resolve, 2000));
        basicResult.value = '操作成功！';
      }
    );

    // ========== 示例 2: 带错误处理 ==========
    const errorMessage = ref('');
    const { execute: handleWithError, isLoading: errorLoading } = useAsyncClick(
      async () => {
        await new Promise(resolve => setTimeout(resolve, 1500));
        // 模拟随机失败
        if (Math.random() > 0.5) {
          throw new Error('随机错误：操作失败了！');
        }
        errorMessage.value = '';
      },
      {
        timeout: 10000,
        onError: (error) => {
          errorMessage.value = error.message;
        },
      }
    );

    // ========== 示例 3: 表单提交 ==========
    const formData = ref({
      name: '',
      email: '',
    });
    const formResult = ref('');
    const { execute: handleFormSubmit, isLoading: formLoading } = useAsyncClick(
      async () => {
        // 模拟 API 调用
        await new Promise(resolve => setTimeout(resolve, 2000));
        formResult.value = `表单已提交: ${formData.value.name} (${formData.value.email})`;
        // 清空表单
        formData.value = { name: '', email: '' };
      },
      {
        onError: (error) => {
          formResult.value = `错误: ${error.message}`;
        },
      }
    );

    // ========== 示例 4: 多个独立按钮 ==========
    const action1Result = ref('');
    const action2Result = ref('');

    const { execute: handleAction1, isLoading: action1Loading } = useAsyncClick(
      async () => {
        await new Promise(resolve => setTimeout(resolve, 1500));
        action1Result.value = '操作1完成！';
      }
    );

    const { execute: handleAction2, isLoading: action2Loading } = useAsyncClick(
      async () => {
        await new Promise(resolve => setTimeout(resolve, 2500));
        action2Result.value = '操作2完成！';
      }
    );

    return {
      // 示例 1
      basicResult,
      handleBasicClick,
      basicLoading,
      // 示例 2
      errorMessage,
      handleWithError,
      errorLoading,
      // 示例 3
      formData,
      formResult,
      handleFormSubmit,
      formLoading,
      // 示例 4
      action1Result,
      action2Result,
      handleAction1,
      action1Loading,
      handleAction2,
      action2Loading,
    };
  },
};
</script>

<style scoped>
.async-button-demo {
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
}

.demo-section {
  margin-bottom: 30px;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 8px;
  background-color: #f9f9f9;
}

.demo-section h3 {
  margin-top: 0;
  color: #333;
  font-size: 16px;
}

.btn {
  padding: 8px 16px;
  margin-right: 10px;
  margin-bottom: 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s ease;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background-color: #409eff;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background-color: #66b1ff;
}

.btn-warning {
  background-color: #e6a23c;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background-color: #ebb563;
}

.btn-success {
  background-color: #67c23a;
  color: white;
}

.btn-success:hover:not(:disabled) {
  background-color: #85ce61;
}

.btn-info {
  background-color: #909399;
  color: white;
  margin-right: 5px;
}

.btn-info:hover:not(:disabled) {
  background-color: #a6a9ad;
}

input {
  padding: 8px 12px;
  margin-right: 10px;
  margin-bottom: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

input:disabled {
  background-color: #f5f5f5;
  cursor: not-allowed;
}

.result {
  margin-top: 10px;
  color: #67c23a;
  font-size: 14px;
}

.error {
  margin-top: 10px;
  color: #f56c6c;
  font-size: 14px;
}

form {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
</style>
