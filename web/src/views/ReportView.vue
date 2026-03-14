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

      <!-- 掌握度分布图表 -->
      <div v-if="masteryData.length" class="section">
        <div class="section-title">📊 知识掌握度分布</div>
        <div class="mastery-chart">
          <div v-for="level in masteryLevels" :key="level.key" class="mastery-level">
            <div class="level-header">
              <span class="level-icon">{{ level.icon }}</span>
              <span class="level-name">{{ level.name }}</span>
              <span class="level-count">{{ getMasteryCount(level.key) }} 个标签</span>
            </div>
            <div class="level-tags">
              <el-tag 
                v-for="item in getMasteryTags(level.key)" 
                :key="item.tag"
                :type="level.type"
                size="small"
                @click="$emit('quick-recommend', [item.tag])"
                style="cursor:pointer;margin:4px"
              >
                {{ item.tag }} ({{ item.avg_score.toFixed(1) }}/5)
              </el-tag>
              <span v-if="getMasteryTags(level.key).length === 0" class="empty-hint">暂无</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 薄弱知识点 - 简洁列表 + 关联推荐 -->
      <div v-if="weakTagsWithRelated.length" class="section">
        <div class="section-title">
          <span class="title-icon">⚠️</span>
          <span>需要加强的知识点</span>
          <span class="title-badge">{{ weakTags.length }}</span>
        </div>
        <div class="weak-knowledge-list">
          <div v-for="item in weakTagsWithRelated" :key="item.tag" class="weak-item">
            <div class="weak-main">
              <span class="weak-label">薄弱点：</span>
              <el-tag type="danger" size="default" @click="$emit('quick-recommend', [item.tag])" style="cursor:pointer">
                {{ item.tag }}
              </el-tag>
            </div>
            <div v-if="item.related.length" class="weak-related">
              <span class="related-label">关联拓展：</span>
              <el-tag v-for="r in item.related" :key="r" type="info" size="small" 
                      @click="$emit('quick-recommend', [r])" style="cursor:pointer;margin-right:6px">
                {{ r }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>

      <!-- 最近答题记录（含 LLM 评估建议） -->
      <div v-if="data.recent_history?.length" class="section">
        <div class="section-title">📝 最近答题</div>
        <div class="recent-list">
          <div v-for="row in data.recent_history" :key="row.id || row.studied_at + row.question_id" class="recent-item">
            <div class="recent-header">
              <span class="recent-q" :title="row.question_text">{{ (row.question_text || '').slice(0, 50) }}{{ (row.question_text || '').length > 50 ? '…' : '' }}</span>
              <el-tag :type="row.score >= 4 ? 'success' : row.score >= 3 ? 'warning' : 'danger'" size="small">
                {{ row.score }}/5
              </el-tag>
              <span class="recent-time">{{ (row.studied_at || row.created_at || '').slice(0, 16) }}</span>
            </div>
            <div v-if="row.eval_details && (row.eval_details.shortcomings?.length || row.eval_details.error_points?.length || row.eval_details.missed_points?.length)" class="eval-details">
              <div v-if="row.eval_details.shortcomings?.length" class="eval-row">
                <strong>不足：</strong>{{ row.eval_details.shortcomings.join('、') }}
              </div>
              <div v-if="row.eval_details.error_points?.length" class="eval-row">
                <strong>错误纠正：</strong>
                <span v-for="(e, i) in row.eval_details.error_points" :key="i" class="error-item">
                  「{{ e.wrong }}」→「{{ e.correct }}」
                  <span v-if="i < row.eval_details.error_points.length - 1">；</span>
                </span>
              </div>
              <div v-if="row.eval_details.missed_points?.length" class="eval-row">
                <strong>遗漏：</strong>{{ row.eval_details.missed_points.join('、') }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 用户自述的混淆/遗漏点（record_weakness 工具记录） -->
      <div v-if="data.weakness_notes?.length" class="section">
        <div class="section-title">📌 我记录的薄弱点</div>
        <div class="weakness-notes-list">
          <div v-for="(n, i) in data.weakness_notes" :key="i" class="weakness-note">
            <span class="note-type">{{ n.event_type === 'user_confusion' ? '🔄 混淆' : '📋 遗漏' }}</span>
            <span class="note-content">{{ n.content }}</span>
            <span class="note-time">{{ (n.created_at || '').slice(0, 16) }}</span>
          </div>
        </div>
      </div>

      <!-- 推荐章节 -->
      <div v-if="data.recommend_chapters?.length" class="section">
        <div class="section-title">💡 推荐复习章节</div>
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
import { Loading } from '@element-plus/icons-vue'
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

// 为每个薄弱知识点查找关联的拓展知识点
const weakTagsWithRelated = computed(() => {
  const weak = weakTags.value
  if (!weak.length) return []
  
  // 从知识图谱中查找关联知识点
  const graph = data.value?.knowledge_graph || {}
  
  return weak.map(item => {
    // item 可能是对象 {tag, avg_score, ...} 或字符串，提取标签名
    const tagName = typeof item === 'string' ? item : (item?.tag ?? String(item))
    const related = []
    
    // 查找该标签的关联节点
    if (graph[tagName]) {
      const edges = graph[tagName].edges || []
      edges.forEach(edge => {
        if (related.length < 3 && edge.target && edge.target !== tagName) {
          related.push(edge.target)
        }
      })
    }
    
    if (related.length === 0) {
      const weakNames = weak.map(w => typeof w === 'string' ? w : w?.tag).filter(Boolean)
      Object.keys(graph).forEach(key => {
        if (related.length >= 3) return
        const edges = graph[key]?.edges || []
        edges.forEach(edge => {
          if (edge.target === tagName && !related.includes(key) && !weakNames.includes(key)) {
            related.push(key)
          }
        })
      })
    }
    
    return { tag: tagName, related: related.slice(0, 3), raw: item }
  })
})

const masteryLevels = [
  { key: 'expert', name: '精通', icon: '🌟', type: 'success' },
  { key: 'proficient', name: '熟练', icon: '✅', type: 'success' },
  { key: 'learning', name: '学习中', icon: '📖', type: 'warning' },
  { key: 'novice', name: '初学', icon: '🔰', type: 'danger' },
]

const masteryData = computed(() => {
  const byLevel = data.value?.mastery_by_level || {}
  return Object.entries(byLevel).flatMap(([level, tags]) => 
    tags.map(t => ({ ...t, level }))
  )
})

const getMasteryCount = (level) => {
  return (data.value?.mastery_by_level?.[level] || []).length
}

const getMasteryTags = (level) => {
  return data.value?.mastery_by_level?.[level] || []
}

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
                 text-transform: uppercase; letter-spacing: .05em; display: flex; align-items: center; gap: 8px; }

/* 掌握度图表 */
.mastery-chart {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #fff 100%);
  border-radius: 12px;
  border: 1px solid var(--border);
}

.mastery-level {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.level-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}

.level-icon {
  font-size: 18px;
}

.level-name {
  color: var(--text-main);
}

.level-count {
  color: var(--text-sub);
  font-size: 12px;
  margin-left: auto;
}

.level-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-left: 26px;
}

