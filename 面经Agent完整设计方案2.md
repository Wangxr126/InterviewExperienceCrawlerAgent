# 面经 Agent 完整设计方案 v2

> 版本：v2.0 | 日期：2026-03-05  
> 基于当前代码库的完整技术文档，涵盖架构、数据流、API、前端及配置

---

## 一、项目概述

### 1.1 产品定位

**面经 Agent** 是一款面向技术面试复习的 AI 助手，核心能力包括：

- **题库管理**：从牛客、小红书等平台采集面经，LLM 提取结构化题目入库
- **智能出题**：基于 SM-2 遗忘曲线、薄弱点、公司/标签的个性化推荐
- **练习对话**：用户与 InterviewerAgent 自然对话，出题、讲解、换问法、记笔记
- **答题评估**：用户提交答案后，LLM 打分并更新 SM-2 参数，支持知识补强推荐
- **多模态记忆**：hello-agents 四层记忆（工作/情景/语义/感知）与 SQLite 持久化结合

### 1.2 技术栈


| 层级       | 技术选型                                          |
| -------- | --------------------------------------------- |
| 后端       | FastAPI + Python 3.x                          |
| 前端       | Vue 3 + Element Plus + Vite                   |
| Agent 框架 | hello-agents（PlanAndSolveAgent / ReActAgent）  |
| LLM      | Ollama / 火山引擎 / OpenAI 兼容 API                 |
| 存储       | SQLite（结构化数据）+ Neo4j（知识图谱） + Qdrant（向量）       |
| 调度       | APScheduler（后台定时爬虫）                           |
| 爬虫       | requests + BeautifulSoup（牛客）+ Playwright（小红书） |


---

## 二、整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         用户 (Web 前端 / API)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          FastAPI (backend/main.py)                          │
│   /api/chat/stream | /api/submit_answer | /api/questions | /api/ingest ...  │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    InterviewSystemOrchestrator                               │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  per-user MemoryTool 池    │  context.set_current_user_id()           │  │
│   │  {user_id: MemoryTool}     │  thinking_capture.ThinkingCapture         │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │                              │
         ▼                              ▼                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  HunterPipeline (纯代码)     │  KnowledgeArchitectAgent  │  InterviewerAgent  │
│  爬取→清洗→校验→OCR?→元信息  │  structure_knowledge     │  PlanAndSolveAgent │
│  (HunterAgent 已移除)        │  check_duplicate         │  get_recommended_q │
│                             │  save_knowledge           │  find_similar_q   │
│                             │  generate_embedding       │  filter_questions │
│                             │                          │  manage_note      │
│                             │                          │  get_mastery     │
│                             │                          │  analyze_resume   │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              存储层                                          │
│  ├── SQLite (questions, study_records, user_profiles, interview_sessions,   │
│  │         crawl_tasks, user_notes, knowledge_resources)                    │
│  ├── Neo4j (Question 节点 + 向量索引 + Tag/Company/Position 关系)            │
│  └── Qdrant (MemoryTool 四层记忆向量)                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块

### 3.1 编排器 (Orchestrator)

**文件**：`backend/agents/orchestrator.py`

**职责**：

- 统一入口：`chat()`、`submit_answer()`、`ingest_instant()`、`end_session()`
- 管理 per-user MemoryTool 实例
- 注入 `user_id` 到线程上下文（`context.set_current_user_id`），供工具自动读取
- 使用 `ThinkingCapture` 捕获 Agent 推理步骤，返回 `(reply, thinking_steps)` 元组
- 答题后确定性流程：`_evaluate_answer_structured` → SM-2 更新 → 记忆写入 → 知识推荐

**关键逻辑**：

```python
# chat() 返回 (reply, thinking_steps)
async def chat(self, user_id, message, session_id=None) -> tuple:
    set_current_user_id(user_id)
    with ThinkingCapture() as tc:
        response = self.interviewer.run(full_input)
    return response, tc.get_steps()
```

### 3.2 思考步骤捕获 (ThinkingCapture)

**文件**：`backend/agents/thinking_capture.py`

