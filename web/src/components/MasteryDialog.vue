<template>
  <el-dialog v-model="visible" title="📊 我的掌握度" width="560px" align-center>
    <div v-if="loading" style="text-align:center;padding:30px">
      <el-icon class="is-loading" style="font-size:28px;color:var(--primary)"><Loading /></el-icon>
    </div>
    <template v-if="data && !loading">
      <div class="ov-row">
        <div class="ov-item">
          <div class="ov-val">{{ data.total_answered ?? 0 }}</div>
          <div class="ov-label">总作答</div>
        </div>
        <div class="ov-item">
          <div class="ov-val">{{ avgScore }}</div>
          <div class="ov-label">平均分</div>
        </div>
        <div class="ov-item">
          <div class="ov-val">{{ data.mastered_count ?? 0 }}</div>
          <div class="ov-label">已掌握</div>
        </div>
      </div>

      <div v-if="weakTags.length" class="section">
        <div class="section-title">薄弱知识点（点击获取推荐）</div>
        <div class="tag-row">
          <el-tag v-for="t in weakTags" :key="t" type="danger" size="small"
                  @click="$emit('quick-recommend', [t])" style="cursor:pointer">
            {{ t }} 👉
          </el-tag>
        </div>
      </div>
    </template>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="load">刷新</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({
  modelValue: Boolean,
  userId:     { type: String, default: 'user_001' },
})
const emit = defineEmits(['update:modelValue', 'quick-recommend'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const data    = ref(null)
const loading = ref(false)
const avgScore = computed(() => {
  const h = data.value?.recent_history
  if (!h?.length) return '-'
  return (h.reduce((s, r) => s + (r.score || 0), 0) / h.length).toFixed(1)
})
const weakTags = computed(() => data.value?.weak_tags || [])

const load = async () => {
  loading.value = true
  try { data.value = await api.getMastery(props.userId) }
  catch { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

watch(visible, (v) => { if (v && !data.value) load() })
</script>

<style scoped>
.ov-row   { display: flex; gap: 12px; margin-bottom: 20px; }
.ov-item  { flex: 1; background: var(--primary-light); border-radius: 10px; padding: 14px; text-align: center; }
.ov-val   { font-size: 24px; font-weight: 700; color: var(--primary); }
.ov-label { font-size: 12px; color: var(--text-sub); margin-top: 4px; }
.section  { margin-bottom: 16px; }
.section-title { font-size: 12px; font-weight: 600; color: var(--text-sub); margin-bottom: 8px;
                 text-transform: uppercase; letter-spacing: .05em; }
.tag-row  { display: flex; flex-wrap: wrap; gap: 6px; }
</style>
