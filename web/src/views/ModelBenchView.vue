<template>
  <div class="mb-wrap">
    <!-- ── Hero ── -->
    <header class="mb-hero">
      <div class="mb-badge">🔬 实时推理对比</div>
      <h1 class="mb-title">多模型并行评测</h1>
      <p class="mb-lead">
        从题库选题后，点击 <strong>运行对比</strong>，在原始模型与三组微调权重上
        <strong>并行推理</strong>，逐 token 流式展示四列回答。
      </p>
    </header>

    <!-- ── 服务配置 ── -->
    <section class="mb-panel">
      <div class="mb-section-title"><span>⚙️</span><span>推理服务配置</span></div>
      <div class="mb-server-row">
        <el-input
          v-model="serverUrl"
          placeholder="http://your-dsw-host:8899"
          clearable
          class="mb-server-input"
        />
        <el-button
          :loading="pinging"
          :type="pingStatus === 'ok' ? 'success' : pingStatus === 'err' ? 'danger' : 'default'"
          class="mb-ping-btn"
          @click="pingServer"
        >
          {{ pingStatus === 'ok' ? '✅ 已连接' : pingStatus === 'err' ? '❌ 无法连接' : '检测连接' }}
        </el-button>
        <el-tag v-if="serverModels.length" type="success" effect="light" size="small">
          {{ serverModels.length }} 个模型可用
        </el-tag>
      </div>
      <p class="mb-server-hint">
        在 DSW 终端执行：<code>cd /mnt/workspace/TEMP-FILE-STATION/finetune && python infer_server.py</code>，
        开启端口 <code>8899</code> 转发后将地址填入上方。
      </p>
    </section>

    <!-- ── 两列布局：左侧选题 / 右侧配置 ── -->
    <div class="mb-config-grid">
      <!-- 左：题库选题 -->
      <section class="mb-panel mb-panel-questions">
        <div class="mb-section-title"><span>📚</span><span>题库选题</span></div>

        <div class="mb-q-toolbar">
          <el-input
            v-model="qSearch"
            placeholder="搜索关键词…"
            clearable
            class="mb-q-search"
            @input="debounceSearch"
          />
          <el-select
            v-model="qType"
            clearable
            placeholder="题目类型"
            class="mb-q-type"
            @change="loadQs"
          >
            <el-option v-for="t in qTypes" :key="t" :label="t" :value="t" />
          </el-select>
          <el-button :icon="Refresh" circle :loading="loadingQs" @click="loadQs" />
        </div>

        <div class="mb-q-list" v-loading="loadingQs">
          <div
            v-for="q in questions"
            :key="q.q_id"
            class="mb-q-item"
            :class="{ selected: selectedQ?.q_id === q.q_id }"
            @click="selectQ(q)"
          >
            <div class="mb-q-text">{{ q.question_text }}</div>
            <div class="mb-q-meta">
              <el-tag size="small" type="info" effect="plain">{{ q.question_type || '未分类' }}</el-tag>
              <el-tag v-if="q.difficulty" size="small" :type="diffColor(q.difficulty)" effect="light">{{ q.difficulty }}</el-tag>
              <el-tag v-if="q.company" size="small" effect="plain">{{ q.company }}</el-tag>
            </div>
          </div>
          <div v-if="!loadingQs && !questions.length" class="mb-q-empty">暂无题目，调整搜索条件后重试</div>
        </div>

        <el-pagination
          v-if="qTotal > qPageSize"
          v-model:current-page="qPage"
          :page-size="qPageSize"
          :total="qTotal"
          layout="prev, pager, next"
          small
          class="mb-pagination"
          @current-change="loadQs"
        />
      </section>

      <!-- 右：手动输入 + 模型槽位 + 运行 -->
      <div class="mb-right-col">
        <!-- 手动输入 -->
        <section class="mb-panel">
          <div class="mb-section-title"><span>✏️</span><span>或手动输入题目</span></div>
          <el-input
            v-model="customQ"
            type="textarea"
            :rows="3"
            placeholder="直接输入任意题目文本…"
          />
        </section>

        <!-- 模型槽位 -->
        <section class="mb-panel">
          <div class="mb-section-title">
            <span>🎛️</span><span>模型配置</span>
            <span class="mb-section-hint">每列对应 DSW 服务中的一个 model_id</span>
          </div>
          <div class="mb-slots">
            <div
              v-for="(slot, i) in slots"
              :key="i"
              class="mb-slot"
              :class="`tone-${i}`"
            >
              <div class="mb-slot-header">
                <span class="mb-slot-badge">{{ ['①','②','③','④'][i] }}</span>
                <el-input
                  v-model="slot.modelId"
                  :placeholder="defaultModelIds[i]"
                  size="small"
                  class="mb-slot-id-input"
                />
              </div>
              <el-input
                v-model="slot.label"
                :placeholder="defaultLabels[i]"
                size="small"
                class="mb-slot-label-input"
              />
            </div>
          </div>
        </section>

        <!-- 当前题目 + 运行 -->
        <section class="mb-panel mb-run-panel">
          <div class="mb-current-q">
            <span class="mb-q-label">当前题目</span>
            <span class="mb-q-preview" :class="{ placeholder: !activeQ }">{{ activeQ || '（未选择题目）' }}</span>
          </div>
          <div class="mb-run-actions">
            <el-button
              type="primary"
              size="large"
              class="mb-run-btn"
              :disabled="!canRun"
              :loading="running"
              @click="runCompare"
            >
              <span v-if="!running">▶&nbsp;运行四模型对比</span>
              <span v-else>推理中…</span>
            </el-button>
            <el-button
              v-if="running"
              type="danger"
              size="large"
              plain
              @click="stopCompare"
            >
              停止
            </el-button>
          </div>
        </section>
      </div>
    </div>

    <!-- ── 四列结果 ── -->
    <section v-if="showResults" class="mb-results">
      <div class="mb-results-title">
        <span>📊</span><span>推理结果</span>
        <span v-if="allDone" class="mb-done-badge">全部完成</span>
      </div>
      <div class="mb-grid">
        <div
          v-for="(col, i) in columns"
          :key="col.modelId"
          class="mb-card"
          :class="[`tone-${i}`, col.status]"
        >
          <!-- 卡片头 -->
          <div class="mb-card-head">
            <div class="mb-card-title-row">
              <span class="mb-card-num">{{ ['①','②','③','④'][i] }}</span>
              <span class="mb-card-label">{{ col.label }}</span>
              <span class="mb-card-id">{{ col.modelId }}</span>
            </div>
            <div class="mb-card-status-row">
              <span v-if="col.status === 'waiting'" class="mb-dot waiting" />
              <span v-else-if="col.status === 'running'" class="mb-dot running" />
              <el-tag v-else-if="col.status === 'done'" type="success" size="small" effect="light">完成</el-tag>
              <el-tag v-else-if="col.status === 'error'" type="danger" size="small" effect="light">错误</el-tag>
              <span v-if="col.status !== 'waiting'" class="mb-stat">{{ col.tokenCount }} tokens</span>
              <span v-if="col.elapsed" class="mb-stat">{{ (col.elapsed / 1000).toFixed(1) }}s</span>
            </div>
          </div>
          <!-- 卡片体 -->
          <div class="mb-card-body">
            <div v-if="col.status === 'waiting'" class="mb-placeholder">等待中…</div>
            <div v-else-if="col.status === 'running' && !col.text" class="mb-placeholder blink">生成中…</div>
            <div v-else-if="col.status === 'error'" class="mb-error-text">{{ col.errorMsg }}</div>
            <div v-else class="mb-text" v-html="renderText(col.text)" />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  prefill: { type: Object, default: null },
})

