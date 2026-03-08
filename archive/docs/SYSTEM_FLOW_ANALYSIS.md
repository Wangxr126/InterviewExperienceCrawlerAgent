# 系统流程完整分析 - python run.py

> **重要提示**：本文档记录了 `python run.py` 的完整工作流程和所有关键逻辑，这些逻辑**不能修改**！

## 📋 目录

1. [启动流程](#启动流程)
2. [核心调度器](#核心调度器)
3. [爬虫管道](#爬虫管道)
4. [题目提取流程](#题目提取流程)
5. [数据存储](#数据存储)
6. [关键文件清单](#关键文件清单)
7. [可归档文件](#可归档文件)

---

## 启动流程

### 1. run.py（入口）

```
run.py
  ↓
检查 Python 环境（NewCoderAgent）
  ↓
检查依赖（uvicorn, fastapi）
  ↓
检查 Neo4j 连接（localhost:7687）
  ↓
启动 uvicorn backend.main:app
```

**关键逻辑**：

- 固定使用 `C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe`
- 如果当前环境不对，自动切换并重启
- 默认端口 8000，可通过 `--port` 修改

### 2. backend/main.py（FastAPI 应用）

```python
@app.on_event("startup")
async def startup_event():
    # 1. 加载 .env 配置
    # 2. 创建必要目录（logs, data, memory, xhs_user_data, post_images）
    # 3. 配置 loguru 日志（终端彩色 + 文件滚动）
    # 4. 安装思考步骤捕获器（thinking_capture）
    # 5. 打印 LLM 配置（Miner/Interviewer Agent）
    # 6. 启动爬虫调度器 crawl_scheduler.start()
    # 7. 可选：预热 LLM（避免首次超时）
```

**关键逻辑**：

- **必须最先加载 .env**（确保所有配置正确）
- **调度器在 FastAPI 启动时自动启动**
- 日志统一到 loguru，支持彩色输出

---

## 核心调度器

### backend/services/scheduler.py

**职责**：

1. 定时发现新帖子（牛客/小红书）→ 写入 `crawl_tasks` 队列
2. 定时处理待爬取任务 → 爬全文 → LLM 提取题目 → 写入数据库
3. 提供手动触发接口

**定时策略**（从 .env 读取）：

```python
# 牛客发现任务：每天 02:00 / 14:00（可配置 SCHEDULER_NOWCODER_HOURS）
CronTrigger(hour="2,14", minute=0)

# 任务处理器：每小时整点（可配置 SCHEDULER_PROCESS_MINUTE）
CronTrigger(minute=0)
```

**核心函数**：

#### 1. `_run_nowcoder_discovery(keywords, max_pages)`

```
调用 NowcoderCrawler.discover()
  ↓
遍历关键词，爬取帖子列表（最多 max_pages 页）
  ↓
提取元信息（标题、公司、岗位、难度等）
  ↓
写入 crawl_tasks 表（状态=pending）
  ↓
返回 (新增数, 发现列表)
```

#### 2. `_run_xhs_discovery(headless)`

```
调用 XHSCrawler.discover()
  ↓
Playwright 启动浏览器（headless=False 时弹窗扫码）
  ↓
搜索关键词，爬取笔记列表
  ↓
直接抓取正文（XHS API）
  ↓
下载图片到 post_images/TASK_XXX/
  ↓
写入 crawl_tasks 表（状态=fetched，已有正文）
  ↓
返回新增数
```

**重要**：XHS 爬虫必须用 `subprocess.Popen` 启动独立进程，否则 Windows 上 headless=False 会崩溃（exit code 21）。

#### 3. `_process_pending_tasks(batch_size)` ⭐ 核心流程

```
Step 1: pending → 抓取详情（仅牛客）
  ├─ 查询 status='pending' 的任务
  ├─ 调用 NowcoderCrawler.fetch_post_content_full(url)
  ├─ 下载图片到 post_images/TASK_XXX/
  └─ 更新状态为 fetched

Step 2: fetched → LLM 提取题目
  ├─ 查询 status='fetched' 的任务（牛客+小红书）
  ├─ 调用 extract_questions_from_post(content, ...)
  │   ├─ 调用 Miner Agent（LLM）结构化提取
  │   ├─ 解析 JSON 返回（题目列表）
  │   └─ 判断是否与面经相关
  ├─ 如果正文无题目 + 有图片 → OCR 识别 → 再次提取
  ├─ 保存题目到 SQLite + Neo4j
  └─ 更新状态为 done（或 error）

Step 3: 递归重试失败任务（最多 N 轮）
  ├─ 查询 status='error' 的任务
  ├─ 重新抓取详情页
  ├─ 重新 LLM 提取
  └─ 直到全部成功或达到最大次数
```

**关键配置**（.env）：

- `CRAWLER_PROCESS_BATCH_SIZE`：每批处理多少条（默认 10）
- `CRAWLER_RECURSIVE_RETRY_MAX`：递归重试最大轮数（默认 3）
- `CRAWLER_FETCH_MAX_RETRIES`：单个任务最大重试次数（默认 3）
- `CRAWLER_RETRY_DELAY`：重试间隔秒数（默认 5）

---

## 爬虫管道

### 牛客爬虫（backend/services/crawler/nowcoder_crawler.py）

**发现阶段**：

```python
def discover(keywords, max_pages):
    for keyword in keywords:
        for page in range(1, max_pages + 1):
            # HTTP 请求帖子列表 API
            posts = self._fetch_posts_page(keyword, page)
            # 提取元信息（标题、公司、岗位等）
            yield post_metadata
```

**抓取阶段**：

```python
def fetch_post_content_full(url):
    # 1. 请求详情页 HTML
    html = self._fetch_detail_html(url)
    # 2. 从 <script id="__INITIAL_STATE__"> 提取 JSON
    content = self._extract_content_from_initial_state_feed(html)
    # 3. 提取图片 URL
    images = self._extract_images_from_html(html)
    return content, images
```

### 小红书爬虫（backend/services/crawler/xhs_crawler.py）

**特点**：

- 使用 Playwright 模拟浏览器
- 需要扫码登录（首次），session 保存到 `backend/data/xhs_user_data/`
- 后续可 headless=True 无头运行

**发现+抓取一体**：

```python
def discover(keywords, max_notes_per_keyword):
    for keyword in keywords:
        # 1. 搜索笔记列表
        note_links = self._search_notes(keyword, max_notes_per_keyword)
        # 2. 逐个访问笔记详情页
        for link in note_links:
            # 3. 提取正文 + 图片
            content, images = self._fetch_note_content(link)
            yield post_data
```

### 图片下载（backend/services/crawler/image_utils.py）

```python
def download_images(image_urls, task_id):
    # 创建目录 post_images/TASK_XXX/
    # 下载图片并保存为 0.jpg, 1.jpg, ...
    # 返回相对路径列表 ["TASK_XXX/0.jpg", ...]
```

**前端访问**：`/post-images/TASK_XXX/0.jpg`（FastAPI 静态文件服务）

---

## 题目提取流程

### backend/services/crawler/question_extractor.py

**核心函数**：`extract_questions_from_post(content, platform, company, ...)`

```
1. 调用 Miner Agent（LLM）
   ├─ Prompt：backend/prompts/miner_prompt.py
   ├─ 输入：帖子正文 + 元信息
   └─ 输出：JSON 格式题目列表

2. 解析 LLM 返回
   ├─ 提取 ```json ... ``` 代码块
   ├─ 解析为 Python dict
   └─ 校验必填字段（question_text, q_id）

3. 判断内容相关性
   ├─ 如果 LLM 返回 {"related": false} → 标记为 unrelated
   ├─ 如果解析失败 → 标记为 parse_error
   └─ 如果成功 → 返回题目列表

4. 记录 LLM 交互日志
   └─ 写入 微调/llm_logs/llm_prompt_log_YYYYMMDD_HHMMSS.jsonl
```

**LLM 配置**（.env）：

- `LLM_PROVIDER`：ollama / openai / dashscope
- `LLM_MODEL_ID`：模型名称（如 qwen2.5:7b）
- `LLM_BASE_URL`：API 地址
- `MINER_TEMPERATURE`：温度（默认 0.1，更确定性）
- `MINER_MAX_TOKENS`：最大输出 token（默认 4096）

### OCR 服务（backend/services/crawler/ocr_service_mcp.py）

**触发条件**：正文提取无题目 + 有图片

```python
def ocr_images_to_text(image_paths, task_id):
    # 1. 调用 MCP OCR 服务（Gemini Vision API）
    # 2. 批量识别图片文字
    # 3. 合并为一段文本
    # 4. 返回 OCR 结果
```

**配置**（.env）：

- `GEMINI_API_KEY`：Google Gemini API Key
- `GEMINI_MODEL`：模型名称（默认 gemini-2.0-flash-exp）

---

## 数据存储

### SQLite（backend/services/sqlite_service.py）

**主要表**：

#### 1. `crawl_tasks`（爬虫任务队列）

```sql
task_id         TEXT PRIMARY KEY    -- UUID
source_url      TEXT UNIQUE         -- 帖子 URL
source_platform TEXT                -- nowcoder / xiaohongshu
status          TEXT                -- pending / fetched / done / error
post_title      TEXT                -- 帖子标题
company         TEXT                -- 公司
position        TEXT                -- 岗位
raw_content     TEXT                -- 正文
image_paths     TEXT                -- JSON 数组 ["TASK_XXX/0.jpg", ...]
questions_count INTEGER             -- 提取到的题目数
error_msg       TEXT                -- 错误信息
extraction_source TEXT              -- content / image（从正文还是图片提取）
discover_keyword TEXT               -- 发现关键词
discovered_at   REAL                -- 发现时间戳
processed_at    REAL                -- 处理时间戳
```

#### 2. `questions`（题库）

```sql
q_id            TEXT PRIMARY KEY    -- 题目 ID（UUID）
question_text   TEXT                -- 题目内容
answer_text     TEXT                -- 参考答案
difficulty      TEXT                -- easy / medium / hard
question_type   TEXT                -- 技术题 / 算法题 / 系统设计 / 行为题 / HR问题
source_platform TEXT                -- 来源平台
source_url      TEXT                -- 来源 URL
company         TEXT                -- 公司
position        TEXT                -- 岗位
business_line   TEXT                -- 业务线
topic_tags      TEXT                -- JSON 数组 ["Redis", "缓存"]
extraction_source TEXT              -- content / image
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

#### 3. 其他表

- `user_profiles`：用户资料
- `study_sessions`：学习会话
- `user_answers`：答题记录
- `tag_mastery`：标签掌握度（SM-2 算法）
- `memory_store`：情景记忆
- `knowledge_resources`：学习资源推荐

### Neo4j（backend/services/neo4j_service.py）

**可选**，用于知识图谱和向量检索。

**节点类型**：

- `Question`：题目节点（含 embedding 向量）
- `Tag`：标签节点
- `Company`：公司节点

**关系**：

- `(Question)-[:HAS_TAG]->(Tag)`
- `(Question)-[:FROM_COMPANY]->(Company)`

**向量索引**：

```cypher
CREATE VECTOR INDEX question_embeddings
FOR (q:Question) ON (q.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}}
```

---

## 关键文件清单

### ✅ 核心文件（不能删除/修改）

#### 启动入口

- `run.py`：启动脚本
- `backend/main.py`：FastAPI 应用主入口

#### 调度器

- `backend/services/scheduler.py`：爬虫调度器（定时任务 + 手动触发）

#### 爬虫服务

- `backend/services/crawler/nowcoder_crawler.py`：牛客爬虫
- `backend/services/crawler/xhs_crawler.py`：小红书爬虫
- `backend/services/crawler/run_xhs_worker.py`：XHS 独立工作进程（subprocess）
- `backend/services/crawler/question_extractor.py`：LLM 题目提取
- `backend/services/crawler/image_utils.py`：图片下载
- `backend/services/crawler/ocr_service_mcp.py`：OCR 识别
- `backend/services/crawler/crawl_helpers.py`：爬虫辅助函数

#### 数据服务

- `backend/services/sqlite_service.py`：SQLite 数据库服务
- `backend/services/neo4j_service.py`：Neo4j 图数据库服务

#### Agent

- `backend/agents/orchestrator.py`：总编排器（对话 + 答题评估）
- `backend/agents/interviewer_agent.py`：面试官 Agent（对话）
- `backend/agents/miner_agent.py`：矿工 Agent（题目提取，已废弃，逻辑在 question_extractor）
- `backend/agents/thinking_capture.py`：思考步骤捕获器

#### Prompt

- `backend/prompts/miner_prompt.py`：Miner Agent Prompt（题目提取）
- `backend/agents/prompts/interviewer_prompt.py`：Interviewer Agent Prompt

#### 工具

- `backend/tools/knowledge_manager_tools.py`：知识管理工具（embedding 生成）
- `backend/tools/interviewer_tools.py`：面试官工具（知识推荐）

#### 配置

- `backend/config/config.py`：配置管理（从 .env 读取）
- `.env`：环境变量配置

#### 其他服务

- `backend/services/knowledge_manager.py`：知识管理器
- `backend/services/llm_warmup.py`：LLM 预热
- `backend/services/llm_parse_failures.py`：LLM 解析失败日志
- `backend/services/finetune_service.py`：微调数据管理

---

## 可归档文件

### 🗂️ 临时修复脚本（已完成使命，可归档）

这些脚本是开发过程中的临时修复工具，现在已经不需要了：

- `fix_log_path.py`：修复日志路径问题（已修复）
- `fix_newline.py`：修复换行符问题（已修复）
- `fix_llm_log.py`：修复 LLM 日志格式（已修复）
- `fix_indent.py`：修复缩进问题（已修复）

**建议**：移动到 `archived/temp_fixes/` 目录

### 🗂️ 未使用的服务

#### `backend/services/hunter_pipeline.py`

- **用途**：旧版内容采集管道
- **当前状态**：仅被 `orchestrator.py` 的 `ingest_instant()` 方法调用
- **问题**：`ingest_instant()` 是手动收录单条 URL 的接口，但前端没有使用
- **建议**：
  - 如果确认不需要手动收录功能 → 归档到 `archived/unused_services/`
  - 如果需要保留 → 重构为调用 scheduler 的 trigger 方法

#### `backend/services/crawler/ocr_service.py`

- **用途**：旧版 OCR 服务（可能用的是其他 API）
- **当前状态**：已被 `ocr_service_mcp.py` 替代
- **建议**：归档到 `archived/unused_services/`

### 🗂️ 旧的 Prompt 文件

#### `backend/prompts/knowledge_manager_prompt.py`

- **用途**：旧版知识管理器 Prompt
- **当前状态**：未被引用（知识管理逻辑已重构）
- **建议**：归档到 `archived/old_prompts/`

### 🗂️ 分析脚本（临时工具）

- `analyze_usage.py`：文件使用情况分析（本次创建的临时工具）
- `cleanup.py`：清理脚本（如果存在）

**建议**：完成清理后移动到 `archived/tools/`

---

## 清理建议

### 创建归档目录结构

```
archived/
├── temp_fixes/          # 临时修复脚本
│   ├── fix_log_path.py
│   ├── fix_newline.py
│   ├── fix_llm_log.py
│   └── fix_indent.py
├── unused_services/     # 未使用的服务
│   ├── hunter_pipeline.py
│   └── ocr_service.py
├── old_prompts/         # 旧的 Prompt
│   └── knowledge_manager_prompt.py
└── tools/               # 临时分析工具
    ├── analyze_usage.py
    └── cleanup.py
```

### 自动化清理脚本

见 `cleanup_project.py`（下一步创建）

---

## 总结

### 核心流程（不能改）

```
python run.py
  ↓
FastAPI 启动
  ↓
scheduler.start()
  ↓
定时任务：
  ├─ 牛客发现（每天 2:00/14:00）
  ├─ 任务处理（每小时整点）
  └─ XHS 发现（手动触发）
  ↓
处理流程：
  pending → 抓取详情 → fetched
  fetched → LLM 提取 → done/error
  error → 递归重试 → done
  ↓
数据存储：
  SQLite（主存储）+ Neo4j（可选）
```

### 关键配置（.env）

```bash
# 爬虫调度
SCHEDULER_ENABLE_NOWCODER=true
SCHEDULER_NOWCODER_HOURS=2,14
SCHEDULER_PROCESS_MINUTE=0
CRAWLER_PROCESS_BATCH_SIZE=10
CRAWLER_RECURSIVE_RETRY_MAX=3

# LLM 配置
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen2.5:7b
LLM_BASE_URL=http://localhost:11434
MINER_TEMPERATURE=0.1
MINER_MAX_TOKENS=4096

# 牛客配置
NOWCODER_COOKIE=你的Cookie
NOWCODER_KEYWORDS=Java后端,Python后端,前端
NOWCODER_MAX_PAGES=2

# 小红书配置
XHS_KEYWORDS=Java面经,Python面经
XHS_MAX_NOTES_PER_KEYWORD=10
```

---

**文档版本**：v1.0  
**创建时间**：2025-01-09  
**最后更新**：2025-01-09