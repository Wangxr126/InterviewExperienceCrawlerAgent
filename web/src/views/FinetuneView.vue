<template>
  <div class="finetune-container">
    <!-- 顶部统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card primary">
        <div class="stat-icon">📊</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total ?? '-' }}</div>
          <div class="stat-label">样本总数</div>
        </div>
      </div>
      <div class="stat-card warning">
        <div class="stat-icon">⏳</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.pending ?? '-' }}</div>
          <div class="stat-label">待标注</div>
        </div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon">✅</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.labeled ?? '-' }}</div>
          <div class="stat-label">已标注</div>
        </div>
      </div>
      <div class="stat-card info">
        <div class="stat-icon">✏️</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.modified ?? '-' }}</div>
          <div class="stat-label">手动修改</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">📁</div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.log_files ?? '-' }}</div>
          <div class="stat-label">日志文件</div>
        </div>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="action-bar">
      <el-button @click="loadStats" :icon="Refresh" size="large">刷新统计</el-button>
      <el-button @click="autoImportAll" :loading="autoImporting" type="primary" size="large">
        {{ autoImporting ? '同步中...' : '🔄 同步日志' }}
      </el-button>
      <el-button type="success" @click="exportLabeled" :loading="exporting" size="large">
        导出标注数据
      </el-button>
    </div>

    <!-- 主内容区 -->
    <el-tabs v-model="activeTab" class="content-tabs" @tab-change="onTabChange">
      <!-- Tab 1: 样本列表 -->
      <el-tab-pane label="📋 样本列表" name="list">
        <div class="list-container">
          <div class="list-toolbar">
            <el-radio-group v-model="filterStatus" @change="loadSamples(1)" size="large">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="pending">待标注</el-radio-button>
              <el-radio-button value="labeled">已标注</el-radio-button>
            </el-radio-group>
            <el-button :icon="Refresh" @click="loadSamples(1)" size="large">刷新</el-button>
          </div>
          
          <el-table :data="samples" class="sample-table" @row-click="onSampleClick">
            <el-table-column label="ID" prop="id" width="80" align="center" />
            <el-table-column label="面经内容">
              <template #default="{ row }">
                <div class="content-cell">{{ row.content_preview }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'labeled' ? 'success' : 'warning'" size="large">
                  {{ row.status === 'labeled' ? '已标注' : '待标注' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="手动修改" width="120" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_modified" type="danger" size="large">已修改</el-tag>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" prop="created_at" width="180" />
          </el-table>
          
          <el-pagination 
            class="pagination"
            background 
            layout="prev, pager, next, total"
            :total="pagerTotal" 
            :page-size="pageSize"
            :current-page="currentPage" 
            @current-change="loadSamples" 
          />
        </div>
      </el-tab-pane>

      <!-- Tab 2: 标注编辑器 -->
      <el-tab-pane label="✏️ 标注编辑" name="editor">
        <div class="editor-container" v-if="currentSample">
          <!-- 编辑器头部 -->
          <div class="editor-header">
            <div class="header-left">
              <span class="sample-id">样本 #{{ currentSample.id }}</span>
              <el-tag :type="currentSample.status === 'labeled' ? 'success' : 'warning'" size="large">
                {{ currentSample.status === 'labeled' ? '已标注' : '待标注' }}
              </el-tag>
              <el-tag v-if="isModified" type="danger" size="large">已修改</el-tag>
            </div>
            <div class="header-right">
              <span class="time-info">创建：{{ currentSample.created_at }}</span>
              <span v-if="currentSample.labeled_at" class="time-info">标注：{{ currentSample.labeled_at }}</span>
            </div>
          </div>

          <!-- 帖子信息 -->
          <div class="post-info" v-if="currentSample.title || currentSample.source_url">
            <div class="post-info-title" v-if="currentSample.title">
              📝 {{ currentSample.title }}
            </div>
            <a 
              v-if="currentSample.source_url" 
              :href="currentSample.source_url" 
              target="_blank" 
              class="post-info-link"
            >
              🔗 查看原帖
            </a>
          </div>

          <!-- 导航按钮（移到顶部） -->
          <div class="navigation-actions-top">
            <el-button @click="gotoPrevSample" :disabled="!hasPrevSample" size="large">
              ← 上一题
            </el-button>
            <span class="sample-progress">{{ currentSampleIndex + 1 }} / {{ samples.length }}</span>
            <el-button @click="gotoNextSample" :disabled="!hasNextSample" size="large">
              下一题 →
            </el-button>
          </div>

          <!-- 三栏布局 -->
          <div class="editor-grid">
            <!-- 左栏：原始面经 -->
            <div class="editor-panel">
              <div class="panel-header">
                <span class="panel-title">① 原始面经正文</span>
              </div>
              
              <!-- 标题和链接 -->
              <div class="post-meta" v-if="currentSample.title || currentSample.source_url">
                <div class="post-title" v-if="currentSample.title">
                  {{ currentSample.title }}
                </div>
                <a 
                  v-if="currentSample.source_url" 
                  :href="currentSample.source_url" 
                  target="_blank" 
                  class="post-link"
                >
                  🔗 查看原帖
                </a>
              </div>
              
              <div class="panel-content">
                <el-input 
                  type="textarea" 
                  :model-value="currentSample.content"
                  readonly 
                  :rows="28" 
                  class="content-textarea"
                />
              </div>
            </div>

            <!-- 中栏：小模型输出 -->
            <div class="editor-panel">
              <div class="panel-header">
                <span class="panel-title">② 小模型提取结果</span>
                <span class="panel-subtitle">（{{ llmQuestionCount }} 道题）</span>
                <el-button @click="copyLlmRaw" size="small" style="margin-left: auto;">
                  📋 复制
                </el-button>
              </div>
              <div class="panel-content json-viewer">
                <vue-json-pretty 
                  :data="parseJson(currentSample.llm_raw)"
                  :deep="99"
                  :showLength="true"
                  :showLine="true"
                />
              </div>
            </div>

            <!-- 右栏：大模型辅助 + 编辑 -->
            <div class="editor-panel">
              <div class="panel-header">
                <span class="panel-title">③ 大模型辅助生成</span>
                <el-button 
                  type="primary" 
                  @click="callAssist"
                  :loading="assisting" 
                  size="large"
                >
                  {{ assisting ? '生成中...' : '调用大模型' }}
                </el-button>
              </div>

              <!-- 操作按钮（移到顶部） -->
              <div class="editor-actions-top">
                <el-button type="success" @click="confirmLabel" :loading="labeling" size="large">
                  ✅ 确认标注
                </el-button>
                <el-button type="info" @click="confirmNoChange" :loading="labeling" size="large">
                  ✔️ 无需修改
                </el-button>
                <el-button @click="formatEditOutput" size="large">格式化 JSON</el-button>
              </div>

              <!-- 可编辑的JSON文本框 -->
              <div class="panel-content">
                <el-input 
                  type="textarea" 
                  v-model="editOutput"
                  :rows="28"
                  placeholder="在此编辑JSON..."
                  class="edit-textarea"
                />
              </div>
            </div>
          </div>
        </div>
        
        <el-empty v-else description="请在「样本列表」中点击一条记录进入编辑" :image-size="200" />
      </el-tab-pane>

      <!-- Tab 3: 日志文件 -->
      <el-tab-pane label="📂 导入日志" name="logs">
        <div class="logs-container">
          <div class="section-title">微调/llm_logs/ 下的日志文件</div>
          <el-table :data="logFiles" class="logs-table" @row-click="onLogRowClick">
            <el-table-column label="模型" prop="model" width="180" />
            <el-table-column label="文件名" prop="filename" />
            <el-table-column label="条数" prop="line_count" width="100" align="center" />
            <el-table-column label="修改时间" prop="mtime" width="200" />
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button size="large" type="primary" @click.stop="importLog(row)">导入</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="tip-text">💡 点击「导入」将该文件的记录写入数据库，重复记录自动跳过</div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VueJsonPretty from 'vue-json-pretty'
import 'vue-json-pretty/lib/styles.css'

const BASE = '/api/finetune'
const api = {
  get: (url) => fetch(url).then(r => r.json()),
  post: (url, body) => fetch(url, { 
    method: 'POST', 
    headers: { 'Content-Type': 'application/json' }, 
    body: JSON.stringify(body) 
  }).then(r => r.json()),
}

// 统计数据
const stats = ref({})
const loadStats = async () => { stats.value = await api.get(`${BASE}/stats`) }

// 自动导入
const autoImporting = ref(false)
const autoImportAll = async () => {
  autoImporting.value = true
  try {
    const res = await api.post(`${BASE}/import-all`, {})
    if (res.imported > 0) {
      ElMessage.success(`自动导入完成：新增 ${res.imported} 条，跳过 ${res.skipped} 条`)
    }
    await loadStats()
    await loadSamples(1)
  } catch (e) {
    ElMessage.error('导入失败：' + e.message)
  } finally {
    autoImporting.value = false
  }
}

// 日志文件
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

// 样本列表
const samples = ref([])
const filterStatus = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const pagerTotal = ref(0)
const activeTab = ref('list')

const loadSamples = async (page = currentPage.value) => {
  currentPage.value = page
  const params = new URLSearchParams({ 
    page, 
    page_size: pageSize.value,
    order: 'asc'  // 按ID从小到大排序
  })
  if (filterStatus.value) params.set('status', filterStatus.value)
  const res = await api.get(`${BASE}/samples?${params}`)
  samples.value = res.items || []
  pagerTotal.value = res.total || 0
}

const onSampleClick = async (row) => {
  const detail = await api.get(`${BASE}/samples/${row.id}`)
  currentSample.value = detail
  // 自动格式化已有的输出
  editOutput.value = detail.assist_output ? formatJson(detail.assist_output) : ''
  activeTab.value = 'editor'
}

// 导航功能
const currentSampleIndex = computed(() => {
  if (!currentSample.value || !samples.value.length) return -1
  return samples.value.findIndex(s => s.id === currentSample.value.id)
})

const hasPrevSample = computed(() => currentSampleIndex.value > 0)
const hasNextSample = computed(() => currentSampleIndex.value >= 0 && currentSampleIndex.value < samples.value.length - 1)

const gotoPrevSample = async () => {
  if (hasPrevSample.value) {
    await onSampleClick(samples.value[currentSampleIndex.value - 1])
  }
}

const gotoNextSample = async () => {
  if (hasNextSample.value) {
    await onSampleClick(samples.value[currentSampleIndex.value + 1])
  }
}

// 标注编辑器
const currentSample = ref(null)
const editOutput = ref('')
const assisting = ref(false)
const labeling = ref(false)
const exporting = ref(false)

const isModified = computed(() => {
  const orig = currentSample.value?.assist_output || ''
  return editOutput.value.trim() !== orig.trim() && editOutput.value.trim() !== ''
})

const parseJson = (str) => {
  if (!str) return {}
  try { return JSON.parse(str) } catch { return { error: '无效JSON', raw: str } }
}

// 计算小模型提取的题目数量
const llmQuestionCount = computed(() => {
  if (!currentSample.value?.llm_raw) return 0
  try {
    const parsed = JSON.parse(currentSample.value.llm_raw)
    if (Array.isArray(parsed)) {
      return parsed.length
    }
    return 0
  } catch {
    return 0
  }
})

// 解析编辑输出：如果是list，去掉首尾括号展示为对象数组
const parsedEditOutput = computed(() => {
  if (!editOutput.value) return []
  try {
    const parsed = JSON.parse(editOutput.value)
    // 如果是数组，直接返回（vue-json-pretty会自动展示）
    if (Array.isArray(parsed)) {
      return parsed
    }
    return parsed
  } catch {
    return { error: '无效JSON', raw: editOutput.value }
  }
})

// 当JSON编辑器内容改变时
const onEditOutputChange = (newData) => {
  editOutput.value = JSON.stringify(newData, null, 2)
}

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
      // 自动跳转到下一题
      if (hasNextSample.value) {
        setTimeout(() => gotoNextSample(), 500)
      }
    }
  } finally {
    labeling.value = false
  }
}