// ── 推理服务 ─────────────────────────────────────────────
const serverUrl   = ref(localStorage.getItem('mb_server_url') || 'http://localhost:8899')
const pingStatus  = ref('')   // '' | 'ok' | 'err'
const pinging     = ref(false)
const serverModels = ref([])

const saveServer = () => localStorage.setItem('mb_server_url', serverUrl.value)

const pingServer = async () => {
  saveServer()
  pinging.value = true
  pingStatus.value = ''
  try {
    const r = await fetch(`${serverUrl.value}/models`, { signal: AbortSignal.timeout(5000) })
    const data = await r.json()
    serverModels.value = Array.isArray(data) ? data : []
    pingStatus.value = 'ok'
    ElMessage.success(`连接成功，${serverModels.value.length} 个模型已就绪`)
  } catch (e) {
    pingStatus.value = 'err'
    serverModels.value = []
    ElMessage.error('无法连接推理服务：' + e.message)
  } finally {
    pinging.value = false
  }
}

// ── 题库 ─────────────────────────────────────────────────
const questions  = ref([])
const qTotal     = ref(0)
const qPage      = ref(1)
const qPageSize  = ref(12)
const loadingQs  = ref(false)
const qSearch    = ref('')
const qType      = ref('')
const qTypes     = ref([])
const selectedQ  = ref(null)
const customQ    = ref('')

