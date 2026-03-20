<template>
  <div class="card">
    <div class="card-title">🕸️ GraphRAG 图谱</div>

    <div class="toolbar">
      <el-radio-group v-model="activeGraph" size="small">
        <el-radio-button label="bank">题库知识图</el-radio-button>
        <el-radio-button label="practice">做题记录图</el-radio-button>
      </el-radio-group>
      <el-button type="primary" size="small" :loading="loading" @click="load">刷新图谱</el-button>
      <el-switch v-model="showQuestionNodes" inline-prompt active-text="显示题目" inactive-text="隐藏题目" />
      <el-switch v-model="focusOnly" inline-prompt active-text="仅看关联" inactive-text="全部显示" />
    </div>
    <div v-if="graph.nodes.length" class="toolbar toolbar-second">
      <el-select
        v-model="selectedNodeId"
        filterable
        clearable
        placeholder="搜索节点并查看关系"
        style="width: 320px"
        @change="onSelectNode"
      >
        <el-option
          v-for="opt in nodeOptions"
          :key="opt.id"
          :label="opt.label"
          :value="opt.id"
        />
      </el-select>
      <div class="quick-nodes">
        <el-tag
          v-for="n in hotNodes"
          :key="n.id"
          size="small"
          effect="plain"
          class="chip"
          @click="onQuickNodeClick(n)"
        >
          {{ n.label }}
        </el-tag>
      </div>
    </div>

    <div v-if="loading" class="loading-wrap">图谱加载中...</div>
    <div v-else-if="!graph.nodes.length" class="empty-state">暂无可展示图谱数据</div>

    <template v-else>
      <div class="stats">
        <span>节点 {{ graph.nodes.length }}</span>
        <span>关系 {{ graph.edges.length }}</span>
        <span v-if="selectedNode">当前展开：{{ selectedNode.label }}</span>
      </div>
      <div class="legend-row">
        <span class="legend-item">
          <i class="legend-dot legend-dot-tag"></i> 知识点
        </span>
        <span class="legend-item">
          <i class="legend-dot legend-dot-question"></i> 题目
        </span>
        <span class="legend-item">
          <i class="legend-line legend-line-co"></i> 关联关系
        </span>
        <span class="legend-item">
          <i class="legend-line legend-line-qt"></i> 题目-知识点
        </span>
      </div>

      <div class="graph-wrap">
        <div ref="cyEl" class="cy-container" />
      </div>

      <div class="detail" v-if="selectedNode">
        <div class="detail-title">关联节点</div>
        <div class="chips">
          <el-tag
            v-for="item in relatedNodes"
            :key="item.id"
            size="small"
            effect="plain"
            @click="toggleNode(item)"
            class="chip"
          >
            {{ item.label }}
          </el-tag>
          <span v-if="!relatedNodes.length" class="empty-hint">该节点暂无可展开关系</span>
        </div>
        <div class="detail-subtitle">对应题目</div>
        <div class="question-list" v-if="relatedQuestions.length">
          <div
            v-for="q in relatedQuestions"
            :key="q.id"
            class="question-item"
            @click="openQuestionDetail(q)"
          >
            <div class="question-title">{{ q.label || q.id }}</div>
            <div class="question-meta">
              <span v-if="q.score != null">得分 {{ Number(q.score).toFixed(1) }}</span>
              <span v-if="q.studied_at">最近作答 {{ String(q.studied_at).slice(0, 16) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty-hint">当前节点暂未关联到题目（或题目节点被过滤）。</div>
      </div>
    </template>

    <el-dialog v-model="questionDialogVisible" title="题目标准答案" width="820px">
      <div v-if="questionDialogLoading" class="loading-wrap">加载题目详情中...</div>
      <template v-else-if="questionDialogData">
        <div class="qa-block">
          <div class="qa-label">题目</div>
          <div class="qa-content">{{ dialogQuestionText || '-' }}</div>
        </div>
        <div class="qa-block">
          <div class="qa-label">标准答案（题库原答案）</div>
          <div class="qa-content answer" v-html="questionDialogAnswerHtml || '暂无标准答案'"></div>
        </div>
      </template>
      <div v-else class="empty-hint">未获取到题目详情</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import cytoscape from 'cytoscape'
import { formatAnswerToHtml } from '../utils/formatAnswer.js'

const props = defineProps({
  userId: { type: String, default: 'Wangxr' },
  isActive: { type: Boolean, default: false },
})

const loading = ref(false)
const activeGraph = ref('bank')
const focusOnly = ref(true)
const showQuestionNodes = ref(true)
const selectedNode = ref(null)
const selectedNodeId = ref('')
const externalRelatedQuestions = ref([])
const questionDialogVisible = ref(false)
const questionDialogLoading = ref(false)
const questionDialogData = ref(null)
const questionDialogAnswerHtml = computed(() => {
  return formatAnswerToHtml(questionDialogData.value?.answer_text || '')
})

function normalizeTextValue(v) {
  if (v == null) return ''
  if (typeof v !== 'string') v = String(v)
  // 兼容后端返回时的转义换行：把字面量的 \n / \r\n 转成真实换行
  return v
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '  ')
    .replace(/\uFEFF/g, '') // 去掉可能存在的 BOM
}

function normalizeAnswerValue(v) {
  let t = normalizeTextValue(v)
  const trimmed = t.trim()
  if (!trimmed) return ''

  // 如果是类似 JSON 数组/对象的字符串，尝试解析后再渲染成文本
  if ((trimmed.startsWith('[') && trimmed.endsWith(']')) || (trimmed.startsWith('{') && trimmed.endsWith('}'))) {
    try {
      const parsed = JSON.parse(trimmed)
      if (Array.isArray(parsed)) return parsed.map((x) => normalizeTextValue(x)).filter(Boolean).join('\n\n')
      if (parsed && typeof parsed === 'object') {
        // 常见：{answer: "..."} / {answer_text:"..."}
        if (parsed.answer_text) return normalizeTextValue(parsed.answer_text)
        if (parsed.answer) return normalizeTextValue(parsed.answer)
        if (parsed.raw_answer) return normalizeTextValue(parsed.raw_answer)
      }
    } catch {
      // ignore parse errors
    }
  }

  return t
}

const dialogQuestionText = computed(() => {
  const d = questionDialogData.value
  return normalizeTextValue(d?.question_text || d?.question || '')
})

const dialogAnswerText = computed(() => {
  const d = questionDialogData.value
  const raw =
    d?.answer_text ??
    d?.answer ??
    d?.raw_answer ??
    d?.rawAnswer ??
    ''
  return normalizeAnswerValue(raw)
})
const data = ref({
  question_bank_graph: { nodes: [], edges: [] },
  practice_record_graph: { nodes: [], edges: [] },
})

const cyEl = ref(null)
let cy = null

const graph = computed(() => {
  return activeGraph.value === 'practice'
    ? (data.value.practice_record_graph || { nodes: [], edges: [] })
    : (data.value.question_bank_graph || { nodes: [], edges: [] })
})

const connectedNodeIds = computed(() => {
  if (!selectedNode.value) return new Set()
  const set = new Set([selectedNode.value.id])
  for (const e of (graph.value.edges || [])) {
    if (e.source === selectedNode.value.id) set.add(e.target)
    if (e.target === selectedNode.value.id) set.add(e.source)
  }
  return set
})

const nodeById = computed(() => {
  const m = {}
  ;(graph.value.nodes || []).forEach((n) => { m[n.id] = n })
  return m
})

const nodeOptions = computed(() => {
  return (graph.value.nodes || [])
    .map((n) => ({
      id: n.id,
      label: `${n.label || n.id} (${n.type || 'node'})`,
      weight: Number(n.weight || 0),
      type: n.type || 'node',
    }))
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === 'tag' ? -1 : 1
      return b.weight - a.weight
    })
})

