<template>
  <el-dialog v-model="visible" :title="question?.question_text || '题目详情'" width="780px"
             align-center destroy-on-close>
    <template v-if="question">
      <div class="dialog-body-with-nav">
        <!-- 左侧上一题区域 -->
        <div
          v-if="showPracticeNav"
          class="side-nav side-nav-left"
          :class="{ disabled: !hasPrev }"
          @click="handlePrevClick"
        >
          <div class="side-nav-inner">
            <span class="arrow">←</span>
            <span class="label">上一题</span>
          </div>
        </div>

        <!-- 中间主体内容 -->
        <div class="dialog-main">
          <div class="meta-row">
            <el-tag v-if="question.company" size="small">🏢 {{ question.company }}</el-tag>
            <el-tag v-if="question.position" size="small" type="success">💼 {{ question.position }}</el-tag>
            <el-tag v-if="question.difficulty" size="small"
                    :type="{ easy:'success', medium:'warning', hard:'danger' }[question.difficulty]">
              {{ { easy:'简单', medium:'中等', hard:'困难' }[question.difficulty] }}
            </el-tag>
            <el-tag v-for="t in (question.topic_tags||[])" :key="t" size="small" type="info">{{ t }}</el-tag>
            <el-tag v-if="question.smart_type" size="small" :type="question.smart_type === 'recommend' ? 'success' : 'info'">
              {{ question.smart_type === 'recommend' ? '推荐题目' : '随机题目' }}
            </el-tag>
          </div>

          <div class="q-full-text">{{ question.question_text }}</div>

          <div v-if="showAnswer && standardAnswer" class="section">
            <div class="section-title">
              📋 标准答案
              <span v-if="question.raw_answer" class="answer-source-badge stage2">Stage2 精答</span>
              <span v-else class="answer-source-badge stage1">Stage1 粗提取</span>
            </div>
            <div class="ref-answer" v-html="formattedAnswerHtml"></div>
          </div>

          <div class="section">
            <div class="section-title">我的作答</div>
            <el-input v-model="myAnswer" type="textarea" :rows="4"
                      placeholder="输入你的回答..." />
          </div>

          <div class="section">
            <div class="section-title">得分</div>
            <div class="score-display">
              {{ displayScore }}/5
              <span v-if="displayScore !== '—'" class="score-emoji">{{ displayScoreEmoji }}</span>
            </div>
          </div>

          <div v-if="evalResult" class="eval-result" :class="evalResult.score >= 3 ? 'good' : 'bad'">
            <div class="eval-feedback" v-html="formattedFeedbackHtml"></div>
            <div v-if="(evalResult.missed_points || evalResult.missing_points)?.length" class="eval-missing">
              <strong>遗漏点：</strong>{{ (evalResult.missed_points || evalResult.missing_points || []).join('、') }}
            </div>
          </div>

          <!-- 之前作答记录：历史回答 + 得分 + 要点 -->
          <div v-if="pastRecords.length > 0" class="section past-records-section">
            <div class="section-title">📜 之前作答记录</div>
            <div class="past-records-list">
              <div v-for="(rec, idx) in pastRecords" :key="idx" class="past-record-card">
                <div class="past-record-head">
                  <span class="past-record-date">{{ formatRecordDate(rec.studied_at) }}</span>
                  <span class="past-record-score" :class="rec.score >= 3 ? 'score-ok' : 'score-low'">{{ rec.score }}/5</span>
                </div>
                <div v-if="rec.user_answer" class="past-record-answer">
                  <span class="past-label">回答：</span>{{ rec.user_answer.length > 120 ? rec.user_answer.slice(0, 120) + '…' : rec.user_answer }}
                </div>
                <div v-if="(rec.missed_points && rec.missed_points.length) || (rec.strong_points && rec.strong_points.length)" class="past-record-points">
                  <template v-if="rec.strong_points?.length">
                    <span class="past-label">答对要点：</span>{{ rec.strong_points.join('、') }}
                  </template>
                  <template v-if="rec.missed_points?.length">
                    <span class="past-label past-label-miss">遗漏点：</span>{{ rec.missed_points.join('、') }}
                  </template>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧下一题区域 -->
        <div
          v-if="showPracticeNav"
          class="side-nav side-nav-right"
          :class="{ disabled: !hasNext }"
          @click="handleNextClick"
        >
          <div class="side-nav-inner">
            <span class="label">下一题</span>
            <span class="arrow">→</span>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="footer-row">
        <span v-if="practiceProgress && practiceProgress.total > 0" class="progress-badge">
          {{ practiceProgress.current }}/{{ practiceProgress.total }}
        </span>
        <div class="footer-buttons">
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
          <el-button type="primary" plain @click.stop="handleRunModelBench">🔬 推理评测</el-button>
          <el-button type="info" @click.stop="handleSendToChat">💬 去对话练习</el-button>
          <el-button type="primary" :loading="submitting" @click="submit">提交作答</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { formatAnswerToHtml } from '../utils/formatAnswer.js'