let _searchTimer = null
const debounceSearch = () => {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(() => { qPage.value = 1; loadQs() }, 380)
}

const loadQs = async () => {
  loadingQs.value = true
  try {
    const p = new URLSearchParams()
    p.set('page', qPage.value)
    p.set('page_size', qPageSize.value)
    if (qSearch.value.trim()) p.set('keyword', qSearch.value.trim())
    if (qType.value) p.set('question_type', qType.value)
    const r = await fetch(`/api/questions?${p}`)
    const data = await r.json()
    questions.value = data.items || data.questions || []
    qTotal.value = data.total || 0
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
    qTypes.value = d.question_types || []
  } catch { /* ignore */ }
}

const selectQ = (q) => {
  selectedQ.value = q
  customQ.value = ''
}

const diffColor = (d) => ({ easy: 'success', medium: 'warning', hard: 'danger' }[d] || 'info')

// ── 模型槽位 ─────────────────────────────────────────────
const defaultModelIds = ['base', 'seq2048', 'seq4096', 'seq8192']
const defaultLabels   = ['原始模型（无 LoRA）', '微调 seq=2048', '微调 seq=4096', '微调 seq=8192']

const slots = ref(
  defaultModelIds.map((id, i) => ({
    modelId: id,
    label:   defaultLabels[i],
  }))
)

// ── 当前题目 ─────────────────────────────────────────────
const activeQ = computed(() => {
  if (customQ.value.trim()) return customQ.value.trim()
  return selectedQ.value?.question_text || ''
})

const canRun = computed(() => !!activeQ.value && !!serverUrl.value)

// ── 结果列 ───────────────────────────────────────────────
const showResults = ref(false)
const running     = ref(false)
const allDone     = ref(false)

const makeColumns = () =>
  slots.value.map(s => ({
    modelId:    s.modelId || s.label,
    label:      s.label   || s.modelId,
    status:     'waiting',  // waiting | running | done | error
    text:       '',
    tokenCount: 0,
    elapsed:    0,
    startAt:    0,
    errorMsg:   '',
  }))

const columns = ref(makeColumns())

const resetColumns = () => {
  columns.value = makeColumns()
  allDone.value = false
}

const renderText = (text) => {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br/>')
}

// ── SSE 连接 ─────────────────────────────────────────────
let _es = null

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

  const modelIds = slots.value.map(s => s.modelId || s.label).filter(Boolean)
  const params = new URLSearchParams()
  params.set('question', activeQ.value)
  params.set('models', modelIds.join(','))
  params.set('server_url', serverUrl.value)
  if (selectedQ.value?.q_id) params.set('question_id', selectedQ.value.q_id)

  const url = `/api/model-bench/stream?${params}`

  if (_es) _es.close()
  _es = new EventSource(url)

  _es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      const col = columns.value.find(c => c.modelId === msg.model)

      if (msg.type === 'start') {
        if (col) { col.status = 'running'; col.startAt = Date.now() }
      } else if (msg.type === 'token') {
        if (col) { col.text += msg.text; col.tokenCount++ }
      } else if (msg.type === 'done') {
        if (col) {
          col.status  = 'done'
          col.elapsed = msg.elapsed_ms ?? (Date.now() - col.startAt)
        }
      } else if (msg.type === 'error') {
        if (col) { col.status = 'error'; col.errorMsg = msg.text }
      } else if (msg.type === 'all_done') {
        running.value = false
        allDone.value = true
        _es.close(); _es = null
        ElMessage.success('四模型推理完成 ✓')
      }
    } catch { /* ignore parse err */ }
  }

  _es.onerror = () => {
    running.value = false
    if (_es) { _es.close(); _es = null }
    ElMessage.error('SSE 连接断开，请检查推理服务是否正常运行')
  }
}

const buildPostPrompt = (task) => {
  const title = task?.post_title || ''
  const body = task?.raw_content || ''
  if (!body.trim()) return ''
  return `【帖子标题】\n${title || '（无）'}\n\n【帖子正文】\n${body}\n\n请基于上面整篇帖子内容，输出：\n1) 帖子中覆盖的核心面试考点；\n2) 可追问的 3-5 道高质量面试题；\n3) 每题给出简明标准答案要点。`
}

