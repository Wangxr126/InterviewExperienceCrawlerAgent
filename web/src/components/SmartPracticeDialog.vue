<template>
  <el-dialog
    v-model="visible"
    width="640px"
    align-center
    destroy-on-close
    :show-close="false"
    class="smart-practice-dialog"
  >
    <template #header>
      <div class="sp-header-bar">
        <div class="sp-header-title">
          <span class="sp-title">智能练习</span>
          <span
            v-if="practiceProgress && practiceProgress.total > 0"
            class="sp-progress-badge"
          >
            {{ practiceProgress.current }}/{{ practiceProgress.total }}
          </span>
        </div>
        <button class="sp-close-btn" @click="visible = false">×</button>
      </div>
    </template>

    <template v-if="question">
      <div class="sp-body">
        <div class="sp-question-section">
          <div class="q-full-text">{{ question.question_text }}</div>
          <div class="meta-row">
            <el-tag
              v-if="question.difficulty"
              size="small"
              :type="{ easy: 'success', medium: 'warning', hard: 'danger' }[question.difficulty]"
              class="meta-tag"
            >
              {{ { easy: '简单', medium: '中等', hard: '困难' }[question.difficulty] }}
            </el-tag>
            <el-tag
              v-if="question.smart_type"
              size="small"
              :type="question.smart_type === 'recommend' ? 'success' : 'info'"
              class="meta-tag"
            >
              {{ question.smart_type === 'recommend' ? '推荐题目' : '随机题目' }}
            </el-tag>
            <el-tag v-if="question.company" size="small" class="meta-tag">
              {{ question.company }}
            </el-tag>
            <el-tag v-if="question.position" size="small" class="meta-tag">
              {{ question.position }}
            </el-tag>
            <el-tag
              v-for="t in (question.topic_tags || [])"
              :key="t"
              size="small"
              class="meta-tag"
            >
              {{ t }}
            </el-tag>
          </div>
        </div>

        <div v-if="showAnswer && standardAnswer" class="sp-answer-section">
          <div class="section-title">标准答案</div>
          <div class="ref-answer" v-html="formattedAnswerHtml"></div>
        </div>

        <div class="sp-input-section">
          <div class="section-title">我的作答</div>
          <el-input
            v-model="myAnswer"
            type="textarea"
            :rows="4"
            :autosize="{ minRows: 4, maxRows: 8 }"
            placeholder="输入你的回答..."
            class="answer-input"
          />
        </div>

        <div class="sp-score-card" :class="scoreClass">
          <span class="score-label">得分</span>
          <span class="score-value">{{ displayScore }}/5</span>
          <span v-if="displayScore !== '—'" class="score-emoji">{{ displayScoreEmoji }}</span>
        </div>

        <div
          v-if="evalResult"
          class="eval-result"
          :class="evalResult.score >= 3 ? 'good' : 'bad'"
        >
          <div class="eval-feedback" v-html="formattedFeedbackHtml"></div>
          <div
            v-if="(evalResult.missed_points || evalResult.missing_points)?.length"
            class="eval-missing"
          >
            <strong>遗漏点：</strong>{{
              (evalResult.missed_points ||
                evalResult.missing_points ||
                []
              ).join('、')
            }}
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="footer-row">
        <div class="footer-nav">
          <button
            type="button"
            class="btn-nav btn-prev"
            :disabled="!hasPrev"
            @click="handlePrevClick"
            title="上一题"
          >
            ‹
          </button>
          <span
            v-if="practiceProgress && practiceProgress.total > 0"
            class="footer-progress"
          >
            {{ practiceProgress.current }}/{{ practiceProgress.total }}
          </span>
          <button
            type="button"
            class="btn-nav btn-next"
            :disabled="!hasNext"
            @click="handleNextClick"
            title="下一题"
          >
            ›
          </button>
        </div>
        <div class="footer-buttons">
          <el-tooltip
            :content="standardAnswer ? '' : '该题暂无标准答案'"
            placement="top"
          >
            <el-button
              class="btn-answer"
              :disabled="!standardAnswer"
              @click="showAnswer = !showAnswer"
            >
              {{ showAnswer ? '隐藏答案' : '标准答案' }}
            </el-button>
          </el-tooltip>
          <el-button
            v-if="question?.source_url"
            class="btn-source"
            @click="openSourceUrl"
          >
            查看原帖
          </el-button>
          <el-button class="btn-chat" @click.stop="handleSendToChat">去对话练习</el-button>
          <el-button
            class="btn-submit"
            :loading="submitting"
            @click="submit"
          >
            提交作答
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { formatAnswerToHtml } from '../utils/formatAnswer.js'

