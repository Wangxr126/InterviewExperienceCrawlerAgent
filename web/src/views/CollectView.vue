<template>
  <div class="collect-page">
    <!-- 顶部：统计 + 采集入口 -->
    <div class="card top-section">
      <div class="section-header">
        <h2 class="section-title">数据采集</h2>
        <el-button size="small" :loading="statsLoading" @click="loadStats">刷新</el-button>
      </div>
      <div class="top-grid">
        <!-- 统计 -->
        <div class="stats-block">
          <div v-if="statsList.length" class="stats-grid">
            <div v-for="item in statsList" :key="item.status" class="stat-item">
              <div class="stat-val" :style="{ color: item.color }">{{ item.count }}</div>
              <div class="stat-key">{{ item.label }}</div>
              <div v-if="item.questions > 0" class="stat-sub">已提取 {{ item.questions }} 题</div>
            </div>
          </div>
          <div v-else class="stats-empty">暂无数据</div>
        </div>
        <!-- 牛客 + 小红书 -->
        <div class="crawl-block">
          <div class="crawl-row">
            <div class="crawl-card">
              <div class="crawl-label">🐮 牛客网</div>
              <el-input v-model="form.keywords" placeholder="关键词，逗号分隔" size="small" />
              <div class="crawl-meta"><span>页数</span><el-input-number v-model="form.maxPages" :min="1" :max="10" size="small" controls-position="right" /></div>
              <el-button type="primary" size="small" :loading="ncLoading" @click.prevent="crawl('nowcoder')">获取帖子</el-button>
            </div>
            <div class="crawl-card">
              <div class="crawl-label">📕 小红书</div>
              <el-input v-model="form.keywords" placeholder="关键词，逗号分隔" size="small" />
              <div class="crawl-meta"><span>条数</span><el-input-number v-model="form.xhsCount" :min="5" :max="50" size="small" controls-position="right" /></div>
              <el-button type="primary" size="small" :loading="xhsLoading" @click.prevent="crawl('xiaohongshu')">获取帖子</el-button>
              <div class="crawl-hint">需扫码登录</div>
            </div>
          </div>
          <div v-if="ncResult || xhsMsg" class="result-msg" :class="(ncResult || xhsMsg)?.ok ? 'ok' : 'err'">
            {{ ncResult?.msg || xhsMsg?.msg }}
          </div>
        </div>
      </div>
    </div>

    <!-- LLM 提取 -->
    <div class="card extract-section">
      <div class="section-header">
        <h3 class="section-title">🤖 LLM 题目提取</h3>
        <div class="extract-badges">
          <span v-if="fetchedCount > 0" class="badge badge-warn">{{ fetchedCount }} 待提取</span>
          <span v-if="errorCount > 0" class="badge badge-err">{{ errorCount }} 失败</span>
        </div>
      </div>
      <p class="extract-desc">对已爬取正文的帖子调用 LLM 提取面试题入库，后台执行</p>
      <div class="extract-actions">
        <el-button type="primary" :loading="extractLoading" @click.prevent="extractPending">
          提取未处理
        </el-button>
        <el-button type="warning" :loading="retryLoading" @click.prevent="retryErrors">重试失败</el-button>
        <el-button type="success" :loading="processLoading" @click.prevent="processQueue">同步处理</el-button>
      </div>
      <div v-if="extractMsg" class="result-msg" :class="extractMsg.ok ? 'ok' : 'err'">
        {{ extractMsg.text }}
      </div>
    </div>

    <!-- 帖子列表 -->
    <div class="card table-section">
      <div class="section-header">
        <h3 class="section-title">📋 帖子记录</h3>
        <div class="table-toolbar">
          <el-select v-model="taskFilter" placeholder="状态" clearable size="small" style="width:100px">
            <el-option label="待抓取" value="pending" />
            <el-option label="待提取" value="fetched" />
            <el-option label="已完成" value="done" />
            <el-option label="失败" value="error" />
          </el-select>
          <el-select v-model="taskPlatform" placeholder="平台" clearable size="small" style="width:90px">
            <el-option label="牛客" value="nowcoder" />
            <el-option label="小红书" value="xiaohongshu" />
          </el-select>
          <el-button size="small" @click="loadTasks">查询</el-button>
          <el-button size="small" @click="loadStats();loadTasks()">刷新</el-button>
        </div>
      </div>
      <el-table :data="tasks" size="small" class="post-table" max-height="420" stripe>
        <el-table-column label="平台" width="76">
          <template #default="{ row }">
            <el-tag :type="row.source_platform === 'xiaohongshu' ? 'danger' : 'warning'" size="small">
              {{ row.source_platform === 'xiaohongshu' ? '小红书' : '牛客' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">
            <a :href="row.source_url" target="_blank" style="color:var(--primary);text-decoration:none;font-size:13px">
              {{ row.post_title || row.source_url.slice(-30) }}
            </a>
          </template>
        </el-table-column>
        <el-table-column label="公司" prop="company" width="80" show-overflow-tooltip />
        <el-table-column label="正文" width="88" align="center">
          <template #default="{ row }">
            <el-link v-if="(row.content_len ?? 0) > 0" type="primary" :underline="false" style="font-size:12px"
                     @click="openContentDialog(row)">
              {{ row.content_len }}字
            </el-link>
            <span v-else style="color:#c0c4cc;font-size:12px">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status]" size="small">{{ STATUS_LABEL[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提取题目" width="80" align="center">
          <template #default="{ row }">
            <el-link v-if="row.questions_count > 0" type="success" :underline="false"
                     style="font-weight:700" @click="openQuestionsDialog(row)">
              {{ row.questions_count }}
            </el-link>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发现时间" prop="discovered_at" width="148" />
      </el-table>
      <div v-if="tasks.length === 0" class="table-empty">暂无记录，点击「查询」加载</div>
    </div>

    <!-- 正文内容弹窗 -->
    <el-dialog v-model="contentDialogVisible" :title="contentDialogTitle" width="560px" destroy-on-close>
      <div v-if="contentLoading" style="text-align:center;padding:24px">加载中...</div>
      <div v-else class="content-body">{{ contentDialogText || '暂无正文' }}</div>
    </el-dialog>

    <!-- 题目详情弹窗 -->
    <el-dialog v-model="questionsDialogVisible" title="已提取题目" width="640px" destroy-on-close>
      <div v-if="questionsLoading" style="text-align:center;padding:24px">加载中...</div>
      <div v-else-if="dialogQuestions.length === 0" style="color:var(--text-sub);text-align:center;padding:24px">
        暂无题目
      </div>
      <div v-else class="questions-list">
        <div v-for="(q, idx) in dialogQuestions" :key="q.q_id" class="question-item">
          <div class="q-num">{{ idx + 1 }}.</div>
          <div class="q-body">
            <div class="q-text">{{ q.question_text }}</div>
            <div v-if="q.answer_text" class="q-answer">{{ q.answer_text }}</div>
            <div v-if="q.topic_tags?.length" class="q-tags">
              <el-tag v-for="t in q.topic_tags" :key="t" size="small" style="margin-right:4px">{{ t }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const rawStats = ref({})
const tasks    = ref([])
const statsLoading   = ref(false)
const ncLoading      = ref(false)
const xhsLoading     = ref(false)
const processLoading = ref(false)
const extractLoading = ref(false)
const retryLoading   = ref(false)
const ncResult   = ref(null)
const xhsMsg     = ref(null)
const extractMsg = ref(null)
const taskFilter    = ref('')
const taskPlatform  = ref('')
const questionsDialogVisible = ref(false)
const questionsLoading      = ref(false)
const dialogQuestions       = ref([])
const contentDialogVisible  = ref(false)
const contentDialogTitle    = ref('')
const contentDialogText     = ref('')
const contentLoading        = ref(false)

const form = reactive({ keywords: '', maxPages: 2, xhsCount: 10 })

const STATUS_META = {
  pending:    { label: '待抓取', color: '#e6a23c' },
  fetched:    { label: '待提取', color: '#409eff' },
  done:       { label: '已完成', color: '#67c23a' },
  error:      { label: '失败',   color: '#f56c6c' },
  skipped:    { label: '已跳过', color: '#909399' },
}
const STATUS_LABEL = { pending:'待抓取', fetched:'待提取', done:'已完成', error:'失败', skipped:'已跳过' }
const STATUS_TAG   = { pending:'warning', fetched:'', done:'success', error:'danger', skipped:'info' }

const fetchedCount = computed(() => {
  const v = rawStats.value['fetched']
  return typeof v === 'object' ? (v.count ?? 0) : (v ?? 0)
})
const errorCount = computed(() => {
  const v = rawStats.value['error']
  return typeof v === 'object' ? (v.count ?? 0) : (v ?? 0)
})

const statsList = computed(() => {
  return Object.entries(rawStats.value).map(([status, v]) => ({
    status,
    count:     typeof v === 'object' ? (v.count ?? 0) : v,
    questions: typeof v === 'object' ? (v.questions ?? 0) : 0,
    label:     STATUS_META[status]?.label ?? status,
    color:     STATUS_META[status]?.color ?? 'var(--primary)',
  }))
})

const loadStats = async () => {
  statsLoading.value = true
  try {
    const d = await api.getCrawlerStats()
    rawStats.value = d.crawl_stats || {}
  } catch {
    ElMessage.error('获取统计失败')
  } finally {
    statsLoading.value = false
  }
}

const loadTasks = async () => {
  try {
    const d = await api.getCrawlerTasks({
      status: taskFilter.value,
      platform: taskPlatform.value,
      limit: 100,
    })
    // 将 raw_content 长度补充到每行，避免传输大字段
    tasks.value = (d.tasks || []).map(t => ({
      ...t,
      content_len: t.content_len ?? (t.raw_content ? t.raw_content.length : 0),
    }))
  } catch {
    ElMessage.error('加载任务失败')
  }
}

const crawl = async (platform) => {
  const kws = form.keywords.trim()
    ? form.keywords.split(',').map(k => k.trim()).filter(Boolean)
    : null
  const body = {
    platform,
    keywords: kws,
    max_pages: form.maxPages,
    max_notes: form.xhsCount,
    headless: false,
    process: true,
  }

  if (platform === 'xiaohongshu') {
    xhsLoading.value = true; xhsMsg.value = null
    try {
      const d = await api.triggerCrawl(body)
      xhsMsg.value = { ok: true, msg: d.message || '✅ 小红书爬取已在后台启动，请查看弹出的浏览器完成扫码' }
    } catch {
      xhsMsg.value = { ok: false, msg: '请求失败，请确认后端已启动' }
    } finally {
      xhsLoading.value = false
    }
    return
  }

  // 牛客：发现立即返回，LLM 提取在后台运行
  ncLoading.value = true; ncResult.value = null
  try {
    const d = await api.triggerCrawl(body)
    ncResult.value = {
      ok: d.status === 'ok',
      msg: d.status === 'ok'
        ? `✅ ${d.message}（LLM 提取在后台运行，稍后刷新任务列表查看）`
        : (d.detail || '爬取失败'),
    }
    if (d.status === 'ok') { await loadStats(); await loadTasks() }
  } catch (e) {
    const detail = e?.response?.data?.detail || '请求失败，请确认后端已启动'
    ncResult.value = { ok: false, msg: detail }
  } finally {
    ncLoading.value = false
  }
}

const processQueue = async () => {
  processLoading.value = true
  try {
    const d = await api.processQueue(20)
    ElMessage.success(`处理完成，入库 ${d.questions_added ?? 0} 道题目`)
    await loadStats(); await loadTasks()
  } catch {
    ElMessage.error('处理队列失败')
  } finally {
    processLoading.value = false
  }
}

const extractPending = async () => {
  extractLoading.value = true
  extractMsg.value = null
  try {
    const d = await api.extractPending(30)
    extractMsg.value = { ok: true, text: `✅ ${d.message}` }
    await loadStats(); await loadTasks()
  } catch {
    extractMsg.value = { ok: false, text: '启动失败，请确认后端已运行' }
  } finally {
    extractLoading.value = false
  }
}

const openContentDialog = async (row) => {
  if (!row.task_id) return
  contentDialogVisible.value = true
  contentDialogTitle.value = row.post_title || '帖子正文'
  contentLoading.value = true
  contentDialogText.value = ''
  try {
    const d = await api.getCrawlerTaskDetail(row.task_id)
    contentDialogText.value = d.raw_content || ''
  } catch {
    ElMessage.error('加载正文失败')
  } finally {
    contentLoading.value = false
  }
}

const openQuestionsDialog = async (row) => {
  if (!row.task_id || row.questions_count <= 0) return
  questionsDialogVisible.value = true
  questionsLoading.value = true
  dialogQuestions.value = []
  try {
    const d = await api.getTaskQuestions(row.task_id)
    dialogQuestions.value = d.questions || []
  } catch {
    ElMessage.error('加载题目失败')
  } finally {
    questionsLoading.value = false
  }
}

const retryErrors = async () => {
  retryLoading.value = true
  extractMsg.value = null
  try {
    const d = await api.retryErrors(30)
    extractMsg.value = { ok: true, text: `🔄 ${d.message}` }
    await loadStats(); await loadTasks()
  } catch {
    extractMsg.value = { ok: false, text: '重试请求失败，请确认后端已运行' }
  } finally {
    retryLoading.value = false
  }
}

onMounted(() => { loadStats(); loadTasks() })
</script>

<style scoped>
.collect-page { padding: 0 4px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-title { font-size: 16px; font-weight: 600; color: var(--text-main); margin: 0; }
.top-section .section-title { font-size: 18px; }

/* 顶部：统计 + 采集 */
.top-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }
.stats-block { background: var(--bg); border-radius: 10px; padding: 16px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(70px, 1fr)); gap: 10px; }
.stat-item { background: var(--card-bg); border-radius: 8px; padding: 12px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-val { font-size: 22px; font-weight: 700; }
.stat-key { font-size: 12px; color: var(--text-sub); margin-top: 4px; }
.stat-sub { font-size: 11px; color: var(--text-sub); margin-top: 2px; }
.stats-empty { color: var(--text-sub); font-size: 13px; text-align: center; padding: 12px; }

.crawl-block { display: flex; flex-direction: column; gap: 12px; }
.crawl-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.crawl-card { background: var(--bg); border-radius: 10px; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.crawl-label { font-size: 14px; font-weight: 600; color: var(--text-main); }
.crawl-meta { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-sub); }
.crawl-meta span { flex-shrink: 0; }
.crawl-hint { font-size: 11px; color: var(--text-sub); }
.crawl-card .el-input-number { width: 90px; }

/* LLM 提取 */
.extract-section { padding: 20px 24px; }
.extract-desc { font-size: 13px; color: var(--text-sub); margin: -8px 0 14px 0; }
.extract-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.extract-badges { display: flex; gap: 8px; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 10px; }
.badge-warn { background: #fef3c7; color: #b45309; }
.badge-err { background: #fee2e2; color: #b91c1c; }

/* 表格 */
.table-section { padding: 20px 24px; }
.table-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.post-table { border-radius: 8px; overflow: hidden; }
.post-table :deep(.el-table__header th) { background: var(--bg) !important; font-weight: 600; font-size: 12px; }
.post-table :deep(.el-table__row td) { font-size: 13px; }
.post-table :deep(.el-table__body tr:hover > td) { background: var(--primary-light) !important; }
.table-empty { text-align: center; color: var(--text-sub); padding: 32px 20px; font-size: 14px; }

.result-msg { padding: 10px 14px; border-radius: 8px; font-size: 13px; margin-top: 12px; }
.result-msg.ok { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
.result-msg.err { background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5; }

.questions-list { max-height: 400px; overflow-y: auto; }
.question-item { display: flex; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.question-item:last-child { border-bottom: none; }
.q-num { flex-shrink: 0; font-weight: 600; color: var(--primary); }
.q-body { flex: 1; min-width: 0; }
.q-text { font-size: 14px; line-height: 1.5; margin-bottom: 6px; }
.q-answer { font-size: 13px; color: var(--text-sub); background: var(--bg); padding: 8px; border-radius: 6px; margin-top: 6px; white-space: pre-wrap; }
.q-tags { margin-top: 8px; }
.content-body { max-height: 400px; overflow-y: auto; font-size: 14px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
</style>
