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

    <!-- 服务说明 -->
    <section class="lc-panel">
      <div class="lc-section-title">
        <span>⚙️</span><span>推理服务</span>
      </div>
      <p class="lc-server-hint">
        本页已改为通过后端 <code>/api/model-bench/stream</code> 统一转发，
        前端无需直接配置或连接 <code>8899</code>。
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
    <section v-if="showResults" class="lc-results" id="lc-infer-results">
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
            <span v-if="col.elapsed" class="lc-stat">耗时 {{ (col.elapsed / 1000).toFixed(1) }}s</span>
          </div>
        </div>
      </div>
    </section>
    </section>

    <!-- ════════════════════════════════════════════════════════
         第二排：Demo Cases 预置案例对比展示区
         ════════════════════════════════════════════════════════ -->
    <section class="dc-section">
      <div class="dc-section-header">
        <div class="dc-section-title">
          <span class="dc-icon">🗂️</span>
          <span>预置案例对比演示</span>
          <span class="dc-subtitle">豆包参考答案 · 基座模型 · 三组 LoRA 微调</span>
        </div>
        <el-button :icon="Refresh" size="small" :loading="loadingCases" @click="loadDemoCases" circle />
      </div>

      <!-- 案例选择 tabs -->
      <div class="dc-case-tabs" v-if="demoCases.length">
        <div
          v-for="c in demoCases"
          :key="c.case_index"
          class="dc-case-tab"
          :class="{ active: selectedCase?.case_index === c.case_index }"
          @click="selectCase(c)"
        >
          <span class="dc-tab-num">{{ c.case_index }}</span>
          <span class="dc-tab-cat">{{ c.category }}</span>
          <span class="dc-tab-title">{{ c.title.slice(0, 12) }}</span>
        </div>
      </div>
      <div v-else-if="!loadingCases" class="dc-empty">暂无预置案例，请先运行 scripts/extract_demo_cases.py</div>

      <!-- 案例详情 -->
      <div v-if="selectedCase" class="dc-case-detail">
        <!-- 基本信息条 -->
        <div class="dc-meta-bar">
          <el-tag size="small" type="warning" effect="light">{{ selectedCase.category }}</el-tag>
          <el-tag v-if="selectedCase.company" size="small" type="info" effect="plain">{{ selectedCase.company }}</el-tag>
          <el-tag v-if="selectedCase.platform" size="small" effect="plain">{{ selectedCase.platform }}</el-tag>
          <span class="dc-meta-title">{{ selectedCase.title }}</span>
          <span class="dc-meta-qcount">📝 {{ selectedCase.questions_count }} 题</span>
          <el-tag v-if="selectedCase.has_irregular_numbering" size="small" type="danger" effect="plain">非规则标号</el-tag>
          <el-tag v-if="selectedCase.is_modified" size="small" type="success" effect="plain">人工修改</el-tag>
        </div>

        <!-- 原始 content 折叠展示 -->
        <div class="dc-content-block">
          <div class="dc-content-header" @click="showContent = !showContent">
            <span>📄 原始帖子正文</span>
            <span class="dc-content-len">（{{ (fullCaseContent || selectedCase.content || selectedCase.content_preview || '').length }} 字符）</span>
            <span class="dc-toggle">{{ showContent ? '▲ 收起' : '▼ 展开查看' }}</span>
          </div>
          <div v-if="showContent" class="dc-content-body">
            <pre class="dc-pre">{{ fullCaseContent || selectedCase.content_preview }}</pre>
            <el-button
              v-if="!fullCaseContent"
              size="small" type="primary" plain
              class="dc-load-full-btn"
              :loading="loadingFullContent"
              @click="loadFullContent"
            >加载完整正文</el-button>
          </div>
        </div>

        <!-- 操作栏 -->
        <div class="dc-compare-toolbar">
          <el-button type="primary" size="small" :loading="demoRunning" @click="runDemoCompare">
            {{ demoRunning ? '推理中…' : '▶ 对此案例运行四模型推理' }}
          </el-button>
          <el-button v-if="demoRunning" type="danger" plain size="small" @click="stopDemoCompare">停止</el-button>
          <span class="dc-toolbar-hint">将用帖子完整正文作为输入，在四个模型上做题目提取推理</span>
        </div>

        <!-- 五列卡片：豆包 + base + seq2048 + seq4096 + seq8192 -->
        <div class="dc-grid">
          <!-- 豆包参考答案 -->
          <div class="dc-card dc-card-doubao">
            <div class="dc-card-head">
              <span class="dc-card-icon">🫘</span>
              <div class="dc-card-info">
                <span class="dc-card-label">豆包参考答案</span>
                <el-tag size="small" type="warning" effect="light">标注基准</el-tag>
              </div>
            </div>
            <div class="dc-card-body">
              <div v-if="selectedCase.doubao_output" v-html="renderJson(selectedCase.doubao_output)" />
              <div v-else class="dc-placeholder">（暂无标注输出）</div>
            </div>
          </div>

          <!-- 四模型推理结果 -->
          <div
            v-for="(dcol, idx) in demoCols"
            :key="dcol.id"
            class="dc-card"
            :class="[`dc-tone-${idx}`, dcol.status]"
          >
            <div class="dc-card-head">
              <span class="dc-card-icon">{{ ['①','②','③','④'][idx] }}</span>
              <div class="dc-card-info">
                <span class="dc-card-label">{{ dcol.label }}</span>
                <span class="dc-card-id">{{ dcol.id }}</span>
              </div>
              <div class="dc-status-area">
                <span v-if="dcol.status === 'waiting'" class="lc-dot waiting" />
                <span v-else-if="dcol.status === 'running'" class="lc-dot running" />
                <el-tag v-else-if="dcol.status === 'done'" type="success" size="small" effect="light">完成</el-tag>
                <el-tag v-else-if="dcol.status === 'error'" type="danger" size="small" effect="light">错误</el-tag>
              </div>
            </div>
            <div class="dc-card-body">
              <div v-if="dcol.status === 'waiting'" class="dc-placeholder">等待推理…</div>
              <div v-else-if="dcol.status === 'running' && !dcol.text" class="dc-placeholder dc-blink">生成中…</div>
              <div v-else-if="dcol.status === 'error'" class="dc-error">{{ dcol.errorMsg }}</div>
              <div v-else v-html="renderJson(dcol.text)" />
            </div>
            <div v-if="dcol.status !== 'waiting'" class="dc-card-foot">
              <span v-if="dcol.tokenCount" class="lc-stat">{{ dcol.tokenCount }} tk</span>
              <span v-if="dcol.elapsed" class="lc-stat">{{ (dcol.elapsed/1000).toFixed(1) }}s</span>
            </div>
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