import { postprocessFeedbackHtml } from '../utils/question-renderer.js'
import { api } from '../api.js'

const props  = defineProps({
  modelValue: Boolean,
  question: Object,
  userId: { type: String, default: 'user_001' },
  sessionId: { type: String, default: '' },
  practiceProgress: { type: Object, default: null }, // { current, total } 如 { 1, 10 }
})
const emit   = defineEmits(['update:modelValue', 'send-to-chat', 'run-model-bench', 'submit-complete', 'prev-question', 'next-question'])
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const myAnswer   = ref('')
const submitting = ref(false)
const evalResult = ref(null)
const showAnswer = ref(false)
const pastRecords = ref([])
const standardAnswer = computed(() =>
  props.question?.answer_text || props.question?.reference_answer || evalResult.value?.standard_answer || ''
)

// 展示得分：优先本次评估结果，否则用题目卡片上的最近得分
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

// 智能练习导航：根据 progress 判断是否展示左右上一题 / 下一题区域
const showPracticeNav = computed(() => !!(props.practiceProgress && props.practiceProgress.total > 0))
const hasPrev = computed(() => {
  if (!props.practiceProgress || !props.practiceProgress.total) return false
  return (props.practiceProgress.current || 0) > 1
})
const hasNext = computed(() => {
  if (!props.practiceProgress || !props.practiceProgress.total) return false
  return (props.practiceProgress.current || 0) < props.practiceProgress.total
})

// 分点答案：1. 2. 或 一、二、 或 （1）（2）等每条占一行，格式清晰
const formattedAnswerHtml = computed(() => formatAnswerToHtml(standardAnswer.value))
const formattedFeedbackHtml = computed(() =>
  postprocessFeedbackHtml(formatAnswerToHtml(evalResult.value?.feedback || ''))
)

const scoreEmoji = computed(() => {
  const s = evalResult.value?.score
  if (s >= 5) return '🌟'
  if (s >= 4) return '✅'
  if (s >= 3) return '👍'
  if (s >= 2) return '🤔'
  return '📚'
})

