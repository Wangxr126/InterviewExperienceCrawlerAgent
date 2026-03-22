<template>
  <div class="mc-wrap">
    <header class="mc-hero">
      <div class="mc-hero-badge">⚖️ 微调效果</div>
      <h1 class="mc-title">模型对比</h1>
      <p class="mc-lead">
        与「微调标注 · AI 辅助」<strong>同一套提取指令</strong>，对同一面经<strong>并行</strong>请求多个端点，并排查看 JSON、题量与耗时。
      </p>
      <div class="mc-hero-deco" aria-hidden="true" />
    </header>

    <el-alert type="info" show-icon :closable="false" class="mc-hint">
      <template #title>配置提示</template>
      「本地 · 微调后」请在 .env 设置 <code>COMPARE_FINETUNED_OLLAMA_MODEL</code>（Ollama 已导入的模型名），并与
      <code>MINER_LOCAL_BASE_URL</code> 指向同一服务。
    </el-alert>

    <section class="mc-panel mc-panel-input">
      <div class="mc-section-title">
        <span class="mc-section-icon">📝</span>
        <span>输入面经</span>
      </div>
      <div class="mc-toolbar">
        <div class="mc-toolbar-row">
          <span class="mc-label">载入样本</span>
          <el-select
            v-model="selectedSampleId"
            clearable
            filterable
            placeholder="从已标注样本拉取正文（可选）"
            class="mc-select-sample"
            @change="onSampleChange"
          >
            <el-option
              v-for="s in sampleOptions"
              :key="s.id"
              :label="sampleOptionLabel(s)"
              :value="s.id"
            />
          </el-select>
          <el-button :icon="Refresh" class="mc-btn-ghost" @click="loadSampleOptions" :loading="loadingSamples">
            刷新列表
          </el-button>
        </div>
        <div class="mc-toolbar-row">
          <span class="mc-label">标题</span>
          <el-input v-model="title" placeholder="可选：帖子标题" clearable class="mc-input-title" />
        </div>
        <div class="mc-field">
          <div class="mc-field-head">
            <span class="mc-label">面经正文</span>
            <span class="mc-char-pill" :class="{ warn: content.length > 0 && content.length < 20 }">
              {{ content.length }} 字
              <template v-if="content.length > 0 && content.length < 20">（至少 20 字可对比）</template>
            </span>
          </div>
          <el-input
            v-model="content"
            type="textarea"
            :rows="9"
            placeholder="粘贴面经原文，或从上方选择样本…"
            class="mc-textarea"
          />
        </div>
      </div>
    </section>

    <section class="mc-panel mc-panel-slots">
      <div class="mc-section-title">
        <span class="mc-section-icon">🎛️</span>
        <span>三列模型槽位</span>
      </div>
      <p class="mc-section-sub">A / B / C 对应并排结果；至少选择 <strong>两个不同</strong> 的预设。</p>
      <div class="mc-slots">
        <div v-for="(slot, idx) in slotConfigs" :key="idx" class="mc-slot" :class="`tone-${idx}`">
          <div class="mc-slot-head">
            <span class="mc-slot-tag">{{ slot.tag }}</span>
            <span class="mc-slot-name">{{ columnLabels[idx] }}</span>
          </div>
          <el-select v-model="slot.presetId" placeholder="选择模型来源" class="mc-slot-select" filterable>
            <el-option
              v-for="p in presets"
              :key="p.id"
              :label="p.label"
              :value="p.id"
              :disabled="!p.configured"
            >
              <div class="mc-opt">
                <span>{{ p.label }}</span>
                <el-tag v-if="!p.configured" type="info" size="small">未配置</el-tag>
              </div>
            </el-option>
          </el-select>
          <p class="mc-slot-desc">{{ presetDesc(slot.presetId) }}</p>
        </div>
      </div>

      <div class="mc-actions">
        <el-button
          type="primary"
          size="large"
          class="mc-run-btn"
          :icon="Histogram"
          :loading="comparing"
          :disabled="!canRun"
          @click="runCompare"
        >
          {{ comparing ? '并行请求中…' : '并行对比' }}
        </el-button>
      </div>
    </section>

    <section v-if="displayResults.length" class="mc-results-wrap">
      <div class="mc-section-title mc-results-heading">
        <span class="mc-section-icon">📊</span>
        <span>对比结果</span>
      </div>

      <div v-if="summaryStats.length" class="mc-summary">
        <div
          v-for="(st, i) in summaryStats"
          :key="i"
          class="mc-summary-item"
          :class="`tone-${i}`"
        >
          <span class="mc-sum-label">{{ st.label }}</span>
          <span class="mc-sum-val">{{ st.value }}</span>
        </div>
      </div>

      <div class="mc-grid">
        <div
          v-for="(row, idx) in displayResults"
          :key="row.preset_id + '-' + idx"
          class="mc-card"
          :class="[`tone-${idx}`, { fail: !row.ok }]"
        >
          <div class="mc-card-head">
            <div class="mc-card-title-row">
              <span class="mc-card-badge">{{ columnLabels[idx] }}</span>
              <h3>{{ row.label }}</h3>
              <el-tag v-if="row.ok" type="success" effect="light" size="small" round>成功</el-tag>
              <el-tag v-else type="danger" effect="light" size="small" round>失败</el-tag>
            </div>
            <div class="mc-card-sub">
              <span v-if="row.model" class="mc-chip mono">{{ row.model }}</span>
              <span class="mc-chip">{{ row.latency_ms }} ms</span>
              <span v-if="row.question_count != null" class="mc-chip mc-chip-strong">题数 {{ row.question_count }}</span>
            </div>
          </div>
          <div class="mc-card-body">
            <template v-if="row.ok">
              <div v-if="row.parsed !== null" class="mc-json-shell">
                <vue-json-pretty :data="row.parsed" :deep="3" />
              </div>
              <pre v-else class="mc-raw">{{ row.output }}</pre>
            </template>
            <el-alert v-else type="error" :title="row.error || '未知错误'" show-icon :closable="false" />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Refresh, Histogram } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'

