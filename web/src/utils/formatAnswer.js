/**
 * 将答案文本格式化为 HTML，支持 Markdown 渲染（加粗、换行、列表等）
 * 豆包 Stage 2 返回的 answer_text 含 **加粗**、1.2.3. 分条等格式，需保留并正确展示
 */
import { marked } from 'marked'

export function formatAnswerToHtml(raw) {
  if (!raw || typeof raw !== 'string') return ''
  const text = raw.trim()
  if (!text) return ''

  try {
    // 使用 marked 渲染 Markdown，保留 **加粗**、换行、列表等格式
    return marked(text)
  } catch (e) {
    console.warn('Markdown 渲染失败，回退为纯文本:', e)
    return escapeHtml(text).replace(/\n/g, '<br>')
  }
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}
