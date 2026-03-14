// 统一 API 调用层
// 开发环境：Vite proxy 转发到 localhost:8000
// 生产环境：FastAPI 静态文件服务，相对路径 /api 即可
const BASE = import.meta.env.DEV ? '' : ''
// 开发时若代理仍缓冲 SSE，可在 .env 设置 VITE_STREAM_DIRECT=true 直连后端验证流式
const STREAM_BASE = import.meta.env.VITE_STREAM_DIRECT === 'true' ? 'http://localhost:8000' : ''

export const api = {
  // ── 配置 ──────────────────────────────────────────────
  async getConfig() {
    const r = await fetch(`${BASE}/api/config`)
    return r.json()
  },

  // ── 对话历史 ───────────────────────────────────────────
  async getChatHistory(userId) {
    const r = await fetch(`${BASE}/api/user/${userId}/chat/history`)
    return r.json()
  },

  // ── 题库 ──────────────────────────────────────────────
  async getMeta() {
    const r = await fetch(`${BASE}/api/questions/meta`)
    return r.json()
  },

  async getQuestions(params = {}) {
    const p = new URLSearchParams()
    if (params.company) p.set('company', params.company)
    if (params.difficulty) p.set('difficulty', params.difficulty)
    if (params.question_type) p.set('question_type', params.question_type)
    if (params.tag) p.set('tag', params.tag)
    if (params.keyword) p.set('keyword', params.keyword)
    if (params.source_platform) p.set('source_platform', params.source_platform)
    if (params.rand) p.set('rand', 'true')
    if (params.page != null) p.set('page', String(params.page))
    if (params.page_size != null) p.set('page_size', String(params.page_size))
    if (params.sort_by) p.set('sort_by', params.sort_by)
    if (params.sort_order) p.set('sort_order', params.sort_order)
    if (params.user_id) p.set('user_id', params.user_id)
    const r = await fetch(`${BASE}/api/questions?${p}`)
    return r.json()
  },

  // ── 答题 ──────────────────────────────────────────────
  async submitAnswer(payload) {
    const r = await fetch(`${BASE}/api/submit_answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await r.json()
    if (!r.ok) {
      const msg = data?.detail || (typeof data?.detail === 'string' ? data.detail : JSON.stringify(data))
      throw new Error(msg)
    }
    return data
  },

  // ── 对话（普通，用于兜底）──────────────────────────────
  async chat(payload, signal) {
    const r = await fetch(`${BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
    return r.json()
  },

  // ── 对话流式 SSE ──────────────────────────────────────
  // 返回 Response 对象，由 ChatView 自行读取 body stream
  async chatStream(payload, signal) {
    return fetch(`${STREAM_BASE || BASE}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',  // 明确请求 SSE，避免代理/中间件缓冲
      },
      body: JSON.stringify(payload),
      signal,
    })
  },

  // ── 用户掌握度 ────────────────────────────────────────
  async getMastery(userId) {
    const r = await fetch(`${BASE}/api/user/${userId}/mastery`)
    return r.json()
  },

  // ── 收录 ──────────────────────────────────────────────
  async ingest(payload) {
    const r = await fetch(`${BASE}/api/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return r.json()
  },

  // ── 爬虫 ──────────────────────────────────────────────
  async getCrawlerStats() {
    const r = await fetch(`${BASE}/api/crawler/stats`)
    return r.json()
  },

  async triggerCrawl(payload) {
    const r = await fetch(`${BASE}/api/crawler/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return r.json()
  },

  async processQueue(batchSize = null) {
    const url = batchSize ? `${BASE}/api/crawler/process?batch_size=${batchSize}` : `${BASE}/api/crawler/process`
    const r = await fetch(url, {
      method: 'POST',
    })
    return r.json()
  },

  async extractPending(batchSize = null) {
    const url = batchSize ? `${BASE}/api/crawler/extract-pending?batch_size=${batchSize}` : `${BASE}/api/crawler/extract-pending`
    const r = await fetch(url, {
      method: 'POST',
    })
    return r.json()
  },

  async retryErrors(batchSize = null) {
    const url = batchSize ? `${BASE}/api/crawler/retry-errors?batch_size=${batchSize}` : `${BASE}/api/crawler/retry-errors`
    const r = await fetch(url, {
      method: 'POST',
    })
    return r.json()
  },

  async reExtractAll(batchSize = null) {
    const url = batchSize ? `${BASE}/api/crawler/re-extract-all?batch_size=${batchSize}` : `${BASE}/api/crawler/re-extract-all`
    const r = await fetch(url, {
      method: 'POST',
    })
    return r.json()
  },

  async cleanData(batchSize = null) {
    const url = batchSize ? `${BASE}/api/crawler/clean-data?batch_size=${batchSize}` : `${BASE}/api/crawler/clean-data`
    const r = await fetch(url, {
      method: 'POST',
    })
    return r.json()
  },

  async getExtractionStatus() {
    const r = await fetch(`${BASE}/api/crawler/extraction-status`)
    return r.json()
  },

  /** 获取当前提取任务的最新推理过程（Miner Agent 的 Thought/工具调用） */
  async getExtractionTrace() {
    const r = await fetch(`${BASE}/api/crawler/extraction-trace`)
    return r.json()
  },

  async getCrawlerKeywords() {
    const r = await fetch(`${BASE}/api/crawler/keywords`)
    return r.json()
  },

  async getCrawlerTasks(params = {}) {
    const p = new URLSearchParams()
    if (params.status) p.set('status', params.status)
    if (params.platform) p.set('platform', params.platform)
    if (params.keyword) p.set('keyword', params.keyword)
    if (params.title) p.set('title', params.title)
    p.set('limit', params.limit ?? '20')
    if (params.offset != null) p.set('offset', String(params.offset))
    if (params.sort_by) p.set('sort_by', params.sort_by)
    if (params.sort_order) p.set('sort_order', params.sort_order)
    const r = await fetch(`${BASE}/api/crawler/tasks?${p}`)
    return r.json()
  },

  async clearAllCrawlData() {
    const r = await fetch(`${BASE}/api/crawler/clear-all`, { method: 'POST' })
    return r.json()
  },

  async getTaskQuestions(taskId) {
    const r = await fetch(`${BASE}/api/crawler/tasks/${taskId}/questions`)
    return r.json()
  },

  async getCrawlerTaskDetail(taskId) {
    const r = await fetch(`${BASE}/api/crawler/tasks/${taskId}`)
    return r.json()
  },

  async checkXhsLogin() {
    const r = await fetch(`${BASE}/api/crawler/xhs/login-status`)
    return r.json()
  },

  async refetchXhsBody(taskId) {
    const r = await fetch(`${BASE}/api/crawler/refetch-xhs-body?task_id=${encodeURIComponent(taskId)}`, {
      method: 'POST',
    })
    return r.json()
  },

  /** 对单个帖子重新执行 LLM 提取（OCR + MinerAgent），需正文≥50字 */
  async reExtractSingle(taskId) {
    const r = await fetch(`${BASE}/api/crawler/tasks/${taskId}/re-extract`, {
      method: 'POST',
    })
    return r.json()
  },

  /** 对选中的多个帖子批量重新提取，后台异步执行 */
  async reExtractBatch(taskIds) {
    const r = await fetch(`${BASE}/api/crawler/tasks/re-extract-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_ids: taskIds }),
    })
    return r.json()
  },

  /** 删除单个帖子及关联数据 */
  async deleteTask(taskId) {
    const r = await fetch(`${BASE}/api/crawler/tasks/${taskId}`, { method: 'DELETE' })
    return r.json()
  },

  /** 批量删除帖子及关联数据 */
  async deleteTasksBatch(taskIds) {
    const r = await fetch(`${BASE}/api/crawler/tasks/delete-batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_ids: taskIds }),
    })
    return r.json()
  },

  // ── 定时任务管理 ──────────────────────────────────────
  async getSchedulerJobs(params = '') {
    const r = await fetch(`${BASE}/api/scheduler/jobs${params}`)
    return r.json()
  },

  async getSchedulerJob(jobId) {
    const r = await fetch(`${BASE}/api/scheduler/jobs/${jobId}`)
    return r.json()
  },

  async createSchedulerJob(payload) {
    const r = await fetch(`${BASE}/api/scheduler/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return r.json()
  },

  async updateSchedulerJob(jobId, payload) {
    const r = await fetch(`${BASE}/api/scheduler/jobs/${jobId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return r.json()
  },

  async deleteSchedulerJob(jobId) {
    const r = await fetch(`${BASE}/api/scheduler/jobs/${jobId}`, {
      method: 'DELETE',
    })
    return r.json()
  },

  async enableSchedulerJob(jobId) {
    const r = await fetch(`${BASE}/api/scheduler/jobs/${jobId}/enable`, {
      method: 'POST',
    })
    return r.json()
  },

  async disableSchedulerJob(jobId) {
    const r = await fetch(`${BASE}/api/scheduler/jobs/${jobId}/disable`, {
      method: 'POST',
    })
    return r.json()
  },

  async runSchedulerJob(jobId) {
    const r = await fetch(`${BASE}/api/scheduler/jobs/${jobId}/run`, {
      method: 'POST',
    })
    return r.json()
  },

  async getJobTypes() {
    const r = await fetch(`${BASE}/api/scheduler/job-types`)
    return r.json()
  },

  async getScheduleExamples() {
    const r = await fetch(`${BASE}/api/scheduler/schedule-examples`)
    return r.json()
  },
}