const FT = '/api/finetune'

async function parseJsonResponse(r) {
  let data
  try {
    data = await r.json()
  } catch {
    data = {}
  }
  if (!r.ok) {
    const d = data?.detail
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d.map((x) => x.msg || x).join('; ')
          : data?.message || `HTTP ${r.status}`
    throw new Error(msg)
  }
  return data
}

const api = {
  get: (url) => fetch(url).then(parseJsonResponse),
  post: (url, body) =>
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(parseJsonResponse),
}

const presets = ref([])
const sampleOptions = ref([])
const selectedSampleId = ref(null)
const loadingSamples = ref(false)
const title = ref('')
const content = ref('')
const comparing = ref(false)
const results = ref([])

const slotConfigs = ref([
  { presetId: 'miner_local', tag: 'A' },
  { presetId: 'finetuned_local', tag: 'B' },
  { presetId: 'miner_remote', tag: 'C' },
])

const columnLabels = ['列 A', '列 B', '列 C']

const presetDesc = (id) => {
  const p = presets.value.find((x) => x.id === id)
  return p?.description || ''
}

const sampleOptionLabel = (s) => {
  const head = (s.title || '').trim() || String(s.content_preview || '').replace(/\s+/g, ' ').slice(0, 48)
  return `#${s.id} ${head || '无标题'}`
}

const canRun = computed(() => content.value.trim().length >= 20)

/** 合并解析结果，避免模板重复调用 parsedJson */
const displayResults = computed(() =>
  results.value.map((r) => ({
    ...r,
    parsed: r.ok ? parsedJson(r.output) : null,
  }))
)

const summaryStats = computed(() => {
  if (!displayResults.value.length) return []
  return displayResults.value.map((r) => ({
    label: r.label,
    value: r.ok ? (r.question_count != null ? `${r.question_count} 题` : '已返回') : '失败',
  }))
})

const parsedJson = (text) => {
  if (!text || typeof text !== 'string') return null
  const t = text.trim()
  const tryParse = (s) => {
    try {
      return JSON.parse(s)
    } catch {
      return null
    }
  }
  let p = tryParse(t)
  if (p !== null) return p
  const m = t.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (m) {
    p = tryParse(m[1].trim())
    if (p !== null) return p
  }
  return null
}

