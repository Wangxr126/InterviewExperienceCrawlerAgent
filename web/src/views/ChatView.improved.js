/**
 * ChatView.vue 中的改进方案
 * 
 * 核心改变：
 * 1. 使用 useAsyncClick 防止重复点击
 * 2. 消息发送完成后，弹出评分框
 * 3. 用户评分后，异步提交评分（不阻塞 UI）
 * 4. 最后才弹出分数卡片
 */

// ========== 在 <script setup> 中添加 ==========

import { useAsyncClick } from '@/utils/useAsyncClick';
import { handleRatingFlow } from '@/utils/useRatingDialog';
import { ElMessage } from 'element-plus';

// ... 其他导入 ...

// ========== 改进的发送函数 ==========

/**
 * 异步提交评分到后端
 */
const submitRatingToBackend = async (rating, comment) => {
  try {
    const response = await api.submitRating({
      user_id: props.userId,
      session_id: sessionId.value,
      rating,
      comment,
    });
    console.log('✅ 评分已提交:', response);
    ElMessage.success('感谢你的评分！');
  } catch (error) {
    console.error('❌ 评分提交失败:', error);
    ElMessage.error('评分提交失败，请重试');
  }
};

/**
 * 核心发送逻辑（异步）
 */
const sendMessage = async () => {
  const text = inputText.value.trim();

  if (!text) return;

  // 清空输入框
  inputText.value = '';
  const displayContent = prefillDisplayRef.value ?? text;
  prefillDisplayRef.value = null;

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: displayContent,
    thinking: [],
    thinkingOpen: false,
    timestamp: new Date().toISOString(),
  });
  scrollToBottom();

  loading.value = true;
  abortCtrl = new AbortController();

  try {
    // 1️⃣ 发送消息并等待 AI 回复完成
    const res = await api.chatStream(
      {
        user_id: props.userId,
        message: text,
        session_id: sessionId.value,
      },
      undefined
    );

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (!res.body) throw new Error('SSE 响应无 body');

    // ... 流式处理代码（保持原样）...
    // 这里省略了原有的流式处理逻辑，保持不变

    // 2️⃣ AI 回复完成后，弹出评分框
    // 注意：这里使用 await，等待用户完成评分操作
    await handleRatingFlow(async (rating, comment) => {
      // 3️⃣ 用户评分后，异步提交（不阻塞 UI）
      await submitRatingToBackend(rating, comment);

      // 4️⃣ 最后才弹出分数卡片
      // 这里可以添加显示分数的逻辑
      console.log(`✅ 用户评分: ${rating}星, 评论: ${comment}`);
    });

  } catch (err) {
    console.error('🔴 发送失败:', err);
    ElMessage.error('消息发送失败');
  } finally {
    loading.value = false;
    sendInProgress = false;
    streamingMsg.value = null;
    chatStore.finishStream(messages.value);
    abortCtrl = null;
    scrollToBottom();
  }
};

/**
 * 使用 useAsyncClick 包装发送函数
 * 功能：
 * - 防止重复点击
 * - 异步执行
 * - 自动管理 loading 状态
 */
const { execute: handleSend, isLoading: sendLoading } = useAsyncClick(
  sendMessage,
  {
    timeout: 120000, // 120秒超时
    onError: (error) => {
      console.error('发送失败:', error.message);
      ElMessage.error(`发送失败: ${error.message}`);
    },
  }
);

// ========== 在模板中使用 ==========
// <el-button 
//   type="primary" 
//   class="send-btn" 
//   :loading="sendLoading"
//   :disabled="sendLoading || !inputText.trim()"
//   @click="handleSend"
// >
//   {{ sendLoading ? '' : '发送' }}
// </el-button>
