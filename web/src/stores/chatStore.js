/**
 * 聊天状态持久化 Store
 * 解决：切换页面再返回时，正在流式输出的内容丢失
 * 策略：流式输出时同步到 store，返回时优先从 store 恢复
 */
import { defineStore } from 'pinia'

export const useChatStore = defineStore('chat', {
  state: () => ({
    userId: '',
    sessionId: '',
    messages: [],
    isStreaming: false,
    lastUpdateTs: 0,
  }),
  actions: {
    /** 开始流式输出时调用 */
    startStream(userId, sessionId, messagesSnapshot) {
      this.userId = userId
      this.sessionId = sessionId
      this.messages = JSON.parse(JSON.stringify(messagesSnapshot))
      this.isStreaming = true
      this.lastUpdateTs = Date.now()
    },
    /** 流式过程中同步（节流，避免过于频繁） */
    syncMessages(messagesSnapshot) {
      if (!this.isStreaming) return
      this.messages = JSON.parse(JSON.stringify(messagesSnapshot))
      this.lastUpdateTs = Date.now()
    },
    /** 流式结束或完成时调用 */
    finishStream(finalMessages) {
      this.messages = JSON.parse(JSON.stringify(finalMessages || this.messages))
      this.isStreaming = false
      this.lastUpdateTs = Date.now()
    },
    /** 清空（用户点击清空时） */
    clear() {
      this.messages = []
      this.sessionId = `sess_${Date.now()}`
      this.isStreaming = false
    },
    /** 是否有当前用户的流式内容可恢复 */
    hasRestorableStreaming(userId) {
      return this.userId === userId && this.isStreaming && this.messages.length > 0
    },
    /** 是否有可恢复的本地内容（流式中或刚完成未刷新） */
    hasRestorableContent(userId) {
      return this.userId === userId && this.messages.length > 0 && this.lastUpdateTs > 0
    },
  },
})