.empty-hint {
  color: var(--text-sub);
  font-size: 12px;
  font-style: italic;
}

/* 标题样式增强 */
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-icon {
  font-size: 18px;
}

.title-badge {
  background: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
  color: white;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  margin-left: 4px;
}

/* 薄弱知识点列表 */
.weak-knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.weak-item {
  padding: 16px;
  background: #fef2f2;
  border-left: 4px solid #ef4444;
  border-radius: 8px;
}

.weak-main {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.weak-label {
  font-size: 14px;
  font-weight: 600;
  color: #991b1b;
}

.weak-related {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-left: 8px;
}

.related-label {
  font-size: 13px;
  color: #6b7280;
  white-space: nowrap;
}

.chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
.chapter-chip { background: var(--primary-light); color: var(--primary);
                padding: 4px 12px; border-radius: 20px; font-size: 13px; }

/* 最近答题（含 LLM 评估建议） */
.recent-list { display: flex; flex-direction: column; gap: 12px; }
.recent-item {
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid var(--border);
}
.recent-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.recent-q { flex: 1; min-width: 0; font-size: 14px; color: var(--text-main); }
.recent-time { font-size: 12px; color: var(--text-sub); }
.eval-details { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border); font-size: 13px; color: #374151; }
.eval-row { margin-bottom: 6px; }
.eval-row:last-child { margin-bottom: 0; }
.eval-row .error-item { display: inline; }

/* 用户自述的薄弱点 */
.weakness-notes-list { display: flex; flex-direction: column; gap: 8px; }
.weakness-note {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 14px; background: #fef3c7; border-radius: 8px;
  border-left: 4px solid #f59e0b; font-size: 13px;
}
.note-type { font-weight: 600; color: #92400e; min-width: 60px; }
.note-content { flex: 1; color: var(--text-main); }
.note-time { font-size: 11px; color: var(--text-sub); }
</style>
