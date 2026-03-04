# 面经 Agent 完整设计方案

> 版本：v3.0 | 日期：2026-02-28  
> 基于 hello_agents 框架，融合 MemoryTool（四层记忆）、RAG、SM-2 遗忘曲线

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户 (CLI / FastAPI)                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────▼─────────────────┐
              │   InterviewSystemOrchestrator      │
              │   ┌──────────────────────────┐    │
              │   │  per-user MemoryTool 池    │    │
              │   │  {user_id: MemoryTool}    │    │
              │   └──────────────────────────┘    │
              └────────┬──────────┬────────┬──────┘
                       │          │        │
       ┌───────────────▼─┐  ┌─────▼──┐  ┌─▼──────────────────────┐
       │ ResourceHunter  │  │Knowled │  │    InterviewerAgent      │
       │  Agent (猎人)   │  │geArchi │  │   (PlanAndSolveAgent)    │
       │  ReActAgent     │  │tect    │  │                          │
       └────────┬────────┘  │Agent   │  │  Tool Registry:          │
                │           │ReAct   │  │  · memory (MemoryTool)   │
       ┌────────▼────────┐  └───┬────┘  │  · get_recommended_q    │
       │ Hunter Tools    │      │       │  · update_progress       │
       │ · web_crawler   │  ┌───▼────┐  │  · find_similar_q       │
       │ · extract_meta  │  │Archit  │  │  · filter_questions     │
       │ · extract_img   │  │Tools   │  │  · manage_note          │
       │ · sanitize_text │  │·meta   │  │  · get_mastery_report   │
       └─────────────────┘  │·struct │  │  · analyze_resume       │
                            │·dedup  │  │  · generate_evaluation  │
                            │·save   │  └──────────────┬──────────┘
                            └───┬────┘                 │
                                │        ┌─────────────▼──────────────┐
                                │        │  hello-agents MemoryTool    │
                                │        │  四层记忆系统（框架内置）    │
                                │        │  ┌──────────────────────┐  │
                                │        │  │ WorkingMemory (TTL)  │  │
                                │        │  │ EpisodicMemory       │  │
                                │        │  │ SemanticMemory       │  │
                                │        │  │ PerceptualMemory     │  │
                                │        │  └──────────────────────┘  │
                                │        └────────────────────────────┘
                                │
          ┌─────────────────────▼─────────────────────────────────┐
          │                   存储层 (Storage Layer)                │
          │  ┌─────────────┐  ┌────────────┐  ┌───────────────┐   │
          │  │ Neo4j 图库  │  │SQLite 关系 │  │ Qdrant 向量库 │   │
          │  │ (题目知识图 │  │库(SM-2数据 │  │(MemoryTool内  │   │
          │  │  谱+向量索  │  │ 用户画像等)│  │ 置,记忆向量)  │   │
          │  │  引题目RAG) │  │            │  │               │   │
          │  └─────────────┘  └────────────┘  └───────────────┘   │
          └───────────────────────────────────────────────────────┘
```

---

## 二、Agent 设计评估与改进

### 2.1 现有 Agent 合理性评估


| Agent                   | 类型                | 评估      | 问题                                                 |
| ----------------------- | ----------------- | ------- | -------------------------------------------------- |
| ResourceHunterAgent     | ReActAgent        | ✅ 合理    | OCR 是模拟的；缺 MetaExtractor                           |
| KnowledgeArchitectAgent | ReActAgent        | ✅ 合理    | `generate_embedding` 是空函数；KnowledgeStructurer 是占位符 |
| InterviewerAgent        | PlanAndSolveAgent | ⚠️ 基本合理 | 遗忘曲线算法太简单；缺 NoteTool、FilterTool                    |


### 2.2 Agent 改进建议

**ResourceHunterAgent** 新增工具：

- `MetaExtractor`：从面经文本中提取公司、岗位、业务线、难度等结构化元信息（用规则+LLM）

**KnowledgeArchitectAgent** 修复：

- 实现真实的 `generate_embedding`（调用 DashScope）
- 实现真实的 `KnowledgeStructurer`（调用 LLM 解析 JSON）
- 新增 `MetadataSaver`：将公司/岗位等元数据写入 SQLite 的 `questions` 表

**InterviewerAgent** 新增工具：

- `NoteTool`：用户主动记笔记（关联题目）
- `FilterTool`：按时间/关键词/公司/标签/难度过滤题目（纯 SQL，不需要 LLM）
- `MasteryReporter`：查询用户的标签掌握度报告

---

## 三、RAG 设计

### 3.1 是否需要 RAG？

**需要，且已经部分实现**。现有的 Neo4j 向量索引就是 RAG 的核心存储，但嵌入函数是空的需要修复。

### 3.2 RAG 的三个使用场景


| 场景              | 输入       | 检索目标            | 是否需要 LLM |
| --------------- | -------- | --------------- | -------- |
| **查重**（入库时）     | 新题文本     | 相似度 > 0.9 的题目   | 否（纯向量距离） |
| **举一反三**（答题后）   | 当前题目文本   | Top-K 相似题（排除自身） | 否        |
| **换个问法**（薄弱时）   | 知识点描述    | 相同知识点不同角度的题目    | 否        |
| **主题检索**（用户过滤时） | 用户输入的关键词 | 语义相关的题目列表       | 否        |


### 3.3 RAG 中存什么（向量化对象）

**向量化对象**：`题目文本（question_text）`

**不向量化**：答案（太长，信息冗余）、标签（用图关系表达更准确）

**元数据过滤字段**（在 Neo4j 节点属性上，支持精确过滤，不需要 LLM）：

- `company`：字节跳动、阿里巴巴 等
- `position`：后端、算法、前端 等
- `difficulty`：easy / medium / hard
- `source_platform`：nowcoder / xiaohongshu
- `question_type`：技术题 / 行为题 / 算法题 / 系统设计题
- `created_at`：时间范围过滤
- 标签（通过图关系 `HAS_TAG` 过滤）

### 3.4 RAG 检索流程

```
用户提问/过滤请求
       │
       ▼
