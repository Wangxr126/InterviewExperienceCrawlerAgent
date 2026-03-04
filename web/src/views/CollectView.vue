<template>
  <div>
    <!-- 统计概览 -->
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center">
        📊 爬取统计
        <el-button size="small" :loading="statsLoading" @click="loadStats">刷新</el-button>
      </div>
      <div v-if="statsList.length" class="stats-grid">
        <div v-for="item in statsList" :key="item.status" class="stat-item">
          <div class="stat-val" :style="{ color: item.color }">{{ item.count }}</div>
          <div class="stat-key">{{ item.label }}</div>
          <div v-if="item.questions > 0" class="stat-sub">已提取 {{ item.questions }} 题</div>
        </div>
      </div>
      <div v-else style="color:var(--text-sub);font-size:14px">暂无统计数据，点击「刷新」加载</div>
    </div>

    <!-- 牛客采集 -->
    <div class="card">
      <div class="card-title">🐮 牛客网面经采集</div>
      <div class="form-grid">
        <div>
          <div class="label">关键词（逗号分隔）</div>
          <el-input v-model="form.keywords" placeholder="后端,Java,Python" />
        </div>
        <div>
          <div class="label">爬取页数</div>
          <el-input-number v-model="form.maxPages" :min="1" :max="10" />
        </div>
      </div>
      <el-button type="primary" :loading="ncLoading" native-type="button"
                 @click.prevent="crawl('nowcoder')">
        立即获取帖子
      </el-button>
      <div v-if="ncResult" class="result-msg" :class="ncResult.ok ? 'ok' : 'err'">
        {{ ncResult.msg }}
      </div>
    </div>

    <!-- 小红书采集 -->
    <div class="card">
      <div class="card-title">📕 小红书面经采集</div>
      <el-alert type="info" :closable="false" style="margin-bottom:14px">
        点击后会弹出浏览器窗口，请在窗口中完成扫码登录后爬取自动进行。
        首次登录后状态会保存，后续定时任务无需再扫码。
      </el-alert>
      <div class="form-grid">
        <div>
          <div class="label">关键词（逗号分隔）</div>
          <el-input v-model="form.keywords" placeholder="后端面经,Java面试" />
        </div>
        <div>
          <div class="label">最多获取帖子数</div>
          <el-input-number v-model="form.xhsCount" :min="5" :max="50" />
        </div>
      </div>
      <el-button type="primary" :loading="xhsLoading" native-type="button"
                 @click.prevent="crawl('xiaohongshu')">
        立即获取帖子（弹出浏览器）
      </el-button>
      <div v-if="xhsMsg" class="result-msg" :class="xhsMsg.ok ? 'ok' : 'err'">
        {{ xhsMsg.msg }}
      </div>
    </div>

    <!-- 题目提取（LLM 处理） -->
    <div class="card">
      <div class="card-title">🤖 LLM 题目提取</div>
      <p style="color:var(--text-sub);font-size:13px;margin-bottom:14px">
        对已爬取正文（<code>fetched</code> 状态）的帖子，调用 LLM 提取面试题入库。<br>
        本地模型每帖约需 1-3 分钟，任务在后台执行，完成后刷新任务列表查看结果。
      </p>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <el-button type="primary" :loading="extractLoading" native-type="button"
                   @click.prevent="extractPending">
          🚀 提取未处理帖子（后台异步）
        </el-button>
        <el-button type="warning" :loading="retryLoading" native-type="button"
                   @click.prevent="retryErrors">
          🔄 重试失败帖子
        </el-button>
        <el-button type="success" :loading="processLoading" native-type="button"
                   @click.prevent="processQueue">
          ⚙️ 同步处理队列（阻塞等待）
        </el-button>
        <span v-if="fetchedCount > 0" style="color:#e6a23c;font-size:13px">
          {{ fetchedCount }} 条待提取
        </span>
        <span v-if="errorCount > 0" style="color:#f56c6c;font-size:13px">
          {{ errorCount }} 条失败（可重试）
        </span>
      </div>
      <div v-if="extractMsg" class="result-msg" :class="extractMsg.ok ? 'ok' : 'err'" style="margin-top:12px">
        {{ extractMsg.text }}
      </div>
    </div>

    <!-- 帖子列表 -->
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center">
        📋 帖子记录
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <el-select v-model="taskFilter" placeholder="状态" clearable style="width:110px">
            <el-option label="待抓取" value="pending" />
            <el-option label="待提取" value="fetched" />
            <el-option label="已完成" value="done" />
            <el-option label="失败" value="error" />
          </el-select>
          <el-select v-model="taskPlatform" placeholder="平台" clearable style="width:100px">
            <el-option label="牛客" value="nowcoder" />
            <el-option label="小红书" value="xiaohongshu" />
          </el-select>
          <el-button size="small" @click="loadTasks">查询</el-button>
          <el-button size="small" @click="loadStats();loadTasks()">刷新</el-button>
        </div>
      </div>
      <el-table :data="tasks" size="small" style="width:100%" max-height="460">
        <el-table-column label="平台" width="76">
          <template #default="{ row }">
            <el-tag :type="row.source_platform === 'xiaohongshu' ? 'danger' : 'warning'" size="small">
              {{ row.source_platform === 'xiaohongshu' ? '小红书' : '牛客' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <a :href="row.source_url" target="_blank" style="color:var(--primary);text-decoration:none;font-size:13px">
              {{ row.post_title || row.source_url.slice(-30) }}
            </a>
          </template>
        </el-table-column>
        <el-table-column label="公司" prop="company" width="80" show-overflow-tooltip />
        <el-table-column label="正文" width="72" align="center">
          <template #default="{ row }">
            <span :style="{ color: row.content_len > 100 ? '#67c23a' : '#909399', fontSize: '12px' }">
              {{ row.content_len ? row.content_len + '字' : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status]" size="small">{{ STATUS_LABEL[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提取题目" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.questions_count > 0" style="color:#67c23a;font-weight:700">{{ row.questions_count }}</span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发现时间" prop="discovered_at" width="148" />
      </el-table>
      <div v-if="tasks.length === 0" style="text-align:center;color:var(--text-sub);padding:20px;font-size:14px">
        暂无记录，点击「查询」加载
      </div>
    </div>
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
.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px,1fr)); gap: 12px; margin-bottom: 4px; }
.stat-item  { background: var(--bg); border-radius: 8px; padding: 12px; text-align: center; }
.stat-val   { font-size: 26px; font-weight: 700; }
.stat-key   { font-size: 13px; color: var(--text-sub); margin-top: 4px; }
.stat-sub   { font-size: 11px; color: var(--text-sub); margin-top: 2px; }
.form-grid  { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
.label      { font-size: 13px; color: var(--text-sub); margin-bottom: 6px; }
.result-msg { margin-top: 12px; padding: 10px 14px; border-radius: 8px; font-size: 14px; }
.result-msg.ok  { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
.result-msg.err { background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5; }
</style>
