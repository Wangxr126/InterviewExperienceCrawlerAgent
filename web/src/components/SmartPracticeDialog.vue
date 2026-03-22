<template>
  <el-dialog
    v-model="visible"
    width="720px"
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
      <div class="sp-wrapper">
        <!-- 可滚动内容区 -->
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
                v-for="t in (question.topic_tags || []).slice(0, 8)"
                :key="t"
                size="small"
                class="meta-tag"
              >
                {{ t }}
              </el-tag>
            </div>
            <!-- 推荐题：展示 Rerank 后相关性分 + 多路召回融合分（重排前） -->
            <div v-if="showSmartRankLine" class="sp-rank-line">
              <template v-if="rerankScoreDisplay != null">
                <span class="sp-rank-item">重排后得分 <strong>{{ rerankScoreDisplay }}</strong></span>
              </template>
              <template v-if="preRerankScoreDisplay != null">
                <span class="sp-rank-sep" v-if="rerankScoreDisplay != null">·</span>
                <span class="sp-rank-item">重排前融合分 <strong>{{ preRerankScoreDisplay }}</strong></span>
              </template>
              <span v-if="rerankScoreDisplay == null && preRerankScoreDisplay == null" class="sp-rank-muted">（本次未记录排序分数）</span>
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
              :rows="5"
              :autosize="{ minRows: 5, maxRows: 10 }"
              placeholder="输入你的回答..."
              class="answer-input"
            />
          </div>

          <div class="sp-score-strip" :class="scoreClass">
            <span class="score-strip-label">得分</span>
            <span class="score-strip-value">{{ typeof displayScore === 'number' ? displayScore.toFixed(1) : displayScore }}</span>
            <span class="score-strip-denom">/ 5</span>
            <span v-if="displayScore !== '—'" class="score-strip-emoji" aria-hidden="true">{{ displayScoreEmoji }}</span>
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

        <!-- 固定底部按钮栏 -->
        <div class="sp-footer-fixed">
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
                  plain
                  :disabled="!standardAnswer"
                  @click="showAnswer = !showAnswer"
                >
                  {{ showAnswer ? '隐藏答案' : '标准答案' }}
                </el-button>
              </el-tooltip>
              <el-button
                v-if="question?.source_url"
                plain
                @click="openSourceUrl"
              >
                查看原帖
              </el-button>
              <el-button link type="primary" @click.stop="handleSendToChat">去对话练习</el-button>
              <el-button type="primary" :loading="submitting" @click="submit">
                提交作答
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

/** 展示召回/重排分数：模型尺度不一，统一保留有效数字 */
function formatRankScore(v) {
  if (v == null || v === '') return null
  const n = Number(v)
  if (!Number.isFinite(n)) return null
  const a = Math.abs(n)
  if (a >= 100) return n.toFixed(2)
  if (a >= 10) return n.toFixed(3)
  if (a >= 1) return n.toFixed(4)
  return n.toFixed(5)
}
import { ElMessage } from 'element-plus'
import { formatAnswerToHtml } from '../utils/formatAnswer.js'
import { postprocessFeedbackHtml } from '../utils/question-renderer.js'
import { api } from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  question: Object,
  userId: { type: String, default: 'user_001' },
  sessionId: { type: String, default: '' },
  practiceProgress: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'send-to-chat', 'submit-complete', 'prev-question', 'next-question'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const showSmartRankLine = computed(
  () => props.question?.smart_type === 'recommend'
)

const rerankScoreDisplay = computed(() =>
  formatRankScore(props.question?.rerank_score)
)

const preRerankScoreDisplay = computed(() =>
  formatRankScore(props.question?.recall_score)
)

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
  postprocessFeedbackHtml(formatAnswerToHtml(evalResult.value?.feedback || ''))
)

const hasPrev = computed(() => {
  if (!props.practiceProgress || !props.practiceProgress.total) return false
  return (props.practiceProgress.current || 0) > 1
})

const hasNext = computed(() => {
  if (!props.practiceProgress || !props.practiceProgress.total) return false
  return (props.practiceProgress.current || 0) < props.practiceProgress.total
})

// 切换题目时重置状态
watch(
  () => props.question?.q_id,
  () => {
    myAnswer.value = ''
    evalResult.value = null
    showAnswer.value = false
  }
)

