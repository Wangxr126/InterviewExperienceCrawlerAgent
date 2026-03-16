<template>
  <div class="rating-flow-demo">
    <div class="demo-container">
      <h2>🎯 防重复点击 + 异步评分流程演示</h2>

      <!-- 消息列表 -->
      <div class="messages-box">
        <div v-if="messages.length === 0" class="empty-state">
          <p>📝 发送消息开始演示</p>
        </div>
        <div v-for="(msg, idx) in messages" :key="idx" class="message" :class="msg.role">
          <div class="msg-content">{{ msg.content }}</div>
          <div class="msg-time">{{ formatTime(msg.timestamp) }}</div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-section">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="输入消息，点击发送..."
          :disabled="isLoading"
        />
        <div class="button-group">
          <el-button
            type="primary"
            :loading="isLoading"
            :disabled="isLoading || !inputText.trim()"
            @click="handleSend"
          >
            {{ isLoading ? '发送中...' : '发送' }}
          </el-button>
          <el-button @click="clearMessages">清空</el-button>
        </div>
      </div>

      <!-- 状态显示 -->
      <div class="status-box">
        <div class="status-item">
          <span class="label">发送状态:</span>
          <span class="value" :class="{ active: isLoading }">
            {{ isLoading ? '🔄 发送中...' : '✅ 就绪' }}
          </span>
        </div>
        <div class="status-item">
          <span class="label">消息数:</span>
          <span class="value">{{ messages.length }}</span>
        </div>
        <div class="status-item">
          <span class="label">最后评分:</span>
          <span class="value">{{ lastRating ? `⭐ ${lastRating}星` : '—' }}</span>
        </div>
      </div>

      <!-- 流程说明 -->
      <div class="flow-explanation">
        <h3>📋 执行流程</h3>
        <ol>
          <li>
            <strong>防重复检查</strong> - useAsyncClick 检查是否已在发送中
            <span class="status" :class="{ done: true }">✓</span>
          </li>
          <li>
            <strong>发送消息</strong> - 异步发送到后端（模拟 2 秒）
            <span class="status" :class="{ done: stepsDone >= 2 }">{{ stepsDone >= 2 ? '✓' : '○' }}</span>
          </li>
          <li>
            <strong>等待回复</strong> - 模拟 AI 回复（模拟 2 秒）
            <span class="status" :class="{ done: stepsDone >= 3 }">{{ stepsDone >= 3 ? '✓' : '○' }}</span>
          </li>
          <li>
            <strong>弹出评分框</strong> - 等待用户评分
            <span class="status" :class="{ done: stepsDone >= 4 }">{{ stepsDone >= 4 ? '✓' : '○' }}</span>
          </li>
          <li>
            <strong>异步提交评分</strong> - 后台提交，不阻塞 UI（模拟 1 秒）
            <span class="status" :class="{ done: stepsDone >= 5 }">{{ stepsDone >= 5 ? '✓' : '○' }}</span>
          </li>
          <li>
            <strong>显示分数卡片</strong> - 最后弹出分数
            <span class="status" :class="{ done: stepsDone >= 6 }">{{ stepsDone >= 6 ? '✓' : '○' }}</span>
          </li>
        </ol>
      </div>

      <!-- 快速测试按钮 -->
      <div class="test-buttons">
        <h3>🧪 快速测试</h3>
        <el-button @click="testQuickClick" :disabled="isLoading">
          快速点击 5 次（测试防重复）
        </el-button>
        <el-button @click="testCancelRating" :disabled="isLoading">
          测试取消评分
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useAsyncClick } from '@/utils/useAsyncClick';
import { handleRatingFlow } from '@/utils/useRatingDialog';

const inputText = ref('');
const messages = ref([]);
const lastRating = ref(0);
const stepsDone = ref(0);

/**
 * 模拟发送消息的核心逻辑
 */