[FilterTool] 构建过滤条件（公司/标签/难度/时间）
       │
       ▼ （如果是语义检索）
[generate_embedding] 对用户输入进行向量化
       │
       ▼
[Neo4j vector search] 召回 Top-K 候选题目
       │
       ▼
[元数据过滤] 在 WHERE 子句中应用精确过滤
       │
       ▼
返回结构化题目列表（无需 LLM 重排）
```

---

## 四、四层记忆设计（基于 hello-agents 框架 MemoryTool）

> 参考：[hello-agents 第八章 记忆与检索](https://datawhalechina.github.io/hello-agents/#/./chapter8/%E7%AC%AC%E5%85%AB%E7%AB%A0%20%E8%AE%B0%E5%BF%86%E4%B8%8E%E6%A3%80%E7%B4%A2)

### 4.1 框架记忆系统总体架构

hello-agents 框架提供了 `MemoryTool` 作为四层记忆的统一接口，底层由 `MemoryManager` 协调四种记忆类型模块：

```
hello-agents MemoryTool（框架内置）
├── 基础设施层 (Infrastructure Layer)
│   ├── MemoryManager      - 统一调度和协调
│   ├── MemoryItem         - 标准化记忆数据结构
│   ├── MemoryConfig       - 系统参数配置
│   └── BaseMemory         - 通用接口定义
├── 记忆类型层 (Memory Types Layer)  ← 四层记忆核心
│   ├── WorkingMemory      - 工作记忆（临时信息，TTL管理）
│   ├── EpisodicMemory     - 情景记忆（具体事件，时间序列）
│   ├── SemanticMemory     - 语义记忆（抽象知识，图谱关系）
│   └── PerceptualMemory   - 感知记忆（多模态数据）
├── 存储后端层 (Storage Backend Layer)
│   ├── QdrantVectorStore  - 向量存储（情景/语义/感知记忆）
│   ├── Neo4jGraphStore    - 图存储（语义记忆知识图谱）
│   └── SQLiteDocumentStore - 文档存储（情景记忆结构化数据）
└── 嵌入服务层 (Embedding Service Layer)
    ├── DashScopeEmbedding  - 云端 API（优先）
    ├── LocalTransformerEmbedding - 本地模型（离线备选）
    └── TFIDFEmbedding      - 轻量兜底
```

### 4.2 四层记忆详细说明与面经 Agent 的映射

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1: Working Memory（工作记忆）                              │
│  框架实现：纯内存存储 + TTL 自动清理 + TF-IDF/关键词混合检索     │
│  默认容量：50条 | TTL：60分钟 | 检索：TF-IDF向量+关键词          │
│                                                                  │
│  面经 Agent 用途：当前对话 session 的临时上下文                  │
│  存什么：                                                         │
│    · "用户当前正在回答：Redis 持久化题目"                         │
│    · "用户刚才说：我觉得RDB是全量快照..."                         │
│    · "当前 session 已出题数：3 道"                               │
│  importance: 0.4~0.7（临时信息，session结束后自动清理）          │
└──────────────────────────────────────────────────────────────────┘
                    ↓ consolidate（重要交互 → 情景记忆）
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2: Episodic Memory（情景记忆）                             │
│  框架实现：SQLite（结构化持久化）+ Qdrant（向量检索）             │
│  检索：结构化预过滤 + 语义向量检索，评分=(相似度×0.8+近因性×0.2)×重要性 │
│                                                                  │
│  面经 Agent 用途：记录用户的具体学习事件和经历                   │
│  存什么：                                                         │
│    · "2026-02-28 用户回答了【Redis主从复制】，得分4/5"           │
│    · "2026-02-28 完成了字节跳动后端模拟面试，平均分3.8"          │
│    · "2026-02-28 上传了简历，目标岗位：字节后端研发"             │
│    · "2026-02-28 记录笔记：Redis持久化=RDB全量+AOF增量"          │
│  importance: 0.7~0.9（重要学习事件）                             │
└──────────────────────────────────────────────────────────────────┘
                    ↓ consolidate（高频/重要模式 → 语义记忆）
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3: Semantic Memory（语义记忆）                             │
│  框架实现：Qdrant（向量检索）+ Neo4j（知识图谱）                  │
│  检索：向量检索×0.7 + 图检索×0.3，评分×重要性权重[0.8,1.2]      │
│  特点：自动提取实体和关系，构建知识图谱                           │
│                                                                  │
│  面经 Agent 用途：用户的长期知识画像和掌握特征（抽象概念级）     │
│  存什么：                                                         │
│    · "用户熟悉 Redis 基础（掌握等级: proficient）"               │
│    · "用户对 Kafka 消息队列掌握薄弱（mastery: novice）"          │
│    · "用户目标公司：字节跳动，目标岗位：后端研发"                │
│    · "用户技术栈：Java, Spring, Redis, MySQL, Kafka"             │
│    · "用户偏好从实际业务场景切入的题目"                          │
│  importance: 0.8~1.0（长期知识，高持久性）                       │
└──────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────────┐
│  Layer 4: Perceptual Memory（感知记忆）                           │
│  框架实现：按模态分离的 Qdrant 集合（text/image/audio）           │
│  检索：同模态向量检索 + 跨模态语义对齐                           │
│                                                                  │
│  面经 Agent 用途：处理多模态输入（简历图片、代码截图等）         │
│  存什么：                                                         │
│    · 用户上传的简历图片/PDF（modality=image）                    │
│    · 包含代码的截图（modality=image，OCR提取文本）               │
│    · 小红书面经图片中的题目（来自 VisualExtractor）              │
│  importance: 0.6~0.8（按内容重要性动态决定）                    │
└──────────────────────────────────────────────────────────────────┘
```