const loadPresets = async () => {
  try {
    const list = await api.get(`${FT}/compare-presets`)
    presets.value = Array.isArray(list) ? list : []
    applyDefaultsIfNeeded()
  } catch (e) {
    console.warn(e)
    ElMessage.error('加载对比预设失败')
  }
}

const applyDefaultsIfNeeded = () => {
  const ids = presets.value.filter((p) => p.configured).map((p) => p.id)
  if (!ids.length) return
  const pick = (want, fallback) => (ids.includes(want) ? want : fallback)
  slotConfigs.value[0].presetId = pick('miner_local', ids[0])
  slotConfigs.value[1].presetId = pick('finetuned_local', pick('finetune_assist', ids[1] || ids[0]))
  slotConfigs.value[2].presetId = pick('miner_remote', ids.find((x) => x !== slotConfigs.value[0].presetId && x !== slotConfigs.value[1].presetId) || ids[0])
}

const loadSampleOptions = async () => {
  loadingSamples.value = true
  try {
    const data = await api.get(`${FT}/samples?page=1&page_size=40&status=labeled&order=desc`)
    sampleOptions.value = data.items || []
  } catch (e) {
    console.warn(e)
    ElMessage.error('加载样本列表失败')
  } finally {
    loadingSamples.value = false
  }
}

const onSampleChange = async (id) => {
  if (id == null) return
  try {
    const s = await api.get(`${FT}/samples/${id}`)
    content.value = s.content || ''
    title.value = s.title || ''
    ElMessage.success('已载入样本 #' + id)
  } catch (e) {
    ElMessage.error('载入样本失败')
  }
}

const runCompare = async () => {
  const ids = slotConfigs.value.map((s) => s.presetId).filter(Boolean)
  const uniq = [...new Set(ids)]
  if (uniq.length < 2) {
    ElMessage.warning('三列中至少选择两个不同的模型')
    return
  }
  comparing.value = true
  results.value = []
  try {
    const res = await api.post(`${FT}/compare`, {
      preset_ids: ids,
      content: content.value.trim(),
      title: title.value.trim(),
    })
    const list = res.results || []
    results.value = list
    if (!list.length) ElMessage.warning('无返回结果')
    else {
      const okN = list.filter((x) => x.ok).length
      ElMessage.success(`对比完成（${okN}/${list.length} 路成功）`)
    }
  } catch (e) {
    ElMessage.error('请求失败：' + (e.message || e))
  } finally {
    comparing.value = false
  }
}

watch(presets, () => applyDefaultsIfNeeded(), { deep: true })

onMounted(async () => {
  await loadPresets()
  await loadSampleOptions()
})
</script>

<style scoped>
.mc-wrap {
  --mc-primary: #5b6ef5;
  --mc-primary-soft: #eef0fe;
  --mc-slate: #0f172a;
  --mc-muted: #64748b;
  --mc-line: #e8ecf4;
  --mc-tone-a: #64748b;
  --mc-tone-b: #3b6ff5;
  --mc-tone-c: #0d9f6e;
  --mc-radius: 16px;
  --mc-shadow: 0 4px 32px rgba(91, 110, 245, 0.08), 0 2px 8px rgba(15, 23, 42, 0.04);
  min-height: 100vh;
  padding: 32px 36px 56px;
  max-width: 1480px;
  margin: 0 auto;
  background:
    radial-gradient(ellipse 120% 80% at 100% -20%, rgba(91, 110, 245, 0.12), transparent 50%),
    radial-gradient(ellipse 80% 60% at -10% 30%, rgba(13, 159, 110, 0.06), transparent 45%),
    linear-gradient(180deg, #f7f8fc 0%, #eef1f8 100%);
  box-sizing: border-box;
  position: relative;
}

.mc-hero {
  margin-bottom: 24px;
  position: relative;
  z-index: 1;
}
.mc-hero-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--mc-primary);
  background: var(--mc-primary-soft);
  padding: 6px 12px;
  border-radius: 999px;
  margin-bottom: 12px;
  border: 1px solid rgba(91, 110, 245, 0.2);
}
.mc-title {
  font-size: 30px;
  font-weight: 800;
  color: var(--mc-slate);
  letter-spacing: -0.03em;
  line-height: 1.2;
}
.mc-lead {
  margin-top: 10px;
  font-size: 15px;
  color: var(--mc-muted);
  max-width: 760px;
  line-height: 1.65;
}
.mc-lead strong {
  color: #475569;
  font-weight: 600;
}
.mc-hero-deco {
  position: absolute;
  right: 0;
  top: -8px;
  width: 160px;
  height: 160px;
  background: radial-gradient(circle, rgba(91, 110, 245, 0.15) 0%, transparent 70%);
  pointer-events: none;
  z-index: -1;
}

