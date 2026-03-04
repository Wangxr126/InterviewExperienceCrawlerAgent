// 统一 API 调用层
// 开发环境：Vite proxy 转发到 localhost:8000
// 生产环境：FastAPI 静态文件服务，相对路径 /api 即可
const BASE = import.meta.env.DEV ? '' : ''

export const api = {
  // ── 题库 ──────────────────────────────────────────────
  async getMeta() {
    const r = await fetch(`${BASE}/api/questions/meta`)
    return r.json()
  },

  async getQuestions(params = {}) {
    const p = new URLSearchParams()
    if (params.company) p.set('company', params.company)
    if (params.difficulty) p.set('difficulty', params.difficulty)
    if (params.tag) p.set('tag', params.tag)
    if (params.keyword) p.set('keyword', params.keyword)
    if (params.source_platform) p.set('source_platform', params.source_platform)
    p.set('limit', params.limit ?? '60')
    if (params.rand) p.set('rand', 'true')
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
    return r.json()
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
    return fetch(`${BASE}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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

  async processQueue(batchSize = 20) {
    const r = await fetch(`${BASE}/api/crawler/process?batch_size=${batchSize}`, {
      method: 'POST',
    })
    return r.json()
  },

  async extractPending(batchSize = 30) {
    const r = await fetch(`${BASE}/api/crawler/extract-pending?batch_size=${batchSize}`, {
      method: 'POST',
    })
    return r.json()
  },

  async retryErrors(batchSize = 30) {
    const r = await fetch(`${BASE}/api/crawler/retry-errors?batch_size=${batchSize}`, {
      method: 'POST',
    })
    return r.json()
  },

  async getCrawlerTasks(params = {}) {
    const p = new URLSearchParams()
    if (params.status) p.set('status', params.status)
    if (params.platform) p.set('platform', params.platform)
    p.set('limit', params.limit ?? '50')
    const r = await fetch(`${BASE}/api/crawler/tasks?${p}`)
    return r.json()
  },

  async checkXhsLogin() {
    const r = await fetch(`${BASE}/api/crawler/xhs/login-status`)
    return r.json()
  },
}