**原理**：在应用启动时全局替换 `sys.stdout` 为线程感知代理，Agent 执行时 `print()` 输出写入线程本地缓冲区，解析为 `[{thought, action, observation, warning}, ...]` 结构化列表。

**解析格式**：`--- 第 N 步 ---`、`🤔 思考:`、`🎬 行动:`、`👀 观察:` 等。

**用途**：前端展示 LLM 推理过程，支持可折叠/展开。

### 3.3 用户上下文注入 (context)

**文件**：`backend/agents/context.py`

**原理**：`threading.local()` 存储当前 `user_id`，Orchestrator 在每次调用 Agent 前 `set_current_user_id(user_id)`，工具内部通过 `_resolve_user_id(parameters)` 获取（参数有则用参数，无则用上下文）。

**目的**：避免 Agent 每次调用工具时都显式传 `user_id`，减少 LLM 解析错误。

### 3.4 数据采集完整流程（四步）

数据采集页（CollectView）与调度器协同，完成从发现到入库的全流程：

| 步骤 | 说明 | 对应操作 |
|------|------|----------|
| **1. 爬取页数、获取链接入库** | 按关键词搜索列表页，发现帖子链接，写入 `crawl_tasks`（status=pending） | 牛客「获取帖子」、小红书「获取帖子」、定时发现任务 |
| **2. 根据链接爬取正文/图片到本地** | 访问详情页，抓取正文文本，下载图片到 `post_images/{task_id}/`，更新 status=fetched | 「抓取并提取」、定时任务 Step 1 |
| **3. 利用 LLM 提取题目** | 对正文调用 LLM 提取结构化题目；正文不足时由 LLM 判断是否需 OCR，若有图片则 OCR 后再次提取 | 「提取题目」「抓取并提取」、定时任务 Step 2 |
| **4. 提取出的 FAQ（问题+答案）保存到本地** | 题目写入 SQLite `questions` 表及 Neo4j，含 question_text、answer_text、topic_tags 等 | 自动入库 |

**OCR 决策**：当前实现为「正文无题目且有图片时自动 OCR」。目标为「由 LLM 判断是否调用 OCR」，待后续优化。

### 3.5 内容采集管道 (HunterPipeline)

**文件**：`backend/services/hunter_pipeline.py`

**流程**（纯代码，无 LLM 编排）：

1. **爬取**：CrawlerTool（牛客 HTTP / 小红书 Playwright）
2. **清洗**：TextSanitizer（正则去噪）
3. **校验**：ContentValidator（规则判断：是否相关、是否需要 OCR）
4. **OCR**：VisualExtractor（仅在 `needs_ocr=True` 时执行）
5. **元信息**：MetaExtractor（规则优先，LLM 兜底）

输出 `HunterPipelineResult` 交给 ArchitectAgent 做结构化。

### 3.6 题目提取 (extract_questions_from_post)

**文件**：`backend/services/crawler/question_extractor.py`

**用途**：对爬取后的帖子文本调用 LLM，提取 JSON 题目列表（question_text, answer_text, tags, difficulty 等），再入库 SQLite + Neo4j。

---

## 四、Agent 与工具

### 4.1 InterviewerAgent

**类型**：PlanAndSolveAgent（hello-agents）

**工具**：


| 工具名                            | 用途      | 输入                             | 输出          |
| ------------------------------ | ------- | ------------------------------ | ----------- |
| `get_recommended_question`     | 智能出题    | 推荐模式、topic、company、exclude_ids | 题目详情        |
| `find_similar_questions`       | 举一反三    | 题目文本、top_k                     | 相似题列表       |
| `filter_questions`             | 按条件筛选   | tags、company、difficulty        | 题目列表        |
| `manage_note`                  | 笔记 CRUD | action、note_id、content         | 操作结果        |
| `get_mastery_report`           | 掌握度报告   | tags                           | 标签掌握度文本     |
| `get_knowledge_recommendation` | 知识补强    | tags                           | 错题回顾 + 学习资源 |
| `analyze_resume`               | 简历分析    | resume_text                    | 技术栈、经验等级    |


**Prompt 要点**：`user_id` 由系统自动注入，调用工具时无需传参。

### 4.2 KnowledgeArchitectAgent

**类型**：ReActAgent

**工具**：


