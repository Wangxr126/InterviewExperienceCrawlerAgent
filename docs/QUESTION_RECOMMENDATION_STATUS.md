# 题目推荐与检索现状与改进方案

## 一、查找相似题目（find_similar_questions）✅ 已改进

### 修改内容（2025-03-13）
1. **过滤自身**：按题目编号 `exclude_id` 排除（向量 meta 中的 q_id），不再用文本相似度
2. **前端带 q_id**：题库浏览点击「去对话练习」时发送 `我想练习这道题【q_id:xxx】：题目内容`
3. **优先向量语义检索**：Neo4j 可用时调用 `search_similar()`，默认返回 3 道

### 检索优先级
1. Neo4j 向量检索（`search_similar`，exclude_ids 按题目 ID 过滤）
2. Neo4j 变体关系（`get_variants`）
3. SQLite 关键词搜索 + exclude_ids 过滤
4. SQLite 按标签兜底

---

## 二、四大核心问题调研结论

### 1. 提取题目完成后有没有加入向量库？

**✅ 有**，两条入库路径都会写入 Neo4j 向量库：

| 入库路径 | 代码位置 | 是否写向量 |
|---------|---------|-----------|
| **Ingest（收录面经）** | `knowledge_manager_tools.BaseManager` | ✅ `generate_embedding` + `neo4j_service.add_question` |
| **数据采集 / 定时爬虫** | `scheduler._save_questions` | ✅ `_get_embedding` + `neo4j_service.add_question` |

两者均先写 SQLite，再写 Neo4j（embedding + 元数据）。Neo4j 不可用时静默跳过，不影响 SQLite。

---

### 2. 有没有把元数据也绑定进去？（公司、题目 ID 等）

**✅ 有**。Neo4j `add_question` 写入的节点属性与关系：

| 属性/关系 | 说明 |
|----------|------|
| `q.id` | 题目 ID（q_id） |
| `q.text` | 题目正文 |
| `q.answer` | 参考答案 |
| `q.embedding` | 1024 维向量 |
| `q.difficulty` | 难度 |
| `q.question_type` | 题型 |
| `q.source_platform` | 来源平台 |
| `q.source` | 来源 URL |
| `q.company` | 公司 |
| `q.position` | 岗位 |
| `(q)-[:HAS_TAG]->(Tag)` | 技术标签 |
| `(q)-[:FROM_COMPANY]->(Company)` | 公司节点 |
| `(q)-[:FOR_POSITION]->(Position)` | 岗位节点 |

---

### 3. 提取题目之后有没有维护知识图谱？

**✅ 已优化（2025-03-13）**：

| 能力 | 状态 | 说明 |
|-----|------|------|
| HAS_TAG / FROM_COMPANY / FOR_POSITION | ✅ 有 | `add_question` 自动建立 |
| VARIANT_OF（变体关系） | ✅ 有 | **入库时** `check_duplicate`（阈值 0.85）发现相似题 → `link_variant` |
| COVERS_CONCEPT（题目-知识点） | ❌ 无 | `link_concept` 存在，待后续 LLM 概念抽取接入 |
| 查重后建变体边 | ✅ 有 | BaseManager + Scheduler `_save_questions` 均已接入 |

---

### 4. 回答问题评分完之后有没有保存到记忆？

**✅ 已优化（2025-03-13）**：

| 存储位置 | 内容 | 说明 |
|---------|------|------|
| `study_records`（SQLite） | 答题记录、SM-2 参数、next_review_at | 原有 |
| `user_tag_mastery`（SQLite） | 标签掌握度 | 原有 |
| `episodic_log`（SQLite） | 情节记忆摘要（答题、收录、对话等） | **新增**，`_write_episodic` 持久化 |
| `episodic_log`（event_type=semantic_*） | 语义记忆（薄弱点、掌握较好等） | **新增**，`_write_semantic` 持久化 |

评分后写入 `study_records` + `episodic_log`。`episodic_log` 可后续扩展为向量化（embedding + Qdrant）实现语义召回。

---

## 三、GraphRAG 改进方向

**Neo4j 图结构：**
- 节点：Question、Tag、Company、Position、Concept
- 关系：HAS_TAG、FROM_COMPANY、FOR_POSITION、COVERS_CONCEPT、VARIANT_OF

**待实现：**
1. **变体边自动建立**：入库时 `check_duplicate` 发现相似题 → 调用 `link_variant`
2. **概念抽取与关联**：LLM 抽取 Concept → 调用 `link_concept`
3. **图检索增强**：向量召回 + 图遍历（HAS_TAG / VARIANT_OF）

---

## 四、加权系数推荐题目

### 现状：❌ 未实现

**当前推荐逻辑（`get_recommended_question`）：**
1. 遗忘曲线到期（`get_due_reviews`）→ 随机选一道
2. 薄弱标签 + Neo4j 按标签 → 随机选一道
3. SQLite 兜底 → 随机选一道

**未考虑的因素：**
- 相近题目上次复习时间（越久未复习，权重越高）
- 题目与当前知识点的语义相近度
- 用户薄弱点与题目标签的匹配度
- 多因子加权综合排序

### 改进方案（建议实现）

```
推荐分数 = w1 * 遗忘曲线紧急度 + w2 * 语义相近度 + w3 * 薄弱点匹配度 + w4 * 上次复习时间衰减
```

| 因子 | 数据来源 | 权重建议 |
|-----|---------|---------|
| 遗忘曲线紧急度 | `next_review_at` 与当前时间差 | 高 |
| 语义相近度 | 与用户当前练习题目/薄弱标签的 embedding 相似度 | 中 |
| 薄弱点匹配 | `user_tag_mastery` 中 novice/learning 标签 | 高 |
| 上次复习时间 | `study_records.studied_at`，越久权重越高 | 中 |

**实现步骤：**
1. 在 `sqlite_service` 或新建 `recommendation_service` 中实现 `get_weighted_recommendations(user_id, topic=None, limit=5)`
2. 查询：到期复习题 + 薄弱标签题 + 可选向量相似题
3. 对候选题目计算加权分，按分排序取 top-k
4. 将 `get_recommended_question` 改为调用该加权逻辑

---

## 五、路径优化总结（2025-03-13）

| 环节 | 优化前 | 优化后 |
|-----|--------|--------|
| **题目入库** | 仅 add_question，无变体边 | `check_duplicate`(0.85) → `add_question` → `link_variant` |
| **知识图谱** | VARIANT_OF 从未建立 | 入库时自动建立变体边 |
| **评分后记忆** | _write_episodic 仅 log | 持久化到 `episodic_log` 表 |
| **语义记忆** | _write_semantic 仅 log | 持久化到 `episodic_log`（event_type=semantic_*） |

### 涉及文件
- `knowledge_manager_tools.py`：BaseManager 查重 + link_variant
- `scheduler.py`：_save_questions 查重 + link_variant
- `sqlite_service.py`：episodic_log 表 + add_episodic_log
- `orchestrator.py`：_write_episodic / _write_semantic 持久化

### 后续可扩展
- `episodic_log` → 生成 embedding → 写入 Qdrant，实现语义召回
- `link_concept`：LLM 抽取题目涉及的概念，建立 COVERS_CONCEPT
