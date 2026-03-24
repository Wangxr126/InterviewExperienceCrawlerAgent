<template>
  <div class="lc-wrap">
    <header class="lc-hero">
      <div class="lc-hero-badge">🧬 LoRA 对比</div>
      <h1 class="lc-title">微调模型对比推理</h1>
      <p class="lc-lead">
        从题库选题，实时在 <strong>原始模型 + 三组 LoRA 权重</strong> 上推理；流式四列下方可对照
        <strong>原帖 content</strong>、<strong>豆包题库答案</strong> 与四模型完整输出，并支持一键导出。
      </p>
    </header>

    <section class="lc-panel">
      <div class="lc-section-title">
        <span>⚙️</span><span>推理服务</span>
      </div>
      <p class="lc-server-hint">
        本页通过后端 <code>/api/model-bench/stream</code> 转发 DSW 上的 <code>infer_server.py</code>；
        环境变量 <code>MODEL_BENCH_SERVER_URL</code> 指向云端地址即可。
      </p>
    </section>

    <section class="lc-panel">
      <div class="lc-section-title"><span>📦</span><span>DSW 预跑结果（本地 JSON）</span></div>
      <p v-if="!dswPresetMeta.exists" class="lc-server-hint">
        将 DSW 导出的 <code>compare_results_10.json</code> 放到仓库
        <code>微调/dsw/</code> 目录（与本机路径一致），重启后端后此处会出现下拉列表。
        也可用环境变量 <code>MODEL_BENCH_DSW_COMPARE_JSON</code> 指定其它路径。
      </p>
      <div v-else class="lc-preset-row">
        <el-tag type="success" size="small" effect="light">{{ dswPresetMeta.count }} 条</el-tag>
        <span v-if="dswPresetMeta.generated_at" class="lc-preset-meta">{{ dswPresetMeta.generated_at }}</span>
        <el-select
          v-model="selectedPresetIdx"
          placeholder="选择一条预跑记录…"
          filterable
          clearable
          class="lc-preset-select"
        >
          <el-option
            v-for="it in dswPresetMeta.items"
            :key="it.idx"
            :label="presetOptionLabel(it)"
            :value="it.idx"
          />
        </el-select>
        <el-button type="primary" plain :disabled="!selectedPresetIdx" @click="applyDswPreset">
          加载到对比区
        </el-button>
        <el-button :icon="Refresh" circle :loading="loadingDswPreset" @click="loadDswPresetMeta" />
      </div>
    </section>

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
      <el-button v-if="running" type="danger" size="large" plain class="lc-stop-btn" @click="stopCompare">
        停止
      </el-button>
    </section>

    <section v-if="showResults" class="lc-results">
      <div class="lc-results-actions">
        <el-button type="primary" plain @click="exportCompareJson">导出对比 JSON</el-button>
        <el-button plain @click="copyCompareText">复制对比文本</el-button>
      </div>

      <div class="lc-section-title lc-results-title"><span>⚡</span><span>流式输出（四模型）</span></div>
      <div class="lc-grid lc-grid-4">
        <div
          v-for="(col, idx) in columns"
          :key="col.id"
          class="lc-card"
          :class="[`tone-${idx}`, col.status]"
        >
          <div class="lc-card-head">
            <span class="lc-card-tag">{{ ['①', '②', '③', '④'][idx] }}</span>
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

      <div class="lc-compare-summary">
        <div class="lc-section-title"><span>📋</span><span>对照：原帖 content · 豆包答案 · 四模型输出</span></div>

        <div v-if="postContentForDisplay" class="lc-post-box">
          <div class="lc-subtitle">原帖 raw_content（题库关联帖）</div>
          <pre class="lc-pre">{{ postContentForDisplay }}</pre>
        </div>
        <p v-else class="lc-muted">
          当前无关联原帖正文（自定义题干或未绑定 <code>crawl_task_id</code> 的题目）。推理仍使用上方题干走 Miner 模板。
        </p>

        <div class="lc-grid lc-grid-5">
          <div class="lc-card lc-static tone-ref">
            <div class="lc-card-head">
              <span class="lc-card-tag">豆</span>
              <div class="lc-card-info">
                <span class="lc-card-label">豆包生成的答案（题库 answer_text）</span>
                <span class="lc-card-id mono">doubao_answer</span>
              </div>
            </div>
            <div class="lc-card-body">
              <div class="lc-text-content" v-html="renderText(doubaoAnswerDisplay)" />
            </div>
          </div>

          <div
            v-for="(col, idx) in columns"
            :key="'sum-' + col.id"
            class="lc-card lc-static"
            :class="[`tone-${idx}`, col.status]"
          >
            <div class="lc-card-head">
              <span class="lc-card-tag">{{ ['①', '②', '③', '④'][idx] }}</span>
              <div class="lc-card-info">
                <span class="lc-card-label">{{ col.label }}</span>
                <span class="lc-card-id mono">{{ col.id }}</span>
              </div>
            </div>
            <div class="lc-card-body">
              <div v-if="col.status === 'error'" class="lc-error-text">{{ col.errorMsg }}</div>
              <div v-else class="lc-text-content" v-html="renderText(col.text)" />
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const serverUrl = ref('')