const hotNodes = computed(() => {
  return (graph.value.nodes || [])
    .filter((n) => n.type === 'tag')
    .sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0))
    .slice(0, 10)
})

const relatedNodes = computed(() => {
  if (!selectedNode.value) return []
  return (graph.value.nodes || [])
    .filter((n) => n.id !== selectedNode.value.id && connectedNodeIds.value.has(n.id))
    .slice(0, 40)
})

const relatedQuestions = computed(() => {
  if (externalRelatedQuestions.value.length) return externalRelatedQuestions.value
  if (!selectedNode.value) return []
  return (graph.value.nodes || [])
    .filter((n) => n.type === 'question' && connectedNodeIds.value.has(n.id))
    .slice(0, 16)
})

const toggleNode = (node) => {
  if (selectedNode.value?.id === node.id) {
    selectedNode.value = null
    return
  }
  selectedNode.value = node
}

function focusNodeInCy(nodeId) {
  if (!cy || !nodeId) return
  const target = cy.getElementById(nodeId)
  if (!target || target.empty()) return
  cy.animate({
    fit: { eles: target.closedNeighborhood(), padding: 80 },
    duration: 260,
  })
}

function onSelectNode(nodeId) {
  if (!nodeId) {
    selectedNode.value = null
    return
  }
  const n = nodeById.value[nodeId]
  if (!n) return
  selectedNode.value = n
  focusNodeInCy(nodeId)
}