const props = defineProps({
  modelValue: Boolean,
  question: Object,
  userId: { type: String, default: 'user_001' },
  sessionId: { type: String, default: '' },
  practiceProgress: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'send-to-chat', 'submit-complete'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const myAnswer = ref('')
const submitting = ref(false)
const evalResult = ref(null)
const showAnswer = ref(false)

const standardAnswer = computed(
  () =>
    props.question?.answer_text ||
    props.question?.reference_answer ||
    evalResult.value?.standard_answer ||
    ''
)

const displayScore = computed(() => {
  if (evalResult.value?.score != null) return evalResult.value.score
  const last = props.question?.last_score
  return last != null ? last : '—'
})

const displayScoreEmoji = computed(() => {
  const s = typeof displayScore.value === 'number' ? displayScore.value : null
  if (s == null) return ''
  if (s >= 5) return '🌟'
  if (s >= 4) return '✅'
  if (s >= 3) return '👍'
  if (s >= 2) return '🤔'
  return '📚'
})

const scoreClass = computed(() => {
  const s = typeof displayScore.value === 'number' ? displayScore.value : null
  if (s == null) return ''
  if (s >= 4) return 'score-high'
  if (s >= 2.5) return 'score-medium'
  return 'score-low'
})

const formattedAnswerHtml = computed(() =>
  formatAnswerToHtml(standardAnswer.value)
)
const formattedFeedbackHtml = computed(() =>
  formatAnswerToHtml(evalResult.value?.feedback || '')
)

const hasPrev = computed(() => {
  if (!props.practiceProgress || !props.practiceProgress.total) return false
  return (props.practiceProgress.current || 0) > 1
})

const hasNext = computed(() => {
  if (!props.practiceProgress || !props.practiceProgress.total) return false
  return (props.practiceProgress.current || 0) < props.practiceProgress.total
})

watch(visible, (v) => {
  if (v) {
    showAnswer.value = false
  } else {
    myAnswer.value = ''
    evalResult.value = null
    showAnswer.value = false
  }
})

const submit = async () => {
  if (!myAnswer.value.trim()) {
    ElMessage.warning('请先输入你的答案')
    return
  }
  if (!props.question?.q_id) {
    ElMessage.warning('题目 ID 缺失，无法记录')
    return
  }

  submitting.value = true
  evalResult.value = null

  try {
    const userAnswer = myAnswer.value.trim()
    const { api } = await import('../api.js')
    
    // Step 1: 提交答案，获取任务 ID
    const submitResp = await api.submitAnswer({
      user_id: props.userId,
      session_id: props.sessionId || `sess_${Date.now()}`,
      question_id: props.question.q_id,
      question_text: props.question.question_text,
      user_answer: userAnswer,
      question_tags: props.question.topic_tags || [],
    })
    
    const taskId = submitResp.task_id
    ElMessage.info('正在评分中，请稍候...')
    
    // Step 2: 轮询获取评分结果（最多等待 60 秒）
    let result = null
    let attempts = 0
    const maxAttempts = 120  // 60 秒（每 500ms 轮询一次）
    
    while (attempts < maxAttempts) {
      await new Promise(resolve => setTimeout(resolve, 500))  // 等待 500ms
      attempts++
      
      try {
        const statusResp = await api.getSubmitAnswerStatus(taskId)
        
        if (statusResp.status === 'completed') {
          result = statusResp.result
          break
        } else if (statusResp.status === 'failed') {
          throw new Error(`评分失败: ${statusResp.error}`)
        }
        // 继续轮询
      } catch (pollError) {
        console.error('轮询状态失败:', pollError)
        if (attempts >= maxAttempts) {
          throw new Error('评分超时，请稍后重试')
        }
      }
    }
    
    if (!result) {
      throw new Error('评分超时（60秒），请稍后重试')
    }
    
    evalResult.value = result
    // 不再弹出分数提示，由 Agent 在对话中展示评分结果

    emit('submit-complete', {
      question: props.question,
      userAnswer,
      result,
    })
  } catch (error) {
    console.error('提交答案失败:', error)
    ElMessage.error(error.message || '提交失败，请重试')
  } finally {
    submitting.value = false
  }
}

const openSourceUrl = () => {
  if (props.question?.source_url) {
    window.open(props.question.source_url, '_blank')
  }
}

const handleSendToChat = () => {
  if (handleSendToChat._pending) return
  handleSendToChat._pending = true
  visible.value = false
  setTimeout(() => {
    emit('send-to-chat', { question: props.question })
    setTimeout(() => {
      handleSendToChat._pending = false
    }, 500)
  }, 100)
}

const handlePrevClick = () => {
  if (!hasPrev.value) return
  emit('prev-question')
}

const handleNextClick = () => {
  if (!hasNext.value) return
  emit('next-question')
}
</script>

<style scoped>
.smart-practice-dialog :deep(.el-dialog) {
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}

.smart-practice-dialog :deep(.el-overlay) {
  background-color: rgba(0, 0, 0, 0.4);
}

.smart-practice-dialog :deep(.el-dialog__header) {
  padding: 0;
  border-bottom: none;
}

.smart-practice-dialog :deep(.el-dialog__body) {
  padding: 0;
  max-height: 70vh;
  overflow-y: auto;
}

.smart-practice-dialog :deep(.el-dialog__footer) {
  padding: 0;
  border-top: none;
}

.sp-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 24px 28px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-bottom: 1px solid #e5e7eb;
}

.sp-header-title {
  display: flex;
  align-items: center;
  gap: 14px;
}

.sp-title {
  font-size: 20px;
  font-weight: 800;
  color: #4F46E5;
  letter-spacing: -0.5px;
}

.sp-progress-badge {
  font-size: 12px;
  font-weight: 700;
  color: #4F46E5;
  background: linear-gradient(135deg, #eef2ff 0%, #f3f4f6 100%);
  padding: 6px 12px;
  border-radius: 20px;
  border: 1px solid #e0e7ff;
  display: inline-block;
}

.sp-close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  font-size: 20px;
  color: #9ca3af;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
}

.sp-close-btn:hover {
  color: #ef4444;
  background: #fee2e2;
}

.sp-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px;
}

