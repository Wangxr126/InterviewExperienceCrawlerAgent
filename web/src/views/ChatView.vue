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
          <img v-if="m.role === 'user'" src="@/assets/avatars/user-avatar.png" alt="user" class="avatar-img" />
          <img v-else src="@/assets/avatars/ai-avatar.png" alt="ai" class="avatar-img" />
        </div>
        <div class="msg-col">
          <!-- 时间戳：放在对话框上方（始终显示，无则用占位） -->
          <div class="msg-timestamp">{{ formatTime(m.timestamp) || '—' }}</div>

          <!-- 思考过程（仅 AI 消息，且存在思考步骤时显示）-->
          <div v-if="m.role === 'assistant' && m.thinking && m.thinking.length > 0"
               class="thinking-block">
            <button class="thinking-toggle" @click="m.thinkingOpen = !m.thinkingOpen">
              <span class="think-icon">🧠</span>
              <span>{{ m.thinkingOpen ? '收起' : '查看' }}推理过程</span>
              <span class="step-badge">{{ m.thinking.filter(s => s.__step !== 'pending').length }} 步 · {{ countTotalTools(m.thinking) }} 工具</span>
              <span class="toggle-arrow" :class="{ open: m.thinkingOpen }">▾</span>
            </button>
            <transition name="slide">
              <div v-if="m.thinkingOpen" class="thinking-steps">
                <div v-for="(step, si) in m.thinking" :key="si" class="think-step">
                  <div v-if="step.__step === 'pending'" class="step-num step-num-pending">⏳ 调用中…</div>
                  <div v-else class="step-num">第 {{ computeStepDisplay(m.thinking, si) }} 步</div>
                  <div v-if="step.thought"     class="step-item thought">
                    <span class="step-icon">🤔</span><span class="step-label">推理</span>
                    <span class="step-text">{{ step.thought }}</span>
                  </div>
                  <div v-if="step.action || (step.tools && step.tools.length)"      class="step-item action">
                    <span class="step-icon">🔧</span><span class="step-label">工具调用</span>
                    <!-- 兼容旧数据：单工具模式 -->
                    <template v-if="!step.tools || !step.tools.length">
                      <code class="step-code">{{ step.action }}</code>
                      <div v-if="step.toolArgs && Object.keys(step.toolArgs).length" class="tool-args">
                        <span class="args-label">参数:</span>
                        <pre class="args-json">{{ JSON.stringify(step.toolArgs, null, 2) }}</pre>
                      </div>
                    </template>
                    <!-- 新协议：同一步多工具 -->
                    <template v-else>
                      <div v-for="(tool, ti) in step.tools" :key="ti" class="tool-item" :class="{ 'tool-pending': tool._pending }">
                        <!-- submit_answer 工具：pending 时只显示"正在评价"，完成后不展示原始结果 -->
                        <template v-if="tool.name === 'submit_answer' || tool.name === '🔧 submit_answer'">
                          <div class="tool-item-header">
                            <code class="step-code">{{ tool.name }}</code>
                          </div>
                          <div class="tool-args-inner tool-pending-result">
                            <span v-if="tool._pending" class="tool-spinner"></span>
                            <span class="step-text" style="color:#94a3b8">{{ tool._pending ? '正在评价…' : '评价完成' }}</span>
                          </div>
                        </template>
                        <!-- 其他工具：正常展示 -->
                        <template v-else>
                          <div class="tool-item-header">
                            <code class="step-code">{{ tool.name }}</code>
                            <span v-if="tool._pending" class="tool-pending-badge">调用中…</span>
                          </div>
                          <div v-if="tool.args && Object.keys(tool.args).length" class="tool-args-inner">
                            <span class="args-label">参数:</span>
                            <pre class="args-json">{{ JSON.stringify(tool.args, null, 2) }}</pre>
                          </div>
                          <div v-if="!tool._pending && (tool.result != null || tool.observation != null)" class="tool-args-inner">
                            <span class="args-label">结果:</span>
                            <pre v-if="(tool.observationIsJson || isObsJson(tool.result || tool.observation))" class="args-json">{{ formatObsJson(tool.result || tool.observation) }}</pre>
                            <span v-else class="step-text">{{ tool.result || tool.observation }}</span>
                          </div>
                          <div v-if="tool._pending" class="tool-args-inner tool-pending-result">
                            <span class="tool-spinner"></span>
                            <span class="step-text" style="color:#94a3b8">等待结果…</span>
                          </div>
                        </template>
                      </div>
                    </template>
                  </div>
                  <div v-if="step.observation" class="step-item obs">
                    <span class="step-icon">📋</span><span class="step-label">工具结果</span>
                    <template v-if="step.observationIsJson || isObsJson(step.observation)">
                      <!-- 题目详情类结果：卡片展示，答案区换行+粗体 -->
                      <div v-if="getObsParsedCached(step) && isQuestionDetailObs(getObsParsedCached(step))"
                           class="obs-friendly-card">
                        <div class="obs-card-meta">
                          <span v-if="getObsParsedCached(step).question_id" class="obs-meta-id">
                            ID: {{ getObsParsedCached(step).question_id }}
                          </span>
                          <span v-if="getObsParsedCached(step).difficulty" class="obs-meta-diff">
                            {{ getObsParsedCached(step).difficulty }}
                          </span>
                          <span v-if="(getObsParsedCached(step).topic_tags || []).length" class="obs-meta-tags">
                            {{ (getObsParsedCached(step).topic_tags || []).join(' · ') }}
                          </span>
                        </div>
                        <div v-if="getObsParsedCached(step).question_text" class="obs-card-q">
                          {{ getObsParsedCached(step).question_text }}
                        </div>
                        <div v-if="getObsParsedCached(step).answer_text" class="obs-card-answer">
                          <div class="obs-answer-label">参考答案</div>
                          <div class="obs-answer-body" v-html="renderObsRichText(getObsParsedCached(step).answer_text)"></div>
                        </div>
                      </div>
                      <!-- 其他 JSON：键值列表，长文本可折叠 -->
                      <div v-else-if="getObsParsedCached(step)" class="obs-kv-wrap">
                        <div v-for="(val, key) in getObsParsedCached(step)" :key="key" class="obs-kv-row">
                          <span class="obs-kv-key">{{ key }}</span>
                          <div class="obs-kv-val">
                            <template v-if="typeof val === 'object' && val !== null">
                              <pre class="obs-kv-json">{{ JSON.stringify(val, null, 2) }}</pre>
                            </template>
                            <template v-else>
                              <span v-if="String(val).length <= 120">{{ val }}</span>
                              <span v-else>
                                <span v-if="!step._obsExpand?.[key]">{{ String(val).slice(0, 120) }}…</span>
                                <span v-else v-html="renderObsRichText(String(val))"></span>
                                <button type="button" class="obs-expand-btn" @click="toggleObsExpand(step, key)">
                                  {{ step._obsExpand?.[key] ? '收起' : '展开' }}
                                </button>
                              </span>
                            </template>
                          </div>
                        </div>
                      </div>
                      <!-- 无法解析为键值或非对象：保留原样格式化 JSON -->
                      <div v-else class="obs-json-wrap">
                        <pre class="step-obs-json"><code>{{ formatObsJson(step.observation) }}</code></pre>
                      </div>
                    </template>
                    <!-- 非 JSON 时也尝试格式化，若含 JSON 片段则以代码块展示 -->
                    <template v-else>
                      <div v-if="extractJsonFromText(step.observation)" class="obs-json-wrap">
                        <pre class="step-obs-json"><code>{{ formatObsJson(step.observation) }}</code></pre>
                      </div>
                      <span v-else class="step-text obs-text">{{ step.observation }}</span>
                    </template>
                  </div>
                  <div v-if="step.warning"     class="step-item warn">
                    <span class="step-text">{{ step.warning }}</span>
                  </div>
                </div>
                <!-- 第 N 步：完成（与后端 [Stream →] 完成 对应，作为最后一步）-->
                <div v-if="!m.streaming" class="think-step completed-step">
                  <div class="step-num">第 {{ m.thinking.filter(s => s.__step !== 'pending').length + 1 }} 步</div>
                  <div class="step-item completed">
                    <span class="step-icon">✓</span>
                    <span class="step-text">完成</span>
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
            <!-- 流式打字光标（单一样式，避免叠加） -->
            <span v-if="m.streaming" class="stream-caret"></span>
          </div>

          <!-- 耗时 & 完成标识（AI 消息完成后显示）-->
          <div v-if="m.role === 'assistant' && !m.streaming"
               class="msg-meta">
            <span v-if="m.duration_ms != null" class="meta-item">
              <span class="meta-icon">⏱</span> {{ (m.duration_ms / 1000).toFixed(1) }}s
            </span>
            <span class="meta-item completed-badge">
              <span class="meta-icon">✓</span> 完成
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
import { useChatStore } from '../stores/chatStore.js'
import { diagnoseSseStream } from '../sse-diagnostic.js'
import { renderEnhancedContent, questionCardStyles } from '../utils/question-renderer.js'