| 工具名                   | 用途                |
| --------------------- | ----------------- |
| `structure_knowledge` | 帖子文本 → JSON 题目列表  |
| `check_duplicate`     | 向量检索查重            |
| `save_knowledge`      | Neo4j + SQLite 双写 |
| `generate_embedding`  | DashScope 向量化     |
| `MetaExtractor`       | 元信息提取             |


### 4.3 HunterPipeline 工具（非 Agent）


| 工具               | 用途           |
| ---------------- | ------------ |
| CrawlerTool      | 爬取页面         |
| TextSanitizer    | 清洗文本         |
| ContentValidator | 相关性 + OCR 决策 |
| VisualExtractor  | 图片 OCR       |
| MetaExtractor    | 公司/岗位/难度等    |


### 4.4 Agent 设计评估与设计 rationale


| Agent                       | 类型                | 评估    | 设计理由                                                             |
| --------------------------- | ----------------- | ----- | ---------------------------------------------------------------- |
| **HunterAgent**             | 原 ReActAgent      | ❌ 已移除 | 管道步骤（爬取→清洗→校验→OCR→元信息）固定顺序，用纯代码更可靠、省 token；OCR 决策为规则判断，无需 LLM 编排 |
| **KnowledgeArchitectAgent** | ReActAgent        | ✅ 保留  | 帖子→题目结构化需 LLM 语义理解；查重、入库为确定性逻辑，由工具完成                             |
| **InterviewerAgent**        | PlanAndSolveAgent | ✅ 保留  | 开放对话需理解用户意图、选择工具；出题/讲解/笔记/掌握度等由工具实现，Agent 负责编排                   |


**InterviewerAgent 工具设计原则**：

- `user_id` 由 Orchestrator 注入上下文，工具内部 `_resolve_user_id()` 读取，避免 LLM 解析失败
- 推荐、过滤、掌握度等为确定性逻辑（SQL/向量检索），不依赖 LLM 推理
- 仅 `analyze_resume` 需 LLM 提取技术栈；评估答案由 Orchestrator 直接调用 `_evaluate_answer_structured`，不走 Agent 循环

---

## 五、数据库设计

### 5.1 SQLite 表设计（完整字段）

#### 表 1：`questions`（题目元数据，与 Neo4j 双写）


| 字段                          | 类型       | 说明                          | 来源             |
| --------------------------- | -------- | --------------------------- | -------------- |
| `q_id`                      | TEXT PK  | 唯一题目ID，格式 `TAG-xxxxxx`      | BaseManager 生成 |
| `question_text`             | TEXT     | 题目正文                        | LLM 解析         |
| `answer_text`               | TEXT     | 参考答案                        | LLM 解析         |
| `difficulty`                | TEXT     | easy/medium/hard            | MetaExtractor  |
| `question_type`             | TEXT     | 技术题/行为题/算法题/系统设计            | LLM 分类         |
| `source_platform`           | TEXT     | nowcoder / xiaohongshu      | 域名判断           |
| `source_url`                | TEXT     | 来源帖子链接                      | Crawler        |
| `company`                   | TEXT     | 公司名称                        | MetaExtractor  |
| `position`                  | TEXT     | 岗位                          | MetaExtractor  |
| `business_line`             | TEXT     | 业务线                         | MetaExtractor  |
| `topic_tags`                | TEXT     | JSON 数组，如 `["Redis","分布式"]` | LLM 提取         |
| `created_at` / `updated_at` | DATETIME | 时间戳                         | 系统自动           |


#### 表 2：`user_profiles`（用户画像 — 语义记忆层）


| 字段                 | 类型      | 说明                |
| ------------------ | ------- | ----------------- |
| `user_id`          | TEXT PK | 用户唯一标识            |
| `resume_text`      | TEXT    | 简历原文              |
| `tech_stack`       | TEXT    | JSON 数组，技术栈标签     |
| `target_company`   | TEXT    | 目标公司              |
| `target_position`  | TEXT    | 目标岗位              |
| `experience_level` | TEXT    | junior/mid/senior |
| `preferred_topics` | TEXT    | JSON 数组，偏好主题      |


#### 表 3：`user_tag_mastery`（标签掌握度 — 推荐引擎核心）