### 4.3 记忆生命周期管理

```python
# ── 每次对话开始时 ──
memory_tool.execute("add",
    content=f"用户开始练习，当前问题：{question}",
    memory_type="working",       # Layer 1
    importance=0.5,
    session_id=session_id
)

# ── 用户答完一道题后 ──
memory_tool.execute("add",
    content=f"用户回答了【{question_title}】，得分{score}/5。"
            f"回答要点：{key_points}",
    memory_type="episodic",      # Layer 2
    importance=0.7 + (score / 10),  # 得分越高重要性越高
    event_type="study_record",
    question_id=question_id,
    session_id=session_id
)

# ── 检测到知识掌握模式时（多次错误同一标签）──
memory_tool.execute("add",
    content=f"用户对【{tag}】标签的题目平均得分{avg_score}，"
            f"掌握等级：{mastery_level}",
    memory_type="semantic",      # Layer 3
    importance=0.85,
    knowledge_type="user_mastery",
    tag=tag
)

# ── session 结束时：整合 + 遗忘 ──
# 将重要的工作记忆升级为情景记忆
memory_tool.execute("consolidate",
    from_type="working",
    to_type="episodic",
    importance_threshold=0.7
)
# 清理低价值工作记忆
memory_tool.execute("forget",
    strategy="importance_based",
    threshold=0.3
)
```

### 4.4 MemoryTool 操作速查


| 操作            | 用途      | 面经 Agent 典型调用               |
| ------------- | ------- | --------------------------- |
| `add`         | 添加记忆    | 记录答题事件、用户偏好、当前上下文           |
| `search`      | 语义搜索记忆  | "用户学过哪些Redis题？"             |
| `consolidate` | 记忆整合提升  | session结束时 working→episodic |
| `forget`      | 遗忘低价值记忆 | 定期清理过期工作记忆                  |
| `summary`     | 获取记忆摘要  | 生成学习进度总结                    |
| `stats`       | 统计信息    | 查看各类记忆数量                    |


### 4.5 记忆 vs RAG 的职责分工


| 系统                    | 存储对象                            | 检索目的           |
| --------------------- | ------------------------------- | -------------- |
| **MemoryTool（四层记忆）**  | 用户的学习历程、偏好、掌握程度                 | 个性化：了解"这个用户"是谁 |
| **Neo4j + RAG（面试题库）** | 全量面试题目（question/answer/tags）    | 出题：从题库里找合适的题   |
| **SQLite（SM-2数据）**    | 遗忘曲线参数（EF、interval、next_review） | 精确计算：下次复习时间    |


---

## 五、数据库完整设计

### 5.1 SQLite 表设计

#### 表 1：`questions`（题目元数据补充表）

> 与 Neo4j 双写，提供高效的结构化过滤；Neo4j 提供向量检索。


| 字段                | 类型       | 说明                        | 来源                         |
| ----------------- | -------- | ------------------------- | -------------------------- |
| `q_id`            | TEXT PK  | 唯一题目ID，格式：`TAG-xxxxxx`    | BaseManager 生成             |
| `question_text`   | TEXT     | 题目正文                      | KnowledgeStructurer（LLM解析） |
| `answer_text`     | TEXT     | 参考答案                      | KnowledgeStructurer（LLM解析） |
| `difficulty`      | TEXT     | 难度：easy/medium/hard       | MetaExtractor（规则+LLM）      |
| `question_type`   | TEXT     | 技术题/行为题/算法题/系统设计          | KnowledgeStructurer（LLM分类） |
| `source_platform` | TEXT     | nowcoder / xiaohongshu    | CrawlerTool（域名判断）          |
| `source_url`      | TEXT     | 来源帖子链接                    | CrawlerTool                |
| `company`         | TEXT     | 公司名称，如"字节跳动"              | MetaExtractor（规则匹配+LLM）    |
| `position`        | TEXT     | 岗位，如"后端研发"                | MetaExtractor（规则匹配+LLM）    |
| `business_line`   | TEXT     | 业务线，如"搜索/推荐/广告"           | MetaExtractor（规则匹配）        |
| `topic_tags`      | TEXT     | JSON数组，如`["Redis","分布式"]` | KnowledgeStructurer（LLM提取） |
| `created_at`      | DATETIME | 入库时间                      | BaseManager（自动填充）          |
| `updated_at`      | DATETIME | 最后更新时间                    | BaseManager（自动更新）          |


#### 表 2：`user_profiles`（用户画像 — 语义记忆层）


| 字段                 | 类型       | 说明                | 来源                        |
| ------------------ | -------- | ----------------- | ------------------------- |
| `user_id`          | TEXT PK  | 用户唯一标识            | 用户输入/系统生成                 |
| `resume_text`      | TEXT     | 简历原文              | 用户粘贴提供                    |
| `tech_stack`       | TEXT     | JSON数组，技术栈标签      | ResumeAnalysisTool（LLM提取） |
| `target_company`   | TEXT     | 目标公司，如"字节跳动"      | 用户输入                      |
| `target_position`  | TEXT     | 目标岗位，如"后端"        | 用户输入                      |
| `experience_level` | TEXT     | junior/mid/senior | ResumeAnalysisTool（LLM判断） |
| `preferred_topics` | TEXT     | JSON数组，偏好练习的主题    | 用户设置                      |
| `created_at`       | DATETIME | 注册时间              | 系统自动                      |
| `updated_at`       | DATETIME | 最后更新时间            | 系统自动                      |


