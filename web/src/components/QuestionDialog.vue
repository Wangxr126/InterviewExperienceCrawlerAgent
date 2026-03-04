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

      <div v-if="question.reference_answer" class="section">
        <div class="section-title">参考答案</div>
        <div class="ref-answer">{{ question.reference_answer }}</div>
      </div>

      <div class="section">
        <div class="section-title">我的作答</div>
        <el-input v-model="myAnswer" type="textarea" :rows="4"
                  placeholder="输入你的回答..." />
      </div>

      <div v-if="evalResult" class="eval-result" :class="evalResult.score >= 3 ? 'good' : 'bad'">
        <div class="eval-score">得分：{{ evalResult.score }}/5 {{ scoreEmoji }}</div>
        <div class="eval-feedback">{{ evalResult.feedback }}</div>
        <div v-if="evalResult.missing_points?.length" class="eval-missing">
          <strong>遗漏点：</strong>{{ evalResult.missing_points.join('、') }}
        </div>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="info" @click="$emit('send-to-chat', { question })">💬 去对话练习</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">提交作答</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props  = defineProps({ modelValue: Boolean, question: Object })
const emit   = defineEmits(['update:modelValue', 'send-to-chat'])
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const myAnswer   = ref('')
const submitting = ref(false)
const evalResult = ref(null)

const scoreEmoji = computed(() => {
  const s = evalResult.value?.score
  if (s >= 5) return '🌟'
  if (s >= 4) return '✅'
  if (s >= 3) return '👍'
  if (s >= 2) return '🤔'
  return '📚'
})

watch(visible, (v) => {
  if (!v) { myAnswer.value = ''; evalResult.value = null }
})

const submit = async () => {
  if (!myAnswer.value.trim()) { ElMessage.warning('请先输入你的答案'); return }
  submitting.value = true
  try {
    const r = await api.submitAnswer({
      user_id: 'user_001',
      session_id: `sess_${Date.now()}`,
      question_id: props.question.q_id,
      question_text: props.question.question_text,
      user_answer: myAnswer.value,
      question_tags: props.question.topic_tags || [],
    })
    evalResult.value = r
  } catch {
    ElMessage.error('提交失败')
  } finally {
    submitting.value = false
  }
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
.eval-result { margin-top: 14px; padding: 14px; border-radius: 10px; }
.eval-result.good { background: #f0fdf4; border: 1px solid #86efac; }
.eval-result.bad  { background: #fef2f2; border: 1px solid #fca5a5; }
.eval-score    { font-size: 15px; font-weight: 700; margin-bottom: 6px; }
.eval-feedback { font-size: 14px; line-height: 1.6; }
.eval-missing  { margin-top: 8px; font-size: 13px; color: #dc2626; }
</style>