| 字段                                | 类型       | 说明                                |
| --------------------------------- | -------- | --------------------------------- |
| `user_id`                         | TEXT     | 用户ID                              |
| `tag`                             | TEXT     | 技术标签                              |
| `total_attempts`                  | INTEGER  | 该标签总做题次数                          |
| `correct_count`                   | INTEGER  | 得分≥3 的次数                          |
| `avg_score`                       | REAL     | 平均分（0-5）                          |
| `mastery_level`                   | TEXT     | novice/learning/proficient/expert |
| `last_practiced` / `last_updated` | DATETIME | 时间戳                               |


**掌握等级判断规则**（纯计算，无需 LLM）：

```
novice:     total_attempts < 3  OR  avg_score < 2.0
learning:   avg_score >= 2.0 AND avg_score < 3.5
proficient: avg_score >= 3.5 AND avg_score < 4.5
expert:     avg_score >= 4.5 AND correct_count >= 5
```

#### 表 4：`study_records`（做题记录 — 情景记忆层 + SM-2）


| 字段                | 类型       | 说明               |
| ----------------- | -------- | ---------------- |
| `user_id`         | TEXT     | 用户ID             |
| `question_id`     | TEXT     | 题目ID             |
| `session_id`      | TEXT     | 关联面试 Session     |
| `score`           | INTEGER  | 用户得分 0-5         |
| `user_answer`     | TEXT     | 用户回答原文           |
| `ai_feedback`     | TEXT     | AI 评价            |
| `easiness_factor` | REAL     | SM-2 易度系数，初始 2.5 |
| `repetitions`     | INTEGER  | 连续正确次数           |
| `interval_days`   | INTEGER  | 下次复习间隔（天）        |
| `next_review_at`  | DATETIME | 下次应复习时间          |
| `studied_at`      | DATETIME | 作答时间             |


#### 表 5：`interview_sessions`（面试会话 — 情景记忆层）


| 字段                              | 类型           | 说明                            |
| ------------------------------- | ------------ | ----------------------------- |
| `session_id`                    | TEXT UNIQUE  | Session 唯一ID                  |
| `user_id`                       | TEXT         | 用户ID                          |
| `session_type`                  | TEXT         | mock/practice/review/weakness |
| `topic_focus`                   | TEXT         | 本次练习主题                        |
| `conversation_history`          | TEXT         | JSON 对话历史（含 reasoning）        |
| `total_questions` / `avg_score` | INTEGER/REAL | 统计                            |
| `ai_summary` / `weak_tags`      | TEXT         | AI 总结、薄弱标签 JSON               |


#### 表 6：`user_notes`（用户笔记）


| 字段                  | 类型          | 说明                          |
| ------------------- | ----------- | --------------------------- |
| `note_id`           | TEXT UNIQUE | 笔记唯一ID                      |
| `user_id`           | TEXT        | 用户ID                        |
| `question_id`       | TEXT        | 关联题目（可为空）                   |
| `title` / `content` | TEXT        | 标题、正文（Markdown）             |
| `tags`              | TEXT        | JSON 标签数组                   |
| `note_type`         | TEXT        | concept/mistake/tip/summary |


#### 表 7：`crawl_tasks`（爬虫任务队列）


| 字段                     | 类型          | 说明                                   |
| ---------------------- | ----------- | ------------------------------------ |
| `task_id`              | TEXT UNIQUE | 任务唯一ID                               |
| `source_url`           | TEXT        | 来源链接                                 |
| `source_platform`      | TEXT        | nowcoder / xiaohongshu               |
| `post_title`           | TEXT        | 帖子标题                                 |
| `status`               | TEXT        | pending / processing / done / failed |
| `company` / `position` | TEXT        | 元信息                                  |
| `content_len`          | INTEGER     | 正文长度                                 |
| `questions_count`      | INTEGER     | 已提取题目数                               |


#### 表 8：`crawl_logs`、`ingestion_logs`（爬取/入库日志）


| 表                | 用途                                            |
| ---------------- | --------------------------------------------- |
| `crawl_logs`     | 爬取结果（url, status, title, questions_extracted） |
| `ingestion_logs` | 入库记录（question_id, source_url, tags）           |


