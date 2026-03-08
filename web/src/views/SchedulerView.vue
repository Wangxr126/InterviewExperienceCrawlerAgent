<template>
  <div class="card">
    <div class="card-title">⏰ 定时任务管理</div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon> 新建任务
      </el-button>
      <el-button @click="loadJobs">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
      <div style="flex:1"></div>
      <el-select v-model="filterEnabled" placeholder="筛选状态" style="width:120px" @change="loadJobs">
        <el-option label="全部任务" :value="null" />
        <el-option label="仅启用" :value="true" />
        <el-option label="仅禁用" :value="false" />
      </el-select>
    </div>

    <!-- 任务列表 -->
    <el-table :data="jobs" v-loading="loading" style="width:100%;margin-top:16px">
      <el-table-column label="任务名称" prop="job_name" min-width="150">
        <template #default="{ row }">
          <div style="font-weight:500">{{ row.job_name }}</div>
        </template>
      </el-table-column>
      
      <el-table-column label="任务类型" width="140">
        <template #default="{ row }">
          <el-tag :type="getJobTypeColor(row.job_type)" size="small">
            {{ getJobTypeName(row.job_type) }}
          </el-tag>
        </template>
      </el-table-column>
      
      <el-table-column label="调度配置" min-width="180">
        <template #default="{ row }">
          <div style="font-size:13px">
            {{ formatSchedule(row) }}
          </div>
        </template>
      </el-table-column>
      
      <el-table-column label="运行状态" width="200">
        <template #default="{ row }">
          <div style="font-size:12px">
            <div v-if="row.last_run_at">
              上次: {{ formatTime(row.last_run_at) }}
            </div>
            <div v-if="row.next_run_at" style="color:var(--primary)">
              下次: {{ formatTime(row.next_run_at) }}
            </div>
            <div v-if="row.run_count > 0" style="color:var(--text-sub)">
              已运行 {{ row.run_count }} 次
            </div>
          </div>
        </template>
      </el-table-column>
      
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-switch v-model="row.enabled" @change="toggleJob(row)" />
        </template>
      </el-table-column>
      
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="editJob(row)">
            编辑
          </el-button>
          <el-button link type="success" size="small" @click="runJobNow(row)">
            立即执行
          </el-button>
          <el-button link type="danger" size="small" @click="deleteJob(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingJob ? '编辑任务' : '新建任务'"
      width="600px"
      @close="resetForm"
    >
      <el-form :model="form" label-width="120px" label-position="left">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.job_name" placeholder="如: 牛客面经发现" />
        </el-form-item>
        
        <el-form-item label="任务类型" required>
          <el-select v-model="form.job_type" placeholder="选择任务类型" style="width:100%" @change="onJobTypeChange">
            <el-option
              v-for="type in jobTypes"
              :key="type.type"
              :label="type.name"
              :value="type.type"
            >
              <div>{{ type.name }}</div>
              <div style="font-size:12px;color:var(--text-sub)">{{ type.description }}</div>
            </el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item label="任务描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
        
        <el-divider content-position="left">调度配置</el-divider>
        
        <el-form-item label="调度类型" required>
          <el-radio-group v-model="form.schedule_type">
            <el-radio label="cron">Cron 表达式</el-radio>
            <el-radio label="interval">固定间隔</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <template v-if="form.schedule_type === 'cron'">
          <el-form-item label="常用模板">
            <el-select v-model="selectedTemplate" placeholder="选择模板快速填充" style="width:100%" @change="applyTemplate">
              <el-option
                v-for="tpl in scheduleExamples.filter(e => e.schedule_type === 'cron')"
                :key="tpl.name"
                :label="tpl.name"
                :value="tpl.name"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item label="小时">
            <el-input v-model="form.schedule_config.hour" placeholder="如: 2,14 或 */2 或 8-20" />
            <div style="font-size:12px;color:var(--text-sub);margin-top:4px">
              * = 每小时, */2 = 每2小时, 2,14 = 2点和14点, 8-20 = 8点到20点
            </div>
          </el-form-item>
          
          <el-form-item label="分钟">
            <el-input v-model="form.schedule_config.minute" placeholder="如: 0 或 */30" />
          </el-form-item>
        </template>
        
        <template v-else>
          <el-form-item label="间隔时间" required>
            <div style="display:flex;gap:10px">
              <el-input-number v-model="intervalValue" :min="1" style="flex:1" />
              <el-select v-model="intervalUnit" style="width:100px">
                <el-option label="分钟" value="minutes" />
                <el-option label="小时" value="hours" />
              </el-select>
            </div>
          </el-form-item>
        </template>
        
        <el-divider content-position="left">任务参数</el-divider>
        
        <!-- 牛客参数 -->
        <template v-if="form.job_type === 'nowcoder_discovery'">
          <el-form-item label="搜索关键词">
            <el-input v-model="nowcoderKeywords" placeholder="多个关键词用逗号分隔，如: 面经,agent面经" />
          </el-form-item>
          <el-form-item label="最大页数">
            <el-input-number v-model="form.job_params.nowcoder_max_pages" :min="1" :max="10" />
          </el-form-item>
        </template>
        
        <!-- 小红书参数 -->
        <template v-if="form.job_type === 'xhs_discovery'">
          <el-form-item label="搜索关键词">
            <el-input v-model="xhsKeywords" placeholder="多个关键词用逗号分隔，如: agent面经,大模型面经" />
          </el-form-item>
          <el-form-item label="最大帖子数">
            <el-input-number v-model="form.job_params.xhs_max_notes" :min="1" :max="50" />
          </el-form-item>
          <el-form-item label="无头模式">
            <el-switch v-model="form.job_params.xhs_headless" />
            <div style="font-size:12px;color:var(--text-sub);margin-top:4px">
              启用无头模式需要已保存登录状态
            </div>
          </el-form-item>
        </template>
        
        <!-- 任务处理参数 -->
        <template v-if="form.job_type === 'process_tasks'">
          <el-form-item label="批次大小">
            <el-input-number v-model="form.job_params.process_batch_size" :min="1" :max="50" />
          </el-form-item>
        </template>
        
        <el-form-item label="启用状态">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="saveJob" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { api } from '../api.js'

