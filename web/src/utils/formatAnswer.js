/**
 * 将答案文本格式化为分条展示的 HTML
 * 支持：1. 2. 3. / 一、二、三、/ （1）（2）/ - 或 • 开头的列表
 */
export function formatAnswerToHtml(raw) {
  if (!raw || typeof raw !== 'string') return ''
  const text = raw.trim()
  if (!text) return ''

  // 在 数字. 数字、 一/二/三…、 （1）（2）前插入换行，便于分条
  const withBreaks = text
    .replace(/(?=\d+[.、)）])/g, '\n')
    .replace(/(?=[一二三四五六七八九十百]+[、.])/g, '\n')
    .replace(/(?=[（(]\d+[)）])/g, '\n')

  return withBreaks
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `<div class="answer-line">${escapeHtml(line)}</div>`)
    .join('')
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}