.sp-question-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  background: linear-gradient(135deg, #f8fafc 0%, #f0f4ff 100%);
  border: 1px solid #e0e7ff;
  border-radius: 12px;
}

.q-full-text {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.6;
  color: #1f2937;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-tag {
  font-size: 12px !important;
  border-radius: 6px !important;
  background: white !important;
  border: 1px solid #e5e7eb !important;
  color: #6b7280 !important;
  font-weight: 500 !important;
  padding: 4px 10px !important;
}

.sp-answer-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-title {
  font-size: 12px;
  font-weight: 800;
  color: #374151;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.ref-answer {
  font-size: 14px;
  line-height: 1.7;
  color: #4b5563;
  padding: 14px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.ref-answer :deep(p) {
  margin: 0 0 10px;
}

.ref-answer :deep(p:last-child) {
  margin-bottom: 0;
}

.sp-input-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.answer-input :deep(.el-textarea__inner) {
  font-size: 14px;
  line-height: 1.7;
  border-radius: 8px;
  border: 1.5px solid #d1d5db;
  background: white;
  transition: all 0.25s ease;
  min-height: 100px;
  resize: vertical;
}

.answer-input :deep(.el-textarea__inner::placeholder) {
  color: #d1d5db;
}

.answer-input :deep(.el-textarea__inner:focus) {
  border-color: #4F46E5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
  outline: none;
}

.sp-score-card {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 18px;
  background: #f3f4f6;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  transition: all 0.3s ease;
}

.sp-score-card.score-high {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-color: #86efac;
}

.sp-score-card.score-medium {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-color: #fcd34d;
}

.sp-score-card.score-low {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: #fca5a5;
}

.score-label {
  font-size: 12px;
  font-weight: 700;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.score-value {
  font-size: 28px;
  font-weight: 900;
  color: #4F46E5;
}

.sp-score-card.score-high .score-value {
  color: #22c55e;
}

.sp-score-card.score-medium .score-value {
  color: #f59e0b;
}

.sp-score-card.score-low .score-value {
  color: #ef4444;
}

.score-emoji {
  font-size: 28px;
  animation: bounce 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
}

@keyframes bounce {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.25); }
}