.mc-hint {
  margin-bottom: 22px;
  border-radius: 12px;
  border: 1px solid #dbe4ff;
  background: linear-gradient(135deg, #f8faff 0%, #f0f4ff 100%);
}
.mc-hint :deep(.el-alert__title) {
  font-weight: 700;
}
.mc-hint code {
  font-size: 12px;
  background: #fff;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--mc-line);
  color: #4338ca;
}

.mc-panel {
  background: #fff;
  border-radius: var(--mc-radius);
  border: 1px solid var(--mc-line);
  box-shadow: var(--mc-shadow);
  padding: 22px 26px 26px;
  margin-bottom: 22px;
}
.mc-panel-input {
  border-top: 3px solid var(--mc-primary);
}
.mc-panel-slots {
  border-top: 3px solid transparent;
  background-image: linear-gradient(#fff, #fff), linear-gradient(90deg, var(--mc-tone-a), var(--mc-tone-b), var(--mc-tone-c));
  background-origin: border-box;
  background-clip: padding-box, border-box;
  border: 1px solid transparent;
  box-shadow: var(--mc-shadow);
}

.mc-section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 800;
  color: var(--mc-slate);
  margin-bottom: 6px;
}
.mc-section-icon {
  font-size: 18px;
  line-height: 1;
}
.mc-section-sub {
  font-size: 13px;
  color: var(--mc-muted);
  margin-bottom: 18px;
  line-height: 1.5;
}
.mc-results-heading {
  margin-bottom: 14px;
}
.mc-results-wrap {
  margin-top: 8px;
}

.mc-toolbar-row {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.mc-label {
  font-size: 13px;
  font-weight: 700;
  color: #475569;
  min-width: 76px;
}
.mc-select-sample {
  min-width: 280px;
  flex: 1;
}
.mc-input-title {
  flex: 1;
  max-width: 600px;
}
.mc-field {
  margin-top: 6px;
}
.mc-field-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.mc-char-pill {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  background: #f1f5f9;
  padding: 4px 10px;
  border-radius: 999px;
}
.mc-char-pill.warn {
  color: #b45309;
  background: #fffbeb;
}
.mc-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', ui-monospace, 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.55;
  border-radius: 12px;
}
.mc-btn-ghost {
  border-radius: 10px;
}

.mc-slots {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-top: 8px;
}
@media (max-width: 1024px) {
  .mc-slots {
    grid-template-columns: 1fr;
  }
}

.mc-slot {
  padding: 16px 18px 18px;
  border-radius: 14px;
  background: #fafbfd;
  border: 1px solid var(--mc-line);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.mc-slot:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}
.mc-slot.tone-0 {
  border-left: 4px solid var(--mc-tone-a);
}
.mc-slot.tone-1 {
  border-left: 4px solid var(--mc-tone-b);
}
.mc-slot.tone-2 {
  border-left: 4px solid var(--mc-tone-c);
}

.mc-slot-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.mc-slot-tag {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 14px;
  color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}
.tone-0 .mc-slot-tag {
  background: linear-gradient(145deg, #78849e, #575f6e);
}
.tone-1 .mc-slot-tag {
  background: linear-gradient(145deg, #5b7cfa, #3b5bdb);
}
.tone-2 .mc-slot-tag {
  background: linear-gradient(145deg, #10b981, #059669);
}
.mc-slot-name {
  font-weight: 800;
  color: #334155;
  font-size: 14px;
}
.mc-slot-select {
  width: 100%;
}
.mc-slot-select :deep(.el-input__wrapper) {
  border-radius: 10px;
}
.mc-slot-desc {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 10px;
  line-height: 1.5;
  min-height: 40px;
}
.mc-opt {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.mc-actions {
  margin-top: 26px;
  display: flex;
  justify-content: center;
}
.mc-run-btn {
  min-width: 200px;
  height: 46px;
  font-weight: 700;
  font-size: 15px;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(91, 110, 245, 0.35);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.mc-run-btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 22px rgba(91, 110, 245, 0.4);
}

.mc-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 20px;
  padding: 4px 0;
}
.mc-summary-item {
  flex: 1;
  min-width: 160px;
  padding: 14px 18px;
  border-radius: 12px;
  background: #fff;
  border: 1px solid var(--mc-line);
  display: flex;
  flex-direction: column;
  gap: 6px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
}
.mc-summary-item.tone-0 {
  border-top: 3px solid var(--mc-tone-a);
}
.mc-summary-item.tone-1 {
  border-top: 3px solid var(--mc-tone-b);
}
.mc-summary-item.tone-2 {
  border-top: 3px solid var(--mc-tone-c);
}
.mc-sum-label {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mc-sum-val {
  font-size: 20px;
  font-weight: 800;
  color: var(--mc-slate);
  letter-spacing: -0.02em;
}

.mc-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  align-items: stretch;
}
@media (max-width: 1200px) {
  .mc-grid {
    grid-template-columns: 1fr;
  }
}

.mc-card {
  background: #fff;
  border-radius: 14px;
  border: 1px solid var(--mc-line);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 300px;
  box-shadow: var(--mc-shadow);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.mc-card:hover {
  box-shadow: 0 8px 36px rgba(15, 23, 42, 0.08);
}
.mc-card.tone-0 {
  border-top: 4px solid var(--mc-tone-a);
}
.mc-card.tone-1 {
  border-top: 4px solid var(--mc-tone-b);
}
.mc-card.tone-2 {
  border-top: 4px solid var(--mc-tone-c);
}
.mc-card.fail {
  border-top-color: #ef4444;
}

.mc-card-head {
  padding: 16px 18px 14px;
  background: linear-gradient(180deg, #fafbfd 0%, #ffffff 100%);
  border-bottom: 1px solid #f1f5f9;
}
.mc-card-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.mc-card-badge {
  font-size: 11px;
  font-weight: 800;
  color: #fff;
  background: var(--mc-slate);
  padding: 3px 8px;
  border-radius: 6px;
  opacity: 0.85;
}
.mc-card.tone-0 .mc-card-badge {
  background: var(--mc-tone-a);
}
.mc-card.tone-1 .mc-card-badge {
  background: var(--mc-tone-b);
}
.mc-card.tone-2 .mc-card-badge {
  background: var(--mc-tone-c);
}
.mc-card-title-row h3 {
  flex: 1;
  min-width: 0;
  font-size: 15px;
  font-weight: 800;
  color: var(--mc-slate);
  margin: 0;
}
.mc-card-sub {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.mc-chip {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  background: #f1f5f9;
  padding: 4px 10px;
  border-radius: 999px;
}
.mc-chip.mono {
  font-family: ui-monospace, monospace;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mc-chip-strong {
  color: #0f766e;
  background: #ccfbf1;
}

.mc-card-body {
  padding: 14px 16px 18px;
  flex: 1;
  overflow: auto;
  max-height: 68vh;
  background: #fcfcfe;
}
.mc-json-shell {
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
  padding: 10px 8px;
  overflow: auto;
}
.mc-card-body :deep(.vjs-tree) {
  font-size: 12px !important;
  font-family: ui-monospace, monospace !important;
}
.mc-raw {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, monospace;
  color: #334155;
  background: #fff;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
  padding: 12px;
}
</style>
