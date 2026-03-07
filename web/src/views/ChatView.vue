<template>
  <div class="chat-wrap">
    <div class="chat-header">
      <span class="chat-title">💬 练习对话</span>
      <div class="header-actions">
        <el-button size="small" @click="clearChat" :icon="Delete">清空</el-button>
      </div>
    </div>

    <!-- 快捷问题 -->
    <div class="quick-btns">
      <el-button v-for="q in quickQuestions" :key="q" size="small"
                 @click="prefillAndSend(q)">{{ q }}</el-button>
    </div>

    <!-- 消息列表 -->
    <div ref="msgBox" class="messages">
      <div v-if="messages.length === 0" class="empty-msg">
        <div style="font-size:48px;margin-bottom:12px">🤖</div>
        <div>发送消息开始练习，支持：出题、解析、换个问法、整理知识点...</div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
        <div class="msg-avatar">{{ m.role === 'user' ? '🧑' : '🤖' }}</div>
        <div class="msg-col">

          <!-- 思考过程（仅 AI 消息，且存在思考步骤时显示）-->
          <div v-if="m.role === 'assistant' && m.thinking && m.thinking.length > 0"
               class="thinking-block">
            <button class="thinking-toggle" @click="m.thinkingOpen = !m.thinkingOpen">
              <span class="think-icon">🧠</span>
              <span>{{ m.thinkingOpen ? '收起' : '查看' }}推理过程</span>
              <span class="step-badge">{{ m.thinking.length }} 步</span>
              <span class="toggle-arrow" :class="{ open: m.thinkingOpen }">▾</span>
            </button>
            <transition name="slide">
              <div v-if="m.thinkingOpen" class="thinking-steps">
                <div v-for="(step, si) in m.thinking" :key="si" class="think-step">
                  <div class="step-num">第 {{ si + 1 }} 步</div>
                  <div v-if="step.thought"     class="step-item thought">
                    <span class="step-icon">🤔</span><span class="step-label">思考</span>
                    <span class="step-text">{{ step.thought }}</span>
                  </div>
                  <div v-if="step.action"      class="step-item action">
                    <span class="step-icon">🎬</span><span class="step-label">行动</span>
                    <code class="step-code">{{ step.action }}</code>
                  </div>
                  <div v-if="step.observation" class="step-item obs">
                    <span class="step-icon">👀</span><span class="step-label">观察</span>
                    <span class="step-text obs-text">{{ step.observation }}</span>
                  </div>
                  <div v-if="step.warning"     class="step-item warn">
                    <span class="step-text">{{ step.warning }}</span>
                  </div>
                </div>
              </div>
            </transition>
          </div>

          <!-- 消息气泡 -->
          <div class="msg-bubble">
            <!-- AI 消息用 Markdown 渲染 -->
            <div v-if="m.role === 'assistant'" class="md-content"
                 v-html="renderMd(m.content)"></div>
            <div v-else>{{ m.content }}</div>
            <!-- 流式打字光标 -->
            <span v-if="m.streaming" class="cursor">▋</span>
          </div>

        </div>
      </div>

      <div v-if="loading && !streamingMsg" class="msg-row assistant">
        <div class="msg-avatar">🤖</div>
        <div class="msg-col">
          <div class="msg-bubble typing">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="3"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
        resize="none"
        :disabled="loading"
        @keydown.enter.exact.prevent="send"
      />
      <el-button type="primary" class="send-btn" :loading="loading"
                 :disabled="loading || !inputText.trim()"
                 native-type="button"
                 @click.prevent="send">
        {{ loading ? '' : '发送' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import { api } from '../api.js'

const props = defineProps({
  userId:   { type: String, default: 'user_001' },
  isActive: { type: Boolean, default: false },
})

// 配置 marked：代码高亮
marked.setOptions({
  highlight: (code, lang) => {
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    return hljs.highlight(code, { language }).value
  },
  breaks: true,
  gfm: true,
})

const renderMd = (text) => {
  try { return marked.parse(text || '') }
  catch { return text }
}

const messages     = ref([])
const inputText    = ref('')
const loading      = ref(false)
const streamingMsg = ref(null)
const msgBox       = ref(null)
const sessionId    = ref(`sess_${Date.now()}`)
let   abortCtrl    = null
let   lastLoadedUserId = ''

const quickQuestions = [
  '出一道 Redis 面试题',
  '出一道 JVM 面试题',
  '给我讲解上面这道题',
  '换个问法考我',
  '总结我的薄弱知识点',
]

const scrollToBottom = () => {
  nextTick(() => {
    if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
  })
}

const loadHistory = async () => {
  if (!props.userId || lastLoadedUserId === props.userId) return
  try {
    const d = await api.getChatHistory(props.userId)
    lastLoadedUserId = props.userId
    if (d.messages?.length) {
      // 历史消息无思考步骤，补齐字段
      messages.value = d.messages.map(m => ({
        ...m,
        thinking: m.thinking || [],
        thinkingOpen: false,
      }))
      if (d.session_id) sessionId.value = d.session_id
      scrollToBottom()
    }
  } catch (e) { console.warn('加载对话历史失败', e) }
}

const clearChat = () => {
  messages.value = []
  sessionId.value = `sess_${Date.now()}`
  lastLoadedUserId = props.userId
}

const prefillAndSend = (text) => {
  inputText.value = text
  nextTick(() => send())
}
defineExpose({ prefillAndSend })

const send = async () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text, thinking: [], thinkingOpen: false })
  scrollToBottom()

  loading.value = true
  abortCtrl = new AbortController()

  try {
    const res = await api.chatStream({
      user_id: props.userId,
      message: text,
      session_id: sessionId.value,
    }, abortCtrl.signal)

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    // AI 消息占位，thinkingOpen 初始 true（有步骤时自动展开）
    const aiMsg = { role: 'assistant', content: '', streaming: true, thinking: [], thinkingOpen: true }
    messages.value.push(aiMsg)
    streamingMsg.value = aiMsg

    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let receivedFirstDelta = false

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || trimmed === 'data: [DONE]') continue
        if (trimmed.startsWith('data: ')) {
          try {
            const payload = JSON.parse(trimmed.slice(6))

            // 思考步骤事件（在 delta 之前到达）
            if (payload.thinking) {
              aiMsg.thinking = payload.thinking
              scrollToBottom()
            } else if (payload.delta) {
              // 收到第一个 delta 时折叠思考面板
              if (!receivedFirstDelta && aiMsg.thinking.length > 0) {
                aiMsg.thinkingOpen = false
                receivedFirstDelta = true
              }
              aiMsg.content += payload.delta
              scrollToBottom()
            } else if (payload.reply) {
              aiMsg.content = payload.reply
              scrollToBottom()
            } else if (payload.error) {
              aiMsg.content = `⚠️ ${payload.error}`
            }
          } catch {
            aiMsg.content += trimmed.slice(6)
            scrollToBottom()
          }
        }
      }
    }

    aiMsg.streaming = false
    streamingMsg.value = null

  } catch (err) {
    if (err.name === 'AbortError') {
      // 用户中止
    } else {
      console.warn('流式接口失败，降级到普通接口', err)
      try {
        const ctrl = new AbortController()
        const timer = setTimeout(() => ctrl.abort(), 90000)
        const d = await api.chat({
          user_id: props.userId,
          message: text,
          session_id: sessionId.value,
        }, ctrl.signal)
        clearTimeout(timer)
        messages.value = messages.value.filter(m => !m.streaming)
        messages.value.push({
          role: 'assistant',
          content: d.reply || '⚠️ 无回复',
          streaming: false,
          thinking: d.thinking || [],
          thinkingOpen: false,
        })
        scrollToBottom()
      } catch (e2) {
        messages.value = messages.value.filter(m => !m.streaming)
        messages.value.push({ role: 'assistant', content: '⚠️ 连接失败，请检查后端是否运行', streaming: false, thinking: [], thinkingOpen: false })
        ElMessage.error('LLM 调用失败')
      }
    }
  } finally {
    loading.value = false
    if (streamingMsg.value) {
      streamingMsg.value.streaming = false
      streamingMsg.value = null
    }
    abortCtrl = null
    scrollToBottom()
  }
}

