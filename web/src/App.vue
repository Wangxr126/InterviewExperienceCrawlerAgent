<template>
  <div class="app-wrap">
    <!-- 顶栏 -->
    <header class="topbar">
      <div class="topbar-logo">
        <span class="logo-icon">🎯</span>
        <span class="logo-text">面经 Agent</span>
        <span class="logo-sub">刷题伴侣</span>
      </div>
      <div class="topbar-right">
        <el-input v-model="userId" placeholder="用户ID" size="small"
                  style="width:140px" :prefix-icon="User" />
        <div class="user-badge" @click="showMastery = true">📊 我的掌握度</div>
      </div>
    </header>

    <!-- 主体 -->
    <div class="main-layout">
      <!-- 侧边导航 -->
      <nav class="sidebar">
        <div v-for="nav in navItems" :key="nav.key"
             class="nav-item" :class="{ active: currentView === nav.key }"
             @click="currentView = nav.key">
          <span class="nav-icon">{{ nav.icon }}</span>
          {{ nav.label }}
        </div>
      </nav>

      <!-- 内容区 -->
      <main class="content">
        <!-- 使用 v-show 保持各视图状态，避免切换时重新挂载 -->
        <BrowseView  v-show="currentView === 'browse'" :meta="meta"
                     :user-id="userId"
                     :is-active="currentView === 'browse'"
                     @send-to-chat="onSendToChat"
                     @submit-complete="onSubmitComplete" />
        <ChatView    v-show="currentView === 'chat'"   ref="chatViewRef"
                     :user-id="userId" :is-active="currentView === 'chat'" />
        <IngestView  v-show="currentView === 'ingest'" :user-id="userId"
                     @ingested="loadMeta" />
        <CollectView v-show="currentView === 'collect'" />
        <SchedulerView v-show="currentView === 'scheduler'" />
        <ReportView   v-show="currentView === 'report'"   :user-id="userId"
                      :is-active="currentView === 'report'" />
        <FinetuneView v-show="currentView === 'finetune'" />
      </main>
    </div>

    <!-- 掌握度弹窗 -->
    <MasteryDialog v-model="showMastery" :user-id="userId"
                   @quick-recommend="onQuickRecommend" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { User } from '@element-plus/icons-vue'
import { api } from './api.js'
import { useChatStore } from './stores/chatStore.js'
import BrowseView   from './views/BrowseView.vue'
import ChatView     from './views/ChatView.vue'
import IngestView   from './views/IngestView.vue'
import CollectView  from './views/CollectView.vue'
import SchedulerView from './views/SchedulerView.vue'
import ReportView   from './views/ReportView.vue'
import FinetuneView from './views/FinetuneView.vue'
import MasteryDialog from './components/MasteryDialog.vue'

const chatStore   = useChatStore()
const userId      = ref('')
// 从 localStorage 恢复上次的视图，默认为 'browse'
const currentView = ref(localStorage.getItem('currentView') || 'browse')
const showMastery = ref(false)
const chatViewRef = ref(null)
const meta        = ref({ total: 0, companies: [], tags: [], positions: [], difficulties: [] })

// 始终使用 chatStore 中的固定 session，若尚未初始化则生成一个稳定的 session
const chatSessionId = computed(() => chatStore.sessionId || `sess_${userId.value || 'default'}`)

// 监听视图变化，保存到 localStorage
watch(currentView, (newView) => {
  localStorage.setItem('currentView', newView)
})

const navItems = [
  { key: 'browse',   icon: '📚', label: '题库浏览' },
  { key: 'chat',     icon: '💬', label: '练习对话' },
  { key: 'ingest',   icon: '🔗', label: '收录面经' },
  { key: 'collect',  icon: '🕷️', label: '数据采集' },
  { key: 'scheduler', icon: '⏰', label: '定时任务' },
  { key: 'report',   icon: '📊', label: '学习报告' },
  { key: 'finetune', icon: '🧪', label: '微调标注' },
]

const loadMeta = async () => {
  try {
    const d = await api.getMeta()
    Object.assign(meta.value, d)
  } catch (e) { console.warn('加载元数据失败', e) }
}

const loadConfig = async () => {
  try {
    const d = await api.getConfig()
    if (d.default_user_id && !userId.value) {
      userId.value = d.default_user_id
    }
  } catch (e) { console.warn('加载配置失败', e) }
  // 与后端 default_user_id 默认值一致（如 Wangxr），避免出现 user_001
  if (!userId.value) userId.value = 'Wangxr'
}