const jobs = ref([])
const loading = ref(false)
const filterEnabled = ref(null)
const showCreateDialog = ref(false)
const editingJob = ref(null)
const saving = ref(false)
const jobTypes = ref([])
const scheduleExamples = ref([])
const selectedTemplate = ref('')
const config = ref({})

// 表单数据
const form = ref({
  job_name: '',
  job_type: '',
  schedule_type: 'cron',
  schedule_config: {
    hour: '',
    minute: '',
  },
  job_params: {},
  enabled: true,
  description: ''
})

// 间隔配置辅助
const intervalValue = ref(30)
const intervalUnit = ref('minutes')

// 关键词辅助（用逗号分隔的字符串）
const nowcoderKeywords = ref('面经')
const xhsKeywords = ref('agent面经')

// 加载任务列表
const loadJobs = async () => {
  loading.value = true
  try {
    const params = filterEnabled.value !== null ? `?enabled_only=${filterEnabled.value}` : ''
    const data = await api.getSchedulerJobs(params)
    jobs.value = data
  } catch (e) {
    ElMessage.error('加载任务列表失败')
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 加载配置
const loadConfig = async () => {
  try {
    config.value = await api.getConfig()
  } catch (e) {
    console.error('加载配置失败', e)
  }
}

// 加载任务类型
const loadJobTypes = async () => {
  try {
    jobTypes.value = await api.getJobTypes()
  } catch (e) {
    console.error('加载任务类型失败', e)
  }
}

// 加载调度示例
const loadScheduleExamples = async () => {
  try {
    scheduleExamples.value = await api.getScheduleExamples()
  } catch (e) {
    console.error('加载调度示例失败', e)
  }
}

// 任务类型变化
const onJobTypeChange = () => {
  // 重置参数
  form.value.job_params = {}
  if (form.value.job_type === 'nowcoder_discovery') {
    form.value.job_params = { nowcoder_keywords: ['面经'], nowcoder_max_pages: 3 }
    nowcoderKeywords.value = '面经'
  } else if (form.value.job_type === 'xhs_discovery') {
    form.value.job_params = { xhs_keywords: ['agent面经'], xhs_max_notes: 20, xhs_headless: true }
    xhsKeywords.value = 'agent面经'
  } else if (form.value.job_type === 'process_tasks') {
    // 使用从 .env 读取的配置作为默认值
    form.value.job_params = { process_batch_size: config.value.crawler_process_batch_size || 100 }
  }
}

// 应用模板
const applyTemplate = () => {
  const tpl = scheduleExamples.value.find(e => e.name === selectedTemplate.value)
  if (tpl) {
    Object.assign(form.value.schedule_config, tpl.schedule_config)
  }
}

// 保存任务
const saveJob = async () => {
  if (!form.value.job_name || !form.value.job_type) {
    ElMessage.warning('请填写任务名称和类型')
    return
  }
  
  // 处理关键词
  if (form.value.job_type === 'nowcoder_discovery') {
    form.value.job_params.nowcoder_keywords = nowcoderKeywords.value.split(',').map(k => k.trim()).filter(k => k)
  } else if (form.value.job_type === 'xhs_discovery') {
    form.value.job_params.xhs_keywords = xhsKeywords.value.split(',').map(k => k.trim()).filter(k => k)
  }
  
  // 处理间隔配置
  if (form.value.schedule_type === 'interval') {
    form.value.schedule_config = {}
    if (intervalUnit.value === 'minutes') {
      form.value.schedule_config.interval_minutes = intervalValue.value
    } else {
      form.value.schedule_config.interval_hours = intervalValue.value
    }
  }
  
  saving.value = true
  try {
    if (editingJob.value) {
      await api.updateSchedulerJob(editingJob.value.job_id, form.value)
      ElMessage.success('任务更新成功')
    } else {
      await api.createSchedulerJob(form.value)
      ElMessage.success('任务创建成功')
    }
    showCreateDialog.value = false
    await loadJobs()
  } catch (e) {
    ElMessage.error(editingJob.value ? '更新失败' : '创建失败')
    console.error(e)
  } finally {
    saving.value = false
  }
}

// 编辑任务
const editJob = (job) => {
  editingJob.value = job
  form.value = {
    job_name: job.job_name,
    job_type: job.job_type,
    schedule_type: job.schedule_type,
    schedule_config: { ...job.schedule_config },
    job_params: { ...job.job_params },
    enabled: job.enabled,
    description: job.description || ''
  }
  
  // 恢复关键词
  if (job.job_type === 'nowcoder_discovery' && job.job_params.nowcoder_keywords) {
    nowcoderKeywords.value = job.job_params.nowcoder_keywords.join(',')
  } else if (job.job_type === 'xhs_discovery' && job.job_params.xhs_keywords) {
    xhsKeywords.value = job.job_params.xhs_keywords.join(',')
  }
  
  // 恢复间隔配置
  if (job.schedule_type === 'interval') {
    if (job.schedule_config.interval_minutes) {
      intervalValue.value = job.schedule_config.interval_minutes
      intervalUnit.value = 'minutes'
    } else if (job.schedule_config.interval_hours) {
      intervalValue.value = job.schedule_config.interval_hours
      intervalUnit.value = 'hours'
    }
  }
  
  showCreateDialog.value = true
}

// 删除任务
const deleteJob = async (job) => {
  try {
    await ElMessageBox.confirm(`确定删除任务"${job.job_name}"吗？`, '确认删除', {
      type: 'warning'
    })
    await api.deleteSchedulerJob(job.job_id)
    ElMessage.success('删除成功')
    await loadJobs()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
      console.error(e)
    }
  }
}

// 启用/禁用任务
const toggleJob = async (job) => {
  try {
    if (job.enabled) {
      await api.enableSchedulerJob(job.job_id)
      ElMessage.success('任务已启用')
    } else {
      await api.disableSchedulerJob(job.job_id)
      ElMessage.success('任务已禁用')
    }
    await loadJobs()
  } catch (e) {
    ElMessage.error('操作失败')
    console.error(e)
    job.enabled = !job.enabled // 回滚
  }
}

// 立即执行
const runJobNow = async (job) => {
  try {
    await ElMessageBox.confirm(`确定立即执行任务"${job.job_name}"吗？`, '确认执行', {
      type: 'info'
    })
    ElMessage.info('任务已开始执行...')
    await api.runSchedulerJob(job.job_id)
    ElMessage.success('任务执行成功')
    await loadJobs()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('执行失败')
      console.error(e)
    }
  }
}

