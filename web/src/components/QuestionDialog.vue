<template>
  <el-dialog v-model="visible" :title="question?.question_text?.slice(0,30) + '…'" width="680px"
             align-center destroy-on-close>
    <template v-if="question">
      <div class="meta-row">
        <el-tag v-if="question.company" size="small">🏢 {{ question.company }}</el-tag>
        <el-tag v-if="question.position" size="small" type="success">💼 {{ question.position }}</el-tag>
        <el-tag v-if="question.difficulty" size="small"
                :type="{ easy:'success', medium:'warning', hard:'danger' }[question.difficulty]">
          {{ { easy:'简单', medium:'中等', hard:'困难' }[question.difficulty] }}
        </el-tag>
        <el-tag v-for="t in (question.topic_tags||[])" :key="t" size="small" type="info">{{ t }}</el-tag>
      </div>

      <div class="q-full-text">{{ question.question_text }}</div>

      <div v-if="showAnswer && standardAnswer" class="section">
        <div class="section-title">📋 标准答案</div>
        <div class="ref-answer" v-html="formattedAnswerHtml"></div>
      </div>

      <div class="section">
        <div class="section-title">我的作答</div>
        <el-input v-model="myAnswer" type="textarea" :rows="4"
                  placeholder="输入你的回答..." />
      </div>

      <div class="section">
        <div class="section-title">得分</div>
        <div class="score-display">{{ evalResult ? `${evalResult.score}/5` : '—/5' }} <span v-if="evalResult" class="score-emoji">{{ scoreEmoji }}</span></div>
      </div>

      <div v-if="evalResult" class="eval-result" :class="evalResult.score >= 3 ? 'good' : 'bad'">
        <div class="eval-feedback" v-html="formattedFeedbackHtml"></div>
        <div v-if="(evalResult.missed_points || evalResult.missing_points)?.length" class="eval-missing">
          <strong>遗漏点：</strong>{{ (evalResult.missed_points || evalResult.missing_points || []).join('、') }}
        </div>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-tooltip :content="standardAnswer ? '' : '该题暂无标准答案'" placement="top">
        <el-button type="success" :disabled="!standardAnswer" @click="showAnswer = !showAnswer">
          {{ showAnswer ? '隐藏答案' : '📋 标准答案' }}
        </el-button>
      </el-tooltip>
      <el-button 
        v-if="question.source_url" 
        type="warning" 
        @click="openSourceUrl"
      >
        🔗 查看原帖
      </el-button>
      <el-button type="info" @click.stop="handleSendToChat">💬 去对话练习</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交作答</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { formatAnswerToHtml } from '../utils/formatAnswer.js'

const props  = defineProps({ modelValue: Boolean, question: Object, userId: { type: String, default: 'user_001' }, sessionId: { type: String, default: '' } })
const emit   = defineEmits(['update:modelValue', 'send-to-chat', 'submit-complete'])
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const myAnswer   = ref('')
const submitting = ref(false)
const evalResult = ref(null)
const showAnswer = ref(false)
const standardAnswer = computed(() =>
  props.question?.answer_text || props.question?.reference_answer || evalResult.value?.standard_answer || ''
)

// 分点答案：1. 2. 或 一、二、 或 （1）（2）等每条占一行，格式清晰
const formattedAnswerHtml = computed(() => formatAnswerToHtml(standardAnswer.value))
const formattedFeedbackHtml = computed(() => formatAnswerToHtml(evalResult.value?.feedback || ''))

const scoreEmoji = computed(() => {
  const s = evalResult.value?.score
  if (s >= 5) return '🌟'
  if (s >= 4) return '✅'
  if (s >= 3) return '👍'
  if (s >= 2) return '🤔'
  return '📚'
})

watch(visible, (v) => {
  if (v) {
    showAnswer.value = !!standardAnswer.value  // 默认打开标准答案
  } else {
    myAnswer.value = ''
    evalResult.value = null
    showAnswer.value = false
  }
})

const submit = async () => {
  if (!myAnswer.value.trim()) { ElMessage.warning('请先输入你的答案'); return }
  if (!props.question?.q_id) { ElMessage.warning('题目 ID 缺失，无法记录'); return }
  
  submitting.value = true
  evalResult.value = null
  
  try {
    const userAnswer = myAnswer.value.trim()
    
    // 调用后端 submit_answer 接口
    const { api } = await import('../api.js')
    const result = await api.submitAnswer({
      user_id: props.userId,
      session_id: props.sessionId || `sess_${Date.now()}`,
      question_id: props.question.q_id,
      question_text: props.question.question_text,
      user_answer: userAnswer,
      question_tags: props.question.topic_tags || []
    })
    
    // 显示评估结果
    evalResult.value = result
    ElMessage.success(`已提交！得分：${result.score}/5`)
    
    // 触发完成事件（用于刷新列表等）
    emit('submit-complete', { 
      question: props.question, 
      userAnswer,
      result 
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
  console.log('🔵 QuestionDialog: 触发 send-to-chat 事件')
  console.log('🔵 question:', props.question)
  
  // 防止重复点击
  if (handleSendToChat._pending) {
    console.log('🔵 防止重复点击，忽略本次调用')
    return
  }
  handleSendToChat._pending = true
  
  // 先关闭当前对话框
  visible.value = false
  
  // 延迟触发事件，确保对话框已关闭
  setTimeout(() => {
    emit('send-to-chat', { question: props.question })
    // 500ms 后重置标志
    setTimeout(() => {
      handleSendToChat._pending = false
    }, 500)
  }, 100)
}
</script>

<style scoped>
.meta-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.q-full-text { font-size: 15px; line-height: 1.7; margin-bottom: 16px;
               padding: 12px; background: var(--bg); border-radius: 8px; }
.section { margin-bottom: 16px; }
.section-title { font-size: 13px; font-weight: 600; color: var(--text-sub);
                 margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em; }
.ref-answer { font-size: 14px; line-height: 1.6; color: var(--text-sub);
              padding: 10px 12px; background: var(--bg); border-radius: 8px; }
.ref-answer :deep(.answer-line) { margin-bottom: 8px; }
.ref-answer :deep(.answer-line:last-child) { margin-bottom: 0; }
.eval-result { margin-top: 14px; padding: 14px; border-radius: 10px; }
.eval-result.good { background: #f0fdf4; border: 1px solid #86efac; }
.eval-result.bad  { background: #fef2f2; border: 1px solid #fca5a5; }
.eval-score    { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
.eval-feedback { font-size: 14px; line-height: 1.6; }
.eval-feedback :deep(.answer-line) { margin-bottom: 6px; }
.eval-feedback :deep(.answer-line:last-child) { margin-bottom: 0; }
.eval-missing  { margin-top: 8px; font-size: 13px; color: #dc2626; }
.score-display { font-size: 18px; font-weight: 700; color: var(--primary); }
.score-emoji   { font-size: 20px; margin-left: 4px; }
</style>