#### 表 3：`user_tag_mastery`（标签掌握度 — 语义记忆层）

> 这是推荐引擎的核心数据，记录用户对每个技术标签的掌握程度。


| 字段               | 类型                       | 说明                                | 来源                         |
| ---------------- | ------------------------ | --------------------------------- | -------------------------- |
| `id`             | INTEGER PK AUTOINCREMENT | 自增主键                              | 系统自动                       |
| `user_id`        | TEXT                     | 用户ID                              | `study_records` 聚合         |
| `tag`            | TEXT                     | 技术标签，如"Redis"                     | `questions.topic_tags`     |
| `total_attempts` | INTEGER                  | 该标签总做题次数                          | 每次 ProgressTracker 调用后更新   |
| `correct_count`  | INTEGER                  | 得分>=3的次数                          | 每次 ProgressTracker 调用后更新   |
| `avg_score`      | REAL                     | 平均分（0-5）                          | 每次 ProgressTracker 调用后更新   |
| `mastery_level`  | TEXT                     | novice/learning/proficient/expert | 由avg_score和correct_count计算 |
| `last_practiced` | DATETIME                 | 最后练习时间                            | ProgressTracker 更新         |
| `last_updated`   | DATETIME                 | 记录最后更新时间                          | 系统自动                       |


**掌握等级判断规则**（纯计算，不需要LLM）：

```
novice:     total_attempts < 3  OR  avg_score < 2.0
learning:   avg_score >= 2.0 AND avg_score < 3.5
proficient: avg_score >= 3.5 AND avg_score < 4.5
expert:     avg_score >= 4.5 AND correct_count >= 5
```

#### 表 4：`study_records`（做题记录 — 情景记忆层，改进版）

> 加入 SM-2 算法所需字段，支持遗忘曲线推荐。


| 字段                | 类型                       | 说明             | 来源                        |
| ----------------- | ------------------------ | -------------- | ------------------------- |
| `id`              | INTEGER PK AUTOINCREMENT | 自增主键           | 系统自动                      |
| `user_id`         | TEXT                     | 用户ID           | 用户Session                 |
| `question_id`     | TEXT                     | 题目ID           | SmartRecommendationEngine |
| `session_id`      | TEXT                     | 关联的面试Session   | interview_sessions表       |
| `score`           | INTEGER                  | 用户得分 0-5       | InterviewerAgent 评估       |
| `user_answer`     | TEXT                     | 用户的回答原文        | 用户输入                      |
| `ai_feedback`     | TEXT                     | AI 的详细评价       | InterviewerAgent（LLM生成）   |
| `easiness_factor` | REAL                     | SM-2易度系数，初始2.5 | SM-2算法计算                  |
| `repetitions`     | INTEGER                  | 连续正确回答次数       | SM-2算法计算                  |
| `interval_days`   | INTEGER                  | 下次复习间隔（天）      | SM-2算法计算                  |
| `next_review_at`  | DATETIME                 | 下次应复习的时间       | SM-2算法计算                  |
| `studied_at`      | DATETIME                 | 本次作答时间         | 系统自动                      |


#### 表 5：`interview_sessions`（面试会话 — 情景记忆层）


| 字段                     | 类型                       | 说明                            | 来源                        |
| ---------------------- | ------------------------ | ----------------------------- | ------------------------- |
| `id`                   | INTEGER PK AUTOINCREMENT | 自增主键                          | 系统自动                      |
| `session_id`           | TEXT UNIQUE              | Session唯一ID（UUID）             | Orchestrator 生成           |
| `user_id`              | TEXT                     | 用户ID                          | 用户Session                 |
| `session_type`         | TEXT                     | mock/practice/review/weakness | 用户选择                      |
| `topic_focus`          | TEXT                     | 本次练习主题，如"Redis+MySQL"         | 用户选择/系统推荐                 |
| `target_company`       | TEXT                     | 目标公司（模拟面试时用）                  | 用户选择                      |
| `conversation_history` | TEXT                     | JSON 存储对话历史（最近20轮）            | Working Memory            |
| `start_time`           | DATETIME                 | 开始时间                          | 系统自动                      |
| `end_time`             | DATETIME                 | 结束时间                          | 系统自动（session结束时更新）        |
| `total_questions`      | INTEGER                  | 本次练了几题                        | 系统统计                      |
| `avg_score`            | REAL                     | 本次平均分                         | 系统计算                      |
| `ai_summary`           | TEXT                     | AI 生成的总结和建议                   | InterviewEvaluator（LLM生成） |
| `weak_tags`            | TEXT                     | JSON 本次薄弱标签                   | 系统计算                      |


#### 表 6：`user_notes`（用户笔记 — Note 工具）


| 字段            | 类型                       | 说明                          | 来源               |
| ------------- | ------------------------ | --------------------------- | ---------------- |
| `id`          | INTEGER PK AUTOINCREMENT | 自增主键                        | 系统自动             |
| `note_id`     | TEXT UNIQUE              | 笔记唯一ID（UUID）                | NoteTool 生成      |
| `user_id`     | TEXT                     | 用户ID                        | 用户Session        |
| `question_id` | TEXT                     | 关联题目ID（可为空）                 | 用户或系统填充          |
| `title`       | TEXT                     | 笔记标题                        | 用户输入             |
| `content`     | TEXT                     | 笔记正文（支持Markdown）            | 用户输入             |
| `tags`        | TEXT                     | JSON 标签数组                   | 用户输入或从question继承 |
| `note_type`   | TEXT                     | concept/mistake/tip/summary | 用户选择             |
| `created_at`  | DATETIME                 | 创建时间                        | 系统自动             |
| `updated_at`  | DATETIME                 | 最后修改时间                      | 系统自动             |