#### 表 9：`knowledge_resources`（知识补强资源）


| 字段              | 类型          | 说明                              |
| --------------- | ----------- | ------------------------------- |
| `resource_id`   | TEXT UNIQUE | 资源唯一ID                          |
| `title`         | TEXT        | 标题                              |
| `url`           | TEXT        | 链接                              |
| `description`   | TEXT        | 摘要                              |
| `tags`          | TEXT        | JSON 标签数组                       |
| `resource_type` | TEXT        | article/video/github/problemset |
| `source`        | TEXT        | 来源站点                            |


---

### 5.2 Neo4j 图设计

**节点类型**：


| 节点         | 属性                                                                            |
| ---------- | ----------------------------------------------------------------------------- |
| `Question` | id, text, answer, embedding(1024维), difficulty, company, position, created_at |
| `Tag`      | name, category                                                                |
| `Company`  | name, industry                                                                |
| `Position` | name, category                                                                |
| `Concept`  | name, description                                                             |


**关系类型**：


| 关系               | 方向                  | 说明         |
| ---------------- | ------------------- | ---------- |
| `HAS_TAG`        | Question → Tag      | 题目归属标签     |
| `FROM_COMPANY`   | Question → Company  | 题目来源公司     |
| `FOR_POSITION`   | Question → Position | 适用岗位       |
| `COVERS_CONCEPT` | Question → Concept  | 考察知识点      |
| `RELATED_TO`     | Question ↔ Question | 相似题（score） |
| `VARIANT_OF`     | Question → Question | 换个问法变体     |
| `PREREQUISITE`   | Tag → Tag           | 标签依赖       |


**向量索引**：question_embedding，1024 维，cosine 相似度。

---

### 5.3 RAG 设计（题目检索）

**向量化对象**：`question_text`（题目正文）。答案、标签不向量化。

**使用场景**：


| 场景      | 输入     | 检索目标          | 是否需要 LLM |
| ------- | ------ | ------------- | -------- |
| 查重（入库时） | 新题文本   | 相似度 > 0.9 的题目 | 否        |
| 举一反三    | 当前题目文本 | Top-K 相似题     | 否        |
| 换个问法    | 知识点描述  | 同知识点不同角度题目    | 否        |
| 主题检索    | 用户关键词  | 语义相关题目列表      | 否        |


**检索流程**：FilterTool 构建条件 → `generate_embedding` 向量化 → Neo4j 向量检索 → 元数据过滤 → 返回题目列表。

---

### 5.4 Qdrant

MemoryTool 内部使用，存储四层记忆向量（见下文「六、记忆机制」）。

---

## 六、记忆机制（四层记忆）

> 基于 hello-agents 框架 MemoryTool，底层由 MemoryManager 协调四种记忆类型。

### 6.1 框架记忆系统架构

```
hello-agents MemoryTool
├── 记忆类型层
│   ├── WorkingMemory   - 工作记忆（临时，TTL 管理）
│   ├── EpisodicMemory  - 情景记忆（具体事件，持久化）
│   ├── SemanticMemory  - 语义记忆（抽象知识，图谱）
│   └── PerceptualMemory - 感知记忆（多模态）
├── 存储后端
│   ├── QdrantVectorStore   - 向量存储
│   ├── Neo4jGraphStore    - 图存储（语义记忆）
│   └── SQLiteDocumentStore - 文档存储（情景记忆）
└── 嵌入服务：DashScopeEmbedding
```

### 6.2 四层记忆详细说明与面经 Agent 映射


| 层级                    | 用途               | 存什么                   | importance | 对应 SQLite                               |
| --------------------- | ---------------- | --------------------- | ---------- | --------------------------------------- |
| **Working Memory**    | 当前 session 临时上下文 | 用户正在回答的题目、已出题数、当前对话摘要 | 0.4~0.7    | interview_sessions.conversation_history |
| **Episodic Memory**   | 具体学习事件           | 答题记录、模拟面试完成、笔记记录      | 0.7~0.9    | study_records, interview_sessions       |
| **Semantic Memory**   | 长期知识画像           | 用户掌握等级、目标公司、技术栈、薄弱标签  | 0.8~1.0    | user_profiles, user_tag_mastery         |
| **Perceptual Memory** | 多模态输入            | 简历图片、代码截图、面经图片（OCR 后） | 0.6~0.8    | —                                       |