const dswPresetMeta = ref({
  exists: false,
  count: 0,
  generated_at: '',
  items: [],
  path: '',
})
const loadingDswPreset = ref(false)
const selectedPresetIdx = ref(null)

const questions = ref([])
const totalQs = ref(0)
const page = ref(1)
const pageSize = ref(30)
const loadingQs = ref(false)
const questionSearch = ref('')
const filterType = ref('')
const questionTypes = ref([])
const selectedQ = ref(null)
const customQuestion = ref('')
const questionDetail = ref(null)

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
    totalQs.value = data.total || 0
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

const loadQuestionDetail = async (qId) => {
  if (!qId) {
    questionDetail.value = null
    return
  }
  try {
    const r = await fetch(`/api/questions/${encodeURIComponent(qId)}`)
    if (!r.ok) {
      questionDetail.value = null
      return
    }
    questionDetail.value = await r.json()
  } catch {
    questionDetail.value = null
  }
}

const selectQuestion = async (q) => {
  selectedQ.value = q
  customQuestion.value = ''
  await loadQuestionDetail(q.q_id)
}

watch(customQuestion, (v) => {
  if ((v || '').trim()) questionDetail.value = null
})

const diffColor = (d) => ({ easy: 'success', medium: 'warning', hard: 'danger' }[d] || 'info')

const activeQuestion = computed(() => {
  if (customQuestion.value.trim()) return customQuestion.value.trim()
  return selectedQ.value?.question_text || ''
})

const postContentForDisplay = computed(() => {
  const s = (questionDetail.value?.post_raw_content || '').trim()
  return s
})

const doubaoAnswerDisplay = computed(() => {
  const s = (questionDetail.value?.answer_text || '').trim()
  if (s) return s
  return '（无）从题库选题、加载 DSW 预跑 JSON、或题目本身无豆包答案时此处为空。'
})

const canRun = computed(() => !!activeQuestion.value)

const MODEL_IDS = ['base', 'seq2048', 'seq4096', 'seq8192']
const MODEL_LABELS = {
  base: '原始模型（无 LoRA）',
  seq2048: '微调 seq=2048',
  seq4096: '微调 seq=4096',
  seq8192: '微调 seq=8192',
}

const columns = ref(MODEL_IDS.map(id => ({
  id,
  label: MODEL_LABELS[id],
  status: 'waiting',
  text: '',
  tokenCount: 0,
  elapsed: 0,
  startAt: 0,
  errorMsg: '',
})))

const showResults = ref(false)
const running = ref(false)
let _es = null

const resetColumns = () => {
  columns.value.forEach(c => Object.assign(c, {
    status: 'waiting', text: '', tokenCount: 0, elapsed: 0, startAt: 0, errorMsg: '',
  }))
}

