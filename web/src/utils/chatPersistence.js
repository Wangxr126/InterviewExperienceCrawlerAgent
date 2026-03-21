/**
 * 练习对话本地草稿：刷新/崩溃后恢复消息与推理步骤（与 SQLite 互补）。
 * 按 userId 单槽位，避免 session_id 前后端不一致导致读不到草稿。
 */
const PREFIX = 'wxr_practice_chat_v1'

export function chatDraftStorageKey(userId) {
  return `${PREFIX}:${userId || 'anon'}`
}

function slimMessage(m) {
  if (!m || typeof m !== 'object') return m
  return {
    role: m.role,
    content: m.content,
    timestamp: m.timestamp,
    streaming: !!m.streaming,
    thinking: Array.isArray(m.thinking) ? m.thinking : [],
    thinkingOpen: !!m.thinkingOpen,
    duration_ms: m.duration_ms,
    isError: !!m.isError,
  }
}

export function saveChatDraft(userId, sessionId, messages) {
  try {
    const list = Array.isArray(messages) ? messages : []
    const payload = {
      userId: userId || '',
      sessionId: sessionId || '',
      savedAt: Date.now(),
      messages: list.map(slimMessage),
    }
    localStorage.setItem(chatDraftStorageKey(userId), JSON.stringify(payload))
  } catch (e) {
    console.warn('[chatPersistence] 保存失败', e)
  }
}

export function loadChatDraft(userId) {
  try {
    const raw = localStorage.getItem(chatDraftStorageKey(userId))
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function clearChatDraft(userId) {
  try {
    localStorage.removeItem(chatDraftStorageKey(userId))
  } catch (e) {
    console.warn('[chatPersistence] 清除失败', e)
  }
}