### 6.3 记忆生命周期管理

```python
# 对话开始 → 工作记忆
memory_tool.execute("add", content="用户开始练习，当前问题：xxx",
                    memory_type="working", importance=0.5, session_id=...)

# 用户答完题 → 情景记忆
memory_tool.execute("add", content="用户回答了【Redis主从复制】，得分4/5",
                    memory_type="episodic", importance=0.7+score/10, event_type="study_record")

# 检测到掌握模式 → 语义记忆
memory_tool.execute("add", content="用户对【Redis】掌握等级：proficient",
                    memory_type="semantic", importance=0.85, knowledge_type="user_mastery")

# session 结束 → 整合 + 遗忘
memory_tool.execute("consolidate", from_type="working", to_type="episodic", importance_threshold=0.7)
memory_tool.execute("forget", strategy="importance_based", threshold=0.3)
```

### 6.4 MemoryTool 操作速查


| 操作            | 用途    | 面经 Agent 典型调用                |
| ------------- | ----- | ---------------------------- |
| `add`         | 添加记忆  | 记录答题事件、用户偏好、当前上下文            |
| `search`      | 语义搜索  | "用户学过哪些 Redis 题？"            |
| `consolidate` | 记忆整合  | session 结束时 working→episodic |
| `forget`      | 遗忘低价值 | 定期清理过期工作记忆                   |
| `summary`     | 记忆摘要  | 生成学习进度总结                     |


### 6.5 记忆 vs RAG 职责分工


| 系统                   | 存储对象           | 检索目的           |
| -------------------- | -------------- | -------------- |
| **MemoryTool（四层记忆）** | 用户学习历程、偏好、掌握程度 | 个性化：了解「这个用户」是谁 |
| **Neo4j + RAG（题库）**  | 全量面试题目         | 出题：从题库找合适的题    |
| **SQLite（SM-2）**     | 遗忘曲线参数         | 精确计算：下次复习时间    |


---

## 七、API 接口

### 7.1 对话与答题


| 方法   | 路径                                 | 说明                                  |
| ---- | ---------------------------------- | ----------------------------------- |
| POST | `/api/chat`                        | 普通对话，返回 `{reply, thinking}`         |
| POST | `/api/chat/stream`                 | SSE 流式对话，先 `{thinking}` 再 `{delta}` |
| POST | `/api/submit_answer`               | 答题提交，评估 + SM-2 + 记忆                 |
| POST | `/api/session/end`                 | 结束 session，记忆整合                     |
| GET  | `/api/user/{user_id}/chat/history` | 最近对话历史                              |


### 7.2 题库


| 方法  | 路径                      | 说明                                 |
| --- | ----------------------- | ---------------------------------- |
| GET | `/api/questions`        | 列表过滤（company/position/tag/keyword） |
| GET | `/api/questions/random` | 随机一题                               |
| GET | `/api/questions/meta`   | 元数据（公司/标签/难度列表）                    |
| GET | `/api/questions/{q_id}` | 单题详情                               |


### 7.3 用户


| 方法  | 路径                            | 说明       |
| --- | ----------------------------- | -------- |
| GET | `/api/user/{user_id}/mastery` | 掌握度报告    |
| GET | `/api/user/{user_id}/reviews` | 到期复习题    |
| GET | `/api/user/{user_id}/memory`  | 记忆摘要（调试） |


### 7.4 收录与爬虫


| 方法   | 路径                                       | 说明                         |
| ---- | ---------------------------------------- | -------------------------- |
| POST | `/api/ingest`                            | 立即收录 URL                   |
| GET  | `/api/crawler/stats`                     | 爬虫统计                       |
| POST | `/api/crawler/trigger`                   | 手动触发（nowcoder/xiaohongshu） |
| GET  | `/api/crawler/tasks`                     | 爬虫任务列表（分页），参数：status、platform、limit、offset；返回 total、tasks |
| GET  | `/api/crawler/tasks/{task_id}`           | 单任务详情（含正文）                 |
| GET  | `/api/crawler/tasks/{task_id}/questions` | 任务提取的题目列表                  |


