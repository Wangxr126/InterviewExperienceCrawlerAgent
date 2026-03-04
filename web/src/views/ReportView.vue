<template>
  <div class="card">
    <div class="card-title">📊 学习报告</div>

    <div v-if="!data && !loading" class="empty-state">
      <div style="font-size:48px;margin-bottom:16px">📈</div>
      <el-button type="primary" @click="load">加载我的学习报告</el-button>
    </div>

    <div v-if="loading" style="text-align:center;padding:40px">
      <el-icon class="is-loading" style="font-size:32px;color:var(--primary)"><Loading /></el-icon>
    </div>

    <template v-if="data && !loading">
      <!-- 总体评分 -->
      <div class="overview">
        <div class="ov-item">
          <div class="ov-val">{{ data.total_answered ?? 0 }}</div>
          <div class="ov-label">总作答</div>
        </div>
        <div class="ov-item">
          <div class="ov-val">{{ avgScore }}</div>
          <div class="ov-label">近期平均分</div>
        </div>
        <div class="ov-item">
          <div class="ov-val">{{ data.mastered_count ?? 0 }}</div>
          <div class="ov-label">已掌握</div>
        </div>
      </div>

      <!-- 薄弱标签 -->
      <div v-if="weakTags.length" class="section">
        <div class="section-title">薄弱知识点</div>
        <div class="tag-row">
          <el-tag v-for="t in weakTags" :key="t" type="danger" size="small"
                  @click="$emit('quick-recommend', [t])" style="cursor:pointer">
            {{ t }} 👉
          </el-tag>
        </div>
      </div>

      <!-- 最近答题记录 -->
      <div v-if="data.recent_history?.length" class="section">
        <div class="section-title">最近答题</div>
        <el-table :data="data.recent_history" size="small">
          <el-table-column label="题目" prop="question_text" show-overflow-tooltip />
          <el-table-column label="得分" prop="score" width="70">
            <template #default="{ row }">
              <el-tag :type="row.score >= 4 ? 'success' : row.score >= 3 ? 'warning' : 'danger'" size="small">
                {{ row.score }}/5
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" prop="created_at" width="160" show-overflow-tooltip />
        </el-table>
      </div>

      <!-- 推荐章节 -->
      <div v-if="data.recommend_chapters?.length" class="section">
        <div class="section-title">推荐复习章节</div>
        <div class="chip-row">
          <span v-for="c in data.recommend_chapters" :key="c" class="chapter-chip">{{ c }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'

const props = defineProps({
  userId:   { type: String, default: 'user_001' },
  isActive: { type: Boolean, default: false },
})
const emit = defineEmits(['quick-recommend'])

const data    = ref(null)
const loading = ref(false)

const avgScore = computed(() => {
  const h = data.value?.recent_history
  if (!h?.length) return '-'
  return (h.reduce((s, r) => s + (r.score || 0), 0) / h.length).toFixed(1)
})

const weakTags = computed(() => data.value?.weak_tags || [])

const load = async () => {
  loading.value = true
  try {
    data.value = await api.getMastery(props.userId)
  } catch {
    ElMessage.error('加载报告失败')
  } finally {
    loading.value = false
  }
}

// 切换到此视图时自动加载
watch(() => props.isActive, (v) => { if (v && !data.value) load() })
</script>

<style scoped>
.empty-state { display: flex; flex-direction: column; align-items: center; padding: 60px; color: var(--text-sub); }
.overview { display: flex; gap: 16px; margin-bottom: 24px; }
.ov-item  { flex: 1; background: var(--primary-light); border-radius: 10px; padding: 16px; text-align: center; }
.ov-val   { font-size: 28px; font-weight: 700; color: var(--primary); }
.ov-label { font-size: 13px; color: var(--text-sub); margin-top: 4px; }
.section  { margin-bottom: 20px; }
.section-title { font-size: 13px; font-weight: 600; color: var(--text-sub); margin-bottom: 10px;
                 text-transform: uppercase; letter-spacing: .05em; }
.tag-row  { display: flex; flex-wrap: wrap; gap: 8px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
.chapter-chip { background: var(--primary-light); color: var(--primary);
                padding: 4px 12px; border-radius: 20px; font-size: 13px; }
</style>
