<template>
  <div>
    <div class="card">
      <div class="card-title">📚 题库浏览</div>

      <!-- 筛选行 -->
      <div class="filter-row">
        <el-select v-model="filters.question_type" placeholder="题目类型" clearable>
          <el-option v-for="t in (props.meta.question_types || ['技术题','算法题','系统设计','行为题','HR问题'])" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filters.company" placeholder="公司" clearable filterable>
          <el-option v-for="c in (props.meta.companies || []).filter(c => c)" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.difficulty" placeholder="难度" clearable>
          <el-option label="简单" value="easy" />
          <el-option label="中等" value="medium" />
          <el-option label="困难" value="hard" />
        </el-select>
        <el-select v-model="filters.tag" placeholder="技术标签" clearable filterable>
          <el-option v-for="t in (props.meta.tags || []).filter(t => t)" :key="t" :label="t" :value="t" />
        </el-select>
        <el-input v-model="filters.keyword" placeholder="关键词搜索" clearable
                  @keyup.enter="onSearch" />
        <el-select v-model="filters.source_platform" placeholder="来源平台" clearable>
          <el-option label="牛客网" value="nowcoder" />
          <el-option label="小红书" value="xiaohongshu" />
        </el-select>
        <el-button type="primary" @click="onSearch" :loading="loading">🔍 搜索</el-button>
        <el-button @click="loadRandom">🎲 随机一题</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <!-- 统计 + 每页条数 -->
      <div class="stats-bar">
        <span>共找到 <strong>{{ pagination.total }}</strong> 道题
          <span v-if="props.meta.total"> · 题库总计 {{ props.meta.total }} 题</span>
        </span>
        <div class="page-size-selector">
          <span>每页</span>
          <el-select v-model="pagination.pageSize" size="small" style="width:80px;margin:0 6px"
                     @change="onPageSizeChange">
            <el-option :value="10" label="10 题" />
            <el-option :value="20" label="20 题" />
            <el-option :value="50" label="50 题" />
            <el-option :value="100" label="100 题" />
          </el-select>
          <span>题</span>
        </div>
      </div>

      <!-- 列头排序栏 -->
      <div class="col-header-bar">
        <span class="col-header-label">排序：</span>
        <button
          v-for="col in SORT_COLUMNS"
          :key="col.key"
          class="col-sort-btn"
          :class="{ active: sortBy === col.key }"
          @click="toggleSort(col.key)"
        >
          {{ col.label }}
          <span class="col-sort-icon">
            <span :class="['arrow', sortBy === col.key && sortOrder === 'asc' ? 'on' : '']">↑</span><span :class="['arrow', sortBy === col.key && sortOrder === 'desc' ? 'on' : '']">↓</span>
          </span>
        </button>
      </div>

      <!-- 题目网格 -->
      <div v-if="questions.length > 0" class="question-grid">
        <div v-for="q in questions" :key="q.q_id" class="q-card" @click="openDialog(q)">
          <div class="q-card-header">
            <div class="q-text">{{ q.question_text }}</div>
            <div class="q-card-badges">
              <span class="type-badge" :class="questionTypeClass(q.question_type)">
                {{ q.question_type || '技术题' }}
              </span>
              <span class="difficulty-badge" :class="`diff-${q.difficulty || 'medium'}`">
                {{ diffLabel(q.difficulty) }}
              </span>
            </div>
          </div>
          <div class="q-meta">
            <span v-if="q.last_score != null" class="score-chip" :class="q.last_score >= 3 ? 'score-ok' : 'score-low'">
              📝 {{ q.last_score }}/5
            </span>
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

      <!-- 分页控件 -->
      <div v-if="pagination.total > 0 && !loading" class="pagination-bar">
        <div class="pagination-info">
          共 <strong>{{ pagination.total }}</strong> 道题 · 
          第 <strong>{{ pagination.page }}</strong> / {{ pagination.totalPages }} 页 ·
          每页 <strong>{{ pagination.pageSize }}</strong> 题
        </div>
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          :pager-count="11"
          layout="prev, pager, next, jumper"
          background
          @current-change="onPageChange"
        />
      </div>
    </div>

    <!-- 题目详情弹窗 -->
    <QuestionDialog v-model="dialogVisible" :question="selectedQ"
                    :user-id="userId"
                    @send-to-chat="handleSendToChat"
                    @submit-complete="handleSubmitComplete" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '../api.js'
import QuestionDialog from '../components/QuestionDialog.vue'

const props = defineProps({
  meta: { type: Object, default: () => ({}) },
  isActive: { type: Boolean, default: false },
  userId: { type: String, default: 'user_001' },
})
const emit = defineEmits(['send-to-chat', 'submit-complete'])

const filters = reactive({ question_type: '', company: '', difficulty: '', tag: '', keyword: '', source_platform: '' })
const pagination = reactive({ page: 1, pageSize: 20, total: 0, totalPages: 1 })
const sortBy = ref('created_at')
const sortOrder = ref('desc')

const SORT_COLUMNS = [
  { key: 'created_at',    label: '时间' },
  { key: 'difficulty',    label: '难度' },
  { key: 'company',       label: '公司' },
  { key: 'question_type', label: '类型' },
  { key: 'question_text', label: '题目' },
]

const toggleSort = (colKey) => {
  if (sortBy.value === colKey) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = colKey
    sortOrder.value = 'desc'
  }
  pagination.page = 1
  loadQuestions(1)
}
const questions = ref([])
const loading   = ref(false)
const dialogVisible = ref(false)
const selectedQ     = ref(null)

