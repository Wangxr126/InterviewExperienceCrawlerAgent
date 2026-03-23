<template>
  <div class="lc-wrap">
    <!-- 标题 -->
    <header class="lc-hero">
      <div class="lc-hero-badge">🧬 LoRA 对比</div>
      <h1 class="lc-title">微调模型对比推理</h1>
      <p class="lc-lead">
        从题库选题，实时在 <strong>原始模型 + 三组 LoRA 权重</strong> 上并行推理，逐 token 流式展示对比结果。
      </p>
    </header>

    <!-- DSW 服务配置 -->
    <section class="lc-panel">
      <div class="lc-section-title">
        <span>⚙️</span><span>推理服务地址</span>
      </div>
      <div class="lc-server-row">
        <el-input
          v-model="serverUrl"
          placeholder="http://your-dsw-host:8899"
          clearable
          class="lc-server-input"
        />
        <el-button :loading="pinging" @click="pingServer" type="default" class="lc-btn-ping">
          {{ pingStatus === 'ok' ? '✅ 已连接' : pingStatus === 'err' ? '❌ 无法连接' : '检测连接' }}
        </el-button>
        <el-tag v-if="serverModels.length" type="success" effect="light" size="small">
          {{ serverModels.length }} 个模型已就绪
        </el-tag>
      </div>
      <p class="lc-server-hint">
        在 DSW 终端执行：<code>cd /mnt/workspace/TEMP-FILE-STATION/finetune &amp;&amp; python infer_server.py</code>，
        然后开启端口 <code>8899</code> 的转发，将转发地址填入上方。
      </p>
    </section>

    <!-- 选题 -->
    <section class="lc-panel">
      <div class="lc-section-title"><span>📚</span><span>选择题目</span></div>

      <div class="lc-question-toolbar">
        <el-input
          v-model="questionSearch"
          placeholder="搜索题目关键词…"
          clearable
          class="lc-q-search"
          @input="debounceSearch"
        />
        <el-select v-model="filterType" clearable placeholder="题目类型" class="lc-q-filter" @change="loadQuestions">
          <el-option v-for="t in questionTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-button :icon="Refresh" @click="loadQuestions" :loading="loadingQs" circle />
      </div>

      <div class="lc-question-list" v-loading="loadingQs">
        <div
          v-for="q in questions"
          :key="q.q_id"
          class="lc-q-item"
          :class="{ selected: selectedQ?.q_id === q.q_id }"
          @click="selectQuestion(q)"
        >
          <div class="lc-q-text">{{ q.question_text }}</div>
          <div class="lc-q-meta">
            <el-tag size="small" type="info" effect="plain">{{ q.question_type || '未分类' }}</el-tag>
            <el-tag v-if="q.difficulty" size="small" :type="diffColor(q.difficulty)" effect="light">{{ q.difficulty }}</el-tag>
          </div>
        </div>
        <div v-if="!loadingQs && !questions.length" class="lc-empty">暂无题目，请调整搜索条件</div>
      </div>

      <el-pagination
        v-if="totalQs > pageSize"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="totalQs"
        layout="prev, pager, next"
        class="lc-pagination"
        @current-change="loadQuestions"
      />
    </section>

    <!-- 自定义题目 -->
    <section class="lc-panel">
      <div class="lc-section-title"><span>✏️</span><span>或手动输入题目</span></div>
      <el-input
        v-model="customQuestion"
        type="textarea"
        :rows="3"
        placeholder="直接输入任意题目…"
        class="lc-custom-input"
      />
    </section>

    <!-- 当前题目预览 + 运行按钮 -->
    <section class="lc-panel lc-run-panel">
      <div class="lc-current-q">
        <span class="lc-q-label">当前题目：</span>
        <span class="lc-q-preview">{{ activeQuestion || '（未选择）' }}</span>
      </div>
      <el-button
        type="primary"
        size="large"
        class="lc-run-btn"
        :disabled="!canRun"
        :loading="running"
        @click="runCompare"
      >
        {{ running ? '推理中…' : '▶ 运行四模型对比' }}
      </el-button>
      <el-button v-if="running" @click="stopCompare" type="danger" size="large" plain class="lc-stop-btn">
        停止
      </el-button>
    </section>

    <!-- 四列结果 -->
    <section v-if="showResults" class="lc-results">
      <div class="lc-grid">
        <div
          v-for="(col, idx) in columns"
          :key="col.id"
          class="lc-card"
          :class="[`tone-${idx}`, col.status]"
        >
          <div class="lc-card-head">
            <span class="lc-card-tag">{{ ['①','②','③','④'][idx] }}</span>
            <div class="lc-card-info">
              <span class="lc-card-label">{{ col.label }}</span>
              <span class="lc-card-id mono">{{ col.id }}</span>
            </div>
            <div class="lc-card-status">
              <span v-if="col.status === 'waiting'" class="lc-dot waiting" />
              <span v-else-if="col.status === 'running'" class="lc-dot running" />
              <el-tag v-else-if="col.status === 'done'" type="success" size="small" effect="light">完成</el-tag>
              <el-tag v-else-if="col.status === 'error'" type="danger" size="small" effect="light">错误</el-tag>
            </div>
          </div>

          <div class="lc-card-body">
            <div v-if="col.status === 'waiting'" class="lc-placeholder">等待中…</div>
            <div v-else-if="col.status === 'running' && !col.text" class="lc-placeholder lc-blink">生成中…</div>
            <div v-else-if="col.status === 'error'" class="lc-error-text">{{ col.errorMsg }}</div>
            <div v-else class="lc-text-content" v-html="renderText(col.text)" />
          </div>

          <div v-if="col.status === 'done' || col.status === 'running'" class="lc-card-foot">
            <span v-if="col.tokenCount" class="lc-stat">{{ col.tokenCount }} tokens</span>
            <span v-if="col.elapsed" class="lc-stat">{{ (col.elapsed / 1000).toFixed(1) }}s</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

