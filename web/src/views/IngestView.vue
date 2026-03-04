<template>
  <div class="card">
    <div class="card-title">🔗 收录面经</div>
    <p style="color:var(--text-sub);font-size:14px;margin-bottom:20px">
      输入帖子链接，后端自动解析正文并提取面试题入库。
    </p>
    <div class="form-row">
      <el-input v-model="url" placeholder="粘贴牛客/小红书帖子链接" clearable style="flex:1" />
      <el-select v-model="platform" style="width:130px">
        <el-option label="牛客网" value="nowcoder" />
        <el-option label="小红书" value="xiaohongshu" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="doIngest">收录</el-button>
    </div>

    <div v-if="result" class="ingest-result" :class="result.ok ? 'ok' : 'err'">
      {{ result.msg }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({ userId: { type: String, default: 'user_001' } })
const emit  = defineEmits(['ingested'])

const url      = ref('')
const platform = ref('nowcoder')
const loading  = ref(false)
const result   = ref(null)

const doIngest = async () => {
  if (!url.value.trim()) { ElMessage.warning('请输入帖子链接'); return }
  loading.value = true; result.value = null
  try {
    const d = await api.ingest({ url: url.value, user_id: props.userId, source_platform: platform.value })
    result.value = {
      ok: d.status === 'success',
      msg: d.details || d.message || JSON.stringify(d),
    }
    if (d.status === 'success') { url.value = ''; emit('ingested') }
  } catch {
    result.value = { ok: false, msg: '请求失败，请检查后端是否启动' }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.form-row { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; }
.ingest-result { padding: 12px 16px; border-radius: 8px; font-size: 14px; margin-top: 8px; }
.ingest-result.ok  { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }
.ingest-result.err { background: #fef2f2; color: #991b1b; border: 1px solid #fca5a5; }
</style>