// ── 服务配置（前端仅连后端） ───────────────────────────────
const serverUrl = ref('')

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
  !!activeQuestion.value
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
  resetColumns()
  showResults.value = true
  running.value = true

  const params = new URLSearchParams()
  params.set('question', activeQuestion.value)
  params.set('models', MODEL_IDS.join(','))
  if (serverUrl.value.trim()) {
    // 兼容开发调试：可在代码里设置 serverUrl 指向远端推理服务
    params.set('server_url', serverUrl.value.trim())
  }
  const url = `/api/model-bench/stream?${params.toString()}`

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
          col.elapsed = Number(msg.elapsed_ms || 0) || (Date.now() - col.startAt)
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

onMounted(() => { loadMeta(); loadQuestions(); loadDemoCases() })
onUnmounted(() => { if (_es) _es.close(); if (_demoEs) _demoEs.close() })

// ══════════════════════════════════════════════════════════
// Demo Cases 第二排逻辑
// ══════════════════════════════════════════════════════════
const demoCases        = ref([])
const loadingCases     = ref(false)
const selectedCase     = ref(null)
const showContent      = ref(false)
const fullCaseContent  = ref('')
const loadingFullContent = ref(false)

const DEMO_MODEL_IDS    = ['base', 'seq2048', 'seq4096', 'seq8192']
const DEMO_MODEL_LABELS = {
  base:    '基座（无 LoRA）',
  seq2048: '微调 seq=2048',
  seq4096: '微调 seq=4096',
  seq8192: '微调 seq=8192',
}