// 重置表单
const resetForm = () => {
  editingJob.value = null
  form.value = {
    job_name: '',
    job_type: '',
    schedule_type: 'cron',
    schedule_config: { hour: '', minute: '' },
    job_params: {},
    enabled: true,
    description: ''
  }
  selectedTemplate.value = ''
  intervalValue.value = 30
  intervalUnit.value = 'minutes'
  nowcoderKeywords.value = '面经'
  xhsKeywords.value = 'agent面经'
}

// 格式化调度配置
const formatSchedule = (job) => {
  if (job.schedule_type === 'cron') {
    const cfg = job.schedule_config
    const parts = []
    if (cfg.hour) parts.push(`${cfg.hour}时`)
    if (cfg.minute) parts.push(`${cfg.minute}分`)
    return parts.length > 0 ? parts.join('') : 'Cron'
  } else {
    const cfg = job.schedule_config
    if (cfg.interval_minutes) return `每${cfg.interval_minutes}分钟`
    if (cfg.interval_hours) return `每${cfg.interval_hours}小时`
    if (cfg.interval_seconds) return `每${cfg.interval_seconds}秒`
    return '间隔'
  }
}

// 格式化时间
const formatTime = (timeStr) => {
  if (!timeStr) return '-'
  const d = new Date(timeStr)
  return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`
}

// 任务类型名称
const getJobTypeName = (type) => {
  const map = {
    'nowcoder_discovery': '牛客发现',
    'xhs_discovery': '小红书发现',
    'process_tasks': '任务处理'
  }
  return map[type] || type
}

// 任务类型颜色
const getJobTypeColor = (type) => {
  const map = {
    'nowcoder_discovery': 'primary',
    'xhs_discovery': 'success',
    'process_tasks': 'warning'
  }
  return map[type] || ''
}

onMounted(async () => {
  await Promise.all([loadConfig(), loadJobs(), loadJobTypes(), loadScheduleExamples()])
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
