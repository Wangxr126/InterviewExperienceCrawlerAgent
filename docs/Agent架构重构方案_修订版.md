# Agent架构重构方案（修订版）

## 🎯 架构调整

### 调整1：重新命名组件

**旧命名 → 新命名**

```
Extractor Service → Extractor Service（保持）
  - 有LLM
  - 提取元信息和题目

Architect Agent → Knowledge Manager（知识管理器）
  - 无LLM
  - 纯数据管理（入库、建图谱）
  - 不是Agent，是Service
```

### 调整2：移除语义查重

**旧设计：**
```
Architect Agent:
  1. 结构化解析
  2. 语义查重 ❌ 移除
  3. 构建知识图谱
  4. 双写入库
```

**新设计：**
```
Knowledge Manager:
  1. 构建知识图谱
  2. 双写入库（Neo4j + SQLite）
  3. 数据库层面去重（避免完全重复）
```

---

## 📋 新架构：三层设计

### 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    爬虫层（Hunter）                      │
│  - 牛客网爬虫（nowcoder_crawler.py）                    │
│  - 小红书爬虫（xhs_crawler.py）                         │
│  职责：抓取原始面经内容                                  │
│  LLM：❌ 无                                              │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              提取层（Extractor Service）                 │
│  - 统一的提取服务（extractor_service.py）               │
│  职责：从原文提取所有结构化信息                          │
│    1. 提取元信息（公司、岗位、业务线、难度）             │
│    2. 提取题目列表（题目、答案、分类、标签）             │
│  LLM：✅ 有（使用LLM提取）                               │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│            管理层（Knowledge Manager）                   │
│  - 知识管理器（knowledge_manager.py）                   │
│  职责：数据管理（不做提取，不做查重）                    │
│    1. 构建知识图谱（题目 → 知识点 → 技术栈）             │
│    2. 双写入库（Neo4j + SQLite）                        │
│    3. 数据库层面去重（避免完全重复的记录）               │
│  LLM：❌ 无（纯数据操作）                                │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              应用层（Interviewer Agent）                 │
│  - 面试官（interviewer_agent.py）                       │
│  职责：面试对话 + RAG检索                                │
│    1. RAG检索相似题目（自然会找到相似题）               │
│    2. 出题推荐                                           │
│    3. 答案评估                                           │
│    4. 知识推荐                                           │
│  LLM：✅ 有（对话和推理）                                │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 详细设计

### 1. Extractor Service（提取服务）

**性质：** 服务层（有LLM）

**职责：** 从面经原文中提取所有结构化信息

**使用LLM：** ✅ 是

**输入：**
```python
{
    "raw_text": "面经原文...",
    "source_platform": "nowcoder",
    "source_url": "https://..."
}
```

**输出：**
```python
{
    "meta": {
        "company": "字节跳动",
        "position": "后端研发",
        "business_line": "抖音",
        "difficulty": "medium"
    },
    "questions": [
        {
            "question_text": "请介绍Redis的持久化机制",
            "answer_text": "RDB、AOF",
            "difficulty": "medium",
            "question_type": "缓存题",
            "topic_tags": ["Redis", "持久化"]
        }
    ]
}
```

---

### 2. Knowledge Manager（知识管理器）

**性质：** 服务层（无LLM）

**职责：** 纯数据管理（不做提取，不做语义查重）

**使用LLM：** ❌ 否

**输入：**
```python
{
    "meta": {...},           # 来自Extractor
    "questions": [...]       # 来自Extractor
}
```

**输出：**
```python
{
    "success": true,
    "processed_count": 10,
    "graph_nodes_created": 15,
    "db_records_inserted": 10,
    "duplicates_skipped": 0  # 数据库层面的完全重复
}
```

**功能：**
1. **构建知识图谱**
   - 题目 → 知识点
   - 知识点 → 技术栈
   - 题目 → 公司
   - 题目 → 岗位

2. **双写入库**
   - Neo4j（知识图谱）
   - SQLite（结构化数据）

3. **数据库去重**
   - 只避免完全重复（相同question_text + 相同company）
   - 不做语义查重
   - 保留所有相似题目

**为什么不做语义查重？**
- ✅ 知识库本身就是存放问题
- ✅ 相似题目有价值（不同公司、不同角度）
- ✅ RAG检索时自然会找到相似题目
- ✅ 用户可以看到多个相似题目，选择最合适的

---

### 3. Interviewer Agent（面试官）

**性质：** Agent（有LLM）

**职责：** 面试对话 + RAG检索

**使用LLM：** ✅ 是

