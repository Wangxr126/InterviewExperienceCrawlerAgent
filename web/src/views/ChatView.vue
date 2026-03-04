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
        <div class="msg-bubble">
          <!-- AI 消息用 Markdown 渲染 -->
          <div v-if="m.role === 'assistant'" class="md-content"
               v-html="renderMd(m.content)"></div>
          <div v-else>{{ m.content }}</div>
          <!-- 流式打字光标 -->
          <span v-if="m.streaming" class="cursor">▋</span>
        </div>
      </div>

      <div v-if="loading && !streamingMsg" class="msg-row assistant">
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble typing">
          <span></span><span></span><span></span>
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
const streamingMsg = ref(null)   // 当前流式写入中的消息对象
const msgBox       = ref(null)
const sessionId    = ref(`sess_${Date.now()}`)
let   abortCtrl    = null

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

const clearChat = () => {
  messages.value = []
  sessionId.value = `sess_${Date.now()}`
}

// 对外暴露：从「发送到对话」或「快捷推荐」调用
const prefillAndSend = (text) => {
  inputText.value = text
  nextTick(() => send())
}
defineExpose({ prefillAndSend })

const send = async () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  loading.value = true
  abortCtrl = new AbortController()

  // 先尝试流式接口
  try {
    const res = await api.chatStream({
      user_id: props.userId,
      message: text,
      session_id: sessionId.value,
    }, abortCtrl.signal)

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    // 创建占位消息，后续追加内容
    const aiMsg = { role: 'assistant', content: '', streaming: true }
    messages.value.push(aiMsg)
    streamingMsg.value = aiMsg

    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 格式：每行 "data: <chunk>\n\n"
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''    // 保留未完整的行

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || trimmed === 'data: [DONE]') continue
        if (trimmed.startsWith('data: ')) {
          try {
            const payload = JSON.parse(trimmed.slice(6))
            if (payload.delta) {
              aiMsg.content += payload.delta
              scrollToBottom()
            } else if (payload.reply) {
              // 兼容非流式回包
              aiMsg.content = payload.reply
              scrollToBottom()
            } else if (payload.error) {
              aiMsg.content = `⚠️ ${payload.error}`
            }
          } catch {
            // 非 JSON 的 data 行，直接追加
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
      // 用户中止或超时，不提示
    } else {
      // 流式失败 → 降级到普通接口
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
        // 移除上面可能加入的空 streaming 消息
        messages.value = messages.value.filter(m => !m.streaming)
        messages.value.push({ role: 'assistant', content: d.reply || '⚠️ 无回复', streaming: false })
        scrollToBottom()
      } catch (e2) {
        messages.value = messages.value.filter(m => !m.streaming)
        messages.value.push({ role: 'assistant', content: '⚠️ 连接失败，请检查后端是否运行', streaming: false })
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

onUnmounted(() => abortCtrl?.abort())
</script>

<style scoped>
.chat-wrap {
  display: flex; flex-direction: column;
  height: calc(100vh - 60px - 48px);   /* 减去 topbar + content padding */
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

.msg-row {
  display: flex; gap: 10px; align-items: flex-start;
}
.msg-row.user { flex-direction: row-reverse; }

.msg-avatar { font-size: 24px; flex-shrink: 0; margin-top: 2px; }

.msg-bubble {
  max-width: 72%; padding: 10px 14px;
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