const renderText = (text) => {
  if (!text) return ''
  return String(text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br/>')
}

const buildExportPayload = () => ({
  exported_at: new Date().toISOString(),
  q_id: selectedQ.value?.q_id || null,
  question_text: activeQuestion.value,
  post_raw_content: postContentForDisplay.value || '',
  doubao_answer: (questionDetail.value?.answer_text || '').trim(),
  model_outputs: Object.fromEntries(columns.value.map(c => [c.id, c.text])),
  model_status: Object.fromEntries(columns.value.map(c => [c.id, c.status])),
})

const exportCompareJson = () => {
  const payload = buildExportPayload()
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `lora-bench-${payload.q_id || 'custom'}-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success('已下载 JSON')
}

const loadDswPresetMeta = async () => {
  loadingDswPreset.value = true
  try {
    const r = await fetch('/api/model-bench/dsw-preset/meta')
    const d = await r.json()
    dswPresetMeta.value = {
      exists: !!d.exists,
      count: d.count || 0,
      generated_at: d.generated_at || '',
      items: d.items || [],
      path: d.path || '',
    }
  } catch {
    dswPresetMeta.value = { exists: false, count: 0, generated_at: '', items: [], path: '' }
  } finally {
    loadingDswPreset.value = false
  }
}

const presetOptionLabel = (it) => {
  const cat = it.category || ''
  const prev = it.question_preview || (it.question_text || '').slice(0, 80)
  return `#${it.idx} ${cat ? `[${cat}] ` : ''}${prev}`
}

const applyDswPreset = async () => {
  if (!selectedPresetIdx.value) return
  if (_es) {
    _es.close()
    _es = null
  }
  running.value = false
  try {
    const r = await fetch(
      `/api/model-bench/dsw-preset/item?idx=${encodeURIComponent(selectedPresetIdx.value)}`,
    )
    if (!r.ok) {
      ElMessage.error('加载预跑条目失败')
      return
    }
    const d = await r.json()
    const item = d.item
    if (!item) {
      ElMessage.error('条目为空')
      return
    }
    customQuestion.value = ''
    selectedQ.value = item.q_id
      ? { q_id: item.q_id, question_text: item.question_text || '' }
      : null
    questionDetail.value = {
      answer_text: item.doubao_answer || '',
      post_raw_content: item.post_raw_content || '',
      topic_tags: [],
    }
    MODEL_IDS.forEach((id) => {
      const col = columns.value.find((c) => c.id === id)
      if (!col) return
      const m = item.models?.[id]
      if (!m) {
        Object.assign(col, {
          status: 'waiting',
          text: '',
          tokenCount: 0,
          elapsed: 0,
          errorMsg: '',
        })
        return
      }
      const err = (m.error || '').trim()
      const txt = m.text || ''
      Object.assign(col, {
        text: txt,
        errorMsg: err,
        status: err ? 'error' : 'done',
        elapsed: Number(m.elapsed_ms || 0),
        tokenCount: Math.max(1, Math.floor(txt.length / 3)),
        startAt: 0,
      })
    })
    showResults.value = true
    ElMessage.success('已加载 DSW 预跑四模型输出 + 豆包答案')
  } catch (e) {
    ElMessage.error('加载失败：' + (e.message || String(e)))
  }
}

const copyCompareText = async () => {
  const p = buildExportPayload()
  const lines = [
    '=== question_text ===',
    p.question_text,
    '',
    '=== post_raw_content ===',
    p.post_raw_content || '(空)',
    '',
    '=== doubao answer_text ===',
    p.doubao_answer || '(空)',
    '',
    ...MODEL_IDS.map(id => [`=== model ${id} ===`, p.model_outputs[id] || '']).flat(),
  ]
  const text = lines.join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请改用导出 JSON')
  }
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
  if (selectedQ.value?.q_id && !customQuestion.value.trim()) {
    params.set('question_id', selectedQ.value.q_id)
  }
  if (serverUrl.value.trim()) params.set('server_url', serverUrl.value.trim())
  const url = `/api/model-bench/stream?${params.toString()}`

  if (_es) _es.close()
  _es = new EventSource(url)

  _es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'keepalive') return

      if (msg.type === 'all_done') {
        running.value = false
        if (_es) { _es.close(); _es = null }
        ElMessage.success('四模型推理完成')
        return
      }

      if (msg.model === 'all' && msg.type === 'error') {
        running.value = false
        if (_es) { _es.close(); _es = null }
        ElMessage.error(msg.text || '推理失败')
        return
      }

      const col = columns.value.find(c => c.id === msg.model)
      if (msg.type === 'start') {
        if (col) { col.status = 'running'; col.startAt = Date.now() }
      } else if (msg.type === 'token') {
        if (col) { col.text += msg.text || ''; col.tokenCount++ }
      } else if (msg.type === 'done') {
        if (col) {
          col.status = 'done'
          col.elapsed = Number(msg.elapsed_ms || 0) || (Date.now() - col.startAt)
        }
      } else if (msg.type === 'error') {
        if (col) { col.status = 'error'; col.errorMsg = msg.text || 'error' }
      }
    } catch { /* ignore */ }
  }

  _es.onerror = () => {
    running.value = false
    if (_es) { _es.close(); _es = null }
    ElMessage.error('SSE 连接断开，请检查推理服务是否正常运行')
  }
}

onMounted(() => {
  loadMeta()
  loadQuestions()
  loadDswPresetMeta()
})
onUnmounted(() => { if (_es) _es.close() })
</script>