#### 表 7：`crawl_logs`（爬取日志，扩展版）


| 字段                    | 类型                       | 说明                       | 来源                         |
| --------------------- | ------------------------ | ------------------------ | -------------------------- |
| `id`                  | INTEGER PK AUTOINCREMENT | 自增主键                     | 系统自动                       |
| `url`                 | TEXT                     | 爬取的URL                   | 用户/定时任务提供                  |
| `status`              | TEXT                     | success/failed/duplicate | CrawlerTool                |
| `title`               | TEXT                     | 帖子标题                     | CrawlerTool 解析             |
| `source_platform`     | TEXT                     | nowcoder/xiaohongshu     | CrawlerTool（域名判断）          |
| `company`             | TEXT                     | 帖子涉及公司                   | MetaExtractor              |
| `position`            | TEXT                     | 帖子涉及岗位                   | MetaExtractor              |
| `questions_extracted` | INTEGER                  | 从该帖子提取的题目数               | KnowledgeArchitectAgent 统计 |
| `crawled_at`          | DATETIME                 | 爬取时间                     | 系统自动                       |


#### 表 8：`ingestion_logs`（入库日志，保留原有）


| 字段            | 类型                       | 说明      | 来源                  |
| ------------- | ------------------------ | ------- | ------------------- |
| `id`          | INTEGER PK AUTOINCREMENT | 自增主键    | 系统自动                |
| `question_id` | TEXT                     | 入库题目ID  | BaseManager         |
| `source_url`  | TEXT                     | 来源链接    | BaseManager         |
| `tags`        | TEXT                     | JSON 标签 | KnowledgeStructurer |
| `created_at`  | DATETIME                 | 入库时间    | 系统自动                |


---

### 5.2 Neo4j 图设计

#### 节点类型


| 节点标签       | 属性                                                                                                              | 说明              |
| ---------- | --------------------------------------------------------------------------------------------------------------- | --------------- |
| `Question` | `id, text, answer, embedding(1024维), difficulty, question_type, source_platform, company, position, created_at` | 面试题主体           |
| `Tag`      | `name, category(技术栈/行为/系统设计)`                                                                                   | 技术标签            |
| `Company`  | `name, industry`                                                                                                | 公司节点            |
| `Position` | `name, category(研发/算法/产品)`                                                                                      | 岗位节点            |
| `Concept`  | `name, description`                                                                                             | 知识点概念（如"CAP定理"） |


#### 关系类型


| 关系               | 方向                  | 属性            | 说明                       |
| ---------------- | ------------------- | ------------- | ------------------------ |
| `HAS_TAG`        | Question → Tag      | 无             | 题目归属标签                   |
| `FROM_COMPANY`   | Question → Company  | 无             | 题目来自哪家公司的面试              |
| `FOR_POSITION`   | Question → Position | 无             | 题目适用于哪个岗位                |
| `COVERS_CONCEPT` | Question → Concept  | 无             | 题目考察哪个知识点                |
| `RELATED_TO`     | Question ↔ Question | `score:float` | 相似题目（查重/举一反三用，预计算）       |
| `VARIANT_OF`     | Question → Question | 无             | 换个问法的变体题                 |
| `PREREQUISITE`   | Tag → Tag           | 无             | 标签依赖关系（学 Redis 前先学 缓存基础） |


#### 向量索引

```cypher
CREATE VECTOR INDEX question_embeddings IF NOT EXISTS
FOR (n:Question) ON (n.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1024,
  `vector.similarity_function`: 'cosine'
}}
```

---

## 六、掌握程度设计（SM-2 算法）

### 6.1 SM-2 算法原理

基于 Anki 使用的间隔重复算法（SuperMemo SM-2），根据用户评分动态调整复习间隔：

**评分标准（用户答题后 AI 打分 0-5 分）**：


| 分数  | 含义    | 对应情况           |
| --- | ----- | -------------- |
| 0   | 完全不会  | 没有思路，直接不知道     |
| 1   | 基本不会  | 有一点印象但说不清楚     |
| 2   | 大部分不会 | 只知道大致方向，细节缺失严重 |
| 3   | 勉强会   | 回答出要点但有遗漏或错误   |
| 4   | 基本掌握  | 回答基本正确，有小错误或遗漏 |
| 5   | 完全掌握  | 回答准确完整，有自己的理解  |


**SM-2 更新公式**：

```python
def update_sm2(score: int, easiness_factor: float, repetitions: int, interval_days: int):
    """
    score: 0-5
    easiness_factor: 初始 2.5，最小 1.3
    repetitions: 连续正确次数（score >= 3 才算正确）
    interval_days: 下次复习间隔天数
    """
    if score < 3:
        # 答错：重置，明天重复
        repetitions = 0
        interval_days = 1
    else:
        # 答对：更新间隔
        if repetitions == 0:
            interval_days = 1
        elif repetitions == 1:
            interval_days = 6
        else:
            interval_days = round(interval_days * easiness_factor)
        repetitions += 1
    
    # 更新易度系数（绝对不低于 1.3）
    easiness_factor = max(1.3, easiness_factor + 0.1 - (5 - score) * (0.08 + (5 - score) * 0.02))
    
    from datetime import datetime, timedelta
    next_review_at = datetime.now() + timedelta(days=interval_days)
    
    return easiness_factor, repetitions, interval_days, next_review_at
```

### 6.2 掌握程度展示

