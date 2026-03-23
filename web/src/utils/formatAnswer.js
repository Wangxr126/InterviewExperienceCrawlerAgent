/**
 * 将答案文本格式化为 HTML，支持 Markdown 渲染（加粗、换行、列表等）
 * 豆包 Stage 2 返回的 answer_text 含 **加粗**、1.2.3. 分条等格式，需保留并正确展示
 */
import { marked } from 'marked'
import markedKatex from 'marked-katex-extension'

let markdownConfigured = false

function ensureMarkdownConfig() {
  if (markdownConfigured) return
  marked.use(markedKatex({ throwOnError: false, nonStandard: true }))
  marked.setOptions({ gfm: true, breaks: true })
  markdownConfigured = true
}

export function formatAnswerToHtml(raw) {
  if (!raw || typeof raw !== 'string') return ''
  const text = normalizeAnswerText(raw)
  if (!text) return ''

  try {
    // 使用 marked 渲染 Markdown，保留 **加粗**、换行、列表和数学公式等格式
    ensureMarkdownConfig()
    return marked(text)
  } catch (e) {
    console.warn('Markdown 渲染失败，回退为纯文本:', e)
    return escapeHtml(text).replace(/\n/g, '<br>')
  }
}

/**
 * 兼容各种后端入库/序列化造成的“转义格式”差异：
 * - 字面量换行：`\\n` / `\\r\\n` -> 真实换行
 * - 字面量制表：`\\t` -> 空格
 * - JSON 包装字符串/对象：尝试解包拿到 answer_text 字段
 */
function normalizeAnswerText(raw) {
  let s = raw
  if (typeof s !== 'string') s = String(s)
  s = s.replace(/\uFEFF/g, '') // 去掉可能存在的 BOM

  // 如果是 JSON 字符串包装（例如 "\"xxx\\nxxx\""），先尝试解包
  const trimmed = s.trim()
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    try {
      // 只在看起来像被 JSON quote 包起来时尝试解析
      const parsed = JSON.parse(trimmed.replace(/^'/, '"').replace(/'$/, '"'))
      if (typeof parsed === 'string') s = parsed
    } catch {
      // ignore
    }
  }

  // 如果是 JSON 对象/数组包装，尝试提取常见答案字段
  const t2 = s.trim()
  if ((t2.startsWith('{') && t2.endsWith('}')) || (t2.startsWith('[') && t2.endsWith(']'))) {
    try {
      const parsed = JSON.parse(t2)
      if (parsed && typeof parsed === 'object') {
        if (typeof parsed.answer_text === 'string') s = parsed.answer_text
        else if (typeof parsed.reference_answer === 'string') s = parsed.reference_answer
        else if (typeof parsed.answer === 'string') s = parsed.answer
        else if (typeof parsed.raw_answer === 'string') s = parsed.raw_answer
      } else if (typeof parsed === 'string') {
        s = parsed
      }
    } catch {
      // ignore
    }
  }

  // 把字面量转义还原为真实字符
  // 注意：这里只影响包含反斜杠的序列；如果已经是真实换行，则不会匹配到这些字面转义
  s = s
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '  ')

  // 把内联列表（全在一行的 "1. xxx；2. xxx"）展开为 Markdown 列表
  // 仅当文本中没有真实换行时才做此处理，避免破坏已有多行格式
  s = expandInlineList(s)

  // 兼容 LaTeX 的 \( ... \) / \[ ... \] 分隔符（部分模型常用），统一转换为 $...$ / $$...$$
  s = normalizeMathDelimiters(s)

  // 规整一下极端情况下的“全是空白”
  s = s.trim()
  return s
}

/**
 * 把「全在一行的数字/中文编号列表」展开为真正的 Markdown 有序列表。
 * 例如："步骤如下：1. 打开页面；2. 点击按钮；3. 提交。" 
 * →  步骤如下：\n1. 打开页面\n2. 点击按钮\n3. 提交。
 *
 * 触发条件：文本中没有真实换行，且含有 "1." 或 "（1）" 或 "一、" 等编号模式，
 * 且编号之间用 "；"、";"、" 或空格隔开。
 */
function expandInlineList(text) {
  if (!text) return text
  // 已有换行的文本不处理
  if (text.includes('\n')) return text

  // 模式1：阿拉伯数字列表 "1. xxx；2. xxx" 或 "1) xxx; 2) xxx"
  // 用非 /g 正则检测，避免 lastIndex 污染
  if (/[；;]\s*\d+[.)、]/.test(text) || /^\d+[.)、]/.test(text)) {
    let result = text
      // 把「；2.」「; 2.」等替换为换行+编号
      .replace(/[；;]\s*(\d+)[.)、]\s*/g, '\n$1. ')
      // 处理开头就是编号的情况（如「1. xxx」直接开头）
      .replace(/^(\d+)[.)、]\s*/, '$1. ')
    if (result.includes('\n')) return result
  }

  // 模式2：中文括号编号 "（1）xxx（2）xxx"
  if (/（\d+）/.test(text)) {
    return text.replace(/（(\d+)）\s*/g, (_, n) => (n === '1' ? `${n}. ` : `\n${n}. `))
  }

  // 模式3：中文序号 "一、xxx二、xxx"
  const chineseNums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
  const chinesePattern = new RegExp(`([${chineseNums.join('')}]+)[、:]`, 'g')
  if (chinesePattern.test(text)) {
    let idx = 0
    return text.replace(new RegExp(`([${chineseNums.join('')}]+)[、:]\\s*`, 'g'), (_, cn) => {
      idx++
      return (idx === 1 ? '' : '\n') + `**${cn}、** `
    })
  }

  return text
}

function normalizeMathDelimiters(text) {
  if (!text) return text
  return text
    // block: \[ ... \] -> $$ ... $$
    .replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (_, expr) => `$$\n${expr}\n$$`)
    // inline: \( ... \) -> $ ... $
    .replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (_, expr) => `$${expr}$`)
}

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}