function onQuickNodeClick(node) {
  if (!node?.id) return
  selectedNodeId.value = node.id
  selectedNode.value = node
  focusNodeInCy(node.id)
}

async function loadRelatedQuestionsByTag(tagName) {
  if (!tagName) {
    externalRelatedQuestions.value = []
    return
  }
  try {
    // 基于当前图谱邻域做一个“相关度”打分：邻域 tag 权重大 -> 排序靠前
    const selectedId = selectedNode.value?.id
    const neighborTagWeights = {}
    if (selectedId) {
      const edges = graph.value.edges || []
      for (const e of edges) {
        const et = e.type || ''
        const isCooccur =
          et.includes('cooccur') // cooccur / cooccur_in_practice
        if (!isCooccur) continue
        if (e.source === selectedId && String(e.target).startsWith('tag:')) {
          neighborTagWeights[String(e.target).slice(4)] = Number(e.weight || 1)
        } else if (e.target === selectedId && String(e.source).startsWith('tag:')) {
          neighborTagWeights[String(e.source).slice(4)] = Number(e.weight || 1)
        }
      }
    }

    const d = await api.getQuestions({
      tag: tagName,
      page: 1,
      page_size: 12,
      user_id: props.userId,
      sort_by: 'updated_at',
      sort_order: 'desc',
    })

    function normalizeTopicTags(raw) {
      if (!raw) return []
      if (Array.isArray(raw)) return raw.map((x) => String(x).trim()).filter(Boolean)
      if (typeof raw === 'string') {
        try {
          const v = JSON.parse(raw)
          if (Array.isArray(v)) return v.map((x) => String(x).trim()).filter(Boolean)
        } catch {
          // ignore
        }
        return raw.split(',').map((x) => String(x).trim()).filter(Boolean)
      }
      return []
    }

    const rows = (d?.questions || []).map((q) => {
      const qTags = normalizeTopicTags(q.topic_tags)
      let relevance = 1
      for (const t of qTags) {
        if (neighborTagWeights[t] != null) relevance += neighborTagWeights[t]
      }
      return {
      id: `q:${q.q_id}`,
      label: q.question_text || q.q_id || '',
      type: 'question',
      score: q.latest_score ?? null,
      studied_at: q.last_studied_at ?? '',
      q_id: q.q_id,
        relevance,
      }
    })

    rows.sort((a, b) => Number(b.relevance || 0) - Number(a.relevance || 0))
    externalRelatedQuestions.value = rows.map(({ relevance, ...rest }) => rest)
  } catch (e) {
    console.warn('按标签加载对应题目失败', e)
    externalRelatedQuestions.value = []
  }
}

function resolveQuestionId(q) {
  if (!q) return ''
  if (q.q_id) return q.q_id
  const id = String(q.id || '')
  if (id.startsWith('q:')) return id.slice(2)
  return id
}