<style scoped>
.lc-wrap {
  --lc-b: #3b6ff5;
  --lc-c: #0d9f6e;
  --lc-d: #c026d3;
  --lc-slate: #0f172a;
  --lc-line: #e2e8f0;
  --lc-radius: 14px;
  min-height: 100vh;
  padding: 24px 28px 56px;
  max-width: 1680px;
  margin: 0 auto;
  background: linear-gradient(180deg, #f7f8fc 0%, #eef1f8 100%);
  box-sizing: border-box;
  color: var(--lc-slate);
}

.lc-hero { margin-bottom: 20px; }
.lc-hero-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  background: #e8ecff;
  color: #4338ca;
  margin-bottom: 8px;
}
.lc-title { font-size: 1.75rem; font-weight: 700; margin: 0 0 8px; letter-spacing: -0.02em; }
.lc-lead { margin: 0; font-size: 15px; line-height: 1.6; color: #475569; max-width: 900px; }

.lc-panel {
  background: #fff;
  border: 1px solid var(--lc-line);
  border-radius: var(--lc-radius);
  padding: 18px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.lc-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 12px;
}
.lc-server-hint { margin: 0; font-size: 13px; color: #64748b; line-height: 1.55; }
.lc-server-hint code { font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }

.lc-preset-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.lc-preset-meta { font-size: 12px; color: #64748b; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lc-preset-select { min-width: 280px; flex: 1; max-width: 560px; }

.lc-question-toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; align-items: center; }
.lc-q-search { flex: 1; min-width: 200px; max-width: 420px; }
.lc-q-filter { width: 200px; }

.lc-question-list {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--lc-line);
  border-radius: 10px;
}
.lc-q-item {
  padding: 12px 14px;
  border-bottom: 1px solid #f1f5f9;
  cursor: pointer;
  transition: background 0.15s;
}
.lc-q-item:last-child { border-bottom: none; }
.lc-q-item:hover { background: #f8fafc; }
.lc-q-item.selected { background: #eef2ff; border-left: 3px solid var(--lc-b); padding-left: 11px; }
.lc-q-text { font-size: 14px; line-height: 1.5; margin-bottom: 6px; word-break: break-word; }
.lc-q-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.lc-empty { padding: 24px; text-align: center; color: #94a3b8; font-size: 14px; }
.lc-pagination { margin-top: 12px; justify-content: center; }

.lc-custom-input :deep(.el-textarea__inner) { font-size: 14px; }

.lc-run-panel { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.lc-current-q { flex: 1; min-width: 200px; }
.lc-q-label { font-size: 13px; color: #64748b; }
.lc-q-preview { font-size: 14px; font-weight: 500; display: block; margin-top: 4px; line-height: 1.45; word-break: break-word; }
.lc-run-btn { min-width: 160px; }

.lc-results { margin-top: 8px; }
.lc-results-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.lc-results-title { margin-top: 0; }

.lc-grid {
  display: grid;
  gap: 12px;
}
.lc-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.lc-grid-5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }

@media (max-width: 1200px) {
  .lc-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .lc-grid-5 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .lc-grid-4, .lc-grid-5 { grid-template-columns: 1fr; }
}

.lc-card {
  background: #fff;
  border: 1px solid var(--lc-line);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 220px;
}
.lc-card.lc-static { min-height: 180px; }
.lc-card.tone-0 { border-top: 3px solid #64748b; }
.lc-card.tone-1 { border-top: 3px solid var(--lc-b); }
.lc-card.tone-2 { border-top: 3px solid var(--lc-c); }
.lc-card.tone-3 { border-top: 3px solid var(--lc-d); }
.lc-card.tone-ref { border-top: 3px solid #f59e0b; }

.lc-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #f8fafc;
  border-bottom: 1px solid var(--lc-line);
}
.lc-card-tag {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.lc-card-info { flex: 1; min-width: 0; }
.lc-card-label { display: block; font-size: 13px; font-weight: 600; }
.lc-card-id { font-size: 11px; color: #94a3b8; }
.mono { font-family: ui-monospace, monospace; }

.lc-card-status { flex-shrink: 0; }
.lc-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
}
.lc-dot.running {
  background: var(--lc-b);
  animation: lc-pulse 1s ease-in-out infinite;
}
.lc-dot.waiting { background: #e2e8f0; }

@keyframes lc-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.lc-card-body {
  flex: 1;
  padding: 12px;
  font-size: 13px;
  line-height: 1.55;
  overflow: auto;
  max-height: 480px;
}
.lc-card.lc-static .lc-card-body { max-height: 360px; }

.lc-placeholder { color: #94a3b8; }
.lc-blink { animation: lc-pulse 1.2s ease-in-out infinite; }
.lc-error-text { color: #dc2626; font-size: 13px; white-space: pre-wrap; word-break: break-word; }
.lc-text-content { word-break: break-word; }

.lc-card-foot {
  padding: 8px 12px;
  border-top: 1px solid var(--lc-line);
  font-size: 11px;
  color: #64748b;
  display: flex;
  gap: 12px;
}

.lc-compare-summary {
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px dashed var(--lc-line);
}
.lc-post-box {
  margin-bottom: 16px;
  border: 1px solid var(--lc-line);
  border-radius: 10px;
  overflow: hidden;
  background: #fafafa;
}
.lc-subtitle {
  font-size: 12px;
  font-weight: 600;
  padding: 8px 12px;
  background: #f1f5f9;
  border-bottom: 1px solid var(--lc-line);
}
.lc-pre {
  margin: 0;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 280px;
  overflow: auto;
}
.lc-muted {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  margin: 0 0 14px;
}
.lc-muted code { font-size: 12px; background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }
</style>