### 7.5 配置


| 方法  | 路径            | 说明                                           |
| --- | ------------- | -------------------------------------------- |
| GET | `/api/config` | 前端配置（default_user_id, interviewer_max_steps） |


---

## 八、前端

### 8.1 页面结构


| 页面          | 路由   | 功能                    |
| ----------- | ---- | --------------------- |
| BrowseView  | 题库浏览 | 筛选、随机出题、发送到对话         |
| ChatView    | 练习对话 | 流式对话、思考过程展示、快捷问题      |
| IngestView  | 收录面经 | 输入 URL 立即收录           |
| CollectView | 数据采集 | 爬取页数获取链接、抓取正文/图片、LLM 提取题目、FAQ 入库、任务列表（分页+关键词筛选）、清除所有 |
| ReportView  | 学习报告 | 掌握度、复习题、历史记录          |


### 8.2 思考过程展示

- 每条 AI 消息上方显示可折叠「推理过程」面板
- 步骤：🤔 思考 / 🎬 行动 / 👀 观察
- 收到 `thinking` SSE 事件后立刻展示，收到第一个 `delta` 后自动折叠

### 8.3 用户 ID

- 顶栏输入框，默认从 `/api/config` 的 `default_user_id` 加载
- 未配置时使用 `user_001`

---

## 九、配置与环境变量

### 9.1 .env 主要配置


| 分类        | 变量                                                          | 说明                  |
| --------- | ----------------------------------------------------------- | ------------------- |
| LLM       | LLM_PROVIDER, LLM_MODEL_ID, LLM_API_KEY, LLM_BASE_URL       | 全局 LLM              |
| LLM       | HUNTER_MODEL, ARCHITECT_MODEL, INTERVIEWER_MODEL            | 各 Agent 差异化（留空则用全局） |
| Embedding | EMBED_MODEL_TYPE, EMBED_API_KEY, EMBED_BASE_URL             | DashScope           |
| Neo4j     | NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD                   | 知识图谱                |
| Qdrant    | QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION               | 记忆向量                |
| 存储        | SQLITE_DB_PATH, MEMORY_DATA_DIR, LOG_DIR, XHS_USER_DATA_DIR | 本地路径                |
| 爬虫        | NOWCODER_COOKIE, NOWCODER_KEYWORDS, XHS_KEYWORDS            | 爬虫参数                |
| 调度        | SCHEDULER_ENABLE_NOWCODER, SCHEDULER_NOWCODER_HOURS         | 定时任务                |
| 对话        | DEFAULT_USER_ID, INTERVIEWER_MAX_STEPS                      | 默认用户、Agent 最大步数     |


---

## 十、调度器

**文件**：`backend/services/scheduler.py`

**任务**：


| 任务    | 触发             | 说明                            |
| ----- | -------------- | ----------------------------- |
| 牛客发现  | Cron 2,14 点    | 搜索关键词，写入 crawl_tasks          |
| 小红书发现 | Cron 3 点（默认关闭） | 需浏览器，建议手动                     |
| 任务处理  | Cron 每小时整点     | 从 crawl_tasks 取待处理，LLM 提取题目入库 |


**手动触发**：`POST /api/crawler/trigger`

---

## 十一、SM-2 遗忘曲线

### 11.1 评分标准（0-5 分）


| 分数  | 含义    | 对应情况           |
| --- | ----- | -------------- |
| 0   | 完全不会  | 没有思路，直接不知道     |
| 1   | 基本不会  | 有一点印象但说不清楚     |
| 2   | 大部分不会 | 只知道大致方向，细节缺失严重 |
| 3   | 勉强会   | 回答出要点但有遗漏或错误   |
| 4   | 基本掌握  | 回答基本正确，有小错误或遗漏 |
| 5   | 完全掌握  | 回答准确完整，有自己的理解  |


### 11.2 SM-2 更新公式