async function openQuestionDetail(q) {
  const qid = resolveQuestionId(q)
  if (!qid) {
    ElMessage.warning('题目 ID 缺失，无法查看标准答案')
    return
  }
  // 保持原有行为：点击题目时仍可定位图节点
  onQuickNodeClick(q)
  questionDialogVisible.value = true
  questionDialogLoading.value = true
  questionDialogData.value = null
  try {
    const d = await api.getQuestionDetail(qid)
    questionDialogData.value = d || null
  } catch (e) {
    ElMessage.error('加载题目详情失败')
    console.warn(e)
  } finally {
    questionDialogLoading.value = false
  }
}

function prepareLayoutEdges(nodes, edges) {
  const maxEdgesForLayout = 520
  const maxContainsTagEdgesPerQuestion = 4

  const nodeSet = new Set((nodes || []).map((n) => n.id))
  const filtered = (edges || []).filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target))

  const others = filtered.filter((e) => e.type !== 'contains_tag')
  const contains = filtered.filter((e) => e.type === 'contains_tag')

  // contains_tag: q -> tag，按每个题目最多保留若干条，避免边爆炸
  const containsByQuestion = {}
  contains.forEach((e) => {
    const qId = e.source?.startsWith('q:') ? e.source : (e.target?.startsWith('q:') ? e.target : e.source)
    if (!containsByQuestion[qId]) containsByQuestion[qId] = []
    containsByQuestion[qId].push(e)
  })
  const trimmedContains = []
  Object.keys(containsByQuestion).forEach((qid) => {
    trimmedContains.push(...containsByQuestion[qid].slice(0, maxContainsTagEdgesPerQuestion))
  })

  let out = [...others, ...trimmedContains]
  if (out.length > maxEdgesForLayout) {
    out = out
      .slice()
      .sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0))
      .slice(0, maxEdgesForLayout)
  }
  return out
}

function shouldShowNodeLabel(n) {
  const total = (graph.value.nodes || []).length || 0
  const zoom = cy?.zoom?.() || 1
  const connected = connectedNodeIds.value

  if (selectedNode.value) {
    if (n.id === selectedNode.value.id) return true
    if (connected.has(n.id)) return true
    // 只给少量高权重 tag 留标签
    return n.type === 'tag' && Number(n.weight || 0) >= (total > 150 ? 18 : 12) && zoom > 1.15
  }

  // 未选中：只显示高权重 tag（避免初始全是文字）
  if (n.type === 'tag') {
    const threshold = total > 150 ? 22 : 15
    return Number(n.weight || 0) >= threshold && zoom > 1.15
  }
  return false
}

function updateCyVisibilityAndStyles({ autoFit = false } = {}) {
  if (!cy) return
  const connected = connectedNodeIds.value
  const hasSelection = !!selectedNode.value
  const focus = !!focusOnly.value && hasSelection
  const allowContainsTagEdges = hasSelection // 只有在点选后才展示 q->tag

  // 节点：显示/隐藏 + 选中样式 + 标签
  cy.nodes().forEach((node) => {
    const id = node.id()
    const n = nodeById.value[id]
    if (!n) return

    const inConnected = connected.has(id)
    // 未选中时不展示题目节点：避免初始 q->tag 边淹没视觉
    if (!showQuestionNodes.value && n.type === 'question') {
      node.style('display', 'none')
      node.style('label', '')
      return
    }

    if (!hasSelection && n.type === 'question') {
      node.style('display', 'none')
      node.style('label', '')
      return
    }

    const shouldShow = !focus || inConnected
    node.style('display', shouldShow ? 'element' : 'none')

    // 类名高亮（避免反复改颜色导致闪烁）
    node.removeClass('is-selected')
    node.removeClass('is-neighbor')
    if (hasSelection) {
      if (id === selectedNode.value.id) node.addClass('is-selected')
      else if (inConnected) node.addClass('is-neighbor')
    }

    // 标签显示：只在选中/邻居或高权重 tag + 放大时显示
    const showLabel = shouldShowNodeLabel(n)
    node.style('label', showLabel ? (n.label || '') : '')
  })

  // 边：显示/隐藏 + 选中关联高亮
  cy.edges().forEach((edge) => {
    const s = edge.data('source')
    const t = edge.data('target')
    const et = edge.data('type') // contains_tag / cooccur / ...

    if (!allowContainsTagEdges && et === 'contains_tag') {
      edge.style('display', 'none')
      return
    }

    if (focus) {
      const show = connected.has(s) && connected.has(t)
      edge.style('display', show ? 'element' : 'none')
    } else {
      edge.style('display', 'element')
    }

    edge.removeClass('is-edge-active')
    if (hasSelection && (s === selectedNode.value.id || t === selectedNode.value.id)) {
      edge.addClass('is-edge-active')
    }
  })

  if (autoFit) {
    const visible = cy.elements(':visible')
    if (visible && visible.length > 0) {
      cy.fit(visible, 56)
    }
  }
}