// 复制小模型提取结果
const copyLlmRaw = () => {
  const text = currentSample.value.llm_raw || ''
  if (!text) {
    ElMessage.warning('没有内容可复制')
    return
  }
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

const confirmNoChange = async () => {
  // 使用小模型的输出作为最终标注
  const llmOutput = currentSample.value.llm_raw
  if (!llmOutput) { ElMessage.warning('小模型输出为空'); return }
  
  labeling.value = true
  try {
    const res = await api.post(`${BASE}/label`, {
      sample_id: currentSample.value.id,
      final_output: llmOutput,
      is_modified: false,
    })
    if (res.status === 'ok') {
      ElMessage.success('已标注为无需修改 ✅')
      currentSample.value.status = 'labeled'
      currentSample.value.labeled_at = res.labeled_at
      loadStats()
      // 自动跳转到下一题
      if (hasNextSample.value) {
        setTimeout(() => gotoNextSample(), 500)
      }
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
  // 不再自动导入，用户需要手动点击按钮导入
})

// 页面激活时重新加载数据
onActivated(async () => {
  await loadSamples()
  await loadStats()
})

</script>

<style scoped>
.finetune-container {
  min-height: 100vh;
  background: #f5f7fa;
  padding: 32px;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  border-radius: 16px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
}

.stat-icon {
  font-size: 40px;
  line-height: 1;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 36px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 8px;
}

.stat-card.primary .stat-value { color: #3b82f6; }
.stat-card.warning .stat-value { color: #f59e0b; }
.stat-card.success .stat-value { color: #10b981; }
.stat-card.info .stat-value { color: #8b5cf6; }

.stat-label {
  font-size: 15px;
  color: #6b7280;
  font-weight: 500;
}

/* 操作按钮 */
.action-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.action-bar .el-button {
  font-size: 16px;
  padding: 12px 24px;
  border-radius: 12px;
  font-weight: 600;
}

/* 主内容区 */
.content-tabs {
  background: white;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  min-height: 600px;
}

.content-tabs :deep(.el-tabs__header) {
  margin-bottom: 24px;
}

.content-tabs :deep(.el-tabs__item) {
  font-size: 18px;
  font-weight: 600;
  padding: 0 24px;
  height: 50px;
  line-height: 50px;
}

/* 样本列表 */
.list-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.list-toolbar {
  display: flex;
  gap: 16px;
  align-items: center;
}

.list-toolbar .el-radio-group {
  font-size: 16px;
}

.sample-table {
  font-size: 15px;
  cursor: pointer;
}

.sample-table :deep(.el-table__header th) {
  background: #f9fafb;
  font-size: 16px;
  font-weight: 600;
}

.sample-table :deep(.el-table__row:hover) {
  background: #f0f9ff;
}

.content-cell {
  font-size: 15px;
  line-height: 1.6;
  color: #374151;
}

.text-muted {
  color: #9ca3af;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

/* 编辑器 */
.editor-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #f9fafb;
  border-radius: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sample-id {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.header-right {
  display: flex;
  gap: 16px;
}

.time-info {
  font-size: 14px;
  color: #6b7280;
}

.editor-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  min-height: 700px;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #f9fafb;
  border-radius: 12px;
  padding: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 12px;
  border-bottom: 2px solid #e5e7eb;
}

.post-info {
  padding: 16px 20px;
  background: #fffbeb;
  border-radius: 8px;
  margin-bottom: 16px;
  border-left: 4px solid #f59e0b;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.post-info-title {
  font-size: 16px;
  font-weight: 600;
  color: #92400e;
  flex: 1;
  line-height: 1.5;
}

.post-info-link {
  display: inline-block;
  font-size: 14px;
  color: #f59e0b;
  text-decoration: none;
  padding: 6px 16px;
  border-radius: 6px;
  background: white;
  border: 1px solid #fbbf24;
  transition: all 0.2s;
  white-space: nowrap;
}

.post-info-link:hover {
  background: #fef3c7;
  color: #d97706;
  border-color: #f59e0b;
}

.post-meta {
  padding: 12px 20px;
  background: #f0f9ff;
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 4px solid #3b82f6;
}

.post-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
  line-height: 1.5;
}

.post-link {
  display: inline-block;
  font-size: 14px;
  color: #3b82f6;
  text-decoration: none;
  padding: 4px 12px;
  border-radius: 6px;
  background: white;
  transition: all 0.2s;
}

.post-link:hover {
  background: #dbeafe;
  color: #2563eb;
}

.panel-title {
  font-size: 17px;
  font-weight: 700;
  color: #111827;
}

.panel-subtitle {
  font-size: 14px;
  color: #9ca3af;
  margin-left: 8px;
}

.panel-content {
  flex: 1;
  overflow: auto;
  background: white;
  border-radius: 8px;
  padding: 16px;
}

.content-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 15px;
  line-height: 1.8;
  color: #1f2937;
}

.edit-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2937;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  padding: 12px;
}

.json-viewer {
  font-size: 15px;
}

.json-viewer :deep(.vjs-tree) {
  font-size: 15px;
}

.editor-actions {
  display: flex;
  gap: 12px;
  padding-top: 12px;
}

.editor-actions-top {
  display: flex;
  gap: 12px;
  padding: 12px 20px;
  background: #f0fdf4;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 2px solid #22c55e;
}

.navigation-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
  margin-top: 12px;
}

.navigation-actions-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #f0f9ff;
  border-radius: 12px;
  margin-bottom: 20px;
  border: 2px solid #3b82f6;
}

.sample-progress {
  font-size: 16px;
  font-weight: 600;
  color: #6b7280;
}

/* 日志文件 */
.logs-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title {
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}

.logs-table {
  font-size: 15px;
  cursor: pointer;
}

.logs-table :deep(.el-table__header th) {
  background: #f9fafb;
  font-size: 16px;
  font-weight: 600;
}

.logs-table :deep(.el-table__row:hover) {
  background: #f0f9ff;
}

.tip-text {
  font-size: 15px;
  color: #6b7280;
  padding: 12px 16px;
  background: #fef3c7;
  border-radius: 8px;
  border-left: 4px solid #f59e0b;
}
</style>