```python
# score < 3：答错，重置，明天重复
if score < 3:
    repetitions = 0
    interval_days = 1
    next_review_at = now + 1天
else:
    # 答对：更新间隔
    if repetitions == 0: interval_days = 1
    elif repetitions == 1: interval_days = 6
    else: interval_days = round(interval_days * easiness_factor)
    repetitions += 1
    easiness_factor = max(1.3, ef + 0.1 - (5-score)*(0.08 + (5-score)*0.02))
```

### 11.3 推荐优先级

1. 到期复习题（`next_review_at <= now`）
2. 薄弱点强化（novice/learning 标签）
3. 按公司/标签/难度过滤
4. 新题（未做过）

---

## 十二、知识补强

- 当 `score <= 2` 时，`KnowledgeRecommender` 查询 `study_records` 遗漏点 + `knowledge_resources` 学习资源
- 输出：错题回顾 + 遗漏点 + 推荐链接

---

## 十二.1 数据存储说明（Qdrant vs 爬取内容）

| 存储 | 存什么 | 说明 |
|------|--------|------|
| **SQLite** | 题目、做题记录、用户画像、爬虫任务 | 爬取的题目在 `questions` 表 |
| **Neo4j** | 题目节点 + 向量索引、图关系 | 题目向量用于 RAG 检索 |
| **Qdrant** | MemoryTool 四层记忆（用户学习历程） | **不存爬取题目**，仅用户记忆 |

**切换到本地 Qdrant 后**：本地 Qdrant 初始为空，用户记忆会随对话重新积累；爬取的题目仍在 SQLite/Neo4j，不受影响。

---

## 十二.2 LLM 解析失败记录

解析失败的样本会写入 `backend/data/llm_failures/`，便于后期微调：

| 文件 | 来源 | 内容 |
|------|------|------|
| `question_extract.jsonl` | 题目提取 | 面经原文 + LLM 原始返回 |
| `answer_eval.jsonl` | 答题评估 | 题目+用户答案 + LLM 原始返回 |

每行一个 JSON：`ts, source, input_preview, raw_output, error, metadata`。

---

## 十三、关键设计决策


| 决策                | 理由                               |
| ----------------- | -------------------------------- |
| HunterAgent 移除    | 管道步骤固定，用纯代码更可靠、省 token           |
| user_id 上下文注入     | 避免 Agent 解析失败导致「缺少 user_id」      |
| 思考步骤捕获            | 通过 stdout 拦截，不侵入 hello-agents 源码 |
| SQLite + Neo4j 双写 | SQLite 做过滤、统计；Neo4j 做图关系、向量检索    |
| 流式先推送 thinking    | 前端先展示推理，再打字机效果展示回复               |


### 13.1 未来优化方向

| 方向 | 说明 |
|------|------|
| **题目/答案分开存储** | 当前 question_text、answer_text 同存于 questions 表。可拆为 questions 表（题目元数据）+ answers 表（答案内容），便于按需加载、版本管理、权限控制（如答案仅在题库浏览时展示） |
| **知识图谱增强** | 题目已入库 Neo4j（Question 节点 + Tag/Company/Position 关系 + 向量索引）。可扩展：Answer 节点、答案要点与 Concept 的 COVERS 关系、题目-答案-知识点的三元组，支撑「按知识点查答案」「答案相似度」等能力 |


---

## 十四、附录：文件结构

```
wxr_agent/
├── backend/
│   ├── agents/
│   │   ├── architect_agent.py
│   │   ├── context.py
│   │   ├── interviewer_agent.py
│   │   ├── orchestrator.py
│   │   ├── prompts/
│   │   └── thinking_capture.py
│   ├── config/
│   │   └── config.py
│   ├── main.py
│   ├── services/
│   │   ├── crawler/
│   │   ├── hunter_pipeline.py
│   │   ├── scheduler.py
│   │   ├── sqlite_service.py
│   │   └── neo4j_service.py
│   └── tools/
│       ├── architect_tools.py
│       ├── hunter_tools.py
│       └── interviewer_tools.py
├── web/
│   └── src/
│       ├── views/ (BrowseView, ChatView, CollectView, IngestView, ReportView)
│       ├── components/
│       └── api.js
├── .env
├── run.py
└── requirements.txt
```

---

*本文档基于当前代码库整理，与实现保持一致。*