function buildCy() {
  if (!cyEl.value) return
  if (cy) {
    cy.destroy()
    cy = null
  }

  const nodes = graph.value.nodes || []
  const edges = prepareLayoutEdges(nodes, graph.value.edges || [])

  // 去掉大多数孤立点，避免把画布撑得很散（保留少量高权重孤立 tag 作为上下文）
  const edgeNodeIds = new Set()
  edges.forEach((e) => {
    edgeNodeIds.add(e.source)
    edgeNodeIds.add(e.target)
  })
  const connectedNodes = nodes.filter((n) => edgeNodeIds.has(n.id))
  const isolatedTopTags = nodes
    .filter((n) => !edgeNodeIds.has(n.id) && n.type === 'tag')
    .sort((a, b) => Number(b.weight || 0) - Number(a.weight || 0))
    .slice(0, 10)
  const renderNodes = [...connectedNodes, ...isolatedTopTags]

  const elements = {
    nodes: renderNodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label || '',
        type: n.type || 'unknown',
        weight: Number(n.weight || 0),
        score: n.score,
        studied_at: n.studied_at,
      },
    })),
    edges: edges.map((e, idx) => ({
      data: {
        id: `${e.type || 'edge'}:${e.source}->${e.target}:${idx}`,
        source: e.source,
        target: e.target,
        weight: Number(e.weight || 1),
        type: e.type || 'edge',
      },
    })),
  }

  const totalNodes = renderNodes.length || 1
  cy = cytoscape({
    container: cyEl.value,
    elements,
    style: [
      {
        selector: 'core',
        style: {
          'selection-box-color': '#5b6ef5',
          'selection-box-opacity': 0.25,
        },
      },
      {
        selector: 'node',
        style: {
          'background-color': '#7b879a',
          'border-width': 2,
          'border-color': '#d8e0ec',
          'width': 'mapData(weight, 0, 60, 18, 40)',
          'height': 'mapData(weight, 0, 60, 18, 40)',
          'label': 'data(label)',
          'font-size': 'mapData(weight, 0, 60, 10, 13)',
          'text-opacity': 0.92,
          'color': '#334155',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.72,
          'text-background-padding': 2,
          'text-border-color': '#cbd5e1',
          'text-border-width': 0.6,
          'text-border-opacity': 0.8,
          'text-halign': 'center',
          'text-valign': 'bottom',
          'text-margin-y': 12,
          'text-wrap': 'wrap',
          'text-max-width': 140,
          'overlay-opacity': 0,
          'z-index': 10,
          'display': 'element',
        },
      },
      {
        selector: 'node[type = "tag"]',
        style: {
          'background-color': '#4f46e5',
          'background-gradient-stop-colors': '#6366f1 #4f46e5',
          'background-gradient-direction': 'to-bottom',
          'shape': 'ellipse',
          'border-color': '#c7d2fe',
        },
      },
      {
        selector: 'node[type = "question"]',
        style: {
          'background-color': '#0f766e',
          'background-gradient-stop-colors': '#14b8a6 #0f766e',
          'background-gradient-direction': 'to-bottom',
          'shape': 'round-rectangle',
          'border-width': 2,
          'border-color': '#99f6e4',
        },
      },
      {
        selector: 'node[weight >= 20]',
        style: {
          'border-width': 3,
          'shadow-blur': 12,
          'shadow-color': '#94a3b8',
          'shadow-opacity': 0.28,
          'shadow-offset-x': 0,
          'shadow-offset-y': 2,
        },
      },
      {
        selector: '.is-selected',
        style: {
          'border-width': 4,
          'border-color': '#111827',
          'background-color': '#0f172a',
          'color': '#0f172a',
          'text-background-color': '#fef08a',
          'text-background-opacity': 0.98,
          'text-border-color': '#f59e0b',
          'text-border-width': 1.2,
          'text-opacity': 1,
          'font-size': 14,
          'z-index': 999,
        },
      },
      {
        selector: '.is-neighbor',
        style: {
          'border-width': 2,
          'border-color': '#38bdf8',
          'background-blacken': -0.08,
          'text-opacity': 0.98,
        },
      },
      {
        selector: 'edge',
        style: {
          'curve-style': 'bezier',
          'target-arrow-shape': 'none',
          'line-color': '#94a3b8',
          'width': 'mapData(weight, 0, 60, 0.5, 2.6)',
          'opacity': 'mapData(weight, 0, 60, 0.06, 0.36)',
          'z-index': 1,
        },
      },
      {
        selector: 'edge[type = "contains_tag"]',
        style: {
          'line-style': 'dashed',
          'line-dash-pattern': [4, 4],
          'line-color': '#67e8f9',
          'opacity': 0.18,
        },
      },
      {
        selector: 'edge[type ^= "cooccur"]',
        style: {
          'line-color': '#818cf8',
          'opacity': 'mapData(weight, 0, 60, 0.08, 0.42)',
          'width': 'mapData(weight, 0, 60, 0.6, 2.8)',
        },
      },
      {
        selector: 'edge.is-edge-active',
        style: {
          'line-color': '#2563eb',
          'opacity': 0.98,
          'width': 'mapData(weight, 0, 60, 1.4, 3.6)',
        },
      },
    ],
    layout: {
      name: 'cose',
      animate: true,
      // Cose 参数：节点越多，排斥越大；理想边长越短越容易聚类
      nodeRepulsion: Math.max(7200, 420000 / Math.sqrt(totalNodes)),
      idealEdgeLength: 34,
      gravity: 0.42,
      componentSpacing: 40,
      numIter: 1000,
      padding: 36,
      randomize: false,
      fit: true,
    },
  })

  // 点击节点：更新选中状态
  cy.on('tap', 'node', (evt) => {
    const id = evt.target.id()
    const n = nodeById.value[id]
    if (!n) return
    toggleNode(n)
    selectedNodeId.value = selectedNode.value?.id || ''
    if (selectedNode.value) focusNodeInCy(selectedNode.value.id)
  })

  // 缩放时更新标签显示（减少初始文字噪声）
  let zoomTimer = null
  cy.on('zoom', () => {
    if (zoomTimer) clearTimeout(zoomTimer)
    zoomTimer = setTimeout(() => updateCyVisibilityAndStyles({ autoFit: false }), 80)
  })

  updateCyVisibilityAndStyles({ autoFit: true })
}