**RAG检索流程：**
```python
# 1. 用户请求
user_request = "推荐Redis相关的题目"

# 2. RAG检索（自动找到相似题目）
similar_questions = rag_search(
    query="Redis",
    top_k=10,
    filters={"company": "字节跳动"}  # 可选
)

# 3. LLM推荐（基于检索结果）
response = interviewer_agent.run(
    user_request=user_request,
    reference_materials=similar_questions  # RAG检索结果
)
```

**为什么RAG能找到相似题目？**
- ✅ 使用Embedding向量检索
- ✅ 自动计算相似度
- ✅ 返回Top-K相似题目
- ✅ 不需要提前合并

---

## 📊 对比表

| 组件 | 性质 | 有LLM | 职责 | 是否查重 |
|------|------|-------|------|---------|
| **Hunter** | 爬虫服务 | ❌ | 抓取原文 | ❌ |
| **Extractor** | 提取服务 | ✅ | 提取信息 | ❌ |
| **Knowledge Manager** | 管理服务 | ❌ | 数据管理 | ✅ 数据库去重 |
| **Interviewer** | Agent | ✅ | 面试对话 | ❌ (RAG检索) |

---

## 🔄 数据流

### 完整流程

```
1. Hunter（爬虫）
   输入：URL
   输出：原文
   LLM：❌
   ↓
2. Extractor Service（提取）
   输入：原文
   输出：{meta, questions}
   LLM：✅ 使用LLM提取
   ↓
3. Knowledge Manager（管理）
   输入：{meta, questions}
   输出：图谱 + 数据库
   LLM：❌ 纯数据操作
   查重：只避免完全重复
   ↓
4. Interviewer Agent（对话）
   输入：用户问题
   输出：面试回答
   LLM：✅ 对话和推理
   检索：RAG自动找相似题目
```

---

## 💡 为什么这样设计？

### 1. 命名更准确

**旧命名：**
- Architect Agent ❌ 误导（不是Agent）

**新命名：**
- Knowledge Manager ✅ 准确（管理服务）

### 2. 职责更清晰

**旧设计：**
- Architect既做提取又做管理 ❌ 混乱

**新设计：**
- Extractor只做提取 ✅
- Knowledge Manager只做管理 ✅

### 3. 不做语义查重

**原因：**
1. **保留信息价值**
   - 相似题目可能来自不同公司
   - 相似题目可能有不同角度
   - 用户需要看到多个版本

2. **RAG自然处理**
   - RAG检索时自动找相似题目
   - 用户可以选择最合适的
   - 不需要提前合并

3. **避免信息丢失**
   - 合并题目会丢失细节
   - 不同公司的题目有差异
   - 保留原始数据更有价值

### 4. 数据库去重

**只避免完全重复：**
```python
# 完全重复（避免）
question1 = {
    "question_text": "请介绍Redis的持久化机制",
    "company": "字节跳动"
}
question2 = {
    "question_text": "请介绍Redis的持久化机制",
    "company": "字节跳动"
}
# → 只保留一条

# 相似但不同（保留）
question1 = {
    "question_text": "请介绍Redis的持久化机制",
    "company": "字节跳动"
}
question2 = {
    "question_text": "Redis如何实现持久化",
    "company": "阿里巴巴"
}
# → 保留两条（不同表述、不同公司）
```

---

## 📝 重构步骤（修订）

### 阶段1：创建Extractor Service
- [x] 创建 `extractor_service.py`
- [x] 实现 `extract_meta()`
- [x] 实现 `extract_questions()`
- [x] 实现 `extract_all()`

### 阶段2：重命名并简化Knowledge Manager
- [ ] 重命名：`architect_agent.py` → `knowledge_manager.py`
- [ ] 移除：`DuplicateChecker`（语义查重）
- [ ] 保留：`GraphBuilder`（构建图谱）
- [ ] 保留：`BaseManager`（双写入库）
- [ ] 添加：数据库层面去重逻辑

### 阶段3：更新调用流程
- [ ] 更新 `scheduler.py`
- [ ] 更新爬虫调用

### 阶段4：Interviewer添加RAG
- [ ] 实现RAG检索
- [ ] 应用RAG原则
- [ ] 测试相似题目检索

---

## 🎉 总结

### 你的两个问题

1. **命名问题** ✅ 已解决
   - Architect Agent → Knowledge Manager
   - 更准确地反映职责（管理服务，不是Agent）

2. **语义查重问题** ✅ 已解决
   - 移除Knowledge Manager的语义查重
   - 只在数据库层面避免完全重复
   - RAG检索时自然找到相似题目

### 新架构优势

1. **命名准确**：有LLM的叫Agent，无LLM的叫Service/Manager
2. **职责清晰**：提取、管理、对话分离
3. **保留信息**：不合并相似题目，保留原始数据
4. **RAG友好**：相似题目通过RAG检索自然找到

---

**你觉得这个修订版如何？** 🤔
