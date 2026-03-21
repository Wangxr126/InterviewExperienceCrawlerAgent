/**
 * 结构化内容渲染器
 * 解析后端发送的结构化题目数据，提取并美化显示
 */

/**
 * 解析题目结构
 * 从 Markdown 内容中提取题目、要求、难度、标签等信息
 */
export function parseQuestionStructure(content) {
  const result = {
    title: '',
    description: '',
    requirements: [],
    difficulty: '',
    tags: [],
    tips: '',
    examples: [],
    rawContent: content
  }

  // 提取标题（第一行的 ✨ 新题 或类似）
  const titleMatch = content.match(/^.*?✨\s*新题\s*\n(.*?)\n/m)
  if (titleMatch) {
    result.title = titleMatch[1].trim()
  }

  // 提取要求部分
  const requirementsMatch = content.match(/要求：\n([\s\S]*?)(?=\n💡|$)/m)
  if (requirementsMatch) {
    const reqText = requirementsMatch[1]
    result.requirements = reqText
      .split('\n')
      .filter(line => line.match(/^\d+\./))
      .map(line => line.replace(/^\d+\.\s*/, '').trim())
  }

  // 提取难度和标签
  const metaMatch = content.match(/💡\s*难度：(\w+)\s*\|\s*🏷️\s*标签：([^\n]+)/m)
  if (metaMatch) {
    result.difficulty = metaMatch[1].trim()
    result.tags = metaMatch[2]
      .split('|')
      .map(tag => tag.trim())
      .filter(tag => tag)
  }

  // 提取提示部分
  const tipsMatch = content.match(/💡\s*([^\n]+)/m)
  if (tipsMatch) {
    result.tips = tipsMatch[1].trim()
  }

  return result
}

/**
 * 渲染结构化题目卡片
 */
export function renderQuestionCard(parsed) {
  if (!parsed.title) {
    return null
  }

  const difficultyColor = {
    'easy': '#52c41a',
    'medium': '#faad14',
    'hard': '#f5222d',
    '简单': '#52c41a',
    '中等': '#faad14',
    '困难': '#f5222d'
  }

  const color = difficultyColor[parsed.difficulty] || '#1890ff'

  return `
    <div class="question-card">
      <div class="question-header">
        <h3 class="question-title">✨ ${parsed.title}</h3>
        <div class="question-meta">
          <span class="difficulty" style="background-color: ${color}">
            ${parsed.difficulty}
          </span>
          ${parsed.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
        </div>
      </div>
      
      ${parsed.requirements.length > 0 ? `
        <div class="question-requirements">
          <h4>要求：</h4>
          <ol>
            ${parsed.requirements.map(req => `<li>${req}</li>`).join('')}
          </ol>
        </div>
      ` : ''}
      
      ${parsed.tips ? `
        <div class="question-tips">
          <span class="tips-icon">💡</span>
          <span>${parsed.tips}</span>
        </div>
      ` : ''}
    </div>
  `
}

/**
 * 检测内容是否是结构化题目
 */
export function isStructuredQuestion(content) {
  return content.includes('✨ 新题') || 
         content.includes('要求：') ||
         content.includes('💡 难度：')
}