const demoCols = ref(DEMO_MODEL_IDS.map(id => ({
  id,
  label:      DEMO_MODEL_LABELS[id],
  status:     'waiting',
  text:       '',
  tokenCount: 0,
  elapsed:    0,
  startAt:    0,
  errorMsg:   '',
})))

const demoRunning = ref(false)
let _demoEs = null

const categorySlug = (cat) => (cat || '').replace(/[^a-z0-9\u4e00-\u9fa5]/gi, '-').toLowerCase()

const loadDemoCases = async () => {
  loadingCases.value = true
  try {
    const r = await fetch('/api/demo-cases')
    const d = await r.json()
    demoCases.value = d.items || []
    if (demoCases.value.length && !selectedCase.value) {
      selectCase(demoCases.value[0])
    }
  } catch (e) {
    ElMessage.warning('加载预置案例失败：' + e.message)
  } finally {
    loadingCases.value = false
  }
}

const selectCase = (c) => {
  selectedCase.value = c
  showContent.value = false
  fullCaseContent.value = ''
  resetDemoCols()
}

const loadFullContent = async () => {
  if (!selectedCase.value) return
  loadingFullContent.value = true
  try {
    const r = await fetch(`/api/demo-cases/${selectedCase.value.case_index}`)
    const d = await r.json()
    fullCaseContent.value = d.content || ''
  } catch (e) {
    ElMessage.error('加载完整正文失败：' + e.message)
  } finally {
    loadingFullContent.value = false
  }
}

const resetDemoCols = () => {
  demoCols.value.forEach(c => Object.assign(c, {
    status: 'waiting', text: '', tokenCount: 0, elapsed: 0, startAt: 0, errorMsg: '',
  }))
}

const stopDemoCompare = () => {
  if (_demoEs) { _demoEs.close(); _demoEs = null }
  demoRunning.value = false
  demoCols.value.forEach(c => { if (c.status === 'running') c.status = 'done' })
}

const renderJson = (text) => {
  if (!text) return ''
  // 尝试美化 JSON
  try {
    const m = text.match(/\[.*\]/s)
    if (m) {
      const parsed = JSON.parse(m[0])
      const pretty = JSON.stringify(parsed, null, 2)
      return '<pre class="dc-json">' + pretty.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>'
    }
  } catch {}
  return '<pre class="dc-json">' + text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>'
}

const runDemoCompare = () => {
  if (!selectedCase.value) return
  resetDemoCols()
  demoRunning.value = true

  // 优先用完整 content，其次 content_preview
  const question = fullCaseContent.value || selectedCase.value.content || selectedCase.value.content_preview || selectedCase.value.title

  const params = new URLSearchParams()
  params.set('question', question)
  params.set('models', DEMO_MODEL_IDS.join(','))
  if (serverUrl.value.trim()) params.set('server_url', serverUrl.value.trim())
  const url = `/api/model-bench/stream?${params.toString()}`

  if (_demoEs) _demoEs.close()
  _demoEs = new EventSource(url)

  _demoEs.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      const col = demoCols.value.find(c => c.id === msg.model)
      if (msg.type === 'start') {
        if (col) { col.status = 'running'; col.startAt = Date.now() }
      } else if (msg.type === 'token') {
        if (col) { col.text += msg.text; col.tokenCount++ }
      } else if (msg.type === 'done') {
        if (col) {
          col.status  = 'done'
          col.elapsed = Number(msg.elapsed_ms || 0) || (Date.now() - col.startAt)
        }
      } else if (msg.type === 'error') {
        if (col) { col.status = 'error'; col.errorMsg = msg.text }
      } else if (msg.type === 'all_done') {
        demoRunning.value = false
        _demoEs.close(); _demoEs = null
        ElMessage.success('案例四模型推理完成')
      }
    } catch {}
  }
  _demoEs.onerror = () => {
    if (!demoRunning.value) return
    demoRunning.value = false
    if (_demoEs) { _demoEs.close(); _demoEs = null }
    ElMessage.error('Demo SSE 连接断开')
  }
}
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