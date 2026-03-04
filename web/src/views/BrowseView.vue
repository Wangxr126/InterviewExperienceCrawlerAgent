<template>
  <div>
    <div class="card">
      <div class="card-title">📚 题库浏览</div>

      <!-- 筛选行 -->
      <div class="filter-row">
        <el-select v-model="filters.company" placeholder="公司" clearable filterable>
          <el-option v-for="c in props.meta.companies" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.difficulty" placeholder="难度" clearable>
          <el-option label="简单" value="easy" />
          <el-option label="中等" value="medium" />
          <el-option label="困难" value="hard" />
        </el-select>
        <el-select v-model="filters.tag" placeholder="技术标签" clearable filterable>
          <el-option v-for="t in props.meta.tags" :key="t" :label="t" :value="t" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="关键词搜索" clearable
                  @keyup.enter="loadQuestions" />
        <el-select v-model="filters.source_platform" placeholder="来源平台" clearable>
          <el-option label="牛客网" value="nowcoder" />
          <el-option label="小红书" value="xiaohongshu" />
        </el-select>
        <el-button type="primary" @click="loadQuestions" :loading="loading">🔍 搜索</el-button>
        <el-button @click="loadRandom">🎲 随机一题</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <!-- 统计 -->
      <div class="stats-bar">
        共找到 <strong>{{ questions.length }}</strong> 道题
        <span v-if="props.meta.total"> · 题库总计 {{ props.meta.total }} 题</span>
      </div>

      <!-- 题目网格 -->
      <div v-if="questions.length > 0" class="question-grid">
        <div v-for="q in questions" :key="q.q_id" class="q-card" @click="openDialog(q)">
          <div class="q-card-header">
            <div class="q-text">{{ q.question_text }}</div>
            <span class="difficulty-badge" :class="`diff-${q.difficulty || 'medium'}`">
              {{ diffLabel(q.difficulty) }}
            </span>
          </div>
          <div class="q-meta">
            <span v-if="q.company" class="meta-chip">🏢 {{ q.company }}</span>
            <span v-if="q.position" class="meta-chip">💼 {{ q.position }}</span>
            <span v-if="q.source_platform" class="meta-chip">{{ platformLabel(q.source_platform) }}</span>
            <span v-for="tag in (q.topic_tags||[]).slice(0,3)" :key="tag" class="tag-chip">{{ tag }}</span>
          </div>
        </div>
      </div>
      <div v-else-if="!loading" class="empty-state">
        <div class="empty-icon">📭</div>
        <div>暂无题目，先去「收录面经」或「数据采集」添加内容吧</div>
      </div>
      <div v-if="loading" class="loading-center">
        <el-icon class="is-loading" style="font-size:32px;color:var(--primary)"><Loading /></el-icon>
      </div>
    </div>

    <!-- 题目详情弹窗 -->
    <QuestionDialog v-model="dialogVisible" :question="selectedQ"
                    @send-to-chat="$emit('send-to-chat', $event)" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import QuestionDialog from '../components/QuestionDialog.vue'

const props = defineProps({
  meta: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['send-to-chat'])

const filters = reactive({ company: '', difficulty: '', tag: '', keyword: '', source_platform: '' })
const questions = ref([])
const loading   = ref(false)
const dialogVisible = ref(false)
const selectedQ     = ref(null)

const diffLabel     = (d) => ({ easy: '简单', medium: '中等', hard: '困难' }[d] || '中等')
const platformLabel = (p) => ({ nowcoder: '牛客', xiaohongshu: '小红书' }[p] || p)

const loadQuestions = async () => {
  loading.value = true
  try {
    const d = await api.getQuestions(filters)
    questions.value = d.questions || []
  } catch {
    ElMessage.error('加载题目失败，请检查后端是否已启动')
  } finally {
    loading.value = false
  }
}

const loadRandom = async () => {
  loading.value = true
  try {
    const d = await api.getQuestions({ ...filters, rand: true, limit: 1 })
    questions.value = d.questions || []
    if (questions.value.length) openDialog(questions.value[0])
  } catch {
    ElMessage.error('随机取题失败')
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  Object.assign(filters, { company: '', difficulty: '', tag: '', keyword: '', source_platform: '' })
  loadQuestions()
}

const openDialog = (q) => {
  selectedQ.value = q
  dialogVisible.value = true
}

onMounted(loadQuestions)
</script>

<style scoped>
.filter-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.filter-row .el-select { width: 130px; }
.stats-bar { color: var(--text-sub); font-size: 13px; margin-bottom: 14px; }

.question-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.q-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow .15s, border-color .15s;
}
.q-card:hover { box-shadow: 0 4px 16px rgba(91,110,245,.12); border-color: var(--primary); }
.q-card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.q-text { font-size: 14px; line-height: 1.5; flex: 1; display: -webkit-box;
          -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.difficulty-badge { font-size: 11px; padding: 2px 8px; border-radius: 12px; white-space: nowrap; flex-shrink: 0; }
.diff-easy   { background: #d1fae5; color: #065f46; }
.diff-medium { background: #fef3c7; color: #92400e; }
.diff-hard   { background: #fee2e2; color: #991b1b; }
.q-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.meta-chip { font-size: 11px; background: var(--primary-light); color: var(--primary);
             padding: 2px 8px; border-radius: 10px; }
.tag-chip  { font-size: 11px; background: #f0fdf4; color: #166534;
             padding: 2px 8px; border-radius: 10px; }
.empty-state { text-align: center; padding: 60px 20px; color: var(--text-sub); }
.empty-icon  { font-size: 48px; margin-bottom: 16px; }
.loading-center { text-align: center; padding: 40px; }
</style>