// 暴露诊断工具到全局，方便在控制台调用
if (typeof window !== 'undefined') {
  window.diagnoseSseStream = diagnoseSseStream
}

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

/** 推理过程观察：尝试格式化为 JSON 展示（工具调用结果用代码块） */
const formatObsJson = (text) => {
  if (!text || typeof text !== 'string') return ''
  const extracted = extractJsonFromText(text)
  if (extracted) {
    try {
      const parsed = JSON.parse(extracted)
      return JSON.stringify(parsed, null, 2)
    } catch { /* fallback */ }
  }
  try {
    const parsed = JSON.parse(text.trim())
    return JSON.stringify(parsed, null, 2)
  } catch {
    return text
  }
}

/** 从文本中提取 JSON 片段（支持工具返回被包裹的情况） */
function extractJsonFromText(text) {
  if (!text || typeof text !== 'string') return null
  const t = text.trim()
  const objStart = t.indexOf('{')
  const arrStart = t.indexOf('[')
  let start = -1
  let openChar = ''
  let closeChar = ''
  if (objStart >= 0 && (arrStart < 0 || objStart < arrStart)) {
    start = objStart
    openChar = '{'
    closeChar = '}'
  } else if (arrStart >= 0) {
    start = arrStart
    openChar = '['
    closeChar = ']'
  }
  if (start < 0) return null
  let depth = 0
  for (let i = start; i < t.length; i++) {
    if (t[i] === openChar) depth++
    else if (t[i] === closeChar) {
      depth--
      if (depth === 0) return t.slice(start, i + 1)
    }
  }
  return null
}

/** 去掉 DeepSeek 输出中的 DSML 工具调用块 */
function stripDsmlBlocks(text) {
  if (!text || typeof text !== 'string') return text
  let s = text
  const startTag = '<｜DSML｜'
  const endTag = '</｜DSML｜function_calls>'
  while (true) {
    const start = s.indexOf(startTag)
    if (start === -1) break
    const end = s.indexOf(endTag, start)
    if (end === -1) {
      // 找不到闭合标签，直接丢掉后半段
      s = s.slice(0, start)
      break
    }
    s = s.slice(0, start) + s.slice(end + endTag.length)
  }
  return s
}

/** 判断观察是否为 JSON 格式（工具调用结果优先以 JSON 代码块展示） */
const isObsJson = (text) => {
  if (!text || typeof text !== 'string') return false
  const t = text.trim()
  if (!(t.startsWith('{') || t.startsWith('['))) {
    const extracted = extractJsonFromText(text)
    if (extracted) return true
    return false
  }
  try {
    JSON.parse(t)
    return true
  } catch {
    const extracted = extractJsonFromText(text)
    return !!extracted
  }
}

/** 避免把「工具调用 JSON 计划」当思考展示：若为 [{"name":"xxx",...}] 则替换为简短说明 */
function normalizeThoughtForStep(thought) {
  if (!thought || typeof thought !== 'string') return thought || ''
  const s = thought.trim()
  if (!s.startsWith('[{') || !s.includes('"name"')) return s.length > 800 ? s.slice(0, 800) + '…' : s
  try {
    const parsed = JSON.parse(s)
    if (Array.isArray(parsed) && parsed.length && typeof parsed[0] === 'object' && parsed[0].name) {
      const names = parsed.slice(0, 5).map(x => x.name).filter(Boolean)
      return '（计划调用: ' + names.join(', ') + (parsed.length > 5 ? ' …' : '') + '）'
    }
  } catch (_) { /* ignore */ }
  return s.length > 800 ? s.slice(0, 800) + '…' : s
}