// ── 服务配置 ──────────────────────────────────────────────
const serverUrl   = ref(localStorage.getItem('lora_server_url') || 'http://localhost:8899')
const pingStatus  = ref('')   // '' | 'ok' | 'err'
const pinging     = ref(false)
const serverModels = ref([])

const saveServer = () => localStorage.setItem('lora_server_url', serverUrl.value)

const pingServer = async () => {
  saveServer()
  pinging.value = true
  pingStatus.value = ''
  try {
    const r = await fetch(`${serverUrl.value}/models`, { signal: AbortSignal.timeout(5000) })
    const data = await r.json()
    serverModels.value = Array.isArray(data) ? data : []
    pingStatus.value = 'ok'
    ElMessage.success(`连接成功，${serverModels.value.length} 个模型`)
  } catch (e) {
    pingStatus.value = 'err'
    serverModels.value = []
    ElMessage.error('无法连接到推理服务：' + e.message)
  } finally {
    pinging.value = false
  }
}

// ── 题库 ──────────────────────────────────────────────────
const questions     = ref([])
const totalQs       = ref(0)
const page          = ref(1)
const pageSize      = ref(10)
const loadingQs     = ref(false)
const questionSearch = ref('')
const filterType    = ref('')
const questionTypes = ref([])
const selectedQ     = ref(null)
const customQuestion = ref('')

let searchTimer = null
const debounceSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadQuestions() }, 400)
}

const loadQuestions = async () => {
  loadingQs.value = true
  try {
    const p = new URLSearchParams()
    p.set('page', page.value)
    p.set('page_size', pageSize.value)
    if (questionSearch.value.trim()) p.set('keyword', questionSearch.value.trim())
    if (filterType.value) p.set('question_type', filterType.value)
    const r = await fetch(`/api/questions?${p}`)
    const data = await r.json()
    questions.value = data.items || data.questions || []
    totalQs.value   = data.total || 0
  } catch (e) {
    ElMessage.error('加载题目失败：' + e.message)
  } finally {
    loadingQs.value = false
  }
}