const load = async () => {
  loading.value = true
  try {
    data.value = await api.getGraphRag(props.userId)
    selectedNode.value = null
    selectedNodeId.value = ''
  } catch (e) {
    ElMessage.error('加载 GraphRAG 失败')
    console.warn(e)
  } finally {
    loading.value = false
    // 关键：必须等 loading 结束后，图容器渲染出来再初始化 Cytoscape
    await nextTick()
    if ((graph.value.nodes || []).length) {
      buildCy()
    }
  }
}

watch(() => props.isActive, (v) => { if (v) load() })

watch(activeGraph, async () => {
  selectedNode.value = null
  selectedNodeId.value = ''
  externalRelatedQuestions.value = []
  await nextTick()
  buildCy()
})

watch([focusOnly, showQuestionNodes], async () => {
  // 只更新样式，不重排
  await nextTick()
  if (cy) updateCyVisibilityAndStyles({ autoFit: !selectedNode.value })
})

watch(selectedNode, async (n) => {
  // 题库知识图只有 tag 节点，需额外从题库 API 反查对应题目
  if (!n || n.type !== 'tag') {
    externalRelatedQuestions.value = []
  } else {
    await loadRelatedQuestionsByTag(n.label || '')
  }
  await nextTick()
  if (cy) updateCyVisibilityAndStyles({ autoFit: !selectedNode.value })
})