watch([() => props.isActive, () => props.userId], ([active, uid]) => {
  if (active && uid) loadHistory()
}, { immediate: true })

onUnmounted(() => abortCtrl?.abort())
</script>

<style scoped>
.chat-wrap {
  display: flex; flex-direction: column;
  height: calc(100vh - 60px - 48px);
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.chat-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.chat-title { font-size: 16px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; }

.quick-btns {
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.quick-btns .el-button { font-size: 12px; height: 26px; }

.messages {
  flex: 1; overflow-y: auto; padding: 16px 20px;
  display: flex; flex-direction: column; gap: 14px;
  min-height: 0;
}

.empty-msg {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: var(--text-sub); text-align: center; padding: 40px;
}

/* ── 消息行 ── */
.msg-row {
  display: flex; gap: 10px; align-items: flex-start;
}
.msg-row.user { flex-direction: row-reverse; }

.msg-avatar { font-size: 24px; flex-shrink: 0; margin-top: 2px; }

/* 每条 AI 消息的竖向容器（思考块 + 气泡） */
.msg-col {
  display: flex; flex-direction: column; gap: 6px;
  max-width: 76%;
}
.msg-row.user .msg-col { align-items: flex-end; }

/* ── 气泡 ── */
.msg-bubble {
  padding: 10px 14px;
  border-radius: 14px; font-size: 14px; line-height: 1.65;
  word-break: break-word; position: relative;
}
.msg-row.user .msg-bubble {
  background: var(--primary); color: #fff;
  border-radius: 14px 4px 14px 14px;
}
.msg-row.assistant .msg-bubble {
  background: var(--bg);
  border-radius: 4px 14px 14px 14px;
}

/* ── 思考块 ── */
.thinking-block {
  background: #f8f7ff;
  border: 1px solid #e0d9ff;
  border-radius: 10px;
  overflow: hidden;
  font-size: 13px;
}

.thinking-toggle {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 8px 12px;
  background: none; border: none; cursor: pointer;
  color: #6c5ce7; font-size: 12px; font-weight: 500;
  text-align: left;
  transition: background 0.15s;
}
.thinking-toggle:hover { background: #f0ecff; }

.think-icon { font-size: 14px; }
.step-badge {
  margin-left: 2px;
  background: #e0d9ff; color: #6c5ce7;
  padding: 1px 6px; border-radius: 10px; font-size: 11px;
}
.toggle-arrow {
  margin-left: auto; font-size: 14px;
  transition: transform 0.2s;
  display: inline-block;
}
.toggle-arrow.open { transform: rotate(180deg); }

.thinking-steps {
  padding: 4px 12px 10px;
  display: flex; flex-direction: column; gap: 10px;
}

.think-step {
  display: flex; flex-direction: column; gap: 4px;
}
.step-num {
  font-size: 11px; font-weight: 600;
  color: #a29bfe; text-transform: uppercase; letter-spacing: 0.5px;
}

.step-item {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 5px 8px; border-radius: 6px; font-size: 12px; line-height: 1.5;
}
.step-icon { font-size: 13px; flex-shrink: 0; margin-top: 1px; }
.step-label {
  flex-shrink: 0; font-weight: 600; font-size: 11px;
  padding: 1px 5px; border-radius: 4px; margin-top: 2px;
}
.step-text { color: #444; word-break: break-all; }
.obs-text { color: #2d3436; }

.step-item.thought {
  background: #fff9e6;
}
.step-item.thought .step-label { background: #ffeaa7; color: #d35400; }

.step-item.action {
  background: #edfbee;
}
.step-item.action .step-label { background: #b2f0b4; color: #00823a; }
.step-code {
  font-family: 'Consolas', 'Fira Code', monospace;
  font-size: 11.5px; color: #00823a;
  background: #e3f9e4; padding: 1px 5px; border-radius: 4px;
  word-break: break-all;
}

.step-item.obs {
  background: #eef4ff;
}
.step-item.obs .step-label { background: #c5d9ff; color: #1a5eb8; }

.step-item.warn {
  background: #fff3f3;
  color: #c0392b; font-size: 12px; padding: 4px 8px;
}

/* slide 动画 */
.slide-enter-active, .slide-leave-active {
  transition: max-height 0.25s ease, opacity 0.2s;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }
.slide-enter-to, .slide-leave-from { max-height: 1000px; opacity: 1; }

/* Markdown 内容 */
.md-content :deep(h1), .md-content :deep(h2), .md-content :deep(h3) {
  margin: 10px 0 6px; font-weight: 600;
}
.md-content :deep(p)  { margin: 4px 0; }
.md-content :deep(ul), .md-content :deep(ol) { padding-left: 20px; margin: 6px 0; }
.md-content :deep(li) { margin: 3px 0; }
.md-content :deep(code) {
  background: #f4f4f8; padding: 1px 5px; border-radius: 4px;
  font-family: 'Consolas', monospace; font-size: 13px;
}
.md-content :deep(pre) {
  background: #1e1e1e; color: #d4d4d4;
  padding: 12px; border-radius: 8px; overflow-x: auto; margin: 8px 0;
}
.md-content :deep(pre code) { background: none; padding: 0; color: inherit; }
.md-content :deep(blockquote) {
  border-left: 3px solid var(--primary); padding-left: 10px;
  color: var(--text-sub); margin: 6px 0;
}

/* 打字光标 */
.cursor { display: inline-block; width: 2px; height: 1em;
          background: currentColor; animation: blink .7s step-end infinite; vertical-align: text-bottom; }
@keyframes blink { 50% { opacity: 0; } }

/* 加载三点动画 */
.typing { display: flex; gap: 5px; align-items: center; padding: 12px 16px; }
.typing span {
  width: 8px; height: 8px; background: var(--text-sub);
  border-radius: 50%; animation: bounce 1.2s infinite;
}
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

/* 输入区 */
.input-area {
  display: flex; gap: 10px; align-items: flex-end;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.input-area .el-textarea { flex: 1; }
.send-btn { height: 72px; width: 72px; font-size: 14px; font-weight: 600; }
</style>