/** 给 <ul> 增加 fb-sec-list，保留已有 class */
function addFbSecListClass(ulHtml) {
  return ulHtml.replace(/^<ul(\s[^>]*)?>/i, (full, attrs = '') => {
    const a = attrs || ''
    const m = a.match(/\sclass\s*=\s*(["'])([^"']*)\1/i)
    if (m) {
      const q = m[1]
      const c = m[2]
      if (/\bfb-sec-list\b/.test(c)) return full
      return full.replace(m[0], ` class=${q}fb-sec-list ${c}${q}`)
    }
    if (!a.trim()) return '<ul class="fb-sec-list">'
    return `<ul class="fb-sec-list"${a}>`
  })
}

/**
 * 将「答对 / 遗漏 / 混淆点 / 错误」规范为并列区块：统一标题行 + 同色点标记 + 列表体
 * （与模型是否使用 ✓ ✗ ⚠ 无关，解析后以同一套 DOM/CSS 展示）
 */
function normalizeFeedbackHtml(html) {
  if (!html || typeof html !== 'string') return html
  let out = html

  const section = (kind, label, ulInner) =>
    `<div class="fb-sec fb-sec--${kind}"><div class="fb-sec-head"><span class="fb-sec-mark" aria-hidden="true"></span><span class="fb-sec-label">${label}</span></div>${ulInner}</div>`

  // 答对：单段或 段 + 列表
  out = out.replace(
    /<p>(?:<span class="icon-correct">✓<\/span>\s*)?答对[：:]\s*([\s\S]*?)<\/p>(?:\s*(<ul[\s\S]*?<\/ul>))?/gi,
    (_, body, ul) => {
      const b = (body || '').trim()
      if (ul) return section('correct', '答对', addFbSecListClass(ul))
      const li = b ? `<li>${b}</li>` : '<li>—</li>'
      return section('correct', '答对', `<ul class="fb-sec-list">${li}</ul>`)
    }
  )

  const blockWithUl = (kind, label, iconRe) => {
    const pat = new RegExp(
      `<p>(?:${iconRe})?${label}[：:]\\s*([\\s\\S]*?)<\\/p>\\s*(<ul[\\s\\S]*?<\\/ul>)`,
      'gi'
    )
    out = out.replace(pat, (_, inlineBody, ul) => {
      let inner = addFbSecListClass(ul)
      const rest = (inlineBody || '').trim()
      if (rest) {
        inner = inner.replace(
          /^<ul(\s[^>]*)?>/i,
          (open) =>
            `${open}<li>${rest}</li>`
        )
      }
      return section(kind, label, inner)
    })
  }

  // 遗漏 / 错误：段 + 列表
  blockWithUl('miss', '遗漏', '(?:<span class="icon-missed">✗<\\/span>\\s*)?')
  blockWithUl('error', '错误', '(?:<span class="icon-error">✗<\\/span>\\s*)?')
  // 混淆点：⚠ 可能在段首，也可能无符号
  blockWithUl(
    'confuse',
    '混淆点',
    '(?:<span class="[^"]*">\\s*<\\/span>\\s*)*(?:\\u26A0\\uFE0F?\\s*)?'
  )

  // 仅段落、无列表：收进单条 li
  const singlePara = (kind, label, iconRe) => {
    const pat = new RegExp(`<p>(?:${iconRe})?${label}[：:]\\s*([\\s\\S]*?)<\\/p>`, 'gi')
    out = out.replace(pat, (_, body) => {
      const b = (body || '').trim()
      if (!b) return section(kind, label, '<ul class="fb-sec-list"><li>—</li></ul>')
      return section(kind, label, `<ul class="fb-sec-list"><li>${b}</li></ul>`)
    })
  }

  singlePara('miss', '遗漏', '(?:<span class="icon-missed">✗<\\/span>\\s*)?')
  singlePara('error', '错误', '(?:<span class="icon-error">✗<\\/span>\\s*)?')
  singlePara(
    'confuse',
    '混淆点',
    '(?:<span class="[^"]*">[\\s\\S]*?<\\/span>\\s*)*(?:\\u26A0\\uFE0F?\\s*)?'
  )

  return out
}

/** 评分反馈后处理：分数徽章 + 答对/遗漏/错误前缀标记 + 并列区块统一结构 */
function applyFeedbackStyles(html) {
  if (!html || typeof html !== 'string') return html
  let out = html
  // 分数徽章：📝 评分：2/5 或 2.5/5 突出显示（避免重复包裹）
  out = out.replace(/(📝\s*评分[：:]\s*[\d.]+\/\d+)/g, (match, _g1, offset, fullStr) => {
    const before = fullStr.slice(0, offset)
    const lastOpen = before.lastIndexOf('<span class="score-badge">')
    const lastClose = before.lastIndexOf('</span>')
    if (lastOpen > lastClose) return match
    return `<span class="score-badge">${match}</span>`
  })
  // 答对：绿色 ✓（兼容列表项内或段落内）
  out = out.replace(/✓\s*答对[：:]/g, '<span class="icon-correct">✓</span> 答对：')
  // 遗漏：橙色 ✗
  out = out.replace(/✗\s*遗漏[：:]/g, '<span class="icon-missed">✗</span> 遗漏：')
  // 错误：红色 ✗
  out = out.replace(/✗\s*错误[：:]/g, '<span class="icon-error">✗</span> 错误：')
  return normalizeFeedbackHtml(out)
}

/** 对已渲染的反馈 HTML 做与聊天区相同的后处理（供弹窗等复用） */
export function postprocessFeedbackHtml(html) {
  return applyFeedbackStyles(html)
}

/**
 * 增强的 Markdown 渲染（完整版 - 支持 Markdown 和 KaTeX）
 */
export function renderEnhancedContent(content, marked) {
  if (!content || typeof content !== 'string') return ''
  
  let html = ''
  
  // 如果是结构化题目，先渲染题目卡片
  if (isStructuredQuestion(content)) {
    const parsed = parseQuestionStructure(content)
    const cardHtml = renderQuestionCard(parsed)
    if (cardHtml) {
      html = cardHtml
    }
  }
  
  // 使用 marked 渲染 Markdown
  if (marked && typeof marked === 'function') {
    try {
      html += marked(content)
    } catch (e) {
      console.warn('Markdown 渲染失败:', e)
      html += '<pre>' + escapeHtml(content) + '</pre>'
    }
  } else if (marked && marked.parse) {
    try {
      html += marked.parse(content)
    } catch (e) {
      console.warn('Markdown 渲染失败:', e)
      html += '<pre>' + escapeHtml(content) + '</pre>'
    }
  } else {
    // 如果没有 marked，使用简单的 HTML 转义
    html += '<pre>' + escapeHtml(content) + '</pre>'
  }
  
  return applyFeedbackStyles(html)
}

/**
 * HTML 转义辅助函数
 */
function escapeHtml(text) {
  if (!text || typeof text !== 'string') return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * CSS 样式
 */
export const questionCardStyles = `
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
  border-top: 1px solid var(--border);
}
`