/** 计算某一步的工具调用总数 */
function countToolsInStep(step) {
  if (!step) return 0
  // 新协议：step.tools 是数组
  if (Array.isArray(step.tools)) {
    return step.tools.length
  }
  // 旧协议：step.action 表示一个工具
  if (step.action) {
    return 1
  }
  return 0
}

/**
 * 计算步骤的显示序号：跳过 pending 步，只给已完成的步骤编号
 * 这样 pending 步不占用编号，避免序号跳空
 */
function computeStepDisplay(thinking, idx) {
  let num = 0
  for (let i = 0; i <= idx; i++) {
    if (thinking[i].__step !== 'pending') num++
  }
  return num
}

/** 计算消息中所有步骤的工具总数 */
function countTotalTools(thinking) {
  if (!Array.isArray(thinking)) return 0
  return thinking.reduce((sum, step) => sum + countToolsInStep(step), 0)
}

/** 解析观察内容为 JSON 对象（仅当为对象时返回，数组等返回 null 便于键值展示） */
function getObsParsed(text) {
  if (!text || typeof text !== 'string') return null
  const raw = extractJsonFromText(text) || text.trim()
  if (!raw || raw.startsWith('[')) return null
  try {
    const o = JSON.parse(raw)
    return typeof o === 'object' && o !== null && !Array.isArray(o) ? o : null
  } catch {
    return null
  }
}

/** 带缓存的解析，避免同一步在模板中多次 parse */
function getObsParsedCached(step) {
  if (!step?.observation) return null
  if (step._obsParsed !== undefined) return step._obsParsed
  step._obsParsed = getObsParsed(step.observation)
  return step._obsParsed
}

/** 是否为「题目详情」类工具返回（get_question_detail 等） */
function isQuestionDetailObs(obj) {
  return obj && typeof obj === 'object' && 'question_text' in obj && ('answer_text' in obj || 'question_id' in obj)
}

