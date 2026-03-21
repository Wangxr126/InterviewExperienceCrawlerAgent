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
              <span class="step-badge">{{ countFinalizedSteps(m.thinking) }} 步 · {{ countTotalTools(m.thinking) }} 工具</span>
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
                        <div class="args-rich-json" v-html="renderToolDataHtml(step.toolArgs)"></div>
                      </div>
                    </template>
                    <!-- 新协议：同一步多工具 -->
                    <template v-else>
                      <div v-for="(tool, ti) in step.tools" :key="ti" class="tool-item" :class="{ 'tool-pending': tool._pending }">
                        <!-- submit_answer 工具：推理过程中只显示原始 JSON，不渲染 -->
                        <template v-if="tool.name === 'submit_answer' || tool.name === '🔧 submit_answer'">
                          <div class="tool-item-header">
                            <code class="step-code">{{ tool.name }}</code>
                            <span v-if="tool._pending" class="tool-pending-badge">评分中…</span>
                          </div>
                          <template v-if="!tool._pending">
                            <div class="tool-args-inner">
                              <span class="args-label">参数:</span>
                              <div class="args-rich-json" v-html="renderToolArgsHtml(tool)"></div>
                            </div>
                            <div class="tool-args-inner">
                              <span class="args-label">结果:</span>
                              <div class="args-rich-json" v-html="renderToolResultHtml(tool)"></div>
                            </div>
                          </template>
                        </template>
                        <!-- 其他工具：正常展示 -->
                        <template v-else>
                          <div class="tool-item-header">
                            <code class="step-code">{{ tool.name }}</code>
                            <span v-if="tool._pending" class="tool-pending-badge">调用中…</span>
                          </div>
                          <div class="tool-args-inner">
                            <span class="args-label">参数:</span>
                            <div class="args-rich-json" v-html="renderToolArgsHtml(tool)"></div>
                          </div>
                          <div v-if="tool._pending" class="tool-args-inner tool-pending-result">
                            <span class="args-label">结果:</span>
                            <span class="tool-spinner"></span>
                            <span class="step-text" style="color:#94a3b8">等待结果…</span>
                          </div>
                          <div v-else class="tool-args-inner">
                            <span class="args-label">结果:</span>
                            <div class="args-rich-json" v-html="renderToolResultHtml(tool)"></div>
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
                      <!-- 其他 JSON：统一按 args-kv 树渲染（参数名 + 参数值） -->
                      <div v-else-if="getObsParsedCached(step)" class="obs-kv-wrap">
                        <div class="args-rich-json" v-html="renderToolDataHtml(getObsParsedCached(step))"></div>
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
import markedKatex from 'marked-katex-extension'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import { api } from '../api.js'
import { useChatStore } from '../stores/chatStore.js'
import { saveChatDraft, loadChatDraft, clearChatDraft } from '../utils/chatPersistence.js'
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
// ⚠️ 禁用 KaTeX 公式渲染以避免卡死，只保留 Markdown 渲染
// marked.use(markedKatex({ throwOnError: false, nonStandard: true }))

const normalizeMathDelimiters = (text) => {
  if (!text || typeof text !== 'string') return text || ''

  const normalizeMathExpr = (expr) => {
    if (!expr || typeof expr !== 'string') return expr || ''
    return expr
      // 二次转义的 LaTeX 命令：\\frac -> \frac
      .replace(/\\\\([a-zA-Z]+)/g, '\\$1')
      // 二次转义的控制符：\\_ \\^ \\{ \\}
      .replace(/\\\\([_^{}[\]()])/g, '\\$1')
      .trim()
  }

  return text
    // 支持 \[...\] 与 \\[...\\]
    .replace(/\\{1,2}\[\s*([\s\S]*?)\s*\\{1,2}\]/g, (_, expr) => `$$\n${normalizeMathExpr(expr)}\n$$`)
    // 支持 \(...\) 与 \\(...\\)
    .replace(/\\{1,2}\(\s*([\s\S]*?)\s*\\{1,2}\)/g, (_, expr) => `$${normalizeMathExpr(expr)}$`)
}

const normalizeEscapedText = (text) => {
  if (!text || typeof text !== 'string') return text || ''
  // 仅对常见序列做轻量还原，避免把任意反斜杠都吞掉
  const restored = text
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '  ')
    // 把二次转义的数学分隔符先降一层，方便后续统一替换
    .replace(/\\\\\(/g, '\\(')
    .replace(/\\\\\)/g, '\\)')
    .replace(/\\\\\[/g, '\\[')
    .replace(/\\\\\]/g, '\\]')
  return normalizeMathDelimiters(restored)
}