onBeforeUnmount(() => {
  if (cy) cy.destroy()
  cy = null
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 10px 0 12px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
}
.toolbar-second {
  margin-top: 0;
  flex-wrap: wrap;
}
.quick-nodes {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.stats {
  display: flex;
  gap: 16px;
  color: #475569;
  font-size: 12px;
  margin-bottom: 10px;
}
.legend-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 10px;
  color: #64748b;
  font-size: 12px;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  display: inline-block;
}
.legend-dot-tag { background: #4f46e5; }
.legend-dot-question { background: #0f766e; }
.legend-line {
  width: 18px;
  height: 0;
  border-top: 2px solid #94a3b8;
  display: inline-block;
}
.legend-line-co { border-top-style: solid; }
.legend-line-qt { border-top-style: dashed; border-top-color: #06b6d4; }
.card-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}
.graph-wrap {
  border: 1px solid #dbe7f5;
  border-radius: 14px;
  overflow: hidden;
  background:
    radial-gradient(circle at 20% 20%, #f8fbff, #edf3ff 45%, #e7eefb 100%),
    linear-gradient(transparent 95%, rgba(148, 163, 184, 0.08) 95%),
    linear-gradient(90deg, transparent 95%, rgba(148, 163, 184, 0.08) 95%);
  background-size: auto, 24px 24px, 24px 24px;
  box-shadow: inset 0 0 0 1px #edf2fb, 0 6px 20px rgba(15, 23, 42, 0.06);
}

.cy-container {
  width: 100%;
  height: 680px;
}
.detail {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  box-shadow: 0 2px 10px rgba(30, 41, 59, 0.05);
}
.detail-title {
  font-size: 13px;
  color: #334155;
  margin-bottom: 8px;
  font-weight: 600;
}
.detail-subtitle {
  margin-top: 10px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #334155;
  font-weight: 600;
}
.chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  cursor: pointer;
  font-size: 13px;
}
.question-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}
.question-item {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  background: #fff;
  transition: all .15s ease;
}
.question-item:hover {
  border-color: #93c5fd;
  box-shadow: 0 2px 10px rgba(37, 99, 235, 0.12);
}
.question-title {
  font-size: 14px;
  color: #1e293b;
  line-height: 1.5;
}
.question-meta {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: #64748b;
}
.loading-wrap,
.empty-state {
  padding: 34px 0;
  text-align: center;
  color: var(--text-sub);
}
.empty-hint {
  color: #64748b;
  font-size: 12px;
}
.qa-block {
  margin-bottom: 14px;
}
.qa-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}
.qa-content {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
  padding: 10px 12px;
  color: #1e293b;
  line-height: 1.6;
  white-space: pre-wrap;
  max-height: 260px;
  overflow: auto;
}
.qa-content.answer {
  background: #f8fbff;
  max-height: 420px;
  white-space: normal;
  padding: 12px 16px 18px;
  scrollbar-gutter: stable;
}

.qa-content.answer :deep(p) {
  margin: 0 0 10px;
}

.qa-content.answer :deep(p:last-child) {
  margin-bottom: 0;
}

.qa-content.answer :deep(ul),
.qa-content.answer :deep(ol) {
  margin: 8px 0 10px;
  padding-left: 1.4em;
}

.qa-content.answer :deep(li) {
  margin-bottom: 6px;
}

.qa-content.answer :deep(h1),
.qa-content.answer :deep(h2),
.qa-content.answer :deep(h3),
.qa-content.answer :deep(h4),
.qa-content.answer :deep(h5),
.qa-content.answer :deep(h6) {
  margin: 6px 0 10px;
  line-height: 1.4;
}

.qa-content.answer :deep(.katex-display) {
  margin: 8px 0;
  overflow-x: auto;
  overflow-y: hidden;
}
</style>