const loadMeta = async () => {
  try {
    const r = await fetch('/api/questions/meta')
    const d = await r.json()
    questionTypes.value = d.question_types || []
  } catch { /* ignore */ }
}

const selectQuestion = (q) => {
  selectedQ.value = q
  customQuestion.value = ''
}

const diffColor = (d) => ({ easy: 'success', medium: 'warning', hard: 'danger' }[d] || 'info')

// ── 当前题目 ──────────────────────────────────────────────
const activeQuestion = computed(() => {
  if (customQuestion.value.trim()) return customQuestion.value.trim()
  return selectedQ.value?.question_text || ''
})

const canRun = computed(() =>
  !!activeQuestion.value && !!serverUrl.value
)

// ── 四列结果 ──────────────────────────────────────────────
const MODEL_IDS    = ['base', 'seq2048', 'seq4096', 'seq8192']
const MODEL_LABELS = {
  base:    '原始模型（无 LoRA）',
  seq2048: '微调 seq=2048',
  seq4096: '微调 seq=4096',
  seq8192: '微调 seq=8192',
}

const columns = ref(MODEL_IDS.map(id => ({
  id,
  label:      MODEL_LABELS[id],
  status:     'waiting',   // waiting | running | done | error
  text:       '',
  tokenCount: 0,
  elapsed:    0,
  startAt:    0,
  errorMsg:   '',
})))

const showResults = ref(false)
const running     = ref(false)
let   _es         = null   // EventSource

const resetColumns = () => {
  columns.value.forEach(c => Object.assign(c, {
    status: 'waiting', text: '', tokenCount: 0, elapsed: 0, startAt: 0, errorMsg: '',
  }))
}

const renderText = (text) => {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br/>')
}

const stopCompare = () => {
  if (_es) { _es.close(); _es = null }
  running.value = false
  columns.value.forEach(c => { if (c.status === 'running') c.status = 'done' })
}

const runCompare = () => {
  if (!canRun.value) return
  saveServer()
  resetColumns()
  showResults.value = true
  running.value = true

  const question = encodeURIComponent(activeQuestion.value)
  const models   = MODEL_IDS.join(',')
  const url      = `${serverUrl.value}/infer/compare-stream?question=${question}&models=${models}`

  if (_es) _es.close()
  _es = new EventSource(url)

  _es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      const col = columns.value.find(c => c.id === msg.model)

      if (msg.type === 'start') {
        if (col) { col.status = 'running'; col.startAt = Date.now() }
      } else if (msg.type === 'token') {
        if (col) { col.text += msg.text; col.tokenCount++ }
      } else if (msg.type === 'done') {
        if (col) {
          col.status  = 'done'
          col.elapsed = Date.now() - col.startAt
        }
      } else if (msg.type === 'error') {
        if (col) { col.status = 'error'; col.errorMsg = msg.text }
      } else if (msg.type === 'all_done') {
        running.value = false
        _es.close(); _es = null
        ElMessage.success('四模型推理完成')
      }
    } catch { /* ignore parse err */ }
  }

  _es.onerror = (e) => {
    running.value = false
    if (_es) { _es.close(); _es = null }
    ElMessage.error('SSE 连接断开，请检查推理服务是否正常运行')
  }
}

onMounted(() => { loadMeta(); loadQuestions() })
onUnmounted(() => { if (_es) _es.close() })
</script>

<style scoped>
.lc-wrap {
  --lc-a: #64748b;
  --lc-b: #3b6ff5;
  --lc-c: #0d9f6e;
  --lc-d: #c026d3;
  --lc-primary: #5b6ef5;
  --lc-slate: #0f172a;
  --lc-line: #e2e8f0;
  --lc-radius: 14px;
  min-height: 100vh;
  padding: 24px 28px 56px;
  max-width: 1600px;
  margin: 0 auto;
  background: linear-gradient(180deg, #f7f8fc 0%, #eef1f8 100%);
  box-sizing: border-box;
}

/* hero */
.lc-hero { margin-bottom: 20px; }
.lc-hero-badge {
  display: inline-block;
  font-size: 12px; 