**个人标签掌握度报告**（MasteryReporter 工具输出）：

```
📊 你的技术掌握度报告（2026-02-28）

🏆 已精通（Expert）：
  ✅ MySQL 基础查询（avg: 4.8/5, 做了12题）

📚 良好掌握（Proficient）：
  ✅ Redis 缓存原理（avg: 4.1/5, 做了8题）
  ✅ HTTP 协议（avg: 3.9/5, 做了6题）

📖 学习中（Learning）：
  ⚠️ 分布式事务（avg: 2.8/5, 做了5题）
  ⚠️ JVM 调优（avg: 3.2/5, 做了4题）

❌ 待提升（Novice）：
  🔴 Kafka 消息队列（avg: 1.5/5, 做了2题）
  🔴 K8s 容器编排（avg: 0/5, 做了0题）

💡 建议：优先复习「分布式事务」和加强「Kafka」的练习
```

---

## 七、推荐算法设计

### 7.1 推荐优先级（SmartRecommendationEngine）

```
推荐决策树：
┌─ 是否有到期复习题（next_review_at <= now）？
│    YES → 返回到期复习题（遗忘曲线优先）
│    NO ↓
├─ 当前是薄弱点强化模式？
│    YES → 从 novice/learning 级别的 tag 中随机取一题
│    NO ↓
├─ 用户指定了 topic/company/difficulty？
│    YES → [FilterTool] 精确过滤 + 语义检索
│    NO ↓
└─ 推荐用户未做过的新题（按 tech_stack 标签匹配）
```

### 7.2 四种推荐模式


| 模式          | 触发条件        | 算法                              | 是否需要 LLM |
| ----------- | ----------- | ------------------------------- | -------- |
| **遗忘曲线复习**  | 有到期题目       | SM-2 日期比较（SQL过滤）                | 否        |
| **相似题举一反三** | 用户答完一题后     | 向量余弦相似度（Neo4j）                  | 否        |
| **换个问法**    | 用户得分>=4，想进阶 | `VARIANT_OF` 图关系查询              | 否        |
| **薄弱点强化**   | 主动触发/自动检测   | `user_tag_mastery` 表查 novice 标签 | 否        |


### 7.3 完整推荐流程示例

```
用户说：「我想练习，不限主题」
       ↓
SmartRecommendationEngine.run({user_id: "wxr", topic: null})
       ↓
Step1: 查 study_records WHERE next_review_at <= now AND user_id = "wxr"
       → 找到 "Redis主从复制" 到期了（3天前做过，得了2分）
       ↓
Step2: 返回复习题 → AI 提问 "Redis 主从复制的同步方式是什么？"
       ↓
用户回答...
       ↓
InterviewerAgent 评估答案 → score = 4
       ↓
ProgressTracker 调用 update_sm2(score=4) → interval_days = 6
       ↓
AI 反馈："回答不错！你知道半同步复制吗？" → 触发举一反三
       ↓
SimilaritySearchTool 检索相关题 → 推荐 "Redis Sentinel 和 Cluster 的区别"
```

---

## 八、工具完整设计

### 8.1 ResourceHunter 工具集


| 工具                | Tool Name            | 输入             | 输出                      | 实现方式                                 |
| ----------------- | -------------------- | -------------- | ----------------------- | ------------------------------------ |
| `CrawlerTool`     | `web_crawler`        | url            | 清洗后的文本                  | requests + BeautifulSoup / xhs-crawl |
| `MetaExtractor`   | `extract_meta`       | raw_text       | JSON（公司/岗位/业务线/难度/帖子类型） | 规则优先 + LLM 兜底                        |
| `VisualExtractor` | `extract_image_text` | text_with_urls | 追加OCR结果的文本              | 调用多模态 LLM Vision API                 |
| `TextSanitizer`   | `sanitize_text`      | raw_text       | 清洗后的文本                  | 正则规则                                 |


### 8.2 KnowledgeArchitect 工具集


| 工具                    | Tool Name             | 输入              | 输出                                              | 实现方式               |
| --------------------- | --------------------- | --------------- | ----------------------------------------------- | ------------------ |
| `KnowledgeStructurer` | `structure_knowledge` | raw_text + meta | JSON 题目列表（question/answer/tags/difficulty/type） | LLM（低温度，JSON模式）    |
| `DuplicateChecker`    | `check_duplicate`     | question        | NEW 或 DUPLICATE + 相似题ID                         | Neo4j 向量检索（阈值0.92） |
| `BaseManager`         | `save_knowledge`      | 结构化题目数据         | SUCCESS + q_id                                  | Neo4j + SQLite 双写  |


### 8.3 Interviewer 工具集


| 工具                          | Tool Name                  | 输入                                                                   | 输出                 | 实现方式                 |
| --------------------------- | -------------------------- | -------------------------------------------------------------------- | ------------------ | -------------------- |
| `SmartRecommendationEngine` | `get_recommended_question` | user_id, topic?, mode?                                               | 题目详情（含SM-2状态）      | SM-2算法 + SQL + Neo4j |
| `ProgressTracker`           | `update_progress`          | user_id, question_id, score, user_answer, feedback                   | SM-2更新结果 + 标签掌握度更新 | SM-2算法 + SQL         |
| `SimilaritySearchTool`      | `find_similar_questions`   | query_text, top_k?, exclude_ids?                                     | 相似题列表              | Neo4j 向量检索           |
| `FilterTool`                | `filter_questions`         | company?, tags?, difficulty?, date_from?, date_to?, keyword?, limit? | 过滤后的题目列表           | 纯 SQL（SQLite）        |
| `NoteTool`                  | `manage_note`              | action(create/update/list/delete), note_id?, user_id, ...            | 笔记操作结果             | SQLite CRUD          |
| `MasteryReporter`           | `get_mastery_report`       | user_id, tags?[]                                                     | 掌握度报告（结构化文本）       | SQL 聚合查询             |
| `ResumeAnalysisTool`        | `analyze_resume`           | resume_text                                                          | 技术栈JSON + 经验等级     | LLM 提取               |
| `InterviewEvaluator`        | `generate_evaluation`      | user_id, session_id?                                                 | 评估报告 + 弱点分析        | SQL聚合 + LLM总结        |


