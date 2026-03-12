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
                 :disabled="loading || sendInProgress"
                 @click="prefillAndSend(q)">{{ q }}</el-button>
    </div>

    <!-- 消息列表 -->
    <div ref="msgBox" class="messages">
      <div v-if="messages.length === 0" class="empty-msg">
        <div style="font-size:48px;margin-bottom:12px">🤖</div>
        <div>发送消息开始练习，支持：出题、解析、换个问法、整理知识点...</div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
        <div class="msg-avatar" :style="getAvatarStyle(m.role)">
          <div class="avatar-inner">{{ m.role === 'user' ? '👤' : '🤖' }}</div>
        </div>
        <div class="msg-col">
          <!-- 时间戳：放在对话框上方 -->
          <div v-if="m.timestamp" class="msg-timestamp">{{ formatTime(m.timestamp) }}</div>

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

          <!-- 耗时 & 思考步骤统计（AI 消息完成后显示）-->
          <div v-if="m.role === 'assistant' && !m.streaming && m.duration_ms != null"
               class="msg-meta">
            <span class="meta-item">
              <span class="meta-icon">⏱</span> {{ (m.duration_ms / 1000).toFixed(1) }}s
            </span>
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
        :placeholder="isRecording ? '🎙️ 正在录音，请说话...' : '输入消息，Enter 发送，Shift+Enter 换行...'"
        resize="none"
        :disabled="loading"
        @keydown.enter.exact.prevent="send"
      />
      <div class="input-btns">
        <!-- 语音输入按钮 -->
        <el-tooltip :content="voiceTooltip" placement="top">
          <button
            class="voice-btn"
            :class="{ recording: isRecording, unsupported: !speechSupported }"
            :disabled="loading || !speechSupported"
            @click="toggleRecording"
            type="button"
          >
            <span v-if="isRecording" class="voice-wave">
              <span></span><span></span><span></span><span></span><span></span>
            </span>
            <span v-else class="mic-icon">🎙️</span>
          </button>
        </el-tooltip>
        <!-- 发送按钮 -->
        <el-button type="primary" class="send-btn" :loading="loading"
                   :disabled="loading || !inputText.trim()"
                   native-type="button"
                   @click.prevent="send">
          {{ loading ? '' : '发送' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted, onUnmounted, computed } from 'vue'
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

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  if (isNaN(d.getTime())) return String(timeStr)
  const y = d.getFullYear()
  const M = String(d.getMonth() + 1).padStart(2, '0')
  const D = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${M}-${D} ${h}:${m}`
}

const getAvatarStyle = (role) => {
  const base = { width: '36px', height: '36px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }
  if (role === 'user') {
    return { ...base, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: '#fff' }
  }
  return { ...base, background: 'linear-gradient(135deg, #a8b3ff 0%, #c4b5fd 100%)', color: '#fff' }
}

const messages     = ref([])
const inputText    = ref('')
const loading      = ref(false)
const streamingMsg = ref(null)
const msgBox       = ref(null)
const sessionId    = ref(`sess_${Date.now()}`)
let   abortCtrl    = null
let   lastLoadedUserId = ''
let   sendInProgress = false  // 防止并发调用的标志

// ── 语音转文字 ──
const isRecording    = ref(false)
const speechSupported = ref(false)
let recognition       = null

const voiceTooltip = computed(() => {
  if (!speechSupported.value) return '浏览器不支持语音识别（推荐 Chrome）'
  return isRecording.value ? '点击停止录音' : '点击开始语音输入'
})

const initSpeech = () => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) {
    speechSupported.value = false
    return
  }
  speechSupported.value = true
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true

  let finalTranscript = ''

  recognition.onresult = (e) => {
    let interim = ''
    finalTranscript = ''
    for (let i = 0; i < e.results.length; i++) {
      if (e.results[i].isFinal) {
        finalTranscript += e.results[i][0].transcript
      } else {
        interim += e.results[i][0].transcript
      }
    }
    // 实时显示：已确认 + 正在识别
    inputText.value = finalTranscript + interim
  }

  recognition.onerror = (e) => {
    console.warn('语音识别错误:', e.error)
    if (e.error === 'not-allowed') {
      ElMessage.error('麦克风权限被拒绝，请在浏览器允许麦克风访问')
    } else if (e.error !== 'aborted') {
      ElMessage.warning(`语音识别出错：${e.error}`)
    }
    isRecording.value = false
  }

  recognition.onend = () => {
    // 如果还在录音状态（因网络超时自动停止），重新启动
    if (isRecording.value) {
      try { recognition.start() } catch (_) { isRecording.value = false }
    }
  }
}

const toggleRecording = () => {
  if (!speechSupported.value) return
  if (isRecording.value) {
    // 停止录音
    isRecording.value = false
    recognition.stop()
  } else {
    // 开始录音：清空当前内容再追加
    isRecording.value = true
    try {
      recognition.start()
    } catch (e) {
      // recognition 可能已启动
      console.warn('recognition.start() 异常:', e)
    }
  }
}

// 挂载时初始化语音识别
onMounted(() => { initSpeech() })

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
  // 防止在发送过程中被调用
  if (loading.value || sendInProgress) {
    ElMessage.warning('请等待当前消息发送完成')
    return
  }
  
  inputText.value = text
  nextTick(() => send())
}
defineExpose({ prefillAndSend })

const send = async () => {
  const text = inputText.value.trim()
  
  // 双重检查：既检查 loading 又检查 sendInProgress
  if (!text || loading.value || sendInProgress) return

  // 立即设置标志，防止并发调用
  sendInProgress = true
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
    if (!res.body) throw new Error('SSE 响应无 body，请检查后端是否返回流式数据')

    // AI 消息占位，thinkingOpen 初始 true（有步骤时自动展开）
    const aiMsg = { role: 'assistant', content: '', streaming: true, thinking: [], thinkingOpen: true }
    messages.value.push(aiMsg)
    streamingMsg.value = aiMsg

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let receivedFirstDelta = false
    let currentStep = {}  // 用于构建 thinking（HelloAgents 官方格式）

    const handleEvent = (payload) => {
      const evType = payload.type
      const data = payload.data || {}

      // HelloAgents 官方 8 种事件类型
      if (evType === 'llm_chunk') {
        const chunk = data.chunk ?? data.content ?? ''
        if (chunk) {
          if (!receivedFirstDelta && aiMsg.thinking.length > 0) {
            aiMsg.thinkingOpen = false
            receivedFirstDelta = true
          }
          aiMsg.content += chunk
          scrollToBottom()
        }
      } else if (evType === 'agent_finish') {
        // result 已通过 synthetic llm_chunk 发送，此处只更新耗时，不覆盖已有内容
        // 仅当内容完全为空时才兜底填充（防御性措施）
        const result = data.result ?? ''
        if (result && !aiMsg.content.trim()) aiMsg.content = result
        aiMsg.duration_ms = data.duration_ms ?? (Date.now() - (aiMsg._startTs || Date.now()))
      } else if (evType === 'step_start') {
        currentStep = {}
      } else if (evType === 'tool_call_finish') {
        const toolName = data.tool_name ?? ''
        const result = data.result ?? ''
        if (toolName === 'Thought') {
          let thought = result
          for (const p of ['已记录推理过程:', '推理:']) {
            if (thought.startsWith(p)) { thought = thought.slice(p.length).trim(); break }
          }
          currentStep.thought = thought || result
        } else if (toolName !== 'Finish') {
          currentStep.action = `🔧 ${toolName}`
          currentStep.observation = String(result).slice(0, 500)
        }
        if (Object.keys(currentStep).length) {
          const last = aiMsg.thinking[aiMsg.thinking.length - 1]
          if (last?.thought && !last?.action) {
            Object.assign(last, currentStep)
          } else {
            aiMsg.thinking.push({ ...currentStep })
          }
          scrollToBottom()
        }
      } else if (evType === 'error') {
        aiMsg.content = `⚠️ ${data.error ?? '未知错误'}`
      }
    }

    aiMsg._startTs = Date.now()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 解析 SSE：event: xxx 与 data: {...} 成对出现
      const parts = buffer.split(/\n\n+/)
      buffer = parts.pop() ?? ''

      for (const block of parts) {
        let dataLine = ''
        for (const line of block.split('\n')) {
          const t = line.trim()
          if (t.startsWith('data: ')) dataLine = t.slice(6)
        }
        if (!dataLine || dataLine === '[DONE]') continue
        try {
          const payload = JSON.parse(dataLine)
          handleEvent(payload)
        } catch (e) {
          if (dataLine) {
            aiMsg.content += dataLine
          }
        }
        // 每处理一个事件后立即更新 DOM，实现真实逐字流式效果
        // 这是关键：不能等到所有 chunk 都收集完再更新
        scrollToBottom()
        await nextTick()
      }
    }

    aiMsg.streaming = false
    streamingMsg.value = null

  } catch (err) {
    console.error('🔴 流式接口错误:', err)
    console.error('🔴 错误类型:', err.name)
    console.error('🔴 错误消息:', err.message)
    console.error('🔴 错误堆栈:', err.stack)
    
    if (err.name === 'AbortError') {
      // 用户中止
      console.log('🟡 用户中止请求')
    } else {
      console.warn('流式接口失败，降级到普通接口', err)
      try {
        const ctrl = new AbortController()
        const timer = setTimeout(() => ctrl.abort(), 300000)
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
    sendInProgress = false  // 重置标志
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

onUnmounted(() => {
  abortCtrl?.abort()
  if (isRecording.value && recognition) {
    isRecording.value = false
    recognition.stop()
  }
})
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
.msg-timestamp {
  font-size: 11px; color: var(--text-sub);
  margin-bottom: 6px; opacity: 0.8;
  align-self: flex-start;
}
.msg-row.user .msg-timestamp {
  align-self: flex-end;
}
.msg-row.user { flex-direction: row-reverse; }

.msg-avatar { font-size: 24px; flex-shrink: 0; margin-top: 2px; }

/* 每条 AI 消息的竖向容器（思考块 + 气泡） */
.msg-col {
  display: flex; flex-direction: column; gap: 6px;
  max-width: 76%;
}
.msg-row.user .msg-col { align-items: flex-end; }

/* ── 耗时/思考步数元信息 ── */
.msg-meta {
  display: flex; gap: 10px; align-items: center;
  font-size: 11px; color: var(--text-sub);
  padding: 0 2px;
  opacity: 0.72;
}
.meta-item {
  display: flex; align-items: center; gap: 3px;
}
.meta-icon { line-height: 1; }

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

/* ── 消息元信息（耗时/思考步数）── */
.msg-meta {
  display: flex; gap: 10px; align-items: center;
  font-size: 11px; color: var(--text-sub);
  padding: 0 2px;
  opacity: 0.75;
}
.meta-item {
  display: flex; align-items: center; gap: 3px;
}
.meta-icon { font-size: 11px; }

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
  margin: 12px 0 8px; font-weight: 700;
  color: #2c3e50;
}
.md-content :deep(h1) { font-size: 16px; }
.md-content :deep(h2) { font-size: 15px; }
.md-content :deep(h3) { font-size: 14px; }

.md-content :deep(p)  { margin: 6px 0; }
.md-content :deep(ul), .md-content :deep(ol) { 
  padding-left: 24px; margin: 8px 0;
}
.md-content :deep(li) { 
  margin: 4px 0;
  line-height: 1.7;
}
.md-content :deep(code) {
  background: linear-gradient(135deg, #f4f4f8 0%, #f0f0f5 100%);
  padding: 2px 6px; border-radius: 4px;
  font-family: 'Consolas', monospace; font-size: 13px;
  color: #d35400;
  font-weight: 500;
}
.md-content :deep(pre) {
  background: linear-gradient(135deg, #1e1e1e 0%, #2d2d2d 100%);
  color: #d4d4d4;
  padding: 14px; border-radius: 10px; overflow-x: auto; margin: 10px 0;
  border: 1px solid #3d3d3d;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.md-content :deep(pre code) { background: none; padding: 0; color: inherit; }
.md-content :deep(blockquote) {
  border-left: 4px solid #6c5ce7; padding-left: 12px;
  color: #555; margin: 8px 0;
  font-style: italic;
  background: rgba(108, 92, 231, 0.05);
  padding: 8px 12px;
  border-radius: 4px;
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
  display: flex; gap: 12px; align-items: flex-end;
  padding: 14px 18px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.5) 0%, rgba(248,249,250,0.5) 100%);
}
.input-area .el-textarea { 
  flex: 1;
  border-radius: 12px;
  border: 1px solid #e0e0e0;
  transition: all 0.2s;
}
.input-area .el-textarea:hover {
  border-color: #6c5ce7;
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.1);
}
.input-area .el-textarea:focus-within {
  border-color: #6c5ce7;
  box-shadow: 0 4px 12px rgba(108, 92, 231, 0.15);
}

.input-btns {
  display: flex; flex-direction: column; gap: 8px; align-items: center;
}

/* 语音按钮 */
.voice-btn {
  width: 44px; height: 44px;
  border-radius: 50%;
  border: 2px solid #e0e0e0;
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f3f7 100%);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  transition: all 0.2s;
  outline: none;
  flex-shrink: 0;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}
.voice-btn:hover:not(:disabled) {
  border-color: #6c5ce7;
  background: linear-gradient(135deg, #f0ecff 0%, #ede8ff 100%);
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(108, 92, 231, 0.2);
}
.voice-btn:disabled {
  opacity: 0.4; cursor: not-allowed;
}
.voice-btn.recording {
  border-color: #ef4444;
  background: linear-gradient(135deg, #fff0f0 0%, #ffe8e8 100%);
  animation: pulse-ring 1.2s ease-in-out infinite;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
}
.voice-btn.recording:hover {
  border-color: #ef4444;
  background: linear-gradient(135deg, #ffd7d7 0%, #ffcccc 100%);
}

/* 录音中的波形动画 */
.voice-wave {
  display: flex; align-items: center; gap: 2px; height: 20px;
}
.voice-wave span {
  display: inline-block; width: 3px; border-radius: 2px;
  background: #ef4444;
  animation: wave-bar 0.8s ease-in-out infinite;
}
.voice-wave span:nth-child(1) { height: 6px;  animation-delay: 0s;    }
.voice-wave span:nth-child(2) { height: 12px; animation-delay: 0.1s;  }
.voice-wave span:nth-child(3) { height: 18px; animation-delay: 0.2s;  }
.voice-wave span:nth-child(4) { height: 12px; animation-delay: 0.3s;  }
.voice-wave span:nth-child(5) { height: 6px;  animation-delay: 0.4s;  }

@keyframes wave-bar {
  0%, 100% { transform: scaleY(0.5); opacity: 0.6; }
  50%       { transform: scaleY(1);   opacity: 1;   }
}
@keyframes pulse-ring {
  0%   { box-shadow: 0 0 0 0   rgba(239,68,68,0.4); }
  70%  { box-shadow: 0 0 0 10px rgba(239,68,68,0);   }
  100% { box-shadow: 0 0 0 0   rgba(239,68,68,0);   }
}

.mic-icon { line-height: 1; }

.send-btn { 
  height: 44px; 
  width: 44px; 
  font-size: 14px; 
  font-weight: 700;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
  transition: all 0.2s;
}
.send-btn:hover:not(:disabled) {
  transform: scale(1.08);
  box-shadow: 0 6px 16px rgba(102, 126, 234, 0.4);
}
.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