const applyPrefillQuestion = async (prefill) => {
  const q = prefill?.question
  if (!q) return

  let inputText = ''
  let linkedTaskId = ''
  try {
    if (q.crawl_task_id != null) {
      const postResp = await fetch(`/api/posts/${encodeURIComponent(q.crawl_task_id)}`)
      if (postResp.ok) {
        const post = await postResp.json()
        linkedTaskId = post?.task_id || ''
      }
    }
    if (linkedTaskId) {
      const taskResp = await fetch(`/api/crawler/tasks/${encodeURIComponent(linkedTaskId)}`)
      if (taskResp.ok) {
        const task = await taskResp.json()
        inputText = buildPostPrompt(task)
      }
    }
  } catch {
    // ignore and fallback
  }

  if (!inputText) inputText = q.question_text || ''
  customQ.value = inputText
  selectedQ.value = q?.q_id ? { q_id: q.q_id, question_text: q.question_text } : null
  await nextTick()
  if (canRun.value && !running.value) {
    runCompare()
  } else if (!canRun.value) {
    ElMessage.warning('推理服务地址未配置，无法自动运行对比')
  }
}

onMounted(() => { loadMeta(); loadQs() })
onUnmounted(() => { if (_es) _es.close() })

watch(
  () => props.prefill?.ts,
  () => { applyPrefillQuestion(props.prefill) },
  { immediate: true }
)
</script>

<style scoped>
.mb-wrap {
  --a: #64748b;
  --b: #3b6ff5;
  --c: #0d9f6e;
  --d: #c026d3;
  --primary: #5b6ef5;
  --slate: #0f172a;
  --line: #e2e8f0;
  min-height: 100vh;
  padding: 24px 28px 60px;
  max-width: 1640px;
  margin: 0 auto;
  background: linear-gradient(170deg, #f7f8fc 0%, #eef1f8 100%);
  box-sizing: border-box;
}

/* ── Hero ── */
.mb-hero { margin-bottom: 20px; }
.mb-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .05em;
  color: var(--primary);
  background: #eef0fe;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid rgba(91,110,245,.2);
  margin-bottom: 10px;
}
.mb-title {
  font-size: 28px;
  font-weight: 800;
  color: var(--slate);
  letter-spacing: -.03em;
  line-height: 1.2;
}
.mb-lead {
  margin-top: 8px;
  font-size: 14px;
  color: #64748b;
  line-height: 1.65;
}
.mb-lead strong { color: #475569; font-weight: 600; }

/* ── Panel ── */
.mb-panel {
  background: #fff;
  border-radius: 14px;
  border: 1px solid var(--line);
  box-shadow: 0 2px 16px rgba(15,23,42,.05);
  padding: 18px 20px 20px;
  margin-bottom: 16px;
}
.mb-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 800;
  color: var(--slate);
  margin-bottom: 12px;
}
.mb-section-hint {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
  margin-left: 4px;
}

/* ── Server row ── */
.mb-server-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.mb-server-input { flex: 1; min-width: 260px; }
.mb-ping-btn { flex-shrink: 0; }
.mb-server-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 8px;
  line-height: 1.5;
}
.mb-server-hint code {
  font-size: 11px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 5px;
  padding: 1px 6px;
  color: #4338ca;
}

/* ── Config grid ── */
.mb-config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 1100px) {
  .mb-config-grid { grid-template-columns: 1fr; }
}
.mb-panel-questions { height: 100%; }
.mb-right-col { display: flex; flex-direction: column; gap: 0; }

/* ── Question toolbar ── */
.mb-q-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.mb-q-search { flex: 1; min-width: 160px; }
.mb-q-type { width: 130px; }