watch(visible, (v) => {
  if (!v) {
    // 关闭弹窗时重置
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

  const userAnswer = myAnswer.value.trim()

  // 关闭弹窗，跳转到 Chat，让 Agent 来评分
  visible.value = false
  const displayMsg = `我想练习这道题：${props.question.question_text}\n\n我的回答：${userAnswer}`
  const apiMsg = `我想练习这道题【q_id:${props.question.q_id}】：${props.question.question_text}\n\n我的回答：${userAnswer}\n\n请给我评分并详细讲解。`
  emit('send-to-chat', { question: props.question, prefill: { display: displayMsg, api: apiMsg } })
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
  width: min(720px, 96vw) !important;
  border-radius: var(--radius, 12px);
  box-shadow: var(--shadow, 0 8px 32px rgba(0, 0, 0, 0.12));
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border, #e5e7eb);
}

.smart-practice-dialog :deep(.el-overlay) {
  background-color: rgba(0, 0, 0, 0.45);
}

.smart-practice-dialog :deep(.el-dialog__header) {
  padding: 0;
  border-bottom: 1px solid var(--border, #e5e7eb);
  flex-shrink: 0;
}

.smart-practice-dialog :deep(.el-dialog__body) {
  padding: 0;
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.smart-practice-dialog :deep(.el-dialog__footer) {
  padding: 0;
  border-top: none;
  display: none;
}

.sp-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: min(78vh, 820px);
}

.sp-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 26px 28px 30px;
}

.sp-footer-fixed {
  flex-shrink: 0;
  border-top: 1px solid var(--border, #e5e7eb);
  background: var(--card-bg, #fff);
  padding: 16px 24px 18px;
}

.sp-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  background: var(--card-bg, #fff);
}

.sp-header-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sp-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-main, #1a1a2e);
  letter-spacing: 0.02em;
}

.sp-progress-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary, #5b6ef5);
  background: var(--primary-light, #eef0fe);
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(91, 110, 245, 0.2);
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

.sp-question-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 22px 22px 20px;
  background: #fafbfc;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: var(--radius, 12px);
}

.q-full-text {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.72;
  color: var(--text-main, #1a1a2e);
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 2px;
}

.sp-rank-line {
  font-size: 13px;
  color: var(--text-sub, #64748b);
  line-height: 1.6;
  padding-top: 12px;
  margin-top: 4px;
  border-top: 1px dashed #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}

.sp-rank-item strong {
  color: var(--text-main, #334155);
  font-weight: 600;
}

.sp-rank-sep {
  color: #cbd5e1;
  user-select: none;
}

.sp-rank-muted {
  color: #94a3b8;
  font-size: 12px;
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
  font-size: 13px;
  font-weight: 600;
  color: var(--text-sub, #6b7280);
  letter-spacing: 0.02em;
  margin-bottom: 2px;
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

.ref-answer :deep(.katex-display) {
  margin: 8px 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.sp-input-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.answer-input :deep(.el-textarea__inner) {
  font-size: 14px;
  line-height: 1.65;
  border-radius: 10px;
  border: 1px solid var(--border, #e5e7eb);
  background: #fff;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  min-height: 120px;
  resize: vertical;
  padding: 14px 16px;
}

.answer-input :deep(.el-textarea__inner::placeholder) {
  color: #9ca3af;
}

.answer-input :deep(.el-textarea__inner:focus) {
  border-color: var(--primary, #5b6ef5);
  box-shadow: 0 0 0 2px rgba(91, 110, 245, 0.12);
  outline: none;
}

/* 得分：单行轻量条，不再用大色块卡片 */
.sp-score-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
  padding: 12px 16px;
  background: #f3f4f6;
  border-radius: 10px;
  border: 1px solid var(--border, #e5e7eb);
}

.sp-score-strip.score-high {
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.sp-score-strip.score-medium {
  background: #fffbeb;
  border-color: #fde68a;
}

.sp-score-strip.score-low {
  background: #fef2f2;
  border-color: #fecaca;
}

.score-strip-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-sub, #6b7280);
}

.score-strip-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary, #5b6ef5);
  line-height: 1;
}

.score-strip-denom {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-sub, #6b7280);
}

.sp-score-strip.score-high .score-strip-value {
  color: #16a34a;
}

.sp-score-strip.score-medium .score-strip-value {
  color: #d97706;
}

.sp-score-strip.score-low .score-strip-value {
  color: #dc2626;
}

.score-strip-emoji {
  font-size: 18px;
  margin-left: 4px;
  line-height: 1;
}

.eval-result {
  padding: 16px 18px;
  border-radius: 10px;
  border: 1px solid var(--border, #e5e7eb);
  border-left-width: 3px;
}

.eval-result.good {
  background: #f8fafc;
  border-left-color: #22c55e;
}

.eval-result.bad {
  background: #fafafa;
  border-left-color: #ef4444;
}

.eval-feedback {
  font-size: 14px;
  line-height: 1.7;
  color: #374151;
}
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
  gap: 20px;
  flex-wrap: wrap;
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
  border-color: var(--primary, #5b6ef5);
  color: var(--primary, #5b6ef5);
  background: var(--primary-light, #eef0fe);
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
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  flex-shrink: 0;
}

.footer-buttons :deep(.el-button) {
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
  padding: 8px 16px;
  white-space: nowrap;
}

.footer-buttons :deep(.el-button--primary) {
  padding-left: 18px;
  padding-right: 18px;
}

.sp-body::-webkit-scrollbar {
  width: 6px;
}

.sp-body::-webkit-scrollbar-track {
  background: transparent;
}

.sp-body::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

.sp-body::-webkit-scrollbar-thumb:hover {
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

  .sp-footer-fixed {
    padding: 12px 16px;
  }

  .footer-row {
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