---

## 九、交互方案设计

### 9.1 四种练习模式

#### 模式 A：自由练习（Practice）

```
用户：「开始练习，我想练 Redis」
 → SmartRecommendationEngine(topic="Redis", mode="practice")
 → 返回一道 Redis 题
用户：回答
 → InterviewerAgent 评估（LLM），ProgressTracker 更新 SM-2
 → 根据得分决定后续：
    score < 3 → 提示关键点 + 推荐更简单的基础题
    score 3-4 → 给反馈 + 问"是否继续下一题"
    score >= 4 → 夸奖 + 推荐"换个问法"进阶题
```

#### 模式 B：模拟面试（Mock Interview）

```
用户：「我要模拟字节跳动后端面试」
 → 创建 session（type=mock, company=字节, position=后端）
 → ResumeAnalysisTool 分析简历（如果有）
 → 按"开场→技术问题→场景题→候选人提问→评估"流程推进
 → 每次出题优先查 company=字节 的历史题
 → session 结束后 InterviewEvaluator 生成报告
```

#### 模式 C：遗忘曲线复习（Review）

```
用户：「今天该复习什么了？」
 → SmartRecommendationEngine(mode="review")
 → SQL: SELECT * FROM study_records WHERE next_review_at <= now() AND user_id=?
 → 返回所有到期题目数量 + 第一道题
 → 用户完成所有到期题后，提示"今日复习完成✅"
```

#### 模式 D：薄弱点强化（Weakness）

```
用户：「帮我强化一下薄弱点」
 → MasteryReporter 获取 novice/learning 级别的标签
 → 按平均分从低到高排序
 → SmartRecommendationEngine 从最薄弱的标签取题
 → 连续练习 5 题同一标签
 → 结束后更新 user_tag_mastery
```

### 9.2 笔记交互

```
用户：「帮我把这道题记个笔记，重点是：Redis 持久化分 RDB 和 AOF 两种」
 → NoteTool.create(question_id=current_q_id, content="...", note_type="concept")
 → 返回：「笔记已保存！Tags: [Redis, 持久化]」

用户：「显示我所有 Redis 相关的笔记」
 → NoteTool.list(user_id=?, tags=["Redis"])
 → 返回格式化的笔记列表
```

### 9.3 过滤查询（不需要 LLM）

```
用户：「给我看看最近一周新收录的字节跳动后端题」
 → FilterTool({
     company: "字节跳动",
     position: "后端",
     date_from: "2026-02-21",
     limit: 10
   })
 → 纯 SQL 查询，秒级返回，无需 LLM
```

---

## 十、代码修改计划

### 需要新增/修改的文件


| 文件                                             | 操作                                                            | 优先级 |
| ---------------------------------------------- | ------------------------------------------------------------- | --- |
| `backend/services/sqlite_service.py`           | 新增5张表，新增CRUD方法                                                | P0  |
| `backend/services/neo4j_service.py`            | 新增Company/Position/Concept节点和关系                               | P1  |
| `backend/tools/architect_tools.py`             | 实现 generate_embedding，完善 KnowledgeStructurer，新增 MetaExtractor | P0  |
| `backend/tools/hunter_tools.py`                | 新增 MetaExtractor                                              | P0  |
| `backend/tools/interviewer_tools.py`           | 加入SM-2算法，新增 NoteTool/FilterTool/MasteryReporter               | P0  |
| `backend/agents/prompts/interviewer_prompt.py` | 更新 Prompt，加入新工具使用说明                                           | P1  |
| `backend/agents/prompts/architect_prompt.py`   | 更新 Prompt                                                     | P1  |
| `backend/agents/hunter_agent.py`               | 注册 MetaExtractor                                              | P1  |
| `backend/agents/architect_agent.py`            | 按需调整                                                          | P2  |
| `backend/main.py`                              | 增加模式选择API，笔记API                                               | P2  |


---

## 十一、关键设计决策说明

### Q1: 为什么用 Neo4j + SQLite 双存储，而不只用一个？

- **Neo4j**：擅长图关系（标签关联、相似推荐）和向量检索（RAG）
- **SQLite**：擅长结构化过滤（时间范围、公司名、难度等），聚合统计（掌握度计算），操作简单

两者互补：Neo4j 做"找相关题目"，SQLite 做"按条件筛选题目"。

### Q2: 为什么推荐算法不需要 LLM？

过滤（时间/公司/标签/难度）是精确匹配，用 SQL 既快又准。  
相似度排序用向量距离，不需要 LLM。  
只有**评估用户答案**和**生成反馈**需要 LLM，其他都是确定性逻辑。

### Q3: SM-2 算法 vs 简单固定间隔的区别？


| 对比     | 简单固定间隔（原设计） | SM-2（新设计）   |
| ------ | ----------- | ----------- |
| 算法复杂度  | 低           | 中           |
| 个性化    | 否（所有人相同）    | 是（根据历史表现调整） |
| 效率     | 低（会过度复习擅长的） | 高（聪明地分配时间）  |
| 遗忘曲线拟合 | 粗糙          | 精确          |


### Q4: RAG 的向量维度为什么是 1024？

