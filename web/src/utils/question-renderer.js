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

/**
 * 增强的 Markdown 渲染
 * 如果是结构化题目，先提取结构再渲染
 * 
 * 注意：marked v17+ 的 parse() 是异步的，这里使用同步的 parseInline()
 * 或者使用 marked() 函数（同步版本）
 */
export function renderEnhancedContent(content, marked) {
  // 使用 marked() 函数而不是 marked.parse()，因为后者在 v17+ 是异步的
  const renderSync = (text) => {
    try {
      // marked() 函数是同步的，marked.parse() 是异步的
      return typeof marked === 'function' ? marked(text) : marked.parse(text)
    } catch (e) {
      console.error('Markdown 渲染失败:', e)
      return text
    }
  }
  
  if (isStructuredQuestion(content)) {
    const parsed = parseQuestionStructure(content)
    const cardHtml = renderQuestionCard(parsed)
    
    if (cardHtml) {
      // 渲染卡片 + 原始 Markdown
      const mdHtml = renderSync(content)
      return cardHtml + '<div class="raw-content">' + mdHtml + '</div>'
    }
  }
  
  // 普通内容，直接用 Markdown 渲染
  return renderSync(content)
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