const sendMessage = async () => {
  const text = inputText.value.trim();
  if (!text) return;

  inputText.value = '';
  stepsDone.value = 0;

  // 1️⃣ 添加用户消息
  messages.value.push({
    role: 'user',
    content: text,
    timestamp: new Date().toISOString(),
  });

  // 2️⃣ 模拟发送消息到后端
  stepsDone.value = 1;
  await new Promise((resolve) => setTimeout(resolve, 2000));
  stepsDone.value = 2;

  // 3️⃣ 模拟 AI 回复
  stepsDone.value = 3;
  const aiReply = `这是对 "${text}" 的回复。请评分这个回答的质量。`;
  messages.value.push({
    role: 'assistant',
    content: aiReply,
    timestamp: new Date().toISOString(),
  });
  await new Promise((resolve) => setTimeout(resolve, 2000));
  stepsDone.value = 4;

  // 4️⃣ 弹出评分框，等待用户操作
  try {
    await handleRatingFlow(async (rating, comment) => {
      lastRating.value = rating;
      stepsDone.value = 5;

      // 5️⃣ 异步提交评分（不阻塞 UI）
      await new Promise((resolve) => setTimeout(resolve, 1000));
      console.log(`✅ 评分已提交: ${rating}星, 评论: ${comment}`);
      stepsDone.value = 6;

      // 6️⃣ 显示分数卡片
      messages.value.push({
        role: 'system',
        content: `✨ 你的评分: ⭐ ${rating}星\n💬 评论: ${comment || '(无)'}`,
        timestamp: new Date().toISOString(),
      });
    });
  } catch (err) {
    console.log('用户取消评分:', err.message);
    ElMessage.info('评分已取消');
  }
};

/**
 * 使用 useAsyncClick 包装发送函数
 */
const { execute: handleSend, isLoading } = useAsyncClick(sendMessage, {
  timeout: 120000,
  onError: (error) => {
    ElMessage.error(`发送失败: ${error.message}`);
  },
});

/**
 * 清空消息
 */
const clearMessages = () => {
  messages.value = [];
  lastRating.value = 0;
  stepsDone.value = 0;
};

/**
 * 格式化时间
 */
const formatTime = (timestamp) => {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  return date.toLocaleTimeString('zh-CN');
};

/**
 * 测试：快速点击 5 次
 */
const testQuickClick = async () => {
  inputText.value = '测试消息';
  const clickCount = ref(0);

  for (let i = 0; i < 5; i++) {
    handleSend();
    clickCount.value++;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  ElMessage.success(`点击了 ${clickCount.value} 次，但只发送了 1 条消息！`);
};

/**
 * 测试：取消评分
 */
const testCancelRating = async () => {
  inputText.value = '测试取消评分';
  await handleSend();
};
</script>

<style scoped>
.rating-flow-demo {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.demo-container {
  background: #f9f9f9;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

h2 {
  margin-top: 0;
  color: #333;
  text-align: center;
  font-size: 20px;
}

/* 消息框 */
.messages-box {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  height: 300px;
  overflow-y: auto;
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
  font-size: 16px;
}

.message {
  padding: 12px 16px;
  border-radius: 8px;
  max-width: 80%;
  word-break: break-word;
}

.message.user {
  align-self: flex-end;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-radius: 12px 4px 12px 12px;
}

.message.assistant {
  align-self: flex-start;
  background: #f0f0f0;
  color: #333;
  border-radius: 4px 12px 12px 12px;
}

.message.system {
  align-self: center;
  background: #e8f5e9;
  color: #2e7d32;
  border-radius: 8px;
  max-width: 90%;
  text-align: center;
}

.msg-content {
  font-size: 14px;
  line-height: 1.5;
}

.msg-time {
  font-size: 11px;
  opacity: 0.7;
  margin-top: 4px;
}

/* 输入区 */
.input-section {
  margin-bottom: 20px;
}

.input-section .el-textarea {
  margin-bottom: 12px;
}

.button-group {
  display: flex;
  gap: 10px;
}

.button-group .el-button {
  flex: 1;
}

/* 状态框 */
.status-box {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.status-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.status-item .label {
  font-size: 12px;
  color: #999;
  font-weight: 600;
}

.status-item .value {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.status-item .value.active {
  color: #667eea;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.6;
  }
}

/* 流程说明 */
.flow-explanation {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.flow-explanation h3 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  color: #333;
}

.flow-explanation ol {
  margin: 0;
  padding-left: 20px;
}

.flow-explanation li {
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.6;
  display: flex;
  align-items: center;
  gap: 12px;
}

.flow-explanation strong {
  color: #333;
  min-width: 120px;
}

.status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #f0f0f0;
  color: #999;
  font-size: 12px;
  font-weight: 600;
  margin-left: auto;
}

.status.done {
  background: #e8f5e9;
  color: #2e7d32;
}

/* 测试按钮 */
.test-buttons {
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
}

.test-buttons h3 {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  color: #333;
}

.test-buttons .el-button {
  margin-right: 10px;
  margin-bottom: 10px;
}

/* 响应式 */
@media (max-width: 600px) {
  .status-box {
    grid-template-columns: 1fr;
  }

  .message {
    max-width: 95%;
  }

  .flow-explanation li {
    flex-direction: column;
    align-items: flex-start;
  }

  .status {
    margin-left: 0;
  }
}
</style>