const diffLabel     = (d) => ({ easy: '简单', medium: '中等', hard: '困难' }[d] || '中等')
const platformLabel = (p) => ({ nowcoder: '牛客', xiaohongshu: '小红书' }[p] || p)
const questionTypeClass = (t) => {
  const m = { '技术题': 'type-tech', '算法题': 'type-algo', '系统设计': 'type-design', '行为题': 'type-behavior', 'HR问题': 'type-hr' }
  return m[t] || 'type-tech'
}

const loadQuestions = async (page = pagination.page) => {
  loading.value = true
  try {
    console.log(`📖 加载第 ${page} 页，每页 ${pagination.pageSize} 题`)
    const d = await api.getQuestions({
      ...filters,
      page,
      page_size: pagination.pageSize,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
      user_id: props.userId || undefined,
    })
    console.log(`📖 后端返回: total=${d.total}, page=${d.page}, total_pages=${d.total_pages}, questions=${d.questions?.length}`)
    questions.value = d.questions || []
    pagination.total = d.total ?? 0
    pagination.totalPages = d.total_pages ?? 1
    pagination.page = d.page ?? page
    console.log(`📖 前端状态: pagination.page=${pagination.page}, pagination.total=${pagination.total}, pagination.totalPages=${pagination.totalPages}`)
  } catch (e) {
    console.error('❌ 加载题目失败:', e)
    ElMessage.error('加载题目失败，请检查后端是否已启动')
  } finally {
    loading.value = false
  }
}

// 搜索时重置到第一页
const onSearch = () => {
  pagination.page = 1
  loadQuestions(1)
}

// 切换页码
const onPageChange = (newPage) => {
  console.log(`🔄 页码变化: ${pagination.page} → ${newPage}`)
  pagination.page = newPage
  loadQuestions(newPage)
}

// 切换每页条数时重置到第一页
const onPageSizeChange = () => {
  pagination.page = 1
  loadQuestions(1)
}

const loadRandom = async () => {
  loading.value = true
  try {
    const d = await api.getQuestions({ ...filters, rand: true, user_id: props.userId || undefined })
    questions.value = d.questions || []
    pagination.total = d.total ?? 0
    pagination.totalPages = 1
    pagination.page = 1
    if (questions.value.length) openDialog(questions.value[0])
  } catch {
    ElMessage.error('随机取题失败')
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  Object.assign(filters, { question_type: '', company: '', difficulty: '', tag: '', keyword: '', source_platform: '' })
  pagination.page = 1
  loadQuestions(1)
}

const openDialog = (q) => {
  selectedQ.value = q
  dialogVisible.value = true
}

const handleSendToChat = (event) => {
  emit('send-to-chat', event)
}

const handleSubmitComplete = (payload) => {
  emit('submit-complete', payload)
}

onMounted(() => loadQuestions(1))

watch(() => props.isActive, (newVal, oldVal) => {
  if (newVal && !oldVal) {
    loadQuestions(pagination.page)
  }
})
</script>

<style scoped>
.filter-row { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.filter-row .el-select { width: 110px; }
.filter-row .el-input { width: 140px; }
.filter-row .el-button { padding: 8px 12px; }
.stats-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--text-sub);
  font-size: 13px;
  margin-bottom: 8px;
}
.col-header-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding: 6px 2px;
  margin-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.col-header-label {
  font-size: 11px;
  color: var(--text-sub);
  margin-right: 2px;
}
.col-sort-btn {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-sub);
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
  white-space: nowrap;
  line-height: 1.6;
}
.col-sort-btn:hover {
  background: var(--primary-light);
  color: var(--primary);
  border-color: var(--primary);
}
.col-sort-btn.active {
  background: var(--primary-light);
  color: var(--primary);
  border-color: var(--primary);
  font-weight: 600;
}
.col-sort-icon {
  display: inline-flex;
  flex-direction: column;
  line-height: 1;
  font-size: 9px;
  margin-left: 1px;
  gap: 0;
}
.col-sort-icon .arrow {
  color: var(--border);
  line-height: 1.1;
}
.col-sort-icon .arrow.on {
  color: var(--primary);
}
.page-size-selector { display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--text-sub); }

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
.q-text { font-size: 14px; line-height: 1.5; flex: 1; min-width: 0; display: -webkit-box;
          -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.q-card-badges { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.type-badge { font-size: 10px; padding: 2px 6px; border-radius: 8px; white-space: nowrap; font-weight: 600; }
.type-tech    { background: #dbeafe; color: #1d4ed8; }
.type-algo    { background: #e9d5ff; color: #6b21a8; }
.type-design  { background: #ccfbf1; color: #0f766e; }
.type-behavior{ background: #fed7aa; color: #c2410c; }
.type-hr      { background: #e5e7eb; color: #4b5563; }
.difficulty-badge { font-size: 11px; padding: 2px 8px; border-radius: 12px; white-space: nowrap; }
.diff-easy   { background: #d1fae5; color: #065f46; }
.diff-medium { background: #fef3c7; color: #92400e; }
.diff-hard   { background: #fee2e2; color: #991b1b; }
.q-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.meta-chip { font-size: 11px; background: var(--primary-light); color: var(--primary);
             padding: 2px 8px; border-radius: 10px; }
.score-chip { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }
.score-chip.score-ok  { background: #dcfce7; color: #166534; }
.score-chip.score-low { background: #fee2e2; color: #991b1b; }
.tag-chip  { font-size: 11px; background: #f0fdf4; color: #166534;
             padding: 2px 8px; border-radius: 10px; }
.empty-state { text-align: center; padding: 60px 20px; color: var(--text-sub); }
.empty-icon  { font-size: 48px; margin-bottom: 16px; }
.loading-center { text-align: center; padding: 40px; }
.pagination-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.pagination-info {
  font-size: 13px;
  color: var(--text-sub);
  text-align: center;
}
</style>
