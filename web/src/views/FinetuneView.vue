<template>
  <div class="finetune-wrap">
    <!-- 顶部统计 -->
    <div class="stat-bar">
      <div class="stat-card">
        <div class="stat-num">{{ stats.total ?? '-' }}</div>
        <div class="stat-label">样本总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-num pending">{{ stats.pending ?? '-' }}</div>
        <div class="stat-label">待标注</div>
      </div>
      <div class="stat-card">
        <div class="stat-num done">{{ stats.labeled ?? '-' }}</div>
        <div class="stat-label">已标注</div>
      </div>
      <div class="stat-card">
        <div class="stat-num modified">{{ stats.modified ?? '-' }}</div>
        <div class="stat-label">手动修改</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.log_files ?? '-' }}</div>
        <div class="stat-label">日志文件</div>
      </div>
      <div class="stat-actions">
        <el-button @click="loadStats" :icon="Refresh" circle title="刷新统计" />
        <el-button @click="autoImportAll" :loading="autoImporting" title="扫描并导入所有日志文件中的新数据">
          {{ autoImporting ? '同步中...' : '🔄 同步日志' }}
        </el-button>
        <el-button type="success" @click="exportLabeled" :loading="exporting">导出标注数据</el-button>
      </div>
    </div>

    <!-- 标签栏 -->
    <el-tabs v-model="activeTab" class="main-tabs" @tab-change="onTabChange">
      <!-- ── Tab 1: 日志文件 ── -->
      <el-tab-pane label="📂 导入日志" name="logs">
        <div class="tab-content">
          <div class="section-title">微调/llm_logs/ 下的日志文件</div>
          <el-table :data="logFiles" border stripe size="small" @row-click="onLogRowClick"
                    style="cursor:pointer">
            <el-table-column label="模型" prop="model" width="160" />
            <el-table-column label="文件名" prop="filename" />
            <el-table-column label="条数" prop="line_count" width="80" align="center" />
            <el-table-column label="修改时间" prop="mtime" width="160" />
            <el-table-column label="操作" width="110" align="center">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click.stop="importLog(row)">导入</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="tip">点击「导入」将该文件的记录写入 SQLite，重复记录自动跳过。</div>
        </div>
      </el-tab-pane>

      <!-- ── Tab 2: 样本列表 ── -->
      <el-tab-pane label="📋 样本列表" name="list">
        <div class="tab-content">
          <div class="toolbar">
            <el-radio-group v-model="filterStatus" @change="loadSamples(1)" size="small">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="pending">待标注</el-radio-button>
              <el-radio-button value="labeled">已标注</el-radio-button>
            </el-radio-group>
            <el-button :icon="Refresh" @click="loadSamples(1)" size="small">刷新</el-button>
          </div>
          <el-table :data="samples" border stripe size="small" @row-click="onSampleClick"
                    style="cursor:pointer;margin-top:12px">
            <el-table-column label="ID" prop="id" width="64" align="center" />
            <el-table-column label="面经摘要">
              <template #default="{ row }">
                <span class="content-preview">{{ row.content_preview }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'labeled' ? 'success' : 'info'" size="small">
                  {{ row.status === 'labeled' ? '已标注' : '待标注' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="手动修改" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_modified" type="warning" size="small">已修改</el-tag>
                <span v-else class="text-sub">—</span>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" prop="created_at" width="160" />
            <el-table-column label="标注时间" prop="labeled_at" width="160">
              <template #default="{ row }">{{ row.labeled_at || '—' }}</template>
            </el-table-column>
          </el-table>
          <el-pagination class="pager" background layout="prev, pager, next, total"
                         :total="pagerTotal" :page-size="pageSize"
                         :current-page="currentPage" @current-change="loadSamples" />
        </div>
      </el-tab-pane>

      <!-- ── Tab 3: 标注编辑器 ── -->
      <el-tab-pane label="✏️ 标注编辑" name="editor">
        <div class="editor-wrap" v-if="currentSample">
          <div class="editor-header">
            <span class="editor-id">样本 #{{ currentSample.id }}</span>
            <el-tag :type="currentSample.status === 'labeled' ? 'success' : 'info'" size="small">
              {{ currentSample.status === 'labeled' ? '已标注' : '待标注' }}
            </el-tag>
            <span class="text-sub" style="margin-left:auto;font-size:12px">
              创建：{{ currentSample.created_at }}
              {{ currentSample.labeled_at ? ' | 标注：' + currentSample.labeled_at : '' }}
            </span>
          </div>

          <div class="three-col">
            <!-- 左：原始面经 -->
            <div class="col">
              <div class="col-title">① 原始面经正文</div>
              <el-input type="textarea" :model-value="currentSample.content"
                        readonly :rows="24" class="mono-area" resize="none" />
            </div>

            <!-- 中：小模型输出 -->
            <div class="col">
              <div class="col-title">② 小模型提取结果（只读参考）</div>
              <el-input type="textarea" :model-value="formatJson(currentSample.llm_raw)"
                        readonly :rows="24" class="mono-area" resize="none" />
            </div>

            <!-- 右：大模型辅助 + 编辑 -->
            <div class="col">
              <div class="col-title">
                ③ 大模型辅助生成（可编辑 → 确认为标注数据）
                <el-button size="small" type="primary" @click="callAssist"
                           :loading="assisting" style="margin-left:auto">调用大模型</el-button>
              </div>
              <!-- 大模型配置（可选覆盖） -->
              <el-collapse class="assist-config" v-model="configExpanded">
                <el-collapse-item title="大模型配置（留空使用 .env 默认）" name="cfg">
                  <div class="config-row">
                    <el-input v-model="assistCfg.base_url" placeholder="base_url（如 https://api.openai.com/v1）" size="small" />
                    <el-input v-model="assistCfg.api_key"  placeholder="api_key" size="small" show-password />
                    <el-input v-model="assistCfg.model"    placeholder="model（如 qwen3:4b）" size="small" />
                  </div>
                </el-collapse-item>
              </el-collapse>
              <el-input type="textarea" v-model="editOutput"
                        :rows="18" class="mono-area" resize="none"
                        placeholder="点击「调用大模型」生成，或直接粘贴/编辑 JSON 数组..." />
              <div class="editor-actions">
                <el-button type="success" @click="confirmLabel" :loading="labeling">
                  ✅ 确认标注
                </el-button>
                <el-button @click="formatEditOutput">格式化 JSON</el-button>
                <span class="text-sub" style="font-size:12px">
                  是否修改：{{ isModified ? '✏️ 是' : '— 否' }}
                </span>
              </div>
            </div>
          </div>
        </div>
        <el-empty v-else description="请在「样本列表」中点击一条记录进入编辑" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const BASE = '/api/finetune'
const api = {
  get:  (url)       => fetch(url).then(r => r.json()),
  post: (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()),
}

// ── 统计 ──
const stats = ref({})
const loadStats = async () => { stats.value = await api.get(`${BASE}/stats`) }

// ── 全量自动导入 ──
const autoImporting = ref(false)
const autoImportAll = async () => {
  autoImporting.value = true
  try {
    const res = await api.post(`${BASE}/import-all`, {})
    if (res.imported > 0) {
      ElMessage.success(`自动导入完成：新增 ${res.imported} 条，跳过 ${res.skipped} 条（共 ${res.files} 个文件）`)
    }
    await loadStats()
    await loadSamples(1)
  } catch (e) {
    // 静默失败，不影响页面使用
  } finally {
    autoImporting.value = false
  }
}

// ── 日志文件 ──
const logFiles = ref([])
const loadLogFiles = async () => { logFiles.value = await api.get(`${BASE}/log-files`) }
const importLog = async (row) => {
  const res = await api.post(`${BASE}/import`, { log_path: row.path })
  ElMessage.success(`导入完成：新增 ${res.imported} 条，跳过 ${res.skipped} 条`)
  await loadStats()
  await loadSamples(1)
  activeTab.value = 'list'
}
const onLogRowClick = (row) => importLog(row)

// ── 样本列表 ──
const samples = ref([])
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const pagerTotal = ref(0)
const activeTab = ref('list')

const loadSamples = async (page = currentPage.value) => {
  currentPage.value = page
  const params = new URLSearchParams({ page, page_size: pageSize.value })
  if (filterStatus.value) params.set('status', filterStatus.value)
  const res = await api.get(`${BASE}/samples?${params}`)
  samples.value = res.items || []
  pagerTotal.value = res.total || 0
}

const onSampleClick = async (row) => {
  const detail = await api.get(`${BASE}/samples/${row.id}`)
  currentSample.value = detail
  editOutput.value = detail.assist_output || ''
  activeTab.value = 'editor'
}

// ── 标注编辑器 ──
const currentSample = ref(null)
const editOutput = ref('')
const assisting = ref(false)
const labeling = ref(false)
const exporting = ref(false)
const configExpanded = ref([])
const assistCfg = ref({ base_url: '', api_key: '', model: '' })

const isModified = computed(() => {
  const orig = currentSample.value?.assist_output || ''
  return editOutput.value.trim() !== orig.trim() && editOutput.value.trim() !== ''
})

const formatJson = (str) => {
  if (!str) return ''
  try { return JSON.stringify(JSON.parse(str), null, 2) } catch { return str }
}

const formatEditOutput = () => {
  editOutput.value = formatJson(editOutput.value)
}

const callAssist = async () => {
  if (!currentSample.value) return
  assisting.value = true
  try {
    const body = { sample_id: currentSample.value.id, content: currentSample.value.content }
    if (assistCfg.value.base_url) body.base_url = assistCfg.value.base_url
    if (assistCfg.value.api_key)  body.api_key  = assistCfg.value.api_key
    if (assistCfg.value.model)    body.model    = assistCfg.value.model
    const res = await api.post(`${BASE}/assist`, body)
    if (res.error) { ElMessage.error('大模型调用失败：' + res.error); return }
    editOutput.value = formatJson(res.output)
    ElMessage.success(`大模型（${res.model}）生成完成`)
  } finally {
    assisting.value = false
  }
}

const confirmLabel = async () => {
  if (!editOutput.value.trim()) { ElMessage.warning('标注内容不能为空'); return }
  labeling.value = true
  try {
    const res = await api.post(`${BASE}/label`, {
      sample_id: currentSample.value.id,
      final_output: editOutput.value.trim(),
      is_modified: isModified.value,
    })
    if (res.status === 'ok') {
      ElMessage.success('标注已保存 ✅')
      currentSample.value.status = 'labeled'
      currentSample.value.labeled_at = res.labeled_at
      loadStats()
    }
  } finally {
    labeling.value = false
  }
}

const exportLabeled = async () => {
  exporting.value = true
  try {
    const res = await api.post(`${BASE}/export`, {})
    ElMessage.success(`已导出 ${res.exported} 条 → ${res.path}`)
  } finally {
    exporting.value = false
  }
}

const onTabChange = (tab) => {
  if (tab === 'list') loadSamples(1)
  else if (tab === 'logs') loadLogFiles()
}

onMounted(async () => {
  await loadStats()
  await loadLogFiles()
  // 自动扫描并导入所有日志文件，已有记录跳过
  await autoImportAll()
})
</script>

<style scoped>
.finetune-wrap { padding: 20px; display: flex; flex-direction: column; gap: 16px; height: 100%; overflow-y: auto; }

.stat-bar {
  display: flex; align-items: center; gap: 16px;
  background: #fff; border-radius: 12px; padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  flex-wrap: wrap;
}
.stat-card { text-align: center; min-width: 72px; }
.stat-num { font-size: 28px; font-weight: 700; color: var(--primary, #5B6EF5); line-height: 1; }
.stat-num.pending { color: #e6a23c; }
.stat-num.done    { color: #67c23a; }
.stat-num.modified { color: #f56c6c; }
.stat-label { font-size: 11px; color: #999; margin-top: 4px; }
.stat-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }

.main-tabs { flex: 1; }
.tab-content { padding: 12px 4px; }
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #333; }
.tip { font-size: 12px; color: #999; margin-top: 8px; }
.toolbar { display: flex; gap: 10px; align-items: center; }
.content-preview { font-size: 13px; color: #444; }
.text-sub { color: #aaa; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }

/* 编辑器 */
.editor-wrap { display: flex; flex-direction: column; gap: 12px; height: 100%; }
.editor-header { display: flex; align-items: center; gap: 10px; }
.editor-id { font-weight: 700; font-size: 14px; }
.three-col { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
.col { display: flex; flex-direction: column; gap: 8px; min-height: 0; }
.col-title {
  font-size: 13px; font-weight: 600; color: #555;
  display: flex; align-items: center; gap: 6px;
  padding-bottom: 4px; border-bottom: 1px solid #eee;
}
.mono-area :deep(textarea) {
  font-family: 'JetBrains Mono', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
}
.assist-config { margin: 0; }
.config-row { display: flex; flex-direction: column; gap: 6px; }
.editor-actions { display: flex; gap: 10px; align-items: center; padding-top: 4px; }
</style>