/** 推理过程观察：尝试格式化为 JSON 展示（工具调用结果用代码块） */
const formatObsJson = (text) => {
  if (!text || typeof text !== 'string') return ''
  const extracted = extractJsonFromText(text)
  if (extracted) {
    const parsed = parseJsonLikeString(extracted)
    if (parsed.ok) return JSON.stringify(parsed.value, null, 2)
  }
  const parsed = parseJsonLikeString(text.trim())
  if (parsed.ok) return JSON.stringify(parsed.value, null, 2)
  return text
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

/** 去掉 DeepSeek 输出中的 DSML 工具调用块（完整块过滤） */
function stripDsmlBlocks(text) {
  if (!text || typeof text !== 'string') return text
  let s = text
  // 兼容 `<｜DSML｜`、`<|DSML|>` 以及 `< | DSML |`（尖括号与竖线间有空格）
  s = s.replace(/<\s*[｜|]\s*DSML\s*[｜|]\s*function_calls\s*>[\s\S]*?<\/\s*[｜|]\s*DSML\s*[｜|]\s*function_calls\s*>/gi, '')
  // 删除独立 DSML 标签行
  s = s.replace(/^\s*<\s*\/?\s*[｜|]\s*DSML\s*[｜|][^>]*>\s*$/gim, '')
  // 若存在未闭合 DSML 起始标签，直接截断
  const danglingStart = s.search(/<\s*[｜|]\s*DSML\s*[｜|]/i)
  if (danglingStart >= 0) s = s.slice(0, danglingStart)
  // 兼容：DSML 标签被切分后，可能残留为纯文本 invoke/parameter 行，统一过滤
  s = s.replace(/^\s*invoke\s+name=.*$/gim, '')
  s = s.replace(/^\s*parameter\s+name=.*$/gim, '')
  return s.replace(/\n{3,}/g, '\n\n')
}

/**
 * 跨 chunk 的 DSML 过滤器：
 * 当 DSML 开始标签被拆分到多个 chunk 时，先把可疑前缀缓存起来
 * 等到确认不是 DSML 再放行，或等到完整块结束再丢弃。
 * 返回 { safe: string, pending: string }
 */
function filterChunkWithDsmlGuard(chunk, pendingBuf) {
  let combined = pendingBuf + chunk

  // 1. 先做完整块过滤
  combined = stripDsmlBlocks(combined)

  // 2. 检查末尾是否有 DSML 开始标签的前缀（跨 chunk 情况）
  const startTags = ['<｜DSML｜', '<|DSML|']
  let newPending = ''
  for (const startTag of startTags) {
    for (let len = Math.min(startTag.length - 1, combined.length); len > 0; len--) {
      const tail = combined.slice(-len)
      if (startTag.startsWith(tail)) {
        newPending = tail
        combined = combined.slice(0, -len)
        break
      }
    }
    if (newPending) break
  }
  // 3. 最后兜底：过滤残留 DSML 行
  if (/[｜|]\s*DSML\s*[｜|]/i.test(combined) || /<\s*[｜|]\s*DSML/i.test(combined)) {
    combined = combined
      .split('\n')
      .filter(ln => !/[｜|]\s*DSML\s*[｜|]/i.test(ln) && !/<\s*[｜|]\s*DSML/i.test(ln))
      .join('\n')
      .replace(/\n{3,}/g, '\n\n')
  }
  return { safe: combined, pending: newPending }
}

/** 检测是否进入了工具调用计划文本（应从聊天正文中屏蔽） */
function detectToolPlanText(text) {
  if (!text || typeof text !== 'string') return false
  const t = text
  // DSML 标签、被切分后的 invoke/parameter 行都视为工具计划文本
  return /[｜|]\s*DSML\s*[｜|]/i.test(t)
    || /<\s*[｜|]\s*DSML\s*[｜|]/i.test(t)
    || /^\s*invoke\s+name\s*=.*$/im.test(t)
    || /^\s*parameter\s+name\s*=.*$/im.test(t)
    || /function_calls/i.test(t)
}

const sanitizeDisplayText = (text, trim = true) => {
  if (!text || typeof text !== 'string') return text || ''
  const cleaned = stripDsmlBlocks(normalizeEscapedText(text))
    .split('\n')
    .filter(ln => !/[｜|]\s*DSML\s*[｜|]/i.test(ln) && !/<\s*[｜|]\s*DSML/i.test(ln))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
  return trim ? cleaned.trim() : cleaned
}

/** 判断观察是否为 JSON 格式（工具调用结果优先以 JSON 代码块展示） */
const isObsJson = (text) => {
  if (!text || typeof text !== 'string') return false
  const t = text.trim()
  if (!(t.startsWith('{') || t.startsWith('['))) {
    const extracted = extractJsonFromText(text)
    if (extracted) return parseJsonLikeString(extracted).ok
    return false
  }
  if (parseJsonLikeString(t).ok) return true
  const extracted = extractJsonFromText(text)
  return extracted ? parseJsonLikeString(extracted).ok : false
}

/** 避免把「工具调用 JSON 计划」当思考展示：若为 [{"name":"xxx",...}] 则替换为简短说明 */
function normalizeThoughtForStep(thought) {
  if (!thought || typeof thought !== 'string') return thought || ''
  // 推理区也要做 DSML 清洗，避免 function_calls 原文泄露到 UI
  const s = sanitizeDisplayText(thought).trim()
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
 * 计算步骤的显示序号：直接使用后端传来的 __step 值
 * 后端已经保证 __step 是正确的步号，无需重新计算
 * ✅ 修复：后端推送 step=1 时，前端直接显示"第 1 步"，不再错位
 */
function computeStepDisplay(thinking, idx) {
  const step = thinking[idx]
  if (!step) return idx + 1
  // 优先使用后端的 __step 值（已验证正确）
  if (typeof step.__step === 'number' && step.__step > 0) {
    return step.__step
  }
  // 降级：按数组位置计算（兼容旧数据）
  let num = 0
  for (let i = 0; i <= idx; i++) {
    if (thinking[i].__step !== 'pending') num++
  }
  return num
}
/**
 * 计算 badge 中显示的步数：
 * - 已完成步（__step !== 'pending'）直接计数
 * - 若存在 pending 步（流式过程中），额外算 1 步
 * 这样流式时 badge 显示正确，agent_finish 后 pending 步被清除也正确。
 */
function countFinalizedSteps(thinking) {
  if (!Array.isArray(thinking)) return 0
  const finalized = thinking.filter(s => s.__step !== 'pending').length
  const hasPending = thinking.some(s => s.__step === 'pending')
  return finalized + (hasPending ? 1 : 0)
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
  const parsed = parseJsonLikeString(raw)
  if (!parsed.ok) return null
  const o = parsed.value
  return typeof o === 'object' && o !== null && !Array.isArray(o) ? o : null
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

/** 解析 submit_answer 工具返回的评估结果（成功时为 JSON，含 score/feedback/strong_points 等） */
function getSubmitAnswerEval(tool) {
  const raw = tool?.result ?? tool?.observation
  if (raw == null || typeof raw !== 'string') return null
  const parsed = getObsParsed(raw)
  if (!parsed || typeof parsed.score === 'undefined') return null
  return {
    score: parsed.score,
    feedback: parsed.feedback ?? '',
    strong_points: Array.isArray(parsed.strong_points) ? parsed.strong_points : [],
    missed_points: Array.isArray(parsed.missed_points) ? parsed.missed_points : [],
    error_points: [
      ...( Array.isArray(parsed.error_points) ? parsed.error_points : [] ),
      ...( Array.isArray(parsed.shortcomings) ? parsed.shortcomings : [] ),
    ],
    standard_answer: parsed.standard_answer ?? '',
  }
}

/** 观察区富文本：换行 + **粗体**，并转义 HTML 防 XSS */
function renderObsRichText(str) {
  if (str == null) return ''
  const s = normalizeEscapedText(String(str))
  try {
    const rendered = marked.parse(s)
    if (typeof rendered === 'string' && rendered.trim()) return rendered
  } catch (e) {
    console.warn('renderObsRichText markdown 渲染失败，降级纯文本:', e)
  }
  const escape = (t) => t
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  const withBreaks = escape(s).replace(/\n/g, '<br>')
  return withBreaks.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

function getToolArgs(tool) {
  if (!tool || typeof tool !== 'object') return {}
  const raw = tool.args ?? tool.toolArgs ?? tool.parameters ?? {}
  return parseToolArgsLike(raw)
}

function toSingleLineText(input) {
  if (input == null) return ''
  return String(input)
    .replace(/\s*\r?\n+\s*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function parseToolArgsLike(raw) {
  if (raw == null) return {}
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    const parsed = parseJsonLikeString(raw)
    if (parsed.ok) {
      const v = parsed.value
      return (v && typeof v === 'object' && !Array.isArray(v)) ? v : { _raw: raw }
    }
    return { _raw: raw }
  }
  return { _raw: String(raw) }
}

function parseJsonLikeString(raw) {
  if (typeof raw !== 'string') return { ok: false, value: null }
  const txt = raw.trim()
  if (!txt) return { ok: false, value: null }
  try {
    return { ok: true, value: JSON.parse(txt) }
  } catch {
    // fallback: 兼容 Python dict/list 字符串（单引号 + True/False/None）
    const pyLike = txt
      .replace(/\bTrue\b/g, 'true')
      .replace(/\bFalse\b/g, 'false')
      .replace(/\bNone\b/g, 'null')
      .replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, s) => `"${String(s).replace(/"/g, '\\"')}"`)
    try {
      return { ok: true, value: JSON.parse(pyLike) }
    } catch {
      return { ok: false, value: null }
    }
  }
}

function extractToolArgsFromEvent(data) {
  // 注意：不要读取 data.input。部分流式适配器会把结果内容放在 input 字段，导致“参数/结果”显示串位。
  const raw =
    data?.args ??
    data?.tool_args ??
    data?.arguments ??
    data?.tool_arguments ??
    data?.tool_input ??
    data?.parameters
  return parseToolArgsLike(raw)
}

function renderToolDataHtml(data) {
  const renderPlainText = (text) => {
    const normalized = toSingleLineText(normalizeEscapedText(String(text)))
    return `<pre class="args-kv-text">${escapeHtml(normalized)}</pre>`
  }

  const maybeRenderStringAsStructured = (text, level = 0) => {
    const parsed = parseJsonLikeString(text)
    if (!parsed.ok) return null
    const val = parsed.value
    if (val == null || typeof val !== 'object') return null
    if (Array.isArray(val)) return renderArrayValue(val, level)
    return renderObjectValue(val, level)
  }

  const renderLongText = (text) => {
    const str = String(text)
    return renderPlainText(str)
  }

  const renderArrayValue = (arr, level = 0) => {
    if (!arr.length) return '<span class="args-kv-primitive">[]</span>'
    const items = arr.map((item, idx) => renderJsonNode(String(idx), item, level + 1)).join('')
    return `<div class="args-kv-group">
      <div class="args-kv-group-title">数组(${arr.length})</div>
      <div class="args-kv-wrap args-kv-nested level-${Math.min(level + 1, 3)}">${items}</div>
    </div>`
  }

  const renderObjectValue = (obj, level = 0) => {
    const entries = Object.entries(obj)
    if (!entries.length) return '<span class="args-kv-primitive">{}</span>'
    const childRows = entries.map(([k, v]) => renderJsonNode(k, v, level + 1)).join('')
    return `<div class="args-kv-group">
      <div class="args-kv-group-title">对象(${entries.length})</div>
      <div class="args-kv-wrap args-kv-nested level-${Math.min(level + 1, 3)}">${childRows}</div>
    </div>`
  }

  const renderJsonNode = (key, value, level = 0) => {
    const keyHtml = `<span class="args-kv-key">${escapeHtml(key)}：</span>`
    const wrap = (content) => `<div class="args-kv-row"><div class="args-kv-inline">${keyHtml}<div class="args-kv-val">${content}</div></div></div>`
    if (value == null) return wrap('<span class="args-kv-primitive">null</span>')
    if (typeof value === 'string') {
      const nested = maybeRenderStringAsStructured(value, level)
      if (nested) return wrap(nested)
      return wrap(renderLongText(value))
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return wrap(`<span class="args-kv-primitive">${escapeHtml(String(value))}</span>`)
    }
    if (Array.isArray(value)) {
      return wrap(renderArrayValue(value, level))
    }
    if (typeof value === 'object') {
      return wrap(renderObjectValue(value, level))
    }
    return wrap(`<span class="args-kv-primitive">${escapeHtml(String(value))}</span>`)
  }

  if (data == null) return ''
  // 1) 字符串：优先按 JSON 解析，失败按 markdown + 公式渲染
  if (typeof data === 'string') {
    const text = normalizeEscapedText(data)
    const nested = maybeRenderStringAsStructured(text)
    if (nested) return `<div class="args-kv-wrap">${nested}</div>`
    return renderLongText(text)
  }

  // 2) 对象：做紧凑 key-value 渲染，字符串值支持公式
  if (typeof data === 'object') {
    const entries = Array.isArray(data) ? data.map((v, i) => [String(i), v]) : Object.entries(data)
    const rows = entries.map(([k, v]) => renderJsonNode(k, v))
    return `<div class="args-kv-wrap">${rows.join('')}</div>`
  }

  return renderPlainText(String(data))
}

function renderToolArgsHtml(tool) {
  const args = getToolArgs(tool)
  if (!args || !Object.keys(args).length) {
    return `<pre class="args-kv-text">${escapeHtml('无入参')}</pre>`
  }
  // 参数统一按 JSON 展示，避免不同工具字段差异导致的视觉歧义
  return `<pre class="args-kv-text">${escapeHtml(stringifyAsJson(args))}</pre>`
}

function stringifyAsJson(raw) {
  if (raw == null) return ''
  if (typeof raw === 'string') {
    const parsed = parseJsonLikeString(raw)
    if (parsed.ok) return JSON.stringify(parsed.value, null, 2)
    return toSingleLineText(raw)
  }
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return toSingleLineText(String(raw))
  }
}

function renderToolResultHtml(tool) {
  const raw = tool?.result ?? tool?.observation
  if (raw == null || raw === '') {
    return `<pre class="args-kv-text">${escapeHtml('暂无结果')}</pre>`
  }
  const jsonText = stringifyAsJson(raw)
  return `<pre class="args-kv-text">${escapeHtml(jsonText)}</pre>`
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
    const content = sanitizeDisplayText(filterToolCallJson(text || ''))
    const result = renderEnhancedContent(content, marked)
    if (result instanceof Promise) {
      console.error('❌ renderMd 返回了 Promise，应该返回字符串！')
      return content
    }
    return result
  }
  catch (e) {
    console.error('renderMd 错误:', e)
    return sanitizeDisplayText(text || '')
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
const getFixedSessionId = () => 'sess_' + (props.userId || 'default')
const sessionId    = ref(getFixedSessionId())
let   abortCtrl    = null
let   lastLoadedUserId = ''
let   sendInProgress = false  // 防止并发调用的标志
const historyLoading = ref(false)  // loadHistory 正在进行中，prefillAndSend 需等待
const STREAM_SYNC_INTERVAL_MS = 120
let lastStreamSyncTs = 0
let lastLocalPersistTs = 0
const LOCAL_PERSIST_MS = 280
/** 本地草稿：节流写入，force 时立即保存（用户发消息、流结束、错误） */
const persistLocalDraft = (force = false) => {
  if (!props.userId) return
  const now = Date.now()
  if (!force && now - lastLocalPersistTs < LOCAL_PERSIST_MS) return
  lastLocalPersistTs = now
  try {
    saveChatDraft(props.userId, sessionId.value, JSON.parse(JSON.stringify(messages.value)))
  } catch (e) {
    console.warn('[ChatView] 本地草稿保存失败', e)
  }
}
const syncStreamState = (force = false) => {
  const now = Date.now()
  if (force || now - lastStreamSyncTs >= STREAM_SYNC_INTERVAL_MS) {
    lastStreamSyncTs = now
    chatStore.syncMessages(messages.value)
    persistLocalDraft(force)
  }
}

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

const onBeforeUnloadPersist = () => {
  if (props.userId && messages.value.length) {
    try {
      saveChatDraft(props.userId, sessionId.value, JSON.parse(JSON.stringify(messages.value)))
    } catch (_) { /* ignore */ }
  }
}

// 挂载时初始化语音识别 + 刷新前落盘
onMounted(() => {
  initSpeech()
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', onBeforeUnloadPersist)
  }
})

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

// 滚动到消息框的最顶部（用于"下一题"等场景）
const scrollToLatestMessageTop = () => {
  nextTick(() => {
    if (msgBox.value) {
      // 滚动到最后一条消息顶部，避免误回到会话最上方
      const rows = msgBox.value.querySelectorAll('.msg-row')
      const lastRow = rows[rows.length - 1]
      if (lastRow) {
        msgBox.value.scrollTop = Math.max(0, lastRow.offsetTop - 8)
        return
      }
      msgBox.value.scrollTop = msgBox.value.scrollHeight
    }
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

const loadHistory = async (loadAll = false) => {
  if (!props.userId) return
  
  if (loading.value || streamingMsg.value) {
    console.log('[loadHistory] 跳过加载：正在流式输出中')
    return
  }
  
  // 🔧 切换回 chat 时优先从 store 恢复（解决切换页面后正在输出的内容丢失）
  if (chatStore.hasRestorableStreaming(props.userId)) {
    if (restoreFromStore()) return
  }

  historyLoading.value = true
  try {
    // 如果 loadAll=true，加载所有会话的历史；否则加载当前会话
    const d = loadAll 
      ? await api.getAllChatHistory(props.userId)
      : await api.getChatHistory(props.userId)
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
              thought: normalizeThoughtForStep(step.thought || ''),
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
            thought: normalizeThoughtForStep(step.thought || ''),
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
      const apiMsgs = d.messages.map(m => {
        const normalizedThinking = normalizeThinkingFromDb(m.thinking)
        return {
          ...m,
          thinking: normalizedThinking,
          // 🔧 修复：有推理步骤时自动展开，刷新后能立即看到推理过程
          thinkingOpen: (normalizedThinking?.length ?? 0) > 0,
          timestamp: m.timestamp || new Date().toISOString(),
        }
      })
      const lastStore = chatStore.messages[chatStore.messages.length - 1]
      const lastApi = apiMsgs[apiMsgs.length - 1]
      const storeHasNewer = chatStore.userId === props.userId && lastStore?.role === 'assistant' &&
        ((lastStore.content?.length || 0) > (lastApi?.content?.length || 0) || lastStore.streaming)
      if (storeHasNewer && !loadAll) {
        if (restoreFromStore()) return
      }
      // 本地草稿：刷新后若服务端仍为「生成中…」或缺少已展示的推理步骤，用浏览器草稿补齐
      let msgsToApply = apiMsgs
      const draft = loadChatDraft(props.userId)
      if (draft?.messages?.length && draft.userId === props.userId) {
        const maxAge = 24 * 60 * 60 * 1000
        if ((Date.now() - (draft.savedAt || 0)) < maxAge) {
          const lastD = draft.messages[draft.messages.length - 1]
          const lastA = apiMsgs[apiMsgs.length - 1]
          const apiPlaceholder = lastA?.role === 'assistant' && String(lastA.content || '').includes('生成中')
          const dThinking = lastD?.thinking?.length || 0
          const aThinking = lastA?.thinking?.length || 0
          const useDraft =
            draft.messages.length > apiMsgs.length ||
            lastD?.streaming === true ||
            (apiPlaceholder && dThinking > aThinking) ||
            (lastD?.role === 'assistant' && lastA?.role === 'assistant' &&
              (lastD.content || '').length > (lastA.content || '').length + 8 &&
              dThinking >= aThinking)
          if (useDraft) {
            msgsToApply = draft.messages.map((m) => {
              const normalizedThinking = normalizeThinkingFromDb(m.thinking)
              return {
                role: m.role,
                content: m.content || '',
                thinking: normalizedThinking,
                thinkingOpen: (normalizedThinking?.length ?? 0) > 0,
                timestamp: m.timestamp || new Date().toISOString(),
                streaming: false,
                duration_ms: m.duration_ms,
                isError: !!m.isError,
              }
            })
            console.log('[loadHistory] 已从本地草稿恢复（含分步推理内容）')
          }
        }
      }
      messages.value = msgsToApply
      if (d.session_id) {
        sessionId.value = d.session_id
        chatStore.sessionId = d.session_id  // 同步到 store，供其他视图使用
      }
      scrollToBottom()
      console.log(`[loadHistory] 加载了 ${d.messages.length} 条历史消息${loadAll ? '（所有会话）' : ''}`)
    } else {
      const draft = loadChatDraft(props.userId)
      if (draft?.messages?.length && draft.userId === props.userId &&
          (Date.now() - (draft.savedAt || 0)) < 24 * 60 * 60 * 1000) {
        const normalizeThinkingFromDb = (thinking) => {
          if (!Array.isArray(thinking)) return []
          return thinking.map(step => ({
            ...step,
            thought: normalizeThoughtForStep(step.thought || ''),
            tools: Array.isArray(step.tools) ? step.tools : [],
          }))
        }
        messages.value = draft.messages.map((m) => {
          const normalizedThinking = normalizeThinkingFromDb(m.thinking)
          return {
            role: m.role,
            content: m.content || '',
            thinking: normalizedThinking,
            thinkingOpen: (normalizedThinking?.length ?? 0) > 0,
            timestamp: m.timestamp || new Date().toISOString(),
            streaming: false,
            duration_ms: m.duration_ms,
            isError: !!m.isError,
          }
        })
        if (draft.sessionId) {
          sessionId.value = draft.sessionId
          chatStore.sessionId = draft.sessionId
        }
        scrollToBottom()
        console.log('[loadHistory] 服务端无历史，已从本地草稿恢复')
      }
    }
  } catch (e) { console.warn('加载对话历史失败', e) }
  finally { historyLoading.value = false }
}

const clearChat = async () => {
  try {
    await api.clearChatSession(props.userId)
  } catch (e) {
    console.warn('清空后端会话失败', e)
  }
  messages.value = []
  sessionId.value = getFixedSessionId()
  lastLoadedUserId = props.userId
  chatStore.clear()
  clearChatDraft(props.userId)
}

// 当传入 { display, api } 时，屏幕只展示 display，实际发给 AI 的是 api
const prefillDisplayRef = ref(null)
const prefillAndSend = async (textOrOptions) => {
  // 等待 loadHistory 完成，避免 session 竞争
  if (historyLoading.value) {
    let waited = 0
    while (historyLoading.value && waited < 3000) {
      await new Promise(r => setTimeout(r, 50))
      waited += 50
    }
  }
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
  nextTick(() => {
    send()
    // 发送后滚动到最新消息的顶部（而不是底部）
    setTimeout(() => scrollToLatestMessageTop(), 100)
  })
}
defineExpose({ prefillAndSend, historyLoading })

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
  persistLocalDraft(true)
  // 用户消息发送后，滚动到该消息顶部（而不是底部）
  scrollToLatestMessageTop()

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
    // DSML 跨 chunk 过滤缓冲区
    let dsmlPendingBuf = ''
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
    // AI 消息出现后，滚动到该消息顶部
    scrollToLatestMessageTop()

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let receivedFirstDelta = false
    let shouldStopStream = false
    let suppressPlanToChat = false
      const STREAM_READ_TIMEOUT_MS = 45000
    let streamEndedByTimeout = false

    /**
     * 按 stepNo 获取或创建步骤对象。
     * 后端每个事件携带 step 编号，前端直接按编号索引，无需 pending 机制。
     */
    const getOrCreateStep = (aiMsg, stepNo) => {
      let stepObj = aiMsg.thinking.find(s => s.__step === stepNo)
      if (!stepObj) {
        stepObj = { __step: stepNo, thought: '', tools: [] }
        aiMsg.thinking.push(stepObj)
        aiMsg.thinking.sort((a, b) => (a.__step || 0) - (b.__step || 0))
      }
      return stepObj
    }

    /**
     * handleEvent — 统一处理后端 hello_agents SSE 事件
     *
     * 后端 to_sse() 格式：
     *   event: <event_type>\n
     *   data: {"type":"<event_type>","agent_name":"...","timestamp":...,"data":{...}}\n\n
     *
     * 前端解析后 payload = 整个 data JSON，即：
     *   payload.type       → 事件类型字符串
     *   payload.data       → 实际载荷对象
     *
     * 事件类型对照：
     *   agent_start       → 忽略（仅日志）
     *   step_start        → 初始化新步骤占位
     *   llm_chunk         → 流式追加正文
     *   thinking          → 追加推理内容（DeepSeek reasoning_content）
     *   tool_call_start   → 添加 pending 工具条目
     *   tool_call_finish  → 填充工具结果
     *   step_finish       → 忽略（步骤已完整）
     *   agent_finish      → 设置最终答案 + thinking_steps
     *   error             → 显示错误
     */
    const handleEvent = (payload) => {
      const evType = payload.type
      // payload.data 是实际载荷；兼容极少数直接把字段放在顶层的旧格式
      const data = (payload.data && typeof payload.data === 'object') ? payload.data : payload

      // 始终从数组获取最新消息对象（splice 后引用会变）
      const aiMsg = messages.value[aiMsgIndex]
      if (!aiMsg) return

      // ── agent_start：忽略 ──────────────────────────────────
      if (evType === 'agent_start') {
        // 仅用于调试，不更新 UI
        return
      }

      // ── step_start：初始化步骤占位 ────────────────────────
      if (evType === 'step_start') {
        const stepNo = data.step ?? 1
        getOrCreateStep(aiMsg, stepNo)
        return
      }

      // ── llm_chunk：流式追加正文 ───────────────────────────
      if (evType === 'llm_chunk') {
        const raw = data.chunk ?? data.content ?? ''
        if (detectToolPlanText(raw)) {
          suppressPlanToChat = true
        }
        const { safe: chunk, pending } = filterChunkWithDsmlGuard(raw, dsmlPendingBuf)
        dsmlPendingBuf = pending
        if (chunk && !suppressPlanToChat) {
          // 第一个正文 chunk 到达时，自动折叠思考块
          if (!receivedFirstDelta && aiMsg.thinking.length > 0) {
            aiMsg.thinkingOpen = false
          }
          receivedFirstDelta = true
          aiMsg.content += sanitizeDisplayText(chunk, false)
        }
        syncStreamState()
        // 流式输出时不自动滚动，保持用户视图稳定
      }

      // ── thinking：追加推理内容（DeepSeek reasoning_content）─
      if (evType === 'thinking') {
        const chunk = data.chunk ?? data.content ?? ''
        if (!chunk || typeof chunk !== 'string') return
        // 工具计划/DSML 文本不进入推理展示，避免“step2 内容”污染对话可见区域
        if (detectToolPlanText(chunk)) return
        const stepNo = data.step ?? 1
        const normalized = normalizeThoughtForStep(chunk)
        const stepObj = getOrCreateStep(aiMsg, stepNo)
        // 后端按 delta.reasoning_content 细粒度推片：直接拼接，勿用 \n 连接（否则每字一行）
        stepObj.thought = (stepObj.thought || '') + (normalized || '')
        syncStreamState()
        return
      }

      // ── tool_call_start：添加 pending 工具条目 ────────────
      if (evType === 'tool_call_start') {
        const toolName = (data.tool_name ?? '').replace(/^[🔧\s]+/u, '').trim()
        const stepNo = data.step ?? 1
        const args = extractToolArgsFromEvent(data)
        if (toolName === 'get_question_detail' && !Object.keys(args).length) {
          console.warn('[tool_call_start] get_question_detail 未拿到参数', data)
        }
        if (!toolName || toolName === 'Thought' || toolName === 'Finish') return
        const stepObj = getOrCreateStep(aiMsg, stepNo)
        stepObj.tools.push({
          name: toolName,
          args: Object.keys(args).length ? args : {},
          result: null,
          observation: null,
          observationIsJson: false,
          _pending: true,
        })
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
        scrollToBottom()
        return
      }

      // ── tool_call_finish：填充工具结果 ────────────────────
      if (evType === 'tool_call_finish') {
        const toolName = (data.tool_name ?? '').replace(/^[🔧\s]+/u, '').trim()
        const stepNo = data.step ?? 1
        const result = data.result ?? ''
        const args = extractToolArgsFromEvent(data)
        if (toolName === 'get_question_detail' && !Object.keys(args).length) {
          console.warn('[tool_call_finish] get_question_detail 未拿到参数', data)
        }

        // Thought 工具：把推理写入步骤 thought 字段
        if (toolName === 'Thought') {
          let thought = String(result)
          for (const p of ['已记录推理过程:', '推理:']) {
            if (thought.startsWith(p)) { thought = thought.slice(p.length).trim(); break }
          }
          const stepObj = getOrCreateStep(aiMsg, stepNo)
          const normalized = normalizeThoughtForStep(thought)
          stepObj.thought = stepObj.thought
            ? `${stepObj.thought}\n${normalized}`
            : normalized
          messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
          streamingMsg.value = messages.value[aiMsgIndex]
          return
        }

        // Finish 工具：不展示在工具列表里，正文由 agent_finish 负责
        if (toolName === 'Finish') return

        // 普通工具：找到 pending 条目并填充结果
        const obs = String(result)
        const stepObj = getOrCreateStep(aiMsg, stepNo)
        let target = stepObj.tools.find(t => t.name === toolName && t.result == null)
        if (!target) {
          // 没有 start 事件（旧版），直接追加
          target = {
            name: toolName,
            args: Object.keys(args).length ? args : {},
            result: null, observation: null, observationIsJson: false,
          }
          stepObj.tools.push(target)
        }
        // 统一实时展示所有工具的结果（包括 get_question_detail）
        target.result = obs
        target.observation = obs
        target.observationIsJson = isObsJson(obs)
        target._pending = false
        if (Object.keys(args).length && !Object.keys(target.args ?? {}).length) {
          target.args = args
        } else if (toolName === 'get_question_detail' && !Object.keys(target.args ?? {}).length) {
          // 极端情况下后端事件丢了 args，尝试从结果里回填 question_id，避免“无入参”。
          const parsed = parseJsonLikeString(obs)
          const qid = parsed.ok && parsed.value && typeof parsed.value === 'object'
            ? (parsed.value.question_id || '')
            : ''
          if (qid) target.args = { question_id: qid }
        }
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
        // 工具调用结束后恢复正文输出（下一步真正回答可继续进入聊天框）
        suppressPlanToChat = false
        // 工具调用时不自动滚动，保持用户视图稳定
      }

      // ── step_finish：忽略（步骤已完整）─────────────────────
      if (evType === 'step_finish') {
        suppressPlanToChat = false
        return
      }

      // ── agent_finish：设置最终答案 + thinking_steps ────────
      if (evType === 'agent_finish') {
        // 清空 DSML 跨 chunk 缓冲区（丢弃未完整的 DSML 前缀）
        dsmlPendingBuf = ''
        const finalResult = sanitizeDisplayText(data.result ?? '')
        // 只在 finalResult 非空时才覆盖；若是通用兜底道歉且已有有效流式内容，则保留流式正文
        const isGenericApology = /抱歉，我无法回答这个问题/.test(finalResult)
        const hasUsefulStreamContent = (aiMsg.content || '').trim().length > 20
        if (isGenericApology) {
          console.warn('[chat] 命中通用兜底回复', {
            hasUsefulStreamContent,
            streamContentLength: (aiMsg.content || '').trim().length,
            finalResultPreview: finalResult.slice(0, 200),
          })
        }
        if (finalResult && !(isGenericApology && hasUsefulStreamContent)) {
          aiMsg.content = finalResult
        }
        aiMsg.duration_ms = data.duration_ms ?? (Date.now() - (aiMsg._startTs ?? Date.now()))

        // 优先使用后端汇总的 thinking_steps（比流式增量更完整）
        const finalThinking = Array.isArray(data.thinking) && data.thinking.length > 0
          ? data.thinking
          : (Array.isArray(data.thinking_steps) && data.thinking_steps.length > 0 ? data.thinking_steps : null)
        if (finalThinking) {
          const cleanName = (n) => typeof n === 'string' ? n.replace(/^[🔧\s]+/u, '').trim() : (n || '')
          aiMsg.thinking = finalThinking.map((step, idx) => ({
            ...step,
            __step: (step.__step && step.__step !== 'pending') ? step.__step : (idx + 1),
            // 与流式 THINKING 一致：落库/汇总的 thought 可能含 DSML，需清洗后再展示
            thought: normalizeThoughtForStep(step.thought || ''),
            tools: Array.isArray(step.tools)
              ? step.tools.map(t => ({
                  ...t,
                  name: cleanName(t.name),
                  result: t.result ?? t.observation ?? null,
                  observation: t.observation ?? t.result ?? null,
                  observationIsJson: isObsJson(t.result ?? t.observation ?? ''),
                }))
              : [],
          }))
        }
        // 流式结束后保留当前展开状态，不强制重新展开
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
        syncStreamState(true)
        shouldStopStream = true
        suppressPlanToChat = false
        return
      }

      // ── error：显示错误消息 ───────────────────────────────
      if (evType === 'error' || data.error) {
        const errMsg = data.error ?? '未知错误'
        const toolError = data.tool_error ? `\n\n**技术细节**: ${data.tool_error}` : ''
        aiMsg.content = `⚠️ **错误**\n\n${errMsg}${toolError}`
        aiMsg.streaming = false
        aiMsg.isError = true  // 标记为错误消息
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
        syncStreamState(true)
        console.error(`[错误事件] ${errMsg}`)
        shouldStopStream = true
        suppressPlanToChat = false
        return
      }
    }

    let eventCount = 0
    let lastUpdateTime = Date.now()
    
    try {
      while (true) {
        const readWithTimeout = Promise.race([
          reader.read(),
          new Promise((resolve) => {
            setTimeout(() => resolve({ done: true, value: undefined, _timeout: true }), STREAM_READ_TIMEOUT_MS)
          }),
        ])
        const { done, value, _timeout } = await readWithTimeout
        if (_timeout) {
          console.warn(`[SSE] 读取超时 ${STREAM_READ_TIMEOUT_MS}ms，执行前端收尾`)
          streamEndedByTimeout = true
          break
        }
        if (done) {
          console.log(`[SSE流完成] 共接收 ${eventCount} 个事件`)
          break
        }
        
        // 解码数据块
        const chunk = decoder.decode(value, { stream: true })
        buffer += chunk
        console.log(`[SSE接收] 块大小=${chunk.length}字节, 缓冲区=${buffer.length}字节`)
        
        // 兼容 LF/CRLF 的 SSE 分隔符
        const lines = buffer.split(/\r?\n\r?\n/)
        
        // 保留最后一个不完整的块在缓冲区
        buffer = lines.pop() || ''
        
        // 处理完整的事件块
        for (const eventBlock of lines) {
          if (!eventBlock.trim()) continue
          
          let eventType = ''
          const dataLines = []
          
          // 解析 SSE 格式: event: xxx\ndata: {...}
          for (const line of eventBlock.split(/\r?\n/)) {
            const trimmed = line.trim()
            if (trimmed.startsWith('event: ')) {
              eventType = trimmed.slice(7)
            } else if (trimmed.startsWith('data: ')) {
              dataLines.push(trimmed.slice(6))
            }
          }

          const dataLine = dataLines.join('\n')
          if (!dataLine) continue
          
          try {
            const payload = JSON.parse(dataLine)
            if (!payload.type && eventType) {
              payload.type = eventType
            }
            
            eventCount++
            
            // 处理事件
            handleEvent(payload)
            
            // 节流滚动：每 150ms 最多触发一次，避免每个 chunk 都重排
            const now = Date.now()
            if (now - lastUpdateTime > 150) {
              lastUpdateTime = now
              // 流式过程中不自动滚动，保持用户视图稳定
            }
          } catch (parseErr) {
            console.warn(`[SSE解析失败] 事件#${eventCount}:`, parseErr, 'data:', dataLine)
          }
        }
        if (shouldStopStream) {
          try { await reader.cancel('terminal_event_received') } catch (_) {}
          break
        }
      }
      // done 时可能剩余最后一个未被空行终止的事件块，主动再解析一次
      if (buffer.trim()) {
        let eventType = ''
        const dataLines = []
        for (const line of buffer.split(/\r?\n/)) {
          const trimmed = line.trim()
          if (trimmed.startsWith('event: ')) {
            eventType = trimmed.slice(7)
          } else if (trimmed.startsWith('data: ')) {
            dataLines.push(trimmed.slice(6))
          }
        }
        const dataLine = dataLines.join('\n')
        if (dataLine) {
          try {
            const payload = JSON.parse(dataLine)
            if (!payload.type && eventType) payload.type = eventType
            eventCount++
            handleEvent(payload)
          } catch (tailErr) {
            console.warn('[SSE尾包解析失败]:', tailErr, 'data:', dataLine)
          }
        }
      }
      if (streamEndedByTimeout) {
        ElMessage.warning('本次流式响应超时，已自动结束')
      } else {
        ElMessage.success('本次流式响应已正常结束')
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
        // 流式结束后保持思考块当前展开状态（流式过程中已自动折叠），不强制重新展开
        messages.value.splice(aiMsgIndex, 1, { ...finalMsg })
        console.log(`[SSE] 消息状态已更新为 completed，消息ID: ${finalMsg.id}`)
      }
      streamingMsg.value = null
      chatStore.finishStream(messages.value)
      persistLocalDraft(true)
      // 流式完成后滚动到消息顶部
      scrollToLatestMessageTop()
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
      const idx = messages.value.findIndex(m => m.streaming && m.role === 'assistant')
      const partialAssistant = idx >= 0 ? messages.value[idx] : null
      try {
        const ctrl = new AbortController()
        const timer = setTimeout(() => ctrl.abort(), 300000)
        const d = await api.chat({
          user_id: props.userId,
          message: text,
          session_id: sessionId.value,
        }, ctrl.signal)
        clearTimeout(timer)
        if (idx >= 0) {
          messages.value[idx] = {
            ...partialAssistant,
            content: d.reply || '⚠️ 无回复',
            streaming: false,
            thinking: d.thinking || partialAssistant.thinking || [],
            thinkingOpen: (d.thinking || partialAssistant.thinking || []).length > 0,
          }
        } else {
          messages.value.push({
            role: 'assistant',
            content: d.reply || '⚠️ 无回复',
            streaming: false,
            thinking: d.thinking || [],
            thinkingOpen: (d.thinking || []).length > 0,
          })
        }
        persistLocalDraft(true)
        // 降级接口完成后滚动到消息顶部
        scrollToLatestMessageTop()
      } catch (e2) {
        if (idx >= 0 && partialAssistant) {
          partialAssistant.streaming = false
          partialAssistant.content = (partialAssistant.content || '') +
            '\n\n⚠️ **连接失败**（已保留上方已生成的内容与推理步骤）\n\n请检查后端是否运行后重试。'
          messages.value.splice(idx, 1, { ...partialAssistant })
        } else {
          messages.value.push({ role: 'assistant', content: '⚠️ 连接失败，请检查后端是否运行', streaming: false, thinking: [], thinkingOpen: false })
        }
        persistLocalDraft(true)
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
    persistLocalDraft(true)
    abortCtrl = null
    // 最后滚动到消息顶部
    scrollToLatestMessageTop()
  }
}

watch([() => props.isActive, () => props.userId], ([active, uid], [prevActive, prevUid]) => {
  if (uid) sessionId.value = getFixedSessionId()
  // 页面激活时加载所有历史记录
  if (active && uid) {
    loadHistory(true)  // 默认加载所有会话的历史
  }
  // 🔧 页面失活时不再中断请求，让后端继续完成
  // 这样切换回来时可以看到完整的历史记录
}, { immediate: true })

onUnmounted(() => {
  onBeforeUnloadPersist()
  if (typeof window !== 'undefined') {
    window.removeEventListener('beforeunload', onBeforeUnloadPersist)
  }
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
  max-height: none; overflow-y: visible; padding: 8px 0;
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
  font-size: 11px; overflow-x: auto; max-height: none; overflow-y: visible;
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
  font-size: 12px; max-height: none; overflow: visible; white-space: pre-wrap; word-break: break-all;
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
.args-rich-json {
  width: 100%;
}
.args-kv-wrap {
  width: 100%;
  border: 1px solid #dbe3ee;
  border-radius: 6px;
  background: #f8fafc;
  padding: 8px;
}
.args-kv-nested {
  margin-top: 6px;
  background: #f1f5f9;
}
.args-kv-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px dashed #e2e8f0;
}
.args-kv-row:last-child { border-bottom: none; }
.args-kv-key {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
}
.args-kv-val {
  font-size: 12px;
  color: #334155;
  line-height: 1.55;
  word-break: break-word;
}
.args-kv-primitive {
  color: #334155;
}
.args-kv-md {
  border-left: 2px solid #cbd5e1;
  padding-left: 8px;
}
.args-kv-text {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-size: 12px;
  line-height: 1.55;
  font-family: 'Consolas', 'Fira Code', monospace;
  white-space: pre-wrap;
  word-break: break-word;
}
.args-kv-group-title {
  color: #475569;
  font-size: 11px;
  margin-bottom: 6px;
}
.args-kv-collapse {
  width: 100%;
}
.args-kv-summary {
  cursor: pointer;
  color: #475569;
  font-size: 11px;
  user-select: none;
}
.args-kv-summary:hover {
  color: #1e293b;
}
.args-kv-val :deep(.katex-display),
.args-kv-val .katex-display {
  overflow-x: auto;
  overflow-y: hidden;
  margin: 6px 0;
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
  transition: max-height 0.35s ease, opacity 0.25s;
  overflow: hidden;
}
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }
.slide-enter-to, .slide-leave-from { max-height: 9999px; opacity: 1; }

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

/* submit_answer 评估结果卡片（图2 格式） */
.submit-answer-eval-card {
  margin-top: 8px;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(248,250,252,0.95) 0%, rgba(241,245,249,0.95) 100%);
  border-radius: 10px;
  border: 1px solid var(--border, #e2e8f0);
}
.submit-answer-eval-card .eval-score-badge {
  display: inline-block;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  padding: 6px 14px;
  border-radius: 20px;
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 10px;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}
.submit-answer-eval-card .eval-feedback {
  color: #475569;
  font-size: 14px;
  line-height: 1.5;
  margin-bottom: 10px;
  white-space: pre-wrap;
}
.submit-answer-eval-card .eval-points {
  margin-bottom: 8px;
}
.submit-answer-eval-card .eval-point-label {
  font-weight: 600;
  font-size: 13px;
  color: #334155;
  margin-right: 4px;
}
.submit-answer-eval-card .eval-list {
  margin: 4px 0 0 18px;
  padding: 0;
  list-style: none;
}
.submit-answer-eval-card .eval-list li { margin: 2px 0; font-size: 13px; }
.submit-answer-eval-card .eval-standard-answer {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #e2e8f0;
}
.submit-answer-eval-card .eval-std-label {
  font-weight: 600;
  color: #475569;
  font-size: 13px;
  margin-bottom: 4px;
}
.submit-answer-eval-card .eval-std-body {
  font-size: 13px;
  line-height: 1.5;
  color: #334155;
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

/* 答对 / 遗漏 / 混淆点 / 错误：并列反馈块（统一标题行 + 圆点 + 列表） */
.md-content :deep(.fb-sec) {
  margin: 10px 0;
  padding: 10px 12px;
  background: rgba(248, 250, 252, 0.95);
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.md-content :deep(.fb-sec-head) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.md-content :deep(.fb-sec-mark) {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #94a3b8;
}
/* 答对、遗漏、并列：统一样式（相同圆点颜色） */
.md-content :deep(.fb-sec--correct .fb-sec-mark) { background: #64748b; }
.md-content :deep(.fb-sec--miss .fb-sec-mark) { background: #64748b; }
.md-content :deep(.fb-sec--confuse .fb-sec-mark) { background: #64748b; }
.md-content :deep(.fb-sec--error .fb-sec-mark) { background: #ef4444; }
.md-content :deep(.fb-sec-label) {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}
.md-content :deep(.fb-sec-list) {
  margin: 0;
  padding-left: 20px;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
}
.md-content :deep(.fb-sec-list li) { margin: 4px 0; }

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

/* ── submit_answer 评分卡片 ── */
.eval-card {
  background: #f8faff;
  border: 1px solid #e0e8ff;
  border-radius: 10px;
  padding: 14px 16px;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.eval-score-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.eval-score-label {
  font-size: 13px;
  color: #64748b;
  margin-right: 6px;
}
.eval-score-value {
  font-size: 28px;
  font-weight: 700;
  color: #4f46e5;
  line-height: 1;
}
.eval-score-unit {
  font-size: 14px;
  color: #94a3b8;
}
.eval-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.eval-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
.eval-section-body {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.6;
}
.eval-standard-answer {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-word;
}
.eval-list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.eval-list li {
  font-size: 13px;
  line-height: 1.5;
}
.eval-list-good li { color: #15803d; }
.eval-list-warn li { color: #b45309; }
.eval-list-bad  li { color: #b91c1c; }

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

/* 错误消息样式 */
.msg-content.error {
  background: linear-gradient(135deg, #fff5f5 0%, #ffe0e0 100%);
  border-left: 4px solid #dc2626;
  padding: 12px 14px;
  border-radius: 8px;
  color: #7f1d1d;
}

.msg-content.error :deep(strong) {
  color: #dc2626;
  font-weight: 700;
}

.msg-content.error :deep(code) {
  background: rgba(220, 38, 38, 0.1);
  color: #991b1b;
  padding: 2px 6px;
  border-radius: 3px;
}

</style>