// 提交作答：跳转到 Chat，延续固定 session，由 Agent 调用 submit_answer 工具完成评分
const onSubmitComplete = ({ question, userAnswer }) => {
  const metaParts = []
  if (question?.company) metaParts.push(`公司：${question.company}`)
  if (question?.difficulty) metaParts.push(`难度：${question.difficulty === 'easy' ? '简单' : question.difficulty === 'hard' ? '困难' : '中等'}`)

  // API 消息：带 q_id 和作答，让 Agent 调用 submit_answer 工具评分
  const lines = []
  // lines.push(`我已作答以下题目，请调用 submit_answer 工具为我评分。`)
  lines.push(`题目：${question?.question_text || ''}【q_id:${question?.q_id || ''}】`)
  if (metaParts.length) lines.push(`【题目信息】${metaParts.join(' | ')}`)
  lines.push(`我的作答：${userAnswer || ''}`)
  const apiMsg = lines.join('\n')

  // 屏幕展示：题目全文 + 我的作答，清晰直观
  const displayLines = []
  displayLines.push(`题目：${question?.question_text || ''}`)
  displayLines.push(`我的作答：${userAnswer || ''}`)
  const displayMsg = displayLines.join('\n')

  // 使用 chatStore 中的固定 session，保持对话连续
  if (!chatStore.sessionId) {
    chatStore.sessionId = `sess_${userId.value || Date.now()}`
  }

  currentView.value = 'chat'
  nextTick(() => {
    setTimeout(() => {
      if (!chatViewRef.value) return
      chatViewRef.value.prefillAndSend({ display: displayMsg, api: apiMsg })
    }, 200)
  })
}

// 发送到对话：切换视图并预填消息。屏幕只展示题目，q_id 等内部信息不展示给用户
const onSendToChat = ({ question }) => {
  if (!question) {
    ElMessage.error('题目数据为空')
    return
  }
  if (!question.question_text) {
    ElMessage.error('题目内容缺失')
    return
  }
  const displayMsg = `我想练习这道题：${question.question_text}`
  const apiMsg = `我想练习这道题【q_id:${question.q_id}】：${question.question_text}`
  currentView.value = 'chat'
  nextTick(() => {
    setTimeout(() => {
      if (!chatViewRef.value) {
        ElMessage.error('对话组件未就绪，请稍后再试')
        return
      }
      chatViewRef.value.prefillAndSend({ display: displayMsg, api: apiMsg })
    }, 200)
  })
}

// 报告页推荐 → 跳转对话
const onQuickRecommend = (tags) => {
  showMastery.value = false
  currentView.value = 'chat'
  chatViewRef.value?.prefillAndSend(
    `给我推荐这些薄弱标签的学习资料：${tags.join('、')}`
  )
}

onMounted(async () => {
  await loadConfig()
  await loadMeta()
})
</script>

<style>
:root {
  --primary: #5B6EF5;
  --primary-light: #EEF0FE;
  --bg: #F5F6FA;
  --card-bg: #ffffff;
  --text-main: #1a1a2e;
  --text-sub: #6b7280;
  --border: #e5e7eb;
  --radius: 12px;
  --shadow: 0 2px 12px rgba(0,0,0,0.06);
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text-main);
  min-height: 100vh;
}

.app-wrap { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* 顶栏 */
.topbar {
  background: var(--card-bg);
  border-bottom: 1px solid var(--border);
  padding: 0 18px;
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky; top: 0; z-index: 100;
  box-shadow: var(--shadow);
  flex-shrink: 0;
}
.topbar-logo { display: flex; align-items: center; gap: 10px; }
.logo-icon { font-size: 24px; }
.logo-text { font-size: 18px; font-weight: 700; color: var(--primary); }
.logo-sub  { font-size: 13px; color: var(--text-sub); background: var(--primary-light);
             padding: 2px 8px; border-radius: 20px; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.user-badge {
  cursor: pointer; padding: 6px 14px; border-radius: 20px;
  background: var(--primary-light); color: var(--primary);
  font-size: 13px; font-weight: 500;
  transition: background .2s;
}
.user-badge:hover { background: #dde1fd; }

/* 主体 */
.main-layout { display: flex; flex: 1; min-height: 0; }

/* 侧边导航 */
.sidebar {
  width: 140px; flex-shrink: 0;
  background: var(--card-bg);
  border-right: 1px solid var(--border);
  padding: 10px 0;
  display: flex; flex-direction: column; gap: 2px;
}
.nav-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; cursor: pointer;
  border-radius: 7px; margin: 0 6px;
  font-size: 13px; color: var(--text-sub);
  transition: all .15s;
}
.nav-item:hover { background: var(--primary-light); color: var(--primary); }
.nav-item.active { background: var(--primary-light); color: var(--primary); font-weight: 600; }
.nav-icon { font-size: 16px; }

/* 内容区 */
.content { flex: 1; overflow-y: auto; padding: 10px 14px; min-height: 0; }

/* 卡片 */
.card {
  background: var(--card-bg);
  border-radius: var(--radius);
  padding: 14px 16px;
  box-shadow: var(--shadow);
  margin-bottom: 10px;
}
.card-title { font-size: 15px; font-weight: 600; margin-bottom: 10px; color: var(--text-main); }
</style>
