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
                     @send-to-chat="onSendToChat" />
        <ChatView    v-show="currentView === 'chat'"   ref="chatViewRef"
                     :user-id="userId" :is-active="currentView === 'chat'" />
        <IngestView  v-show="currentView === 'ingest'" :user-id="userId"
                     @ingested="loadMeta" />
        <CollectView v-show="currentView === 'collect'" />
        <ReportView  v-show="currentView === 'report'" :user-id="userId"
                     :is-active="currentView === 'report'" />
      </main>
    </div>

    <!-- 掌握度弹窗 -->
    <MasteryDialog v-model="showMastery" :user-id="userId"
                   @quick-recommend="onQuickRecommend" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { User } from '@element-plus/icons-vue'
import { api } from './api.js'
import BrowseView   from './views/BrowseView.vue'
import ChatView     from './views/ChatView.vue'
import IngestView   from './views/IngestView.vue'
import CollectView  from './views/CollectView.vue'
import ReportView   from './views/ReportView.vue'
import MasteryDialog from './components/MasteryDialog.vue'

const userId      = ref('user_001')
const currentView = ref('browse')
const showMastery = ref(false)
const chatViewRef = ref(null)
const meta        = ref({ total: 0, companies: [], tags: [], positions: [], difficulties: [] })

const navItems = [
  { key: 'browse',  icon: '📚', label: '题库浏览' },
  { key: 'chat',    icon: '💬', label: '练习对话' },
  { key: 'ingest',  icon: '🔗', label: '收录面经' },
  { key: 'collect', icon: '🕷️', label: '数据采集' },
  { key: 'report',  icon: '📊', label: '学习报告' },
]

const loadMeta = async () => {
  try {
    const d = await api.getMeta()
    Object.assign(meta.value, d)
  } catch (e) { console.warn('加载元数据失败', e) }
}

// 发送到对话：切换视图并预填消息
const onSendToChat = ({ question }) => {
  currentView.value = 'chat'
  chatViewRef.value?.prefillAndSend(
    `我想练习这道题：${question.question_text.slice(0, 50)}`
  )
}

// 报告页推荐 → 跳转对话
const onQuickRecommend = (tags) => {
  showMastery.value = false
  currentView.value = 'chat'
  chatViewRef.value?.prefillAndSend(
    `给我推荐这些薄弱标签的学习资料：${tags.join('、')}`
  )
}

onMounted(() => loadMeta())
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
  padding: 0 28px;
  height: 60px;
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
  width: 160px; flex-shrink: 0;
  background: var(--card-bg);
  border-right: 1px solid var(--border);
  padding: 16px 0;
  display: flex; flex-direction: column; gap: 4px;
}
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 18px; cursor: pointer;
  border-radius: 8px; margin: 0 8px;
  font-size: 14px; color: var(--text-sub);
  transition: all .15s;
}
.nav-item:hover { background: var(--primary-light); color: var(--primary); }
.nav-item.active { background: var(--primary-light); color: var(--primary); font-weight: 600; }
.nav-icon { font-size: 16px; }

/* 内容区 */
.content { flex: 1; overflow-y: auto; padding: 24px; min-height: 0; }

/* 卡片 */
.card {
  background: var(--card-bg);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: var(--shadow);
  margin-bottom: 20px;
}
.card-title { font-size: 17px; font-weight: 600; margin-bottom: 18px; color: var(--text-main); }
</style>