/* ── Question list ── */
.mb-q-list {
  max-height: 380px;
  overflow-y: auto;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fafbfd;
}
.mb-q-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f1f5f9;
  transition: background .15s;
}
.mb-q-item:last-child { border-bottom: none; }
.mb-q-item:hover { background: #f0f4ff; }
.mb-q-item.selected { background: #eef0fe; border-left: 3px solid var(--primary); }
.mb-q-text {
  font-size: 13px;
  color: #1e293b;
  line-height: 1.4;
  margin-bottom: 5px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.mb-q-meta { display: flex; gap: 5px; flex-wrap: wrap; }
.mb-q-empty { padding: 24px; text-align: center; color: #94a3b8; font-size: 13px; }
.mb-pagination { margin-top: 10px; justify-content: center; }

/* ── Slots ── */
.mb-slots {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
@media (max-width: 900px) {
  .mb-slots { grid-template-columns: repeat(2, 1fr); }
}
.mb-slot {
  padding: 10px 12px 12px;
  border-radius: 10px;
  background: #fafbfd;
  border: 1px solid var(--line);
}
.mb-slot.tone-0 { border-left: 3px solid var(--a); }
.mb-slot.tone-1 { border-left: 3px solid var(--b); }
.mb-slot.tone-2 { border-left: 3px solid var(--c); }
.mb-slot.tone-3 { border-left: 3px solid var(--d); }
.mb-slot-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.mb-slot-badge {
  font-size: 16px;
  line-height: 1;
  flex-shrink: 0;
}
.mb-slot-id-input { flex: 1; }
.mb-slot-label-input { width: 100%; margin-top: 4px; }

/* ── Run panel ── */
.mb-run-panel { border-top: 3px solid var(--primary); }
.mb-current-q {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 14px;
}
.mb-q-label {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  white-space: nowrap;
  padding-top: 2px;
}
.mb-q-preview {
  font-size: 13px;
  color: #1e293b;
  line-height: 1.5;
  flex: 1;
}
.mb-q-preview.placeholder { color: #94a3b8; font-style: italic; }
.mb-run-actions { display: flex; gap: 10px; align-items: center; }
.mb-run-btn {
  min-width: 180px;
  font-weight: 700;
  font-size: 14px;
  border-radius: 10px;
  box-shadow: 0 4px 14px rgba(91,110,245,.28);
}

/* ── Results ── */
.mb-results { margin-top: 8px; }
.mb-results-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 800;
  color: var(--slate);
  margin-bottom: 14px;
}
.mb-done-badge {
  font-size: 11px;
  font-weight: 700;
  color: #059669;
  background: #d1fae5;
  padding: 3px 10px;
  border-radius: 999px;
}

/* ── Grid ── */
.mb-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  align-items: stretch;
}
@media (max-width: 1300px) {
  .mb-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 760px) {
  .mb-grid { grid-template-columns: 1fr; }
}

/* ── Card ── */
.mb-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid var(--line);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 280px;
  box-shadow: 0 2px 12px rgba(15,23,42,.05);
  transition: box-shadow .2s;
}
.mb-card:hover { box-shadow: 0 6px 28px rgba(15,23,42,.09); }
.mb-card.tone-0 { border-top: 4px solid var(--a); }
.mb-card.tone-1 { border-top: 4px solid var(--b); }
.mb-card.tone-2 { border-top: 4px solid var(--c); }
.mb-card.tone-3 { border-top: 4px solid var(--d); }
.mb-card.error  { border-top-color: #ef4444; }

.mb-card-head {
  padding: 12px 14px 10px;
  background: linear-gradient(180deg,#fafbfd,#fff);
  border-bottom: 1px solid #f1f5f9;
}
.mb-card-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.mb-card-num { font-size: 18px; line-height: 1; }
.mb-card-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--slate);
  flex: 1;
}
.mb-card-id {
  font-size: 11px;
  font-family: ui-monospace, monospace;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 2px 7px;
  border-radius: 5px;
}
.mb-card-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.mb-stat {
  font-size: 11px;
  color: #64748b;
  background: #f8fafc;
  padding: 2px 7px;
  border-radius: 5px;
  border: 1px solid #e2e8f0;
}

.mb-card-body {
  padding: 12px 14px 16px;
  flex: 1;
  overflow-y: auto;
  max-height: 60vh;
  background: #fcfcfe;
}

/* status dots */
.mb-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
}
.mb-dot.waiting { background: #cbd5e1; }
.mb-dot.running {
  background: var(--primary);
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0%,100% { opacity: 1; transform: scale(1); }
  50%      { opacity: .5; transform: scale(1.3); }
}

.mb-placeholder {
  color: #94a3b8;
  font-size: 13px;
  padding: 8px 0;
}
.mb-placeholder.blink {
  animation: blink 1.1s infinite;
}
@keyframes blink {
  0%,100% { opacity: 1; }
  50%      { opacity: .3; }
}

.mb-error-text {
  color: #ef4444;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-all;
}

.mb-text {
  font-size: 13px;
  line-height: 1.7;
  color: #1e293b;
  word-break: break-word;
  white-space: pre-wrap;
}
</style> 