.eval-result {
  padding: 14px;
  border-radius: 10px;
  border-left: 4px solid;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.eval-result.good {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-left-color: #22c55e;
}

.eval-result.bad {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-left-color: #ef4444;
}

.eval-feedback {
  font-size: 14px;
  line-height: 1.7;
  color: #374151;
}

.eval-missing {
  margin-top: 10px;
  font-size: 13px;
  color: #dc2626;
  font-weight: 600;
}

.footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 24px;
  background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  border-top: 1px solid #e5e7eb;
}

.footer-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-shrink: 0;
}

.btn-nav {
  width: 36px;
  height: 36px;
  border: 1.5px solid #d1d5db;
  background: white;
  color: #6b7280;
  border-radius: 8px;
  cursor: pointer;
  font-size: 18px;
  font-weight: 600;
  transition: all 0.25s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
}

.btn-nav:hover:not(:disabled) {
  border-color: #4F46E5;
  color: #4F46E5;
  background: #eef2ff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15);
}

.btn-nav:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.footer-progress {
  font-size: 13px;
  color: #6b7280;
  font-weight: 600;
  min-width: 50px;
  text-align: center;
}

.footer-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
  justify-content: flex-end;
  flex-shrink: 0;
}

.footer-buttons :deep(.el-button) {
  height: 36px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  border: none;
  padding: 0 14px;
  white-space: nowrap;
}

.btn-answer {
  border: 1.5px solid #22c55e !important;
  color: #22c55e !important;
  background: white !important;
}

.btn-answer:hover {
  background: #f0fdf4 !important;
  border-color: #16a34a !important;
  color: #16a34a !important;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
}

.btn-answer:disabled {
  border-color: #d1d5db !important;
  color: #d1d5db !important;
  opacity: 0.5;
}

.btn-source {
  border: 1.5px solid #d1d5db !important;
  color: #6b7280 !important;
  background: white !important;
}

.btn-source:hover {
  border-color: #9ca3af !important;
  color: #374151 !important;
  background: #f9fafb !important;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.btn-chat {
  background: #f3f4f6 !important;
  color: #374151 !important;
  border: none !important;
}

.btn-chat:hover {
  background: #e5e7eb !important;
  color: #1f2937 !important;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.btn-submit {
  background: linear-gradient(135deg, #4F46E5 0%, #6366f1 100%) !important;
  color: white !important;
  border: none !important;
  box-shadow: 0 4px 15px rgba(79, 70, 229, 0.3);
  font-weight: 700;
}

.btn-submit:hover {
  background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%) !important;
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(79, 70, 229, 0.4);
}

.smart-practice-dialog :deep(.el-dialog__body)::-webkit-scrollbar {
  width: 6px;
}

.smart-practice-dialog :deep(.el-dialog__body)::-webkit-scrollbar-track {
  background: transparent;
}

.smart-practice-dialog :deep(.el-dialog__body)::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

.smart-practice-dialog :deep(.el-dialog__body)::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

@media (max-width: 680px) {
  .smart-practice-dialog :deep(.el-dialog) {
    width: 92vw !important;
  }

  .sp-body {
    padding: 16px;
    gap: 12px;
  }

  .footer-row {
    padding: 12px 16px;
    flex-direction: row;
    align-items: center;
    gap: 8px;
  }

  .footer-nav {
    gap: 6px;
  }

  .btn-nav {
    width: 32px;
    height: 32px;
    font-size: 16px;
  }

  .footer-buttons {
    gap: 6px;
  }

  .footer-buttons :deep(.el-button) {
    height: 32px;
    padding: 0 10px;
    font-size: 12px;
  }
}
</style>