/** 观察区富文本：换行 + **粗体**，并转义 HTML 防 XSS */
function renderObsRichText(str) {
  if (str == null) return ''
  const s = String(str)
  const escape = (t) => t
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  const withBreaks = escape(s).replace(/\n/g, '<br>')
  return withBreaks.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

/** 切换某一步某 key 的长文本展开状态 */
function toggleObsExpand(step, key) {
  if (!step._obsExpand) step._obsExpand = {}
  step._obsExpand[key] = !step._obsExpand[key]
}

/** 过滤工具调用 JSON，避免泄露到聊天框 */
const filterToolCallJson = (text) => {
  if (!text || typeof text !== 'string') return text || ''
  return text.split('\n').filter(ln => !(ln.includes('"name":"') && ln.includes('"parameters"'))).join('\n').replace(/\n{3,}/g, '\n\n').trim()
}

/** 不做过滤，原样展示模型输出 */
const renderMd = (text) => {
  try {
    const content = filterToolCallJson(text || '')
    const result = renderEnhancedContent(content, marked)
    if (result instanceof Promise) {
      console.error('❌ renderMd 返回了 Promise，应该返回字符串！')
      return content
    }
    return result
  }
  catch (e) {
    console.error('renderMd 错误:', e)
    return text || ''
  }
}

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  if (isNaN(d.getTime())) return ''
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

const chatStore = useChatStore()
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

const restoreFromStore = () => {
  if (chatStore.userId !== props.userId || !chatStore.messages.length) return false
  messages.value = chatStore.messages.map(m => ({
    ...m,
    thinking: m.thinking || [],
    thinkingOpen: (m.thinking?.length ?? 0) > 0,
    timestamp: m.timestamp || new Date().toISOString(),
  }))
  if (chatStore.sessionId) sessionId.value = chatStore.sessionId
  const last = messages.value[messages.value.length - 1]
  if (last?.streaming) {
    streamingMsg.value = last
  } else {
    streamingMsg.value = null
  }
  scrollToBottom()
  console.log(`[restoreFromStore] 从 store 恢复 ${messages.value.length} 条消息`)
  return true
}

const loadHistory = async () => {
  if (!props.userId) return
  
  if (loading.value || streamingMsg.value) {
    console.log('[loadHistory] 跳过加载：正在流式输出中')
    return
  }
  
  // 🔧 切换回 chat 时优先从 store 恢复（解决切换页面后正在输出的内容丢失）
  if (chatStore.hasRestorableStreaming(props.userId)) {
    if (restoreFromStore()) return
  }
  
  try {
    const d = await api.getChatHistory(props.userId)
    lastLoadedUserId = props.userId
    
    if (d.messages?.length) {
      // 规范化 thinking 步骤字段，兼容新旧两种数据格式：
      // 旧格式：step.action(工具名) + step.toolArgs(参数) + step.observation(结果)
      // 新格式：step.tools[{name, args, observation/result, observationIsJson}]
      // 统一转为新格式，并保证 result/observation/args 字段都存在
      const normalizeThinkingFromDb = (thinking) => {
        if (!Array.isArray(thinking)) return []
        return thinking.map(step => {
          // 旧格式：有 step.action 但没有 step.tools 数组 → 转成 tools 数组
          if ((step.action || step.toolArgs) && (!step.tools || !step.tools.length)) {
            const obs = step.observation ?? step.result ?? null
            const obsStr = obs != null ? String(obs) : null
            const convertedTools = step.action ? [{
              name: step.action,
              args: step.toolArgs && Object.keys(step.toolArgs).length ? step.toolArgs : {},
              result: obsStr,
              observation: obsStr,
              observationIsJson: obsStr ? isObsJson(obsStr) : false,
            }] : []
            return {
              ...step,
              tools: convertedTools,
              // 清除旧字段避免模板重复渲染
              action: undefined,
              toolArgs: undefined,
              observation: undefined,
            }
          }
          // 新格式：规范化 tools 数组中的字段
          return {
            ...step,
            tools: Array.isArray(step.tools)
              ? step.tools.map(t => ({
                  ...t,
                  args: t.args && Object.keys(t.args).length ? t.args : (t.toolArgs && Object.keys(t.toolArgs).length ? t.toolArgs : {}),
                  result: t.result ?? t.observation ?? null,
                  observation: t.observation ?? t.result ?? null,
                }))
              : [],
          }
        })
      }
      const apiMsgs = d.messages.map(m => ({
        ...m,
        thinking: normalizeThinkingFromDb(m.thinking),
        thinkingOpen: (m.thinking?.length ?? 0) > 0,
        timestamp: m.timestamp || new Date().toISOString(),
      }))
      const lastStore = chatStore.messages[chatStore.messages.length - 1]
      const lastApi = apiMsgs[apiMsgs.length - 1]
      const storeHasNewer = chatStore.userId === props.userId && lastStore?.role === 'assistant' &&
        ((lastStore.content?.length || 0) > (lastApi?.content?.length || 0) || lastStore.streaming)
      if (storeHasNewer) {
        if (restoreFromStore()) return
      }
      messages.value = apiMsgs
      if (d.session_id) sessionId.value = d.session_id
      scrollToBottom()
      console.log(`[loadHistory] 加载了 ${d.messages.length} 条历史消息`)
    }
  } catch (e) { console.warn('加载对话历史失败', e) }
}

const clearChat = () => {
  messages.value = []
  sessionId.value = `sess_${Date.now()}`
  lastLoadedUserId = props.userId
  chatStore.clear()
}

// 当传入 { display, api } 时，屏幕只展示 display，实际发给 AI 的是 api
const prefillDisplayRef = ref(null)
const prefillAndSend = (textOrOptions) => {
  if (loading.value || sendInProgress) {
    ElMessage.warning('请等待当前消息发送完成')
    return
  }
  let text, display
  if (typeof textOrOptions === 'object' && textOrOptions?.display != null && textOrOptions?.api != null) {
    display = textOrOptions.display
    text = textOrOptions.api
    prefillDisplayRef.value = display
  } else {
    text = typeof textOrOptions === 'string' ? textOrOptions : ''
    prefillDisplayRef.value = null
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
  const displayContent = prefillDisplayRef.value ?? text
  prefillDisplayRef.value = null
  messages.value.push({ 
    role: 'user', 
    content: displayContent, 
    thinking: [], 
    thinkingOpen: false,
    timestamp: new Date().toISOString()  // 添加用户消息时间戳
  })
  scrollToBottom()

  loading.value = true
  abortCtrl = new AbortController()
  // 不传 signal，切换页面时流式输出不被中断（onUnmounted 已不再 abort）
  try {
    const res = await api.chatStream({
      user_id: props.userId,
      message: text,
      session_id: sessionId.value,
    }, undefined)

    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    if (!res.body) throw new Error('SSE 响应无 body，请检查后端是否返回流式数据')

    // AI 消息占位，thinkingOpen 初始 true（有步骤时自动展开）
    const aiMsgIndex = messages.value.length  // 记录索引而不是对象引用
    messages.value.push({ 
      role: 'assistant', 
      content: '', 
      streaming: true, 
      thinking: [], 
      thinkingOpen: true,
      timestamp: new Date().toISOString(),
      _startTs: Date.now()
    })
    streamingMsg.value = messages.value[aiMsgIndex]
    chatStore.startStream(props.userId, sessionId.value, messages.value)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let receivedFirstDelta = false
    let currentStep = {}  // 用于构建 thinking（HelloAgents 官方格式）
    // tool_call_start 阶段：用 Map 暂存「调用中」工具
    // key 格式：「toolName__callIndex」（callIndex 单调递增），value = 工具条目引用
    // tool_call_finish 按 FIFO 顺序取出同名工具的最早一条匹配记录
    const pendingToolsMap = new Map()  // Map<"toolName__N", toolEntry>
    let _toolCallCounter = 0           // 单调递增，保证同名工具多次调用时 key 不重复

    const handleEvent = (payload) => {
      const evType = payload.type
      const data = payload.data || payload   // 兼容新旧两种事件格式：新协议字段在顶层
      
      // 始终从数组中获取最新的消息对象
      const aiMsg = messages.value[aiMsgIndex]
      if (!aiMsg) return

      // ========== 新版自定义三通道协议 ==========
      // 后端以 SSE event: message|thinking|tool 推送，data 中直接携带字段：
      //  - message: { type:'message', phase:'chunk'|'finish', step, chunk }
      //  - thinking: { type:'thinking', step, chunk }
      //  - tool: { type:'tool', phase:'start'|'finish', step, tool_name, args, result }
      if (evType === 'message' && !payload.data) {
        const phase = data.phase || 'chunk'
        const chunk = data.chunk ?? ''
        if (phase === 'chunk') {
          let c = stripDsmlBlocks(chunk)
          if (c) {
            if (!receivedFirstDelta && aiMsg.thinking.length > 0) {
              aiMsg.thinkingOpen = false
              receivedFirstDelta = true
            }
            aiMsg.content += c
            messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
            streamingMsg.value = messages.value[aiMsgIndex]
            scrollToBottom()
          }
        } else if (phase === 'finish') {
          const cleanResult = stripDsmlBlocks(chunk).trim()
          aiMsg.content = stripDsmlBlocks(aiMsg.content || '').trim()
          if (cleanResult) {
            if (!aiMsg.content) {
              aiMsg.content = cleanResult
            } else if (!aiMsg.content.includes(cleanResult)) {
              aiMsg.content += '\n\n' + cleanResult
            }
          }
          aiMsg.duration_ms = data.duration_ms ?? (Date.now() - (aiMsg._startTs || Date.now()))
          messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
          streamingMsg.value = messages.value[aiMsgIndex]
        }
      } else if (evType === 'thinking') {
        // 支持多种格式：自定义 {step, chunk}、hello_agents {data: {content}}、reasoning_content
        const inner = data.data || data
        const chunk = data.chunk ?? data.content ?? inner?.content ?? inner?.chunk ?? inner?.reasoning_content ?? ''
        if (!chunk || typeof chunk !== 'string') {
          chatStore.syncMessages(messages.value)
          return
        }
        const stepNo = data.step ?? inner?.step ?? 1
        let stepObj = aiMsg.thinking.find(s => s.__step === stepNo)
        if (!stepObj) {
          stepObj = { __step: stepNo, thought: '', tools: [] }
          aiMsg.thinking.push(stepObj)
        }
        const normalized = normalizeThoughtForStep(chunk)
        stepObj.thought = stepObj.thought ? `${stepObj.thought}\n${normalized}` : normalized
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
      } else if (evType === 'tool' && !payload.data) {
        const phase = data.phase || 'start'
        const stepNo = data.step ?? 1
        const toolName = data.tool_name ?? ''
        if (!toolName || toolName === 'Thought' || toolName === 'Finish') {
          chatStore.syncMessages(messages.value)
          return
        }
        let stepObj = aiMsg.thinking.find(s => s.__step === stepNo)
        if (!stepObj) {
          stepObj = { __step: stepNo, thought: '', tools: [] }
          aiMsg.thinking.push(stepObj)
        }
        if (!Array.isArray(stepObj.tools)) {
          stepObj.tools = []
        }
        if (phase === 'start') {
          stepObj.tools.push({
            name: toolName,
            args: data.args || {},
            result: null,
            observationIsJson: false,
          })
        } else {
          // finish：找到最近一个同名且尚未写入 result 的记录，补充结果
          const toolsArr = stepObj.tools
          let target = null
          for (let i = toolsArr.length - 1; i >= 0; i--) {
            if (toolsArr[i].name === toolName && toolsArr[i].result == null) {
              target = toolsArr[i]
              break
            }
          }
          if (!target) {
            target = {
              name: toolName,
              args: data.args || {},
              result: null,
              observationIsJson: false,
            }
            toolsArr.push(target)
          }
          const obs = data.result != null ? String(data.result) : ''
          target.result = obs
          target.observationIsJson = isObsJson(obs)
        }
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
        scrollToBottom()

      // ========== 旧版 HelloAgents 官方事件格式（向后兼容） ==========
      } else if (evType === 'llm_chunk') {
        let chunk = data.chunk ?? data.content ?? ''
        // 流式过程中去掉 DSML 工具调用块，避免污染对话内容
        chunk = stripDsmlBlocks(chunk)
        if (chunk) {
          if (!receivedFirstDelta && aiMsg.thinking.length > 0) {
            aiMsg.thinkingOpen = false
            receivedFirstDelta = true
          }
          aiMsg.content += chunk
          
          // 强制触发 Vue 响应式更新
          messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
          streamingMsg.value = messages.value[aiMsgIndex]
          // console.log(`[响应式更新] content长度=${aiMsg.content.length}, 最新内容="${aiMsg.content.slice(-50)}"`)
          scrollToBottom()
        }
      } else if (evType === 'agent_finish') {
        const rawResult = data.result ?? ''
        const cleanResult = stripDsmlBlocks(rawResult).trim()

        // 也清理一下已累积内容中的 DSML，避免残留
        aiMsg.content = stripDsmlBlocks(aiMsg.content || '').trim()

        // 优先使用最终 result（评分+点评+标准答案），恢复为“图2”那种单条卡片格式
        // agent_finish.result 是最终完整答案
        // 若流式 llm_chunk 已累积了内容（正常情况），忽略 result，避免重复推送
        // 若流式内容为空（纯 reasoning 模式）或 DSML 残留，则用 result 覆盖
        if (cleanResult) {
          if (!aiMsg.content || aiMsg.content.startsWith('<｜DSML｜')) {
            aiMsg.content = cleanResult
          }
          // 有流式内容时不追加 result，避免重复
        }
        aiMsg.duration_ms = data.duration_ms ?? (Date.now() - (aiMsg._startTs || Date.now()))
        // ✅ 优先使用后端 agent_finish 中汇总的完整 thinking_steps
        // 复用 normalizeThinkingFromDb 同一套规范化逻辑（兼容旧格式 + 补齐 args/result/observation）
        const normalizeThinkingSteps = (steps) => {
          if (!Array.isArray(steps)) return []
          return steps.map(step => {
            if ((step.action || step.toolArgs) && (!step.tools || !step.tools.length)) {
              const obs = step.observation ?? step.result ?? null
              const obsStr = obs != null ? String(obs) : null
              const convertedTools = step.action ? [{
                name: step.action,
                args: step.toolArgs && Object.keys(step.toolArgs).length ? step.toolArgs : {},
                result: obsStr,
                observation: obsStr,
                observationIsJson: obsStr ? isObsJson(obsStr) : false,
              }] : []
              return { ...step, tools: convertedTools, action: undefined, toolArgs: undefined, observation: undefined }
            }
            return {
              ...step,
              tools: Array.isArray(step.tools)
                ? step.tools.map(t => ({
                    ...t,
                    args: t.args && Object.keys(t.args).length ? t.args : (t.toolArgs && Object.keys(t.toolArgs).length ? t.toolArgs : {}),
                    result: t.result ?? t.observation ?? null,
                    observation: t.observation ?? t.result ?? null,
                  }))
                : [],
            }
          })
        }
        if (Array.isArray(data.thinking) && data.thinking.length > 0) {
          // normalizeThinkingSteps 中同时清理后端写入的 🔧 前缀（前端模板自带图标）
          const cleanToolName = (n) => typeof n === 'string' ? n.replace(/^🔧\s*/, '') : (n || '')
          aiMsg.thinking = normalizeThinkingSteps(data.thinking).map(step => ({
            ...step,
            tools: Array.isArray(step.tools)
              ? step.tools.map(t => ({ ...t, name: cleanToolName(t.name) }))
              : [],
          }))
        } else if (aiMsg.thinking.length > 0) {
          // 降级：保留流式过程中已建好的 thinking 步骤（过滤掉残留的 pending 临时步）
          aiMsg.thinking = aiMsg.thinking.filter(s => s.__step !== 'pending')
        } else if (Object.keys(currentStep).length > 0 && (currentStep.thought || currentStep.action)) {
          // 最后降级：用 currentStep
          const last = aiMsg.thinking[aiMsg.thinking.length - 1]
          if (last?.thought && !last?.action) {
            Object.assign(last, { ...currentStep })
          } else {
            aiMsg.thinking.push({ ...currentStep })
          }
        }
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
      } else if (evType === 'step_start') {
        currentStep = {}
      } else if (evType === 'thinking') {
        const content = data.content ?? ''
        if (content) {
          currentStep.thought = normalizeThoughtForStep(content)
          currentStep.isReasoning = true
        }
      } else if (evType === 'tool_call_start') {
        const toolName = data.tool_name ?? ''
        const toolArgs = data.tool_args ?? {}
        if (toolName && toolName !== 'Thought' && toolName !== 'Finish') {
          // tool_call_start 时 backend 不发送 step 编号，无法确定归属哪一步。
          // 先在 pendingToolsMap 暂存占位条目，等 tool_call_finish 带着 step 编号到来时再挂入正确的 stepObj。
          // 同时创建一个「无归属」的临时 stepObj（__step: 'pending'）用于实时展示。
          const toolEntry = {
            name: toolName,
            args: Object.keys(toolArgs).length ? toolArgs : {},
            result: null,
            observationIsJson: false,
            _pending: true,
          }
          // 用单调递增计数器作为唯一 key，避免同名工具多次调用时混淆
          const callKey = `${toolName}__${_toolCallCounter++}`
          pendingToolsMap.set(callKey, toolEntry)

          // 找或创建 pending 临时步（__step: 'pending'）供实时展示
          let pendingStep = aiMsg.thinking.find(s => s.__step === 'pending')
          if (!pendingStep) {
            pendingStep = { __step: 'pending', thought: '', tools: [] }
            aiMsg.thinking.push(pendingStep)
          }
          pendingStep.tools.push(toolEntry)
          messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
          streamingMsg.value = messages.value[aiMsgIndex]
          scrollToBottom()
          // 保留 currentStep 兼容旧路径
          currentStep.pendingAction = `🔧 ${toolName}`
          currentStep.pendingArgs = Object.keys(toolArgs).length ? toolArgs : null
        }
      } else if (evType === 'tool_call_finish') {
        const toolName = data.tool_name ?? ''
        const result = data.result ?? ''
        const toolArgs = data.tool_args ?? {}

        if (toolName === 'Thought') {
          // Thought 工具：把推理内容写入 pending 步（与普通工具同属一步）
          let thought = String(result)
          for (const p of ['已记录推理过程:', '推理:']) {
            if (thought.startsWith(p)) { thought = thought.slice(p.length).trim(); break }
          }
          const normalizedThought = normalizeThoughtForStep(thought)
          // 找 pending 步（工具调用所在的步），没有则取最后一步，保证推理和工具在同一步
          let targetStep = aiMsg.thinking.find(s => s.__step === 'pending')
          if (!targetStep) {
            targetStep = aiMsg.thinking[aiMsg.thinking.length - 1]
          }
          if (!targetStep) {
            targetStep = { __step: 'pending', thought: '', tools: [] }
            aiMsg.thinking.push(targetStep)
          }
          targetStep.thought = targetStep.thought
            ? `${targetStep.thought}\n${normalizedThought}`
            : normalizedThought
        } else if (toolName === 'Finish') {
          // 单步直接 Finish：无 Thought 时也显示一步
          if (aiMsg.thinking.length === 0 && result) {
            aiMsg.thinking.push({
              __step: 1, thought: '', tools: [],
              action: '📝 输出',
              observation: result.length > 300 ? result.slice(0, 300) + '…' : result
            })
            messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
            streamingMsg.value = messages.value[aiMsgIndex]
            scrollToBottom()
          }
        } else {
          const obs = String(result)
          // 从 pendingToolsMap 按 FIFO 顺序取出最早匹配此工具名的占位条目
          // key 格式为 "toolName__callIndex"，按插入顺序遍历 Map 取第一个匹配的
          let pendingEntry = null
          let pendingKey = null
          for (const [k, v] of pendingToolsMap.entries()) {
            if (k.startsWith(toolName + '__')) {
              pendingEntry = v
              pendingKey = k
              break
            }
          }
          if (pendingKey) pendingToolsMap.delete(pendingKey)

          if (pendingEntry) {
            // 原地更新占位条目（它已经在 pendingStep.tools 里）
            pendingEntry.result = obs
            pendingEntry.observation = obs
            pendingEntry.observationIsJson = isObsJson(obs)
            pendingEntry._pending = false
            if (Object.keys(toolArgs || {}).length && !Object.keys(pendingEntry.args || {}).length) {
              pendingEntry.args = toolArgs
            }
            // pendingStep 中该工具已完成：若所有工具都完成则把 pendingStep 转为正式步
            const pendingStep = aiMsg.thinking.find(s => s.__step === 'pending')
            if (pendingStep && pendingStep.tools.every(t => !t._pending)) {
              // 所有工具已完成，将 pendingStep 转为正式编号步
              pendingStep.__step = Date.now()  // 用时间戳确保唯一，不与其他步冲突
            }
          } else {
            // 没有对应的 start 占位（旧协议只发 finish），追加到 pending 步或新建
            let pendingStep = aiMsg.thinking.find(s => s.__step === 'pending')
            if (!pendingStep) {
              pendingStep = { __step: 'pending', thought: '', tools: [] }
              aiMsg.thinking.push(pendingStep)
            }
            pendingStep.tools.push({
              name: toolName,
              args: Object.keys(toolArgs || {}).length ? toolArgs : {},
              result: obs,
              observation: obs,
              observationIsJson: isObsJson(obs),
            })
            // 旧协议没有 start，直接转为正式步
            pendingStep.__step = Date.now()
          }
        }

        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
        scrollToBottom()
      } else if (evType === 'error' || (payload && 'error' in payload && payload.error)) {
        const errMsg = data.error ?? payload?.error ?? '未知错误'
        aiMsg.content = `⚠️ ${errMsg}`
        aiMsg.streaming = false
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
      }
      chatStore.syncMessages(messages.value)
    }

    let eventCount = 0
    let lastUpdateTime = Date.now()
    
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          console.log(`[SSE流完成] 共接收 ${eventCount} 个事件`)
          break
        }
        
        // 解码数据块
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk
        console.log(`[SSE接收] 块大小=${chunk.length}字节, 缓冲区=${buffer.length}字节`)
        
        // 按 \n\n 分割 SSE 事件
        const lines = buffer.split('\n\n')
        
        // 保留最后一个不完整的块在缓冲区
        buffer = lines.pop() || ''
        
        // 处理完整的事件块
        for (const eventBlock of lines) {
          if (!eventBlock.trim()) continue
          
          let eventType = ''
          let dataLine = ''
          
          // 解析 SSE 格式: event: xxx\ndata: {...}
          for (const line of eventBlock.split('\n')) {
            const trimmed = line.trim()
            if (trimmed.startsWith('event: ')) {
              eventType = trimmed.slice(7)
            } else if (trimmed.startsWith('data: ')) {
              dataLine = trimmed.slice(6)
            }
          }
          
          if (!dataLine) continue
          
          try {
            const payload = JSON.parse(dataLine)
            if (!payload.type && eventType) {
              payload.type = eventType
            }
            
            eventCount++
            console.log(`[SSE事件 #${eventCount}] type=${payload.type}, data=`, payload.data)
            
            // 处理事件
            handleEvent(payload)
            
            // 使用 requestAnimationFrame 确保 DOM 实时更新（不阻塞）
            requestAnimationFrame(() => {
              scrollToBottom()
            })
            
            // 限制日志频率，避免控制台刷屏
            const now = Date.now()
            if (now - lastUpdateTime > 100) {
              lastUpdateTime = now
            }
          } catch (parseErr) {
            console.warn(`[SSE解析失败] 事件#${eventCount}:`, parseErr, 'data:', dataLine)
          }
        }
      }
    } catch (streamErr) {
      console.error(`[SSE流错误]:`, streamErr)
      throw streamErr
    } finally {
      // 流结束，更新 streaming 状态，确保耗时已设置
      console.log(`[SSE] 流式响应完成，共接收 ${eventCount} 个事件`)
      const finalMsg = messages.value[aiMsgIndex]
      if (finalMsg) {
        finalMsg.streaming = false
        if (finalMsg.duration_ms == null && finalMsg._startTs) {
          finalMsg.duration_ms = Date.now() - finalMsg._startTs
        }
        // 当前回复的推理过程默认展开，避免用户看到的是上一轮消息的步骤（前后一致）
        if (finalMsg.thinking?.length > 0) {
          finalMsg.thinkingOpen = true
        }
        messages.value.splice(aiMsgIndex, 1, { ...finalMsg })
        console.log(`[SSE] 消息状态已更新为 completed，消息ID: ${finalMsg.id}`)
      }
      streamingMsg.value = null
      chatStore.finishStream(messages.value)
      scrollToBottom()
    }

  } catch (err) {
    console.error('🔴 流式接口错误:', err)
    console.error('🔴 错误类型:', err.name)
    console.error('🔴 错误消息:', err.message)
    console.error('🔴 错误堆栈:', err.stack)
    
    if (err.name === 'AbortError') {
      // 用户中止（页面切换/手动停止）- 静默处理，不显示错误
      console.log('🟡 用户中止请求（页面切换或手动停止）')
      // 移除流式消息占位符
      if (streamingMsg.value) {
        messages.value = messages.value.filter(m => m !== streamingMsg.value)
        streamingMsg.value = null
      }
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
    chatStore.finishStream(messages.value)
    abortCtrl = null
    scrollToBottom()
  }
}

