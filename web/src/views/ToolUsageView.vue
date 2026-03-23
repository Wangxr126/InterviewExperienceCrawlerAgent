<template>
  <div class="card">
    <div class="card-title">🧰 Agent 工具使用统计</div>

    <div class="toolbar">
      <el-button :icon="Refresh" @click="load" :loading="loading" type="primary" size="small">
        刷新统计
      </el-button>
      <div class="toolbar-right">
        <el-tag size="small" type="success" v-if="data?.mode === 'runtime'">
          实时统计
        </el-tag>
      </div>
    </div>

    <div v-if="loading" class="loading-wrap">
      <Loading class="is-loading" />
      <span>加载中...</span>
    </div>

    <div v-else-if="tableRows.length" class="content">
      <div class="summary-row">
        <div class="summary-item">
          <div class="summary-val">{{ data.total_calls }}</div>
          <div class="summary-label">总调用次数</div>
        </div>
        <div class="summary-item">
          <div class="summary-val">{{ data.agents?.length || 0 }}</div>
          <div class="summary-label">涉及 Agent 数</div>
        </div>
      </div>

      <el-table
        :data="tableRows"
        style="width:100%"
        row-key="row_key"
        border
        :span-method="agentColumnSpanMethod"
      >
        <el-table-column prop="agent_name" label="Agent" min-width="180" />
        <el-table-column prop="tool_name" label="工具名称" min-width="220" />
        <el-table-column prop="count" label="调用次数" width="120" align="right" />
        <el-table-column prop="success" label="成功" width="100" align="right" />
        <el-table-column prop="failed" label="失败" width="100" align="right" />
        <el-table-column prop="success_rate" label="成功率(%)" width="140" align="right">
          <template #default="{ row }">
            {{ Number(row.success_rate || 0).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="avg_execution_time_ms" label="平均耗时(ms)" width="140" align="right">
          <template #default="{ row }">
            {{ Number(row.avg_execution_time_ms || 0).toFixed(1) }}
          </template>
        </el-table-column>
        <el-table-column prop="latest_params_input" label="最近入参" min-width="260">
          <template #default="{ row }">
            <span class="params-preview">{{ formatParamsInput(row.latest_params_input) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else class="empty-state">
      <div style="font-size:46px;margin-bottom:10px">📭</div>
      <div style="color:var(--text-sub);margin-bottom:12px">暂无工具调用数据。</div>
      <el-button type="primary" @click="load">重新加载</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Loading } from '@element-plus/icons-vue'
import { api } from '../api.js'

const props = defineProps({
  userId: { type: String, default: 'Wangxr' },
  isActive: { type: Boolean, default: false },
})

const data = ref(null)
const loading = ref(false)
let timer = null

const tableRows = computed(() => {
  const rows = data.value?.tools || []
  return rows.map((r, idx) => ({
    ...r,
    row_key: `${r.agent_name || 'agent'}:${r.tool_name || 'tool'}:${idx}`,
  }))
})

/** 连续相同 Agent 合并首列（与接口按 agent 分组后的顺序一致） */
function agentColumnSpanMethod({ rowIndex, columnIndex }) {
  if (columnIndex !== 0) {
    return { rowspan: 1, colspan: 1 }
  }
  const rows = tableRows.value
  if (!rows.length) {
    return { rowspan: 1, colspan: 1 }
  }
  const name = rows[rowIndex]?.agent_name
  if (rowIndex > 0 && rows[rowIndex - 1]?.agent_name === name) {
    return { rowspan: 0, colspan: 0 }
  }
  let span = 1
  for (let j = rowIndex + 1; j < rows.length; j++) {
    if (rows[j]?.agent_name === name) {
      span++
    } else {
      break
    }
  }
  return { rowspan: span, colspan: 1 }
}

const load = async ({ silent = false } = {}) => {
  if (!silent) loading.value = true
  try {
    const d = await api.getToolUsage(props.userId)
    data.value = d
  } catch (e) {
    ElMessage.error('加载工具统计失败')
    console.warn(e)
  } finally {
    if (!silent) loading.value = false
  }
}

const stopAutoRefresh = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  timer = setInterval(() => {
    if (!loading.value && props.isActive) {
      load({ silent: true })
    }
  }, 3000)
}

watch(
  () => props.isActive,
  (v) => {
    if (v) {
      load()
      startAutoRefresh()
    } else {
      stopAutoRefresh()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => stopAutoRefresh())

const formatParamsInput = (val) => {
  if (!val) return '-'
  try {
    const s = typeof val === 'string' ? val : JSON.stringify(val)
    return s.length > 120 ? `${s.slice(0, 120)}...` : s
  } catch {
    return String(val)
  }
}
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  margin-bottom: 12px;
}
.toolbar-right {
  margin-left: auto;
}
.loading-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  padding: 40px 0;
  color: var(--text-sub);
}
.content {
  margin-top: 12px;
}
.summary-row {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}
.summary-item {
  flex: 1;
  background: var(--primary-light);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
}
.summary-val {
  color: var(--primary);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}
.summary-label {
  margin-top: 6px;
  color: var(--text-sub);
  font-size: 12px;
}
.empty-state {
  text-align: center;
  padding: 60px 12px;
  color: var(--text-sub);
}
.params-preview {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  color: var(--text-sub);
}
</style>