function formatRecordDate(studiedAt) {
  if (!studiedAt) return ''
  const d = new Date(studiedAt)
  if (isNaN(d.getTime())) return studiedAt
  const now = new Date()
  const sameDay = d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
  if (sameDay) {
    return '今天 ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function loadPastRecords() {
  pastRecords.value = []
  const qid = props.question?.q_id
  const uid = props.userId
  if (!qid || !uid) return
  try {
    const { api } = await import('../api.js')
    const list = await api.getQuestionStudyRecords(uid, qid)
    pastRecords.value = (list || []).map((r) => ({
      score: r.score,
      user_answer: r.user_answer || '',
      ai_feedback: r.ai_feedback || '',
      studied_at: r.studied_at,
      missed_points: r.eval_details?.missed_points || [],
      strong_points: r.eval_details?.strong_points || [],
    }))
  } catch (e) {
    console.warn('加载作答记录失败:', e)
  }
}

watch(visible, (v) => {
  if (v) {
    // 默认隐藏答案，符合刷题场景习惯
    showAnswer.value = false
    loadPastRecords()
  } else {
    myAnswer.value = ''
    evalResult.value = null
    showAnswer.value = false
    pastRecords.value = []
  }
})

const submit = async () => {
  if (!myAnswer.value.trim()) { ElMessage.warning('请先输入你的答案'); return }
  if (!props.question?.q_id) { ElMessage.warning('题目 ID 缺失，无法记录'); return }

  const userAnswer = myAnswer.value.trim()
  if (submitting.value) return
  submitting.value = true

  // 关闭弹窗并跳转到 chat：由 Agent（/api/chat/stream + submit_answer tool）在对话中完成评分
  visible.value = false

  const displayMsg = `我想练习这道题：${props.question.question_text}\n\n我的回答：${userAnswer}`
  const apiMsg = `我想练习这道题【q_id:${props.question.q_id}】：${props.question.question_text}\n\n我的回答：${userAnswer}\n\n请给我评分并详细讲解。`

  setTimeout(() => {
    emit('send-to-chat', { question: props.question, prefill: { display: displayMsg, api: apiMsg } })
    setTimeout(() => { submitting.value = false }, 500)
  }, 100)
}

const openSourceUrl = () => {
  if (props.question?.source_url) {
    window.open(props.question.source_url, '_blank')
  }
}

const emitPrev = () => {
  emit('prev-question')
}

const emitNext = () => {
  emit('next-question')
}

const handlePrevClick = () => {
  if (!hasPrev.value) return
  emitPrev()
}

const handleNextClick = () => {
  if (!hasNext.value) return
  emitNext()
}

const sendToChatPending = ref(false)
const handleSendToChat = () => {
  // 防止重复点击
  if (sendToChatPending.value) return
  sendToChatPending.value = true

  // 先关闭当前对话框
  visible.value = false

  // 延迟触发事件，确保对话框已关闭
  setTimeout(() => {
    emit('send-to-chat', { question: props.question })
    setTimeout(() => {
      sendToChatPending.value = false
    }, 500)
  }, 100)
}

const handleRunModelBench = () => {
  if (!props.question?.question_text) {
    ElMessage.warning('题目内容为空，无法发起推理评测')
    return
  }
  visible.value = false
  setTimeout(() => {
    emit('run-model-bench', { question: props.question })
  }, 100)
}
</script>

<style scoped>
.meta-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.q-full-text { font-size: 15px; line-height: 1.7; margin-bottom: 16px;
               padding: 12px; background: var(--bg); border-radius: 8px; }
.section { margin-bottom: 16px; }
.section-title { font-size: 13px; font-weight: 600; color: var(--text-sub);
                 margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em;
                 display: flex; align-items: center; gap: 8px; }
.answer-source-badge {
  font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 10px;
  text-transform: none; letter-spacing: 0; vertical-align: middle;
}
.answer-source-badge.stage2 { background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe; }
.answer-source-badge.stage1 { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
.ref-answer { font-size: 14px; line-height: 1.6; color: var(--text-sub);
              padding: 10px 12px; background: var(--bg); border-radius: 8px; }
.ref-answer :deep(p) { margin: 0 0 8px; }
.ref-answer :deep(p:last-child) { margin-bottom: 0; }
.ref-answer :deep(strong) { font-weight: 600; color: var(--text-sub); }
.ref-answer :deep(ul), .ref-answer :deep(ol) { margin: 8px 0; padding-left: 1.5em; }
.ref-answer :deep(li) { margin-bottom: 4px; }
.ref-answer :deep(.katex-display) { margin: 8px 0; overflow-x: auto; overflow-y: hidden; }
.eval-result { margin-top: 14px; padding: 14px; border-radius: 10px; }
.eval-result.good { background: #f0fdf4; border: 1px solid #86efac; }
.eval-result.bad  { background: #fef2f2; border: 1px solid #fca5a5; }
.eval-score    { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
.eval-feedback { font-size: 14px; line-height: 1.6; }
.eval-feedback :deep(p) { margin: 0 0 6px; }
.eval-feedback :deep(p:last-child) { margin-bottom: 0; }
.eval-feedback :deep(strong) { font-weight: 600; }
/* 与练习对话一致：答对 / 遗漏 / 混淆点 并列区块 */
.eval-feedback :deep(.score-badge) {
  display: inline-block;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  padding: 6px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 15px;
  margin: 8px 0;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}
.eval-feedback :deep(.fb-sec) {
  margin: 10px 0;
  padding: 10px 12px;
  background: rgba(248, 250, 252, 0.95);
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.eval-feedback :deep(.fb-sec-head) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.eval-feedback :deep(.fb-sec-mark) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #94a3b8;
}
.eval-feedback :deep(.fb-sec--correct .fb-sec-mark) { background: #22c55e; }
.eval-feedback :deep(.fb-sec--miss .fb-sec-mark) { background: #f59e0b; }
.eval-feedback :deep(.fb-sec--confuse .fb-sec-mark) { background: #64748b; }
.eval-feedback :deep(.fb-sec--error .fb-sec-mark) { background: #ef4444; }
.eval-feedback :deep(.fb-sec-label) {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}
.eval-feedback :deep(.fb-sec-list) {
  margin: 0;
  padding-left: 20px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}
.eval-feedback :deep(.fb-sec-list li) { margin: 4px 0; }
.eval-missing  { margin-top: 8px; font-size: 13px; color: #dc2626; }
.score-display { font-size: 18px; font-weight: 700; color: var(--primary); }
.score-emoji   { font-size: 20px; margin-left: 4px; }
.footer-row { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.footer-buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.progress-badge {
  font-size: 15px; font-weight: 700; color: var(--primary);
  padding: 4px 12px; background: var(--primary-light); border-radius: 20px;
}

/* 之前作答记录 */
.past-records-section { margin-top: 16px; }
.past-records-list { display: flex; flex-direction: column; gap: 10px; max-height: 220px; overflow-y: auto; }
.past-record-card {
  padding: 10px 12px; background: var(--bg); border-radius: 8px;
  border: 1px solid #e2e8f0; font-size: 13px; line-height: 1.5;
}
.past-record-head {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;
}
.past-record-date { color: #64748b; font-size: 12px; }
.past-record-score {
  font-weight: 600; padding: 2px 6px; border-radius: 6px; font-size: 12px;
}
.past-record-score.score-ok  { background: #dcfce7; color: #166534; }
.past-record-score.score-low { background: #fee2e2; color: #991b1b; }
.past-record-answer { color: var(--text-sub); margin-bottom: 4px; }
.past-record-points { font-size: 12px; color: #475569; }
.past-label { font-weight: 600; color: #64748b; margin-right: 4px; }
.past-label-miss { color: #dc2626; }

/* 左右导航侧边区域 */
.dialog-body-with-nav {
  display: flex; align-items: stretch; gap: 0;
  min-height: 0;
}
.dialog-main { flex: 1; min-width: 0; }
.side-nav {
  width: 44px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  border-radius: 8px;
  transition: background .15s;
  user-select: none;
  color: var(--primary);
}
.side-nav:hover:not(.disabled) { background: var(--primary-light); }
.side-nav.disabled { color: #cbd5e1; cursor: not-allowed; }
.side-nav-inner {
  display: flex; flex-direction: column;
  align-items: center; gap: 4px;
  font-size: 11px; font-weight: 600;
}
.side-nav .arrow { font-size: 18px; line-height: 1; }
.side-nav .label { font-size: 10px; color: inherit; }
</style>