watch([() => props.isActive, () => props.userId], ([active, uid], [prevActive, prevUid]) => {
  // 页面激活时加载历史
  if (active && uid) {
    loadHistory()
  }
  // 🔧 页面失活时不再中断请求，让后端继续完成
  // 这样切换回来时可以看到完整的历史记录
}, { immediate: true })

onUnmounted(() => {
  // 不再在卸载时 abort，避免切换页面时打断流式输出；页面关闭时浏览器会自动清理
  if (isRecording.value && recognition) {
    isRecording.value = false
    try {
      recognition.stop()
    } catch (e) {
      // 忽略停止错误
    }
  }
})
</script>

<style scoped>
.chat-wrap {
  display: flex; flex-direction: column;
  height: calc(100vh - 50px - 20px);
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.chat-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.chat-title { font-size: 14px; font-weight: 600; }
.header-actions { display: flex; gap: 6px; }

.quick-btns {
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.quick-btns .el-button { font-size: 11px; height: 24px; }

.messages {
  flex: 1; overflow-y: auto; padding: 10px 14px;
  display: flex; flex-direction: column; gap: 10px;
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

.msg-avatar { font-size: 24px; flex-shrink: 0; margin-top: 2px; overflow: hidden; }
.avatar-img { width: 100%; height: 100%; object-fit: cover; border-radius: 10px; }

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
  padding: 8px 12px;
  border-radius: 12px; font-size: 13px; line-height: 1.6;
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
.meta-item.completed-badge { color: #22c55e; font-weight: 500; }

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
.step-num-pending {
  color: #94a3b8; font-style: italic; font-weight: 500; letter-spacing: 0;
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
/* 思考过程（reasoning_content）在对话框中以灰色显示 */
.step-item.thought .step-text {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.5;
}
.obs-text { color: #2d3436; }

/* 观察区：题目详情卡片 */
.obs-friendly-card {
  width: 100%; border-radius: 8px; overflow: hidden;
  border: 1px solid #cbd5e1; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 12px 14px; font-size: 13px; line-height: 1.55;
}
.obs-card-meta {
  display: flex; flex-wrap: wrap; gap: 8px 12px; margin-bottom: 8px;
  font-size: 11px; color: #64748b;
}
.obs-meta-id { font-family: 'Consolas', monospace; }
.obs-meta-diff {
  padding: 1px 6px; border-radius: 4px; background: #e2e8f0; color: #475569;
}
.obs-meta-tags { color: #0369a1; }
.obs-card-q {
  color: #1e293b; font-weight: 500; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #e2e8f0;
}
.obs-card-answer { margin-top: 8px; }
.obs-answer-label {
  font-size: 11px; font-weight: 600; color: #64748b; margin-bottom: 6px;
}
.obs-answer-body {
  max-height: 320px; overflow-y: auto; padding: 8px 0;
  color: #334155; white-space: pre-wrap; word-break: break-word;
}
.obs-answer-body br { display: block; content: ''; margin-bottom: 0.25em; }
.obs-answer-body strong { color: #0f172a; font-weight: 600; }

/* 观察区：通用键值列表 */
.obs-kv-wrap {
  width: 100%; border-radius: 8px; overflow: hidden;
  border: 1px solid #cbd5e1; background: #fafbfc; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  padding: 10px 12px; font-size: 12px;
}
.obs-kv-row {
  margin-bottom: 8px; display: flex; flex-direction: column; gap: 2px;
}
.obs-kv-row:last-child { margin-bottom: 0; }
.obs-kv-key {
  font-weight: 600; color: #475569; font-size: 11px;
}
.obs-kv-val {
  color: #1e293b; white-space: pre-wrap; word-break: break-word;
}
.obs-kv-val pre.obs-kv-json {
  margin: 0; padding: 8px; background: #f1f5f9; border-radius: 4px;
  font-size: 11px; overflow-x: auto; max-height: 200px; overflow-y: auto;
}
.obs-expand-btn {
  margin-top: 4px; padding: 2px 8px; font-size: 11px; cursor: pointer;
  color: #0369a1; background: transparent; border: 1px solid #bae6fd; border-radius: 4px;
}
.obs-expand-btn:hover { background: #e0f2fe; }

.obs-json-wrap {
  width: 100%; border-radius: 8px; overflow: hidden;
  border: 1px solid #cbd5e1; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.step-obs-json {
  margin: 0; padding: 12px 14px; background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  font-size: 12px; max-height: 400px; overflow: auto; white-space: pre-wrap; word-break: break-all;
  color: #1e293b; font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  line-height: 1.5;
}
.step-obs-json code {
  background: none; padding: 0; color: inherit; font-size: inherit;
}

.step-item.thought {
  background: #fff9e6;
}
.step-item.thought .step-label { background: #ffeaa7; color: #d35400; }

.step-item.action {
  background: #edfbee;
}
.step-item.action .step-label { background: #b2f0b4; color: #00823a; }
.tool-args {
  margin-top: 6px; font-size: 11px; color: #64748b;
}
.tool-args .args-label { font-weight: 500; margin-right: 4px; }
.tool-args .args-json {
  margin: 4px 0 0; padding: 8px; background: #f8fafc;
  border-radius: 4px; overflow-x: auto; font-family: 'Consolas', monospace;
  font-size: 10.5px; white-space: pre-wrap; word-break: break-all;
}

/* 新增：工具项容器，确保流式和完成后样式一致 */
.tool-item {
  margin-top: 6px; padding: 6px 8px; background: #f0f4ff; border-radius: 6px;
  border-left: 3px solid #6c5ce7;
}
.tool-item .step-code {
  display: block; margin-bottom: 6px;
}
.tool-item .tool-args-inner {
  margin-top: 4px; font-size: 11px; color: #64748b;
}
.tool-item .args-label { font-weight: 500; margin-right: 4px; }
.tool-item .args-json {
  margin: 4px 0 0; padding: 8px; background: #f8fafc;
  border-radius: 4px; overflow-x: auto; font-family: 'Consolas', monospace;
  font-size: 10.5px; white-space: pre-wrap; word-break: break-all;
}

/* 工具项头部：工具名 + 状态徽章 */
.tool-item-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}

/* 调用中状态：半透明边框 */
.tool-item.tool-pending {
  border-left-color: #a78bfa;
  background: #f5f3ff;
  opacity: 0.9;
}

/* 「调用中…」徽章 */
.tool-pending-badge {
  font-size: 10px; font-weight: 500;
  color: #7c3aed; background: #ede9fe;
  padding: 1px 6px; border-radius: 8px;
  animation: pulse-badge 1.2s ease-in-out infinite;
}
@keyframes pulse-badge {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.45; }
}

/* 等待结果行 */
.tool-pending-result {
  display: flex; align-items: center; gap: 6px;
}

/* 小旋转加载图标 */
.tool-spinner {
  display: inline-block;
  width: 12px; height: 12px;
  border: 2px solid #c4b5fd;
  border-top-color: #7c3aed;
  border-radius: 50%;
  animation: spin-tool 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes spin-tool {
  to { transform: rotate(360deg); }
}
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

.step-item.completed {
  background: #e8f5e9;
  color: #2e7d32; font-weight: 500;
}
.step-item.completed .step-icon { color: #22c55e; }
.completed-step .step-num { color: #22c55e; }

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
  background: linear-gradient(135deg, #f5f5f7 0%, #f0f0f5 100%);
  color: #2c3e50;
  padding: 14px; border-radius: 10px; overflow-x: auto; margin: 10px 0;
  border: 1px solid #e0e0e6;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  font-family: 'Fira Code', 'Consolas', monospace;
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

/* 评分反馈样式 */
.md-content :deep(.score-badge) {
  display: inline-block;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  padding: 6px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 15px;
  margin: 8px 0;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}
.md-content :deep(.icon-correct) {
  color: #22c55e;
  font-weight: 700;
  margin-right: 2px;
}
.md-content :deep(.icon-missed) {
  color: #f59e0b;
  font-weight: 700;
  margin-right: 2px;
}
.md-content :deep(.icon-error) {
  color: #ef4444;
  font-weight: 700;
  margin-right: 2px;
}

/* 流式打字光标：单一、低调，不与其它样式冲突 */
.stream-caret {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  background-color: currentColor;
  vertical-align: text-bottom;
  animation: stream-caret-blink .8s step-end infinite;
}
@keyframes stream-caret-blink {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}

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
  display: flex; gap: 8px; align-items: flex-end;
  padding: 8px 12px;
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
  width: 36px; height: 36px;
  border-radius: 50%;
  border: 2px solid #e0e0e0;
  background: linear-gradient(135deg, #f5f7fa 0%, #f0f3f7 100%);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
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
  height: 36px; 
  width: 36px; 
  font-size: 13px; 
  font-weight: 700;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
  box-shadow: 0 3px 8px rgba(102, 126, 234, 0.3);
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

/* ── 结构化题目卡片 ── */
.question-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  color: white;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
}

.question-header {
  margin-bottom: 16px;
}

.question-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.question-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.difficulty {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  text-transform: uppercase;
}

.tag {
  background: rgba(255, 255, 255, 0.2);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.question-requirements {
  margin-bottom: 12px;
}

.question-requirements h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
}

.question-requirements ol {
  margin: 0;
  padding-left: 20px;
}

.question-requirements li {
  margin-bottom: 6px;
  font-size: 14px;
  line-height: 1.5;
}

.question-tips {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255, 255, 255, 0.1);
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  border-left: 3px solid rgba(255, 255, 255, 0.5);
}

.tips-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.raw-content {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
}
</style>