DashScope 的 `text-embedding-v3` 默认输出 1024 维，与 Neo4j 向量索引配置一致。

---

---

## 九、知识补强推荐设计

### 9.1 需求背景

用户在练习中，某些知识点反复答不好（如 Redis AOF 重写、MySQL MVCC）。
单纯靠 SM-2 遗忘曲线重复出题不够——用户需要知道：

1. **我在这块哪里没掌握好**（近期错题 + 具体遗漏点）
2. **我该去哪里系统学**（推荐对应章节/文章）

### 9.2 数据流

```
用户答题 → update_progress(score, ai_feedback=<具体遗漏描述>) → study_records 表
                                    ↓
当 score ≤ 2 时
                                    ↓
InterviewerAgent 调用 get_knowledge_recommendation(tags=[...])
                                    ↓
KnowledgeRecommender 工具
  ├─ 查 study_records WHERE score<3 AND tag IN [...]  ← get_weak_study_records()
  │       返回：题目文本 + ai_feedback（含遗漏点描述）
  │
  └─ 查 knowledge_resources WHERE tags LIKE ...       ← get_resources_by_tags()
          返回：标题 + URL + 描述
                                    ↓
输出：错题回顾 + 遗漏点 + 学习资源推荐
```

### 9.3 knowledge_resources 表设计


| 字段            | 类型         | 说明                              |
| ------------- | ---------- | ------------------------------- |
| resource_id   | TEXT PK    | 唯一ID，如 `RES-Redis-001`          |
| title         | TEXT       | 资源标题                            |
| url           | TEXT       | 链接                              |
| description   | TEXT       | 内容摘要（≤100字）                     |
| tags          | TEXT(JSON) | 相关技术标签，如 `["Redis","AOF"]`      |
| resource_type | TEXT       | article/video/github/problemset |
| source        | TEXT       | 来源站点，如 "小林coding","JavaGuide"   |


**预置资源覆盖**（首次运行自动 seed）：

- Redis（持久化/主从/哨兵/缓存问题/数据结构）
- MySQL（索引/事务锁/日志）
- 操作系统（进程线程/内存/死锁）
- 计算机网络（TCP/HTTP-HTTPS）
- Java（集合/JVM/并发）
- 分布式（事务/CAP/Kafka）
- 算法（二叉树/动态规划/滑动窗口）
- 系统设计（缓存/消息队列）

### 9.4 遗漏点提取策略

`ai_feedback` 字段由 InterviewerAgent 写入，要求格式包含明确的遗漏描述：

```
评价内容：回答了大方向，但有以下遗漏：
- 未提到 AOF 重写的 BGREWRITEAOF 命令触发时机
- 忘记了子进程重写期间父进程数据变更的处理方式（aof_rewrite_buf）
- 对 RDB 和 AOF 的性能权衡描述不完整
```

`KnowledgeRecommender` 用正则切句，筛选含「遗漏/未提到/忘记/记错/不完整」等词的句子呈现给用户。

### 9.5 连续薄弱自动触发

Agent 在同一 session 内追踪每个 tag 的失误次数：

- 同一 tag **累计 ≥ 2 次**得分 ≤ 2 → 主动触发知识推荐
- 将薄弱点写入 **语义记忆**（importance=0.9），下次 session 仍会优先复习

---

## 十、智能图片决策设计（ContentValidator）

### 10.1 需求背景

爬取帖子分为三类：


| 类型    | 正文状态             | 图片状态    | 应对策略        |
| ----- | ---------------- | ------- | ----------- |
| 纯文字面经 | 题目完整（400+字，4+问句） | 无/少量图   | 跳过 OCR，直接处理 |
| 图片面经  | 很少（<200字或<3问句）   | 多张图片    | 触发 OCR      |
| 混合面经  | 有一些内容（200~400字）  | 有图（≥2张） | 触发 OCR      |
| 非面经内容 | 无关（关键词命中<2）      | 任意      | 整体跳过        |


### 10.2 判断逻辑

```python
# Step 1：面试相关性（关键词命中数 >= 2）
keyword_hits >= 2 → relevant = True
（小红书/牛客来源降低门槛：>= 1 即可）

# Step 2：内容完整性
clean_len >= 400 AND question_hits >= 4  → needs_ocr = False  (sufficient)
clean_len < 200  OR  question_hits < 3   → needs_ocr = (image_count > 0)  (insufficient)
else 200≤len<400                         → needs_ocr = (image_count >= 2)  (partial)
```

**面试相关关键词**（共 30+）：
面试面经、题目、问答、考察、岗位、技术栈、算法题、系统设计、
校招、社招、手撕、redis、mysql、java、spr、ing、kafka、分布式…

**问题特征词**（共 15+）：
？、如何、为什么、什么是、区别、原理、怎么、讲一下、说说…

### 10.3 工作流变化

**旧流程**（总是 OCR）：

```
爬取 → 清洗 → OCR所有图片 → 提取元信息 → 输出
```

**新流程**（按需 OCR）：

```
爬取 → 清洗 → ContentValidator校验 
                    ├─ 不相关 → 终止
                    ├─ 相关 + 不需OCR → 提取元信息 → 输出（节省约60%OCR调用）
                    └─ 相关 + 需要OCR → OCR → 提取元信息 → 输出
```

### 10.4 `validate_content` 返回格式

```json
{
  "relevant": true,
  "needs_ocr": false,
  "reason": "正文内容充足（512字，7个问题特征），无需识别图片",
  "content_quality": "sufficient",
  "image_count": 3,
  "keyword_hits": ["面试", "Redis", "MySQL"],
  "question_pattern_count": 7
}
```

---

*本文档由 AI 辅助生成，对应代码修改见各工具/服务文件。*