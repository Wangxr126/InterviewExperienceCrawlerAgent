<template>
  <div class="collect-page">
    <!-- 1. 统计卡片（单独一行） -->
    <div class="card stats-section">
      <div class="section-header">
        <h2 class="section-title">数据采集</h2>
        <el-button size="small" :loading="statsLoading" @click="async () => { await loadStats(); await loadTasks() }">刷新</el-button>
      </div>
      <div v-if="statsList.length" class="stats-row">
        <div v-for="item in statsList" :key="item.status" class="stat-card" :style="{ borderLeftColor: item.color }">
          <div class="stat-val" :style="{ color: item.color }">{{ item.count }}</div>
          <div class="stat-key">{{ item.label }}</div>
          <div v-if="item.questions > 0" class="stat-sub">已提取 {{ item.questions }} 题</div>
        </div>
      </div>
      <div v-else class="stats-empty">暂无数据</div>
    </div>

    <!-- 2. 数据源采集 -->
    <div class="card crawl-section">
      <div class="crawl-section-header">
        <h3 class="subsection-title">数据源</h3>
        <div class="crawl-keywords-row">
          <span class="keywords-label">🔍 关键词</span>
          <el-input v-model="form.keywords" placeholder="如：面经、Java、算法（逗号分隔，两平台共用）" size="default"
                    class="crawl-keywords-input" clearable />
        </div>
      </div>
      <div class="crawl-cards">
        <div class="crawl-card nowcoder">
          <div class="crawl-card-inner">
            <div class="crawl-header">
              <img src="https://www.nowcoder.com/favicon.ico" alt="牛客" class="platform-icon" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex'">
              <span class="platform-fallback">牛</span>
              <span class="crawl-label">牛客网</span>
            </div>
            <div class="crawl-meta">
              <span class="meta-label">爬取页数</span>
              <el-input-number v-model="form.maxPages" :min="1" :max="50" size="default" controls-position="right" />
            </div>
            <div class="crawl-actions">
              <el-button type="primary" size="default" :loading="ncLoading" @click.prevent="crawl('nowcoder')" class="crawl-btn">
                获取帖子
              </el-button>
              <span class="crawl-hint crawl-hint-spacer"></span>
            </div>
          </div>
        </div>
        <div class="crawl-card xiaohongshu">
          <div class="crawl-card-inner">
            <div class="crawl-header">
              <img src="https://www.xiaohongshu.com/favicon.ico" alt="小红书" class="platform-icon" onerror="this.style.display='none';this.nextElementSibling.style.display='inline-flex'">
              <span class="platform-fallback">红</span>
              <span class="crawl-label">小红书</span>
            </div>
            <div class="crawl-meta">
              <span class="meta-label">获取条数</span>
              <el-input-number v-model="form.xhsCount" :min="1" :max="100" size="default" controls-position="right" />
            </div>
            <div class="crawl-actions">
              <el-button type="primary" size="default" :loading="xhsLoading" @click.prevent="crawl('xiaohongshu')" class="crawl-btn">
                获取帖子
              </el-button>
              <span class="crawl-hint">需扫码登录</span>
            </div>
          </div>
        </div>
      </div>
      <div class="crawl-both-wrap">
        <el-button type="success" size="default" :loading="bothLoading" @click.prevent="crawlBoth" class="crawl-both-btn">
          🚀 同时获取牛客 + 小红书
        </el-button>
      </div>
      <!-- 抓取进度：牛客/小红书获取帖子后轮询显示 -->
      <div v-if="crawlPolling" class="progress-bar-wrap">
        <!-- 待抓取进度条 -->
        <div class="progress-item">
          <div class="progress-header">
            <span class="progress-label">📥 待抓取</span>
            <span class="progress-count">{{ pendingCount }} 条</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill pending" :style="{ width: pendingProgressPct + '%' }"></div>
          </div>
        </div>
        <!-- 待提取进度条 -->
        <div class="progress-item">
          <div class="progress-header">
            <span class="progress-label">🤖 待提取</span>
            <span class="progress-count">{{ fetchedCount }} 条</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill fetched" :style="{ width: fetchedProgressPct + '%' }"></div>
          </div>
        </div>
        <!-- 已完成统计 -->
        <div class="progress-summary">
          已完成 {{ doneCount }} 条 · 失败 {{ errorCount }} 条
        </div>
      </div>
      <div v-else-if="ncResult || xhsMsg" class="result-msg" :class="(ncResult || xhsMsg)?.ok ? 'ok' : 'err'">
        {{ ncResult?.msg || xhsMsg?.msg }}
      </div>
      <!-- 牛客发现链接日志 -->
      <div v-if="ncCrawlLog.length" class="crawl-log-wrap">
        <div class="crawl-log-title">牛客发现 {{ ncCrawlLog.length }} 条非重复链接：</div>
        <div class="crawl-log-list">
          <div v-for="(item, i) in ncCrawlLog" :key="i" class="crawl-log-item">
            <span class="crawl-log-num">{{ i + 1 }}.</span>
            <a :href="item.url" target="_blank" class="crawl-log-link">{{ item.title }}{{ item.title.length >= 50 ? '...' : '' }}</a>
          </div>
        </div>
      </div>
    </div>

    <!-- 3. LLM 提取 -->
    <div class="card extract-section">
      <div class="section-header">
        <h3 class="section-title">🤖 LLM 题目提取</h3>
        <div class="extract-badges">
          <span v-if="fetchedCount > 0" class="badge badge-warn">{{ fetchedCount }} 待提取</span>
          <span v-if="errorCount > 0" class="badge badge-err">{{ errorCount }} 失败</span>
        </div>
      </div>
      <p class="extract-desc">对已爬取正文的帖子调用 LLM 提取面试题入库，后台执行（与练习对话互不阻塞）</p>
      <div class="extract-actions">
        <el-tooltip content="对「待提取」状态的帖子（已有正文）调用 LLM 提取面试题，后台异步执行" placement="top">
          <el-button type="primary" :loading="extractLoading" @click.prevent="extractPending">
            提取面试题
          </el-button>
        </el-tooltip>
        <el-tooltip content="将「失败」状态的帖子重置后重新处理：有正文的重新提取，无正文的重新抓取" placement="top">
          <el-button type="warning" :loading="retryLoading" @click.prevent="retryErrors">重试失败项</el-button>
        </el-tooltip>
        <el-tooltip content="将「已完成」或「失败」且有正文的帖子全部重新提取（删除旧题目后用 LLM 重新提取）" placement="top">
          <el-button type="info" :loading="reExtractLoading" @click.prevent="showReExtractDialog = true">重新提取所有</el-button>
        </el-tooltip>
        <el-tooltip content="先抓取「待抓取」帖子的正文，再对「待提取」的做 LLM 提取，同步等待完成" placement="top">
          <el-button type="success" :loading="processLoading" @click.prevent="processQueue">抓取正文并提取</el-button>
        </el-tooltip>
        <el-tooltip content="用 LLM 判断「已完成」帖子是否与面经相关，无关则删除帖子及题目" placement="top">
          <el-button type="danger" :loading="cleanLoading" @click.prevent="cleanData">清洗无关帖</el-button>
        </el-tooltip>
      </div>
      <!-- 处理进度：提取进行中时轮询显示，牛客和小红书分开 -->
      <div v-if="extractPolling" class="extract-progress-wrap">
        <div v-for="item in extractProgressByPlatform" :key="item.platform" class="extract-progress-item">
          <span class="extract-platform-label">{{ item.label }}</span>
          <div class="extract-progress-bar">
            <div class="extract-progress-track">
              <div class="extract-progress-fill" :style="{ width: item.pct + '%' }"></div>
            </div>
          </div>
          <span class="extract-progress-text">{{ item.pct }}% · {{ item.text }}</span>
        </div>
        <div v-if="extractProgressByPlatform.length === 0" class="extract-progress-item">
          <span class="extract-progress-text">处理中...</span>
        </div>
      </div>
      <div v-else-if="extractMsg" class="result-msg" :class="extractMsg.ok ? 'ok' : 'err'">
        {{ extractMsg.text }}
      </div>
    </div>

    <!-- 帖子列表 -->
    <div class="card table-section">
      <div class="section-header">
        <h3 class="section-title">📋 帖子记录</h3>
        <div class="table-toolbar">
          <el-select v-model="taskFilter" placeholder="状态" clearable size="small" style="width:90px">
            <el-option v-for="opt in STATUS_OPTIONS" :key="opt.value" :label="`${opt.label}`" :value="opt.value" />
          </el-select>
          <el-tooltip placement="bottom" effect="light">
            <template #content>
              <div class="status-help">
                <div><strong>待抓取</strong>：已发现链接，尚未获取正文</div>
                <div><strong>待提取</strong>：正文已获取，待 LLM 提取面试题</div>
                <div><strong>已完成</strong>：题目已提取并入库</div>
                <div><strong>无关帖</strong>：LLM 判断正文与面经无关，参与「清洗无关帖」后删除</div>
                <div><strong>失败</strong>：抓取正文或 LLM 提取时出错</div>
              </div>
            </template>
            <el-icon class="status-help-icon"><QuestionFilled /></el-icon>
          </el-tooltip>
          <el-select v-model="taskPlatform" placeholder="平台" clearable size="small" style="width:90px">
            <el-option label="牛客" value="nowcoder" />
            <el-option label="小红书" value="xiaohongshu" />
          </el-select>
          <el-select v-model="taskKeyword" placeholder="关键词" clearable size="small" style="width:100px">
            <el-option v-for="kw in keywordOptions" :key="kw" :label="kw" :value="kw" />
          </el-select>
          <el-button size="small" @click="taskPage=1;loadTasks()">查询</el-button>
          <el-button size="small" @click="async () => { await loadStats(); await loadTasks() }">刷新</el-button>
          <el-button size="small" type="danger" plain @click="showClearAllDialog = true">清除所有</el-button>
        </div>
      </div>
      <el-table :data="tasks" size="small" class="post-table" stripe
        @sort-change="onSortChange"
        :default-sort="{ prop: 'id', order: 'descending' }"
      >
        <el-table-column label="ID" prop="id" width="60" align="center" sortable="custom" />
        <el-table-column label="平台" prop="source_platform" width="82" sortable="custom">
          <template #default="{ row }">
            <el-tag :type="row.source_platform === 'xiaohongshu' ? 'danger' : 'warning'" size="small">
              {{ row.source_platform === 'xiaohongshu' ? '小红书' : '牛客' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关键词" prop="discover_keyword" width="100" show-overflow-tooltip sortable="custom">
          <template #default="{ row }">{{ row.discover_keyword || '—' }}</template>
        </el-table-column>
        <el-table-column label="标题" prop="post_title" min-width="100" show-overflow-tooltip sortable="custom">
          <template #default="{ row }">
            <a :href="row.source_url" target="_blank" style="color:var(--primary);text-decoration:none;font-size:13px">
              {{ row.post_title || row.source_url.slice(-30) }}
            </a>
          </template>
        </el-table-column>
        <el-table-column label="公司" prop="company" width="72" show-overflow-tooltip sortable="custom" />
        <el-table-column label="正文" prop="content_len" width="68" align="center" sortable="custom">
          <template #default="{ row }">
            <el-link v-if="(row.content_len ?? 0) > 0" type="primary" :underline="false" style="font-size:12px"
                     @click="openContentDialog(row)">
              {{ row.content_len }}字
            </el-link>
            <span v-else style="color:#c0c4cc;font-size:12px">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" prop="status" width="74" align="center" sortable="custom">
          <template #default="{ row }">
            <el-tag :type="STATUS_TAG[row.status]" size="small">{{ STATUS_LABEL[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="题目" prop="questions_count" width="70" align="center" sortable="custom">
          <template #default="{ row }">
            <el-link v-if="row.questions_count > 0" type="success" :underline="false"
                     style="font-weight:700" @click="openQuestionsDialog(row)">
              {{ row.questions_count }}
            </el-link>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" prop="extraction_source" width="70" align="center" sortable="custom">
          <template #default="{ row }">
            <el-tag v-if="row.extraction_source === 'image'" type="warning" size="small">图片</el-tag>
            <el-tag v-else-if="row.extraction_source === 'content'" type="primary" size="small">正文</el-tag>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="工具调用" prop="agent_used_tool" width="90" align="center" sortable="custom">
          <template #default="{ row }">
            <el-tag v-if="row.agent_used_tool === 1" type="success" size="small">✓ 是</el-tag>
            <el-tag v-else-if="row.agent_used_tool === 0 && row.status === 'done'" type="info" size="small">否</el-tag>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="耗时" prop="extract_duration_sec" width="72" align="center" sortable="custom">
          <template #default="{ row }">
            <span v-if="row.extract_duration_sec != null" style="font-size:12px;color:var(--text-main)">{{ row.extract_duration_sec }}s</span>
            <span v-else style="color:#c0c4cc;font-size:12px">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提取时间" prop="processed_at" width="110" align="center" sortable="custom">
          <template #default="{ row }">
            <span v-if="row.processed_at" style="font-size:11px">{{ row.processed_at?.slice(0,16) }}</span>
            <span v-else style="color:#c0c4cc;font-size:12px">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发现时间" prop="discovered_at" width="110" align="center" sortable="custom">
          <template #default="{ row }">
            <span style="font-size:11px">{{ row.discovered_at?.slice(0,16) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="tasks.length === 0" class="table-empty">暂无记录，点击「查询」加载</div>
      <div v-else class="pagination-wrap">
        <!-- 自定义分页器 - 显示所有页码 -->
        <div class="custom-pagination">
          <span class="pagination-total">共 {{ taskTotal }} 条 · 共 {{ totalPages }} 页</span>
          <button class="pagination-btn" :disabled="taskPage <= 1" @click="taskPage = 1; loadTasks()">
            ◀◀
          </button>
          <button class="pagination-btn" :disabled="taskPage <= 1" @click="taskPage--; loadTasks()">
            ◀
          </button>
          
          <!-- 页码按钮 -->
          <div class="pagination-pager">
            <button
              v-for="page in visiblePages"
              :key="page"
              class="pagination-page-btn"
              :class="{ active: page === taskPage }"
              @click="taskPage = page; loadTasks()"
            >
              {{ page }}
            </button>
          </div>
          
          <button class="pagination-btn" :disabled="taskPage >= totalPages" @click="taskPage++; loadTasks()">
            ▶
          </button>
          <button class="pagination-btn" :disabled="taskPage >= totalPages" @click="taskPage = totalPages; loadTasks()">
            ▶▶
          </button>
          
          <!-- 跳转输入 -->
          <div class="pagination-jumper">
            <span>跳至</span>
            <input
              v-model="jumpPage"
              type="number"
              :min="1"
              :max="totalPages"
              :placeholder="`1-${totalPages}`"
              @keyup.enter="handleJump"
              class="pagination-jumper-input"
            />
            <span class="pagination-jumper-hint">/ {{ totalPages }} 页</span>
            <button @click="handleJump" class="pagination-jumper-btn">跳转</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 重新提取所有确认弹窗 -->
    <el-dialog v-model="showReExtractDialog" width="440px" align-center class="clear-all-dialog"
               :close-on-click-modal="false" :show-close="true">
      <template #header>
        <div class="clear-all-header">
          <div class="clear-all-icon-wrap">
            <el-icon class="warn-icon"><WarningFilled /></el-icon>
          </div>
          <h3 class="clear-all-title">重新提取所有题目</h3>
        </div>
      </template>
      <div class="clear-all-body">
        <p class="clear-all-desc">此操作将对所有有正文的帖子重新调用 LLM 提取面试题：</p>
        <div class="clear-all-items">
          <div class="clear-all-item">删除所有已提取的面试题</div>
          <div class="clear-all-item">重置所有帖子状态为「待提取」</div>
          <div class="clear-all-item">重新调用 LLM 提取所有题目</div>
        </div>
        <p class="clear-all-tip">此操作会清除所有已提取的题目信息，请谨慎操作。</p>
      </div>
      <template #footer>
        <div class="clear-all-footer">
          <el-button size="large" @click="showReExtractDialog = false">取消</el-button>
          <el-button type="warning" size="large" :loading="reExtractLoading" @click="confirmReExtractAll">
            确认重新提取
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 清除所有确认弹窗 -->
    <el-dialog v-model="showClearAllDialog" width="440px" align-center class="clear-all-dialog"
               :close-on-click-modal="false" :show-close="true">
      <template #header>
        <div class="clear-all-header">
          <div class="clear-all-icon-wrap">
            <el-icon class="warn-icon"><WarningFilled /></el-icon>
          </div>
          <h3 class="clear-all-title">清除所有数据</h3>
        </div>
      </template>
      <div class="clear-all-body">
        <p class="clear-all-desc">此操作将永久删除以下数据，且无法恢复：</p>
        <div class="clear-all-items">
          <div class="clear-all-item">所有帖子记录</div>
          <div class="clear-all-item">所有已提取的面试题</div>
          <div class="clear-all-item">相关爬取日志与本地图片</div>
          <div class="clear-all-item">LLM 交互日志、解析失败记录、小红书链接缓存</div>
        </div>
        <p class="clear-all-tip">请确认您已备份重要数据后再执行。</p>
      </div>
      <template #footer>
        <div class="clear-all-footer">
          <el-button size="large" @click="showClearAllDialog = false">取消</el-button>
          <el-button type="danger" size="large" :loading="clearAllLoading" @click="confirmClearAll">
            确认清除
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 正文内容弹窗 -->
    <el-dialog v-model="contentDialogVisible" :title="contentDialogTitle" width="560px" destroy-on-close>
      <div v-if="contentLoading" style="text-align:center;padding:24px">加载中...</div>
      <div v-else class="content-body">{{ contentDialogText || '暂无正文' }}</div>
    </el-dialog>

    <!-- 题目详情弹窗 -->
    <el-dialog v-model="questionsDialogVisible" title="已提取题目" width="640px" destroy-on-close>
      <div v-if="questionsLoading" style="text-align:center;padding:24px">加载中...</div>
      <div v-else-if="dialogQuestions.length === 0" style="color:var(--text-sub);text-align:center;padding:24px">
        暂无题目
      </div>
      <div v-else class="questions-list">
        <div v-for="(q, idx) in dialogQuestions" :key="q.q_id" class="question-item">
          <div class="q-num">{{ idx + 1 }}.</div>
          <div class="q-body">
            <div class="q-text">{{ q.question_text }}</div>
            <div class="q-meta-row">
              <span v-if="q.topic_tags?.length" class="q-tags">
              <el-tag v-for="t in q.topic_tags" :key="t" size="small" style="margin-right:4px">{{ t }}</el-tag>
              </span>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted, onActivated } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled, Loading, QuestionFilled } from '@element-plus/icons-vue'
import { api } from '../api.js'

const rawStats = ref({})
const extractPolling = ref(false)
const extractInitialByPlatform = ref({})  // { nowcoder: 5, xiaohongshu: 17 }
let extractPollTimer = null
const tasks    = ref([])
const statsLoading   = ref(false)
const ncLoading      = ref(false)
const xhsLoading     = ref(false)
const processLoading = ref(false)
const extractLoading   = ref(false)
const retryLoading     = ref(false)
const reExtractLoading = ref(false)
const cleanLoading     = ref(false)
const ncResult   = ref(null)
const ncCrawlLog = ref([])  // 牛客发现链接列表，用于日志展示
const xhsMsg     = ref(null)
const bothLoading = ref(false)
const extractMsg = ref(null)
const taskFilter    = ref('')
const taskPlatform  = ref('')
const taskKeyword   = ref('')
const keywordOptions = ref([])
const taskPage      = ref(1)
const taskPageSize  = ref(20)
const taskTotal     = ref(0)
const questionsDialogVisible = ref(false)
const questionsLoading      = ref(false)
const dialogQuestions       = ref([])
const contentDialogVisible  = ref(false)
const contentDialogTitle    = ref('')
const contentDialogText     = ref('')
const contentLoading        = ref(false)
const showClearAllDialog    = ref(false)
const showReExtractDialog   = ref(false)
const clearAllLoading       = ref(false)
const crawlPolling          = ref(false)
const crawlDiscovered       = ref(0)
const crawlInitialDone      = ref(0)
let crawlPollTimer          = null
const refetchLoading        = ref(null)  // task_id 正在重抓正文

const form = reactive({ keywords: '', maxPages: 5, xhsCount: 20 })

const STATUS_OPTIONS = [
  { value: 'pending',   label: '待抓取',  desc: '未获取正文' },
  { value: 'fetched',   label: '待提取',  desc: '待 LLM 提取' },
  { value: 'done',      label: '已完成',  desc: '题目已入库' },
  { value: 'unrelated', label: '无关帖',  desc: 'LLM 判断与面经无关' },
  { value: 'error',     label: '失败',    desc: '抓取或提取出错' },
]
const STATUS_META = {
  pending:    { label: '待抓取', color: '#e6a23c' },
  fetched:    { label: '待提取', color: '#409eff' },
  done:       { label: '已完成', color: '#67c23a' },
  unrelated:  { label: '无关帖', color: '#909399' },
  error:      { label: '失败',   color: '#f56c6c' },
  skipped:    { label: '已跳过', color: '#c0c4cc' },
}
const STATUS_LABEL = { pending:'待抓取', fetched:'待提取', done:'已完成', unrelated:'无关帖', error:'失败', skipped:'已跳过' }
const STATUS_TAG   = { pending:'warning', fetched:'', done:'success', unrelated:'info', error:'danger', skipped:'info' }

const fetchedCount = computed(() => {
  const v = rawStats.value['fetched']
  return typeof v === 'object' ? (v.count ?? 0) : (v ?? 0)
})
const fetchedByPlatform = computed(() => {
  const v = rawStats.value['fetched_by_platform']
  return v && typeof v === 'object' ? v : {}
})
const PLATFORM_LABELS = { nowcoder: '牛客', xiaohongshu: '小红书' }
const extractProgressByPlatform = computed(() => {
  if (!extractPolling.value) return []
  const initial = extractInitialByPlatform.value || {}
  const current = fetchedByPlatform.value || {}
  const platforms = ['nowcoder', 'xiaohongshu']
  return platforms
    .filter(p => (initial[p] ?? 0) > 0)
    .map(p => {
      const init = initial[p] ?? 0
      const cur = current[p] ?? 0
      const done = init - cur
      const pct = init > 0 ? Math.min(100, Math.round((done / init) * 100)) : 0
      return {
        platform: p,
        label: PLATFORM_LABELS[p] || p,
        pct,
        text: `已处理 ${done} / ${init} 条`,
      }
    })
})
const errorCount = computed(() => {
  const v = rawStats.value['error']
  return typeof v === 'object' ? (v.count ?? 0) : (v ?? 0)
})

const doneCount = computed(() => {
  const v = rawStats.value['done']
  return typeof v === 'object' ? (v.count ?? 0) : (v ?? 0)
})

const pendingCount = computed(() => {
  const v = rawStats.value['pending']
  return typeof v === 'object' ? (v.count ?? 0) : (v ?? 0)
})

const crawlInitialPending = ref(0)
const crawlInitialFetched = ref(0)

const pendingProgressPct = computed(() => {
  if (!crawlPolling.value || crawlInitialPending.value <= 0) return 0
  const current = pendingCount.value
  const processed = Math.max(0, crawlInitialPending.value - current)
  return Math.min(100, Math.round((processed / crawlInitialPending.value) * 100))
})

const fetchedProgressPct = computed(() => {
  if (!crawlPolling.value || crawlInitialFetched.value <= 0) return 0
  const current = fetchedCount.value
  const processed = Math.max(0, crawlInitialFetched.value - current)
  return Math.min(100, Math.round((processed / crawlInitialFetched.value) * 100))
})

const crawlProgressPct = computed(() => {
  if (!crawlPolling.value || crawlDiscovered.value <= 0) return 0
  const delta = Math.max(0, doneCount.value - crawlInitialDone.value)
  return Math.min(100, Math.round((delta / crawlDiscovered.value) * 100))
})

const crawlProgressText = computed(() => {
  if (!crawlPolling.value) return ''
  const pending = typeof rawStats.value['pending'] === 'object' ? (rawStats.value['pending']?.count ?? 0) : (rawStats.value['pending'] ?? 0)
  const fetched = typeof rawStats.value['fetched'] === 'object' ? (rawStats.value['fetched']?.count ?? 0) : (rawStats.value['fetched'] ?? 0)
  const done = doneCount.value
  // return `待抓取 ${pending} · 待提取 ${fetched} · 已完成 ${done}`
  return `待抓取 ${pending} · 待提取 ${fetched} · 已完成 ${done}`
})

const statsList = computed(() => {
  return Object.entries(rawStats.value)
    .filter(([k]) => k !== 'fetched_by_platform')  // 排除内部字段
    .map(([status, v]) => ({
      status,
      count:     typeof v === 'object' ? (v.count ?? 0) : v,
      questions: typeof v === 'object' ? (v.questions ?? 0) : 0,
      label:     STATUS_META[status]?.label ?? status,
      color:     STATUS_META[status]?.color ?? 'var(--primary)',
    }))
})

const loadStats = async (silent = false) => {
  if (!silent) statsLoading.value = true
  try {
    const d = await api.getCrawlerStats()
    rawStats.value = d.crawl_stats || {}
    if (Array.isArray(d.keywords)) keywordOptions.value = d.keywords
  } catch {
    if (!silent) ElMessage.error('获取统计失败')
  } finally {
    if (!silent) statsLoading.value = false
  }
}

const loadKeywords = async () => {
  try {
    const d = await api.getCrawlerStats()
    keywordOptions.value = d.keywords || []
  } catch {
    keywordOptions.value = []
  }
}

const taskSortBy    = ref('')
const taskSortOrder = ref('desc')
const jumpPage      = ref(1)

const totalPages = computed(() => Math.ceil(taskTotal.value / taskPageSize.value))

const visiblePages = computed(() => {
  const total = totalPages.value
  const current = taskPage.value
  const maxVisible = 5  // 最多显示5个页码按钮，简洁不拥挤
  
  if (total <= maxVisible) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  
  const half = Math.floor(maxVisible / 2)
  let start = Math.max(1, current - half)
  let end = Math.min(total, start + maxVisible - 1)
  
  if (end - start + 1 < maxVisible) {
    start = Math.max(1, end - maxVisible + 1)
  }
  
  const pages = []
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  return pages
})

const handleJump = () => {
  const page = parseInt(jumpPage.value, 10)
  if (!isNaN(page) && page >= 1 && page <= totalPages.value) {
    taskPage.value = page
    loadTasks()
  } else {
    ElMessage.warning(`共 ${totalPages.value} 页，请输入 1～${totalPages.value} 之间的页码（不是条数 ${taskTotal.value}）`)
  }
}

const onSortChange = ({ prop, order }) => {
  taskSortBy.value = prop || ''
  taskSortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  taskPage.value = 1
  loadTasks()
}

const loadTasks = async () => {
  try {
    const d = await api.getCrawlerTasks({
      status: taskFilter.value,
      platform: taskPlatform.value,
      keyword: taskKeyword.value,
      limit: taskPageSize.value,
      offset: (taskPage.value - 1) * taskPageSize.value,
      sort_by: taskSortBy.value || undefined,
      sort_order: taskSortOrder.value,
    })
    taskTotal.value = d.total ?? 0
    tasks.value = (d.tasks || []).map(t => ({
      ...t,
      content_len: t.content_len ?? (t.raw_content ? t.raw_content.length : 0),
    }))
  } catch {
    ElMessage.error('加载任务失败')
  }
}

const onTaskPageChange = () => {
  loadTasks()
}

const crawlBoth = async () => {
  bothLoading.value = true
  crawlPolling.value = false
  ncCrawlLog.value = []
  try {
    await loadStats()
    crawlInitialDone.value = doneCount.value
    crawlInitialPending.value = pendingCount.value
    crawlInitialFetched.value = fetchedCount.value
    const kws = form.keywords.trim()
      ? form.keywords.split(',').map(k => k.trim()).filter(Boolean)
      : null
    const body = { keywords: kws, max_pages: form.maxPages, max_notes: form.xhsCount, headless: false, process: true }
    const [ncRes, xhsRes] = await Promise.all([
      api.triggerCrawl({ ...body, platform: 'nowcoder' }),
      api.triggerCrawl({ ...body, platform: 'xiaohongshu' }),
    ])
    const ncOk = ncRes?.status === 'ok'
    const xhsOk = xhsRes?.status === 'ok'
    const ncDiscovered = ncRes?.discovered ?? 0
    ncCrawlLog.value = ncRes?.discovered_links || []
    crawlDiscovered.value = ncDiscovered > 0 ? ncDiscovered : 999
    crawlPolling.value = true
    if (ncOk && xhsOk) {
      ncResult.value = { ok: true, msg: `牛客发现 ${ncDiscovered} 条，小红书已启动。请完成扫码后查看下方进度。` }
      xhsMsg.value = { ok: true, msg: xhsRes?.message }
    } else if (ncOk) {
      ncResult.value = { ok: true, msg: ncRes?.message }
      xhsMsg.value = { ok: false, msg: xhsRes?.detail || '小红书启动失败' }
    } else if (xhsOk) {
      ncResult.value = { ok: false, msg: ncRes?.detail || '牛客启动失败' }
      xhsMsg.value = { ok: true, msg: xhsRes?.message }
    } else {
      ncResult.value = { ok: false, msg: ncRes?.detail || '牛客失败' }
      xhsMsg.value = { ok: false, msg: xhsRes?.detail || '小红书失败' }
    }
    await loadStats()
    await loadTasks()
  } catch (e) {
    ncResult.value = { ok: false, msg: e?.response?.data?.detail || '请求失败' }
    xhsMsg.value = { ok: false, msg: '请求失败' }
  } finally {
    bothLoading.value = false
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
    xhsLoading.value = true; xhsMsg.value = null; crawlPolling.value = false
    try {
      await loadStats()
      crawlInitialDone.value = doneCount.value
      crawlInitialPending.value = pendingCount.value
      crawlInitialFetched.value = fetchedCount.value
      const d = await api.triggerCrawl(body)
      xhsMsg.value = { ok: true, msg: d.message || '✅ 小红书爬取已在后台启动，请查看弹出的浏览器完成扫码' }
      crawlDiscovered.value = 999
      crawlPolling.value = true
    } catch {
      xhsMsg.value = { ok: false, msg: '请求失败，请确认后端已启动' }
    } finally {
      xhsLoading.value = false
    }
    return
  }

  // 牛客：发现立即返回，LLM 提取在后台运行
  ncLoading.value = true; ncResult.value = null; ncCrawlLog.value = []; crawlPolling.value = false
  try {
    const d = await api.triggerCrawl(body)
    ncCrawlLog.value = d.discovered_links || []
    ncResult.value = {
      ok: d.status === 'ok',
      msg: d.status === 'ok'
        ? `✅ ${d.message}（后台处理中，下方显示实时进度）`
        : (d.detail || '爬取失败'),
    }
    if (d.status === 'ok' && (d.discovered ?? 0) > 0) {
      await loadStats()
      crawlDiscovered.value = d.discovered
      crawlInitialDone.value = doneCount.value
      crawlInitialPending.value = pendingCount.value
      crawlInitialFetched.value = fetchedCount.value
      crawlPolling.value = true
      await loadTasks()
    } else if (d.status === 'ok') {
      await loadStats(); await loadTasks()
    }
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
  extractPolling.value = false
  try {
    await loadStats()
    extractInitialByPlatform.value = { ...(rawStats.value['fetched_by_platform'] || {}) }
    if (fetchedCount.value <= 0) {
      ElMessage.info('没有待提取的帖子')
      extractLoading.value = false
      return
    }
    const d = await api.extractPending(30)
    extractMsg.value = { ok: true, text: `✅ ${d.message}` }
    extractPolling.value = true
    await loadTasks()
  } catch {
    extractMsg.value = { ok: false, text: '启动失败，请确认后端已运行' }
  } finally {
    extractLoading.value = false
  }
}

const stopExtractPolling = () => {
  if (extractPollTimer) clearInterval(extractPollTimer)
  extractPollTimer = null
  extractPolling.value = false
}

const openContentDialog = async (row) => {
  if (!row.task_id) return
  contentDialogVisible.value = true
  contentDialogTitle.value = row.post_title || '帖子正文'
  contentLoading.value = true
  contentDialogText.value = ''
  try {
    const d = await api.getCrawlerTaskDetail(row.task_id)
    contentDialogText.value = d.raw_content || ''
  } catch {
    ElMessage.error('加载正文失败')
  } finally {
    contentLoading.value = false
  }
}

const openQuestionsDialog = async (row) => {
  if (!row.task_id || row.questions_count <= 0) return
  questionsDialogVisible.value = true
  questionsLoading.value = true
  dialogQuestions.value = []
  try {
    const d = await api.getTaskQuestions(row.task_id)
    dialogQuestions.value = d.questions || []
  } catch {
    ElMessage.error('加载题目失败')
  } finally {
    questionsLoading.value = false
  }
}

const retryErrors = async () => {
  retryLoading.value = true
  extractMsg.value = null
  extractPolling.value = false
  try {
    await loadStats()
    const d = await api.retryErrors(30)
    extractMsg.value = { ok: true, text: `🔄 ${d.message}` }
    if ((d.reset ?? 0) > 0) {
      extractPolling.value = true  // 后台处理中，轮询刷新帖子列表
    }
    await loadTasks()
  } catch {
    extractMsg.value = { ok: false, text: '重试请求失败，请确认后端已运行' }
  } finally {
    retryLoading.value = false
  }
}

const reExtractAll = async () => {
  reExtractLoading.value = true
  extractMsg.value = null
  extractPolling.value = false
  try {
    await loadStats()
    const doneCount = typeof rawStats.value['done'] === 'object' ? (rawStats.value['done']?.count ?? 0) : (rawStats.value['done'] ?? 0)
    const errorCount = typeof rawStats.value['error'] === 'object' ? (rawStats.value['error']?.count ?? 0) : (rawStats.value['error'] ?? 0)
    if (doneCount <= 0 && errorCount <= 0) {
      ElMessage.info('没有已完成或失败的帖子可重新提取')
      reExtractLoading.value = false
      return
    }
    const d = await api.reExtractAll(50)
    extractMsg.value = { ok: true, text: `🔄 ${d.message}` }
    if ((d.reset ?? 0) > 0) {
      extractPolling.value = true
    }
    await loadStats()
    await loadTasks()
  } catch {
    extractMsg.value = { ok: false, text: '重新提取请求失败，请确认后端已运行' }
  } finally {
    reExtractLoading.value = false
  }
}

const confirmReExtractAll = async () => {
  reExtractLoading.value = true
  extractMsg.value = null
  extractPolling.value = false
  try {
    await loadStats()
    const d = await api.reExtractAll(50)
    showReExtractDialog.value = false
    extractMsg.value = { ok: true, text: `🔄 ${d.message}` }
    if ((d.reset ?? 0) > 0) {
      extractPolling.value = true
    }
    await loadStats()
    await loadTasks()
    ElMessage.success(d.message || '已开始重新提取')
  } catch {
    extractMsg.value = { ok: false, text: '重新提取请求失败，请确认后端已运行' }
    ElMessage.error('重新提取失败')
  } finally {
    reExtractLoading.value = false
  }
}

const confirmClearAll = async () => {
  clearAllLoading.value = true
  try {
    const d = await api.clearAllCrawlData()
    showClearAllDialog.value = false
    ElMessage.success(d.message || '已清除')
    await loadStats()
    await loadTasks()
    await loadKeywords()
  } catch {
    ElMessage.error('清除失败')
  } finally {
    clearAllLoading.value = false
  }
}

const cleanData = async () => {
  cleanLoading.value = true
  extractMsg.value = null
  try {
    const d = await api.cleanData(50)
    extractMsg.value = { ok: true, text: `🧹 ${d.message}` }
    await loadStats(); await loadTasks()
    ElMessage.success(d.message)
  } catch {
    extractMsg.value = { ok: false, text: '清洗请求失败，请确认后端已运行' }
    ElMessage.error('清洗失败')
  } finally {
    cleanLoading.value = false
  }
}

const canRefetchXhs = (row) => {
  if (row?.source_platform !== 'xiaohongshu') return false
  const empty = (row.content_len ?? 0) <= 0
  const pageNotFound = (row.post_title || '').includes('页面不见了')
  return empty || pageNotFound
}

const refetchXhsBody = async (row) => {
  if (!row?.task_id) return
  refetchLoading.value = row.task_id
  try {
    const d = await api.refetchXhsBody(row.task_id)
    if (d?.status === 'ok') {
      ElMessage.success(d.message || '重抓正文成功')
      await loadStats()
      await loadTasks()
    } else {
      ElMessage.warning(d?.message || '重抓失败，请确认已登录小红书')
    }
  } catch {
    ElMessage.error('重抓正文请求失败')
  } finally {
    refetchLoading.value = null
  }
}

const stopCrawlPolling = () => {
  if (crawlPollTimer) clearInterval(crawlPollTimer)
  crawlPollTimer = null
  crawlPolling.value = false
}

onMounted(async () => {
  await loadStats()
  await loadTasks()
  loadKeywords()
  // 刷新后恢复提取进度显示（若后端仍在处理）
  try {
    const d = await api.getExtractionStatus()
    if (d?.running) {
      extractPolling.value = true
      extractInitialByPlatform.value = d.initial_by_platform || (fetchedCount.value > 0 ? { nowcoder: fetchedCount.value, xiaohongshu: 0 } : {})
    }
  } catch {
    // 忽略
  }
})

// 页面激活时重新加载数据（解决删除后切换页面数据不刷新的问题）
onActivated(async () => {
  await loadStats()
  await loadTasks()
})

onUnmounted(() => { stopExtractPolling(); stopCrawlPolling() })

// 提取进行中时轮询显示进度（不自动刷新表格，避免体验差）
watch(extractPolling, (polling) => {
  if (extractPollTimer) clearInterval(extractPollTimer)
  extractPollTimer = null
  if (polling) {
    extractPollTimer = setInterval(async () => {
      await loadStats(true)
      const allDone = extractProgressByPlatform.value.length === 0 || extractProgressByPlatform.value.every(p => p.pct >= 100)
      if (fetchedCount.value <= 0 || allDone) {
        stopExtractPolling()
      }
    }, 5000)
  }
})

// 抓取进行中时轮询显示进度（不自动刷新表格，避免体验差）
watch(crawlPolling, (polling) => {
  if (crawlPollTimer) clearInterval(crawlPollTimer)
  crawlPollTimer = null
  if (polling) {
    crawlPollTimer = setInterval(async () => {
      await loadStats(true)
      const pending = typeof rawStats.value['pending'] === 'object' ? (rawStats.value['pending']?.count ?? 0) : (rawStats.value['pending'] ?? 0)
      const fetched = typeof rawStats.value['fetched'] === 'object' ? (rawStats.value['fetched']?.count ?? 0) : (rawStats.value['fetched'] ?? 0)
      if (crawlProgressPct.value >= 100 || (pending === 0 && fetched === 0)) {
        stopCrawlPolling()
      }
    }, 5000)
  }
})
</script>

<style scoped>
.collect-page {
  padding: 0 8px 24px;
  /*数据采集页面宽度 */
  max-width: 1200px;
  margin: 0 auto;
}
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-title { font-size: 16px; font-weight: 600; color: var(--text-main); margin: 0; }
.stats-section .section-title { font-size: 18px; }

/* 1. 统计区域 - 更紧凑的网格 */
.stats-section { padding: 24px 28px; margin-bottom: 20px; }
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.stat-card {
  background: linear-gradient(135deg, #fff 0%, #f8fafc 100%);
  border-radius: 12px;
  padding: 20px 18px;
  border: 1px solid var(--border);
  border-left-width: 4px;
  text-align: center;
  transition: box-shadow 0.2s, transform 0.2s;
}
.stat-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.06); transform: translateY(-1px); }
.stat-val { font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }
.stat-key { font-size: 13px; color: var(--text-sub); margin-top: 6px; font-weight: 500; }
.stat-sub { font-size: 11px; color: var(--text-sub); margin-top: 2px; opacity: 0.9; }
.stats-empty { color: var(--text-sub); font-size: 13px; text-align: center; padding: 24px; }

/* 2. 数据源 - 现代卡片风格 */
.crawl-section {
  padding: 28px 32px;
  margin-bottom: 20px;
  background: linear-gradient(180deg, #fafbff 0%, #fff 100%);
  border: 1px solid rgba(91, 110, 245, 0.12);
  border-radius: 16px;
}
.crawl-section-header { margin-bottom: 24px; }
.subsection-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-main);
  margin: 0 0 16px 0;
  letter-spacing: -0.02em;
}
.crawl-keywords-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.keywords-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-sub);
  white-space: nowrap;
}
.crawl-keywords-input { flex: 1; min-width: 280px; max-width: 420px; }
.crawl-keywords-input :deep(.el-input__wrapper) {
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.crawl-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  align-items: stretch;
}
.crawl-card {
  border-radius: 14px;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
  display: flex;
}
.crawl-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
}
.crawl-card.nowcoder .crawl-card-inner {
  background: linear-gradient(145deg, #fff9f0 0%, #fff 50%);
  border: 1px solid rgba(245, 158, 11, 0.25);
}
.crawl-card.xiaohongshu .crawl-card-inner {
  background: linear-gradient(145deg, #fff5f5 0%, #fff 50%);
  border: 1px solid rgba(244, 63, 94, 0.2);
}
.crawl-card-inner {
  padding: 24px;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  flex: 1;
  width: 100%;
}
.crawl-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
.crawl-hint-spacer {
  visibility: hidden;
  height: 1.2em;
  font-size: 12px;
  display: block;
}
.crawl-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.platform-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  object-fit: contain;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.platform-fallback {
  display: none;
  width: 36px;
  height: 36px;
  line-height: 36px;
  text-align: center;
  border-radius: 10px;
  font-weight: 700;
  font-size: 16px;
}
.crawl-card.nowcoder .platform-fallback { background: linear-gradient(135deg, #fbbf24, #f59e0b); color: #fff; }
.crawl-card.xiaohongshu .platform-fallback { background: linear-gradient(135deg, #f43f5e, #e11d48); color: #fff; }
.crawl-label {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-main);
  letter-spacing: -0.02em;
}
.crawl-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
}
.meta-label {
  color: var(--text-sub);
  font-weight: 500;
  flex-shrink: 0;
}
.crawl-card .el-input-number { width: 120px; }
.crawl-card .el-input-number :deep(.el-input__wrapper) { border-radius: 8px; }
.crawl-both-wrap {
  margin-top: 16px;
  text-align: center;
}
.crawl-both-btn {
  font-weight: 600;
  padding: 10px 24px;
}
.crawl-btn {
  font-weight: 600;
  padding: 10px 20px;
  border-radius: 10px;
}
.crawl-hint {
  font-size: 12px;
  color: var(--text-sub);
  opacity: 0.9;
}

/* 进度条 - 简洁双条样式 */
.crawl-section .progress-bar-wrap {
  margin-top: 20px;
  padding: 20px 24px;
  background: linear-gradient(135deg, rgba(91, 110, 245, 0.05) 0%, rgba(91, 110, 245, 0.02) 100%);
  border-radius: 12px;
  border: 1px solid rgba(91, 110, 245, 0.12);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.progress-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.progress-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
}
.progress-count {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-sub);
}
.progress-track {
  height: 8px;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 8px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 8px;
  transition: width 0.4s ease;
}
.progress-fill.pending {
  background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%);
}
.progress-fill.fetched {
  background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%);
}
.progress-summary {
  font-size: 13px;
  color: var(--text-sub);
  text-align: center;
  padding-top: 4px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}
.crawl-section .result-msg { margin-top: 20px; border-radius: 12px; }

/* 3. LLM 提取 */
.extract-section { padding: 24px 28px; margin-bottom: 20px; }
.extract-desc { font-size: 13px; color: var(--text-sub); margin: 0 0 18px 0; line-height: 1.5; }
.extract-actions { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.extract-badges { display: flex; gap: 10px; align-items: center; }
.badge { font-size: 12px; padding: 4px 10px; border-radius: 20px; font-weight: 500; }
.badge-warn { background: #fef3c7; color: #b45309; }
.badge-err { background: #fee2e2; color: #b91c1c; }

/* LLM 提取进度条：牛客和小红书分开显示 */
.extract-progress-wrap {
  margin-top: 24px;
  padding: 20px 24px;
  background: linear-gradient(135deg, rgba(91, 110, 245, 0.08) 0%, rgba(91, 110, 245, 0.04) 100%);
  border-radius: 14px;
  border: 1px solid rgba(91, 110, 245, 0.15);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.extract-progress-item {
  display: flex;
  align-items: center;
  gap: 16px;
}
.extract-platform-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-main);
  min-width: 56px;
}
.extract-progress-bar { flex: 1; min-width: 0; }
.extract-progress-track {
  height: 10px;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  overflow: hidden;
}
.extract-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #5b6ef5 0%, #7c8ff7 100%);
  border-radius: 10px;
  transition: width 0.35s ease;
}
.extract-progress-text {
  font-size: 14px;
  color: var(--text-main);
  font-weight: 600;
  white-space: nowrap;
}
.extract-section .result-msg { margin-top: 24px; }

/* 4. 表格 */
.table-section { padding: 24px 28px; }
.table-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.table-toolbar .el-button { padding: 5px 10px; }
.status-help-icon { font-size: 16px; color: var(--text-sub); cursor: help; margin-left: -4px; }
.status-help-icon:hover { color: var(--primary); }
.status-help { font-size: 12px; line-height: 1.8; }
.status-help div { margin-bottom: 4px; }
.status-help div:last-child { margin-bottom: 0; }

/* 表格整体容器 */
.post-table {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  font-size: 13px;
}

/* 表头 */
.post-table :deep(.el-table__header-wrapper) {
  background: linear-gradient(135deg, #f0f4ff 0%, #f8fafc 100%);
}
.post-table :deep(.el-table__header th) {
  background: transparent !important;
  font-weight: 700;
  font-size: 12px;
  color: #4a5568;
  letter-spacing: 0.02em;
  padding: 10px 0;
  border-bottom: 2px solid rgba(91,110,245,0.15);
}
/* 排序箭头颜色 */
.post-table :deep(.el-table__column-filter-trigger),
.post-table :deep(.caret-wrapper) {
  color: #a0aec0;
}
.post-table :deep(.caret-wrapper .sort-caret) {
  color: #a0aec0;
}
.post-table :deep(.caret-wrapper .sort-caret.ascending) {
  color: var(--primary);
}
.post-table :deep(.caret-wrapper .sort-caret.descending) {
  color: var(--primary);
}
.post-table :deep(.el-table__column-header-button:hover .caret-wrapper .sort-caret) {
  color: var(--primary);
}

/* 行样式 */
.post-table :deep(.el-table__row td) {
  font-size: 13px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f4f8;
  transition: background 0.15s;
}
.post-table :deep(.el-table__body tr:hover > td) {
  background: #f0f4ff !important;
}
.post-table :deep(.el-table__body tr.el-table__row--striped td) {
  background: #fafbff;
}

.table-empty { text-align: center; color: var(--text-sub); padding: 40px 20px; font-size: 14px; }
.pagination-wrap { margin-top: 16px; display: flex; justify-content: center; }

/* 自定义分页器 */
.custom-pagination {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid var(--border);
  flex-wrap: wrap;
  justify-content: center;
}

.pagination-total {
  font-size: 13px;
  color: var(--text-sub);
  font-weight: 500;
  margin-right: 8px;
}

.pagination-btn {
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: white;
  color: var(--text-main);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pagination-btn:hover:not(:disabled) {
  background: var(--primary-light);
  color: var(--primary);
  border-color: var(--primary);
}

.pagination-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  color: var(--text-sub);
}

.pagination-pager {
  display: flex;
  gap: 4px;
  align-items: center;
}

.pagination-page-btn {
  min-width: 32px;
  height: 32px;
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: white;
  color: var(--text-main);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pagination-page-btn:hover {
  background: var(--primary-light);
  color: var(--primary);
  border-color: var(--primary);
}

.pagination-page-btn.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
  font-weight: 600;
}

.pagination-jumper {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--border);
}
.pagination-jumper-hint {
  font-size: 12px;
  color: var(--text-sub);
}

.pagination-jumper-input {
  width: 50px;
  height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  text-align: center;
}

.pagination-jumper-input:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(91, 110, 245, 0.1);
}

.pagination-jumper-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--primary);
  border-radius: 6px;
  background: var(--primary);
  color: white;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.pagination-jumper-btn:hover {
  background: #4a5ef5;
  border-color: #4a5ef5;
}

.pagination-jumper-btn:active {
  transform: scale(0.98);
}

.result-msg { padding: 12px 16px; border-radius: 10px; font-size: 13px; margin-top: 14px; line-height: 1.5; }
.result-msg.ok { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
.result-msg.err { background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5; }
.crawl-log-wrap { margin-top: 16px; padding: 12px 16px; background: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0; max-height: 240px; overflow-y: auto; }
.crawl-log-title { font-size: 13px; font-weight: 600; color: var(--text-main); margin-bottom: 8px; }
.crawl-log-list { display: flex; flex-direction: column; gap: 4px; }
.crawl-log-item { font-size: 12px; display: flex; align-items: flex-start; gap: 6px; }
.crawl-log-num { color: var(--text-sub); flex-shrink: 0; }
.crawl-log-link { color: var(--primary); text-decoration: none; word-break: break-all; }
.crawl-log-link:hover { text-decoration: underline; }

.questions-list { max-height: 400px; overflow-y: auto; }
.question-item { display: flex; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.question-item:last-child { border-bottom: none; }
.q-num { flex-shrink: 0; font-weight: 600; color: var(--primary); }
.q-body { flex: 1; min-width: 0; }
.q-text { font-size: 14px; line-height: 1.5; margin-bottom: 6px; }
.q-meta-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.extraction-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.extraction-badge.content { background: #dbeafe; color: #1d4ed8; }
.extraction-badge.image { background: #fce7f3; color: #be185d; }
.q-tags { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.content-body { max-height: 400px; overflow-y: auto; font-size: 14px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }

/* 清除所有确认弹窗 */
/* 清除所有弹窗 - 简洁现代 */
.clear-all-dialog :deep(.el-dialog) {
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 24px 48px rgba(0,0,0,0.12);
}
.clear-all-dialog :deep(.el-dialog__header) {
  padding: 24px 24px 0;
  margin-right: 0;
}
.clear-all-dialog :deep(.el-dialog__body) { padding: 20px 24px 24px; }
.clear-all-dialog :deep(.el-dialog__footer) { padding: 0 24px 24px; }
.clear-all-header {
  text-align: center;
  padding-bottom: 8px;
}
.clear-all-icon-wrap {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.clear-all-icon-wrap .warn-icon {
  font-size: 28px;
  color: #b45309;
}
.clear-all-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-main);
  margin: 0;
  letter-spacing: -0.02em;
}
.clear-all-body { padding: 0 4px; }
.clear-all-desc {
  font-size: 14px;
  color: var(--text-sub);
  margin: 0 0 14px 0;
  line-height: 1.5;
}
.clear-all-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 18px;
}
.clear-all-item {
  font-size: 14px;
  color: var(--text-main);
  padding: 10px 14px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid var(--border);
}
.clear-all-tip {
  font-size: 13px;
  color: #b91c1c;
  margin: 0;
  padding: 10px 14px;
  background: #fef2f2;
  border-radius: 10px;
  border: 1px solid #fecaca;
}
.clear-all-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .crawl-cards { grid-template-columns: 1fr; }
}
</style>
