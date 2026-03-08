# Architect Agent vs Extractor - 详细对比

## 🎯 核心区别

### Extractor（题目提取器）

**文件位置：** `backend/services/crawler/question_extractor.py`

**性质：** 服务层工具函数（不是Agent）

**职责：** 从面经原文中提取结构化题目

**输入：** 一篇面经原文（可能包含10~30道面试题混在叙述文字中）

**输出：** 结构化的题目列表
```json
[
  {
    "question_text": "请介绍Redis的应用场景",
    "answer_text": "RDB、AOF",
    "difficulty": "medium",
    "question_type": "缓存题",
    "topic_tags": ["Redis", "缓存"],
    "company": "字节跳动",
    "position": "后端开发"
  }
]
```

**使用场景：** 爬虫抓取面经后，立即提取题目

**调用时机：** 
- 牛客网爬虫抓取到帖子后
- 小红书爬虫抓取到笔记后
- 需要从原文中提取题目时

**特点：**
- ✅ 简单直接：一次LLM调用，直接提取题目
- ✅ 快速：专注于题目提取，不做其他处理
- ✅ 无状态：纯函数，输入原文，输出题目列表

---

### Architect Agent（知识架构师）

**文件位置：** `backend/agents/architect_agent.py`

**性质：** 独立Agent（使用hello-agents框架）

**职责：** 元信息提取 → 结构化解析 → 语义查重 → 双写入库

**输入：** 已提取的题目列表（来自Extractor）

**输出：** 
- 知识图谱（Neo4j）
- 结构化数据（SQLite）
- 去重后的题目

**使用场景：** 题目提取后，进行知识管理

**调用时机：**
- Extractor提取完题目后
- 需要构建知识图谱时
- 需要语义查重时

**工具：**
- `MetaExtractor` - 元信息提取
- `KnowledgeStructurer` - 结构化解析
- `DuplicateChecker` - 语义查重
- `BaseManager` - 双写入库（Neo4j + SQLite）

**特点：**
- ✅ 复杂：多步骤处理，使用多个工具
- ✅ 智能：语义查重，避免重复题目
- ✅ 持久化：写入知识图谱和数据库

---

## 📊 工作流程

### 完整流程

```
1. 爬虫抓取面经原文
   ↓
2. Extractor 提取题目
   输入：面经原文（文本）
   输出：题目列表（JSON）
   ↓
3. Architect Agent 知识管理
   输入：题目列表（JSON）
   输出：知识图谱 + 数据库记录
   ↓
4. 用户查询和学习
```

### 示例

**步骤1：爬虫抓取**
```
原文：
"一面问了Redis的持久化，我说了RDB和AOF。
然后问了MySQL的索引优化，我讲了B+树。
最后手撕了LRU缓存。"
```

**步骤2：Extractor提取**
```json
[
  {
    "question_text": "请介绍Redis的持久化机制",
    "answer_text": "RDB、AOF",
    "question_type": "缓存题",
    "topic_tags": ["Redis", "持久化"]
  },
  {
    "question_text": "请介绍MySQL索引优化",
    "answer_text": "B+树",
    "question_type": "数据库题",
    "topic_tags": ["MySQL", "索引", "B+树"]
  },
  {
    "question_text": "手写LRU缓存",
    "question_type": "算法题",
    "topic_tags": ["LRU", "缓存", "算法"]
  }
]
```

**步骤3：Architect处理**
- 检查是否有重复题目（语义查重）
- 构建知识图谱关系
  - Redis → 持久化 → RDB/AOF
  - MySQL → 索引 → B+树
  - 算法 → LRU → 缓存
- 写入Neo4j和SQLite

---

## 🔧 配置对比

### Extractor配置

```bash
# 只需配置temperature
EXTRACTOR_TEMPERATURE=0.2
EXTRACTOR_MAX_RETRIES=3

# 其他配置使用全局LLM配置
# 使用 settings.llm_provider
# 使用 settings.llm_model_id
# 使用 settings.llm_api_key
# 使用 settings.llm_base_url
```

**原因：**
- Extractor是简单工具，不需要独立配置
- 使用全局LLM配置即可

### Architect配置

```bash
# 完整的独立配置
ARCHITECT_MODE=local
ARCHITECT_LOCAL_PROVIDER=ollama
ARCHITECT_LOCAL_MODEL=qwen3:4b
ARCHITECT_LOCAL_BASE_URL=http://localhost:11434/v1
ARCHITECT_LOCAL_TIMEOUT=60
ARCHITECT_REMOTE_PROVIDER=volcengine
ARCHITECT_REMOTE_MODEL=doubao-1-5-pro-32k-250115
ARCHITECT_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARCHITECT_REMOTE_TIMEOUT=300
ARCHITECT_TEMPERATURE=0.2
```

**原因：**
- Architect是独立Agent，可能需要不同的模型
- 知识管理任务可能需要更强大的模型

---

## 💡 为什么需要两个？

### 1. 职责分离

**Extractor：** 专注于题目提取
- 输入：原文
- 输出：题目列表
- 简单、快速、专一

**Architect：** 专注于知识管理
- 输入：题目列表
- 输出：知识图谱 + 数据库
- 复杂、智能、全面

### 2. 性能优化

**Extractor：**
- 高频调用（每个帖子都要提取）
- 需要快速响应
- 可以使用小模型（qwen3:4b）

**Architect：**
- 低频调用（提取后才处理）
- 可以慢一点
- 可以使用大模型（更准确的语义理解）

### 3. 灵活配置

**场景1：全部使用本地**
```bash
LLM_MODE=local
ARCHITECT_MODE=  # 留空，使用全局
```

**场景2：Extractor用本地，Architect用远程**
```bash
LLM_MODE=local              # Extractor使用本地（快速）
ARCHITECT_MODE=remote       # Architect使用远程（更准确）
```

---

## 📋 总结

### Extractor（题目提取器）

| 特性 | 说明 |
|------|------|
| **性质** | 服务层工具函数 |
| **职责** | 从原文提取题目 |
| **输入** | 面经原文（文本） |
| **输出** | 题目列表（JSON） |
| **调用时机** | 爬虫抓取后 |
| **配置** | 只有temperature，其他用全局 |
| **特点** | 简单、快速、专一 |

### Architect Agent（知识架构师）

| 特性 | 说明 |
|------|------|
| **性质** | 独立Agent |
| **职责** | 知识管理（查重、图谱、入库） |
| **输入** | 题目列表（JSON） |
| **输出** | 知识图谱 + 数据库 |
| **调用时机** | 题目提取后 |
| **配置** | 完整的LOCAL和REMOTE配置 |
| **特点** | 复杂、智能、全面 |

### 关系

```
Extractor → Architect
（提取题目）→（知识管理）
```

**不重复，互补！**

- Extractor负责"提取"
- Architect负责"管理"

---

## 🎯 使用建议

### 开发环境

```bash
# 全部使用本地（快速开发）
LLM_MODE=local
ARCHITECT_MODE=
```

### 生产环境

```bash
# Extractor用本地（高频调用，快速）
LLM_MODE=local

# Architect用远程（低频调用，准确）
ARCHITECT_MODE=remote
ARCHITECT_REMOTE_MODEL=doubao-1-5-pro-32k-250115
```

---

**总结：Extractor是"提取工具"，Architect是"知识管家"，各司其职！** 🎊
