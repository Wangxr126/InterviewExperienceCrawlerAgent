# 面经 Agent 系统流程梳理与清理建议

## 📋 核心流程（已验证可运行，不要改动！）

### 1. 启动流程
```
run.py 
  → 检查 NewCoderAgent 环境
  → 启动 uvicorn backend.main:app
  → backend/main.py 加载
```

### 2. 主程序初始化 (backend/main.py)
```python
1. 加载 .env 配置
2. 创建必要目录（data/logs/memory/images等）
3. 配置 loguru 日志系统
4. 安装思考捕获器（thinking_capture）
5. 启动 FastAPI 应用
6. 启动爬虫调度器（scheduler）
7. 启动 LLM 预热（llm_warmup）
```

### 3. 爬虫调度流程 (backend/services/scheduler.py)

#### 3.1 定时任务
- **牛客发现任务**: 每天 2:00/14:00（可配置）
  - 调用 `_run_nowcoder_discovery()`
  - 搜索关键词 → 发现帖子 → 写入 crawl_tasks 表（status=pending）

- **任务处理器**: 每小时整点（可配置）
  - 调用 `_process_pending_tasks()`
  - Step 1: pending → 抓取详情 → fetched
  - Step 2: fetched → LLM 提取题目 → done/error
  - Step 3: 递归重试 error 任务（最多3轮）

#### 3.2 核心处理链路
```
pending 任务
  ↓
抓取详情页（nowcoder_crawler.fetch_post_content_full）
  ↓
status = fetched（保存 raw_content + image_paths）
  ↓
LLM 提取题目（question_extractor.extract_questions_from_post）
  ├─ 使用 miner_prompt.py 的极简版 prompt
  ├─ 调用 LLM（qwen3.5:4b 或 deepseek-r1:7b）
  ├─ 解析 JSON 返回
  └─ 返回 (questions, status)
  ↓
保存题目（_save_questions）
  ├─ SQLite: questions 表（主存储）
  ├─ Neo4j: 知识图谱（可选）
  └─ 更新 crawl_tasks.company（如果 LLM 提取到）
  ↓
status = done（questions_count > 0）
```

### 4. 题目提取流程 (backend/services/crawler/question_extractor.py)

#### 4.1 核心函数
```python
extract_questions_from_post(content, platform, company, position, ...)
  ↓
1. 拼接标题+正文
2. 调用 LLM（_call_llm）
   - System Prompt: miner_prompt.py 的 MINER_SYSTEM_PROMPT
   - User Prompt: 面经原文
3. 解析 JSON（_parse_json_from_llm）
   - 支持多种格式容错
   - 返回 (items, status)
4. 重试机制（最多3次）
5. 构建题目字典
6. 返回 (questions, status)
```

#### 4.2 日志记录
```python
_append_llm_log_to_csv()
  ├─ 旧路径（调试）: 微调/llm_logs/{模型名}/llm_prompt_log_{时间}.jsonl
  └─ 微调日志: 微调/llm_logs/{模型名}/{来源}_{日期}.jsonl
```

### 5. 数据存储

#### 5.1 SQLite (backend/services/sqlite_service.py)
- **crawl_tasks**: 爬取任务队列
  - pending → fetched → done/error
- **questions**: 题目主存储
  - q_id, question_text, answer_text, difficulty, question_type, topic_tags, company, position, source_url, etc.

#### 5.2 Neo4j (backend/services/neo4j_service.py)
- 知识图谱（可选）
- 向量索引（用于语义搜索）

---

## 🗑️ 可以清理的文件

### 1. 重复/废弃的 OCR 服务
**问题**: 有两个 OCR 服务实现
- `backend/services/crawler/ocr_service.py` - 旧版本（未使用）
- `backend/services/crawler/ocr_service_mcp.py` - 当前使用版本

**建议**: 
```bash
# 删除旧版本
rm backend/services/crawler/ocr_service.py
```

### 2. 未使用的 XHS Worker
**文件**: `backend/services/crawler/run_xhs_worker.py`
**问题**: 这是一个独立的 worker 脚本，但实际上 XHS 爬取已经集成到 scheduler.py 中

**检查**: 
```bash
# 搜索是否有地方调用这个文件
grep -r "run_xhs_worker" backend/
```

**建议**: 如果没有被调用，可以移到 `archive/` 目录

### 3. 旧版 Prompt 文件
**文件**: `backend/prompts/miner_prompt_old.py`
**状态**: 已被 `miner_prompt.py` 替代

**建议**:
```bash
# 移到归档目录
mkdir -p archive/prompts
mv backend/prompts/miner_prompt_old.py archive/prompts/
```

### 4. 临时修复脚本
**文件**: 
- `fix_log_path.py`
- `fix_indent.py`
- `fix_newline.py`
- `fix_llm_log.py`

**建议**: 这些是一次性修复脚本，可以删除或移到 `scripts/fixes/` 目录

### 5. 未使用的 Hunter Pipeline
**文件**: `backend/services/hunter_pipeline.py`
**检查**: 
```bash
grep -r "hunter_pipeline" backend/main.py
grep -r "from.*hunter_pipeline" backend/
```

**建议**: 如果没有被使用，移到 `archive/`

---

## 📁 建议的目录结构优化

### 当前问题
- 临时脚本散落在项目根目录
- 旧版本文件没有归档
- 日志文件路径不统一

### 建议结构
```
wxr_agent/
├── backend/
│   ├── main.py                    # ✅ 核心入口
│   ├── config/
│   │   └── config.py              # ✅ 配置管理
│   ├── services/
│   │   ├── scheduler.py           # ✅ 调度器
│   │   ├── sqlite_service.py      # ✅ SQLite 服务
│   │   ├── neo4j_service.py       # ✅ Neo4j 服务
│   │   ├── llm_warmup.py          # ✅ LLM 预热
│   │   ├── finetune_service.py    # ✅ 微调服务
│   │   └── crawler/
│   │       ├── nowcoder_crawler.py      # ✅ 牛客爬虫
│   │       ├── xhs_crawler.py           # ✅ 小红书爬虫
│   │       ├── question_extractor.py    # ✅ 题目提取
│   │       ├── ocr_service_mcp.py       # ✅ OCR 服务
│   │       ├── image_utils.py           # ✅ 图片工具
│   │       └── crawl_helpers.py         # ✅ 爬虫辅助
│   ├── prompts/
│   │   └── miner_prompt.py        # ✅ 当前使用的 prompt
│   └── agents/
│       └── orchestrator.py        # ✅ Agent 编排
├── 微调/
│   └── llm_logs/
│       ├── qwen3.5_4b/            # ✅ 按模型分目录
│       └── deepseek-r1_7b/
├── scripts/                       # 建议新增：工具脚本目录
│   └── fixes/                     # 一次性修复脚本
├── archive/                       # 建议新增：归档目录
│   ├── prompts/                   # 旧版 prompt
│   ├── services/                  # 废弃的服务
│   └── scripts/                   # 废弃的脚本
├── run.py                         # ✅ 启动入口
└── .env                           # ✅ 配置文件
```

---

## 🔍 需要进一步检查的文件

### 1. knowledge_manager.py
**位置**: `backend/services/knowledge_manager.py`
**问题**: 不确定是否在使用

**检查命令**:
```bash
grep -r "knowledge_manager" backend/main.py
grep -r "from.*knowledge_manager" backend/
```

### 2. llm_parse_failures.py
**位置**: `backend/services/llm_parse_failures.py`
**用途**: 记录 LLM 解析失败的案例
**检查**: 是否在 question_extractor.py 中被调用

---

## ✅ 清理步骤建议

### Step 1: 创建归档目录
```bash
mkdir -p archive/prompts
mkdir -p archive/services
mkdir -p archive/scripts
mkdir -p scripts/fixes
```

### Step 2: 移动旧版文件
```bash
# 旧版 prompt
mv backend/prompts/miner_prompt_old.py archive/prompts/

# 临时修复脚本
mv fix_*.py scripts/fixes/
```

### Step 3: 删除重复文件
```bash
# 删除旧版 OCR（确认后）
rm backend/services/crawler/ocr_service.py
```

### Step 4: 检查并归档未使用的服务
```bash
# 检查 hunter_pipeline 是否被使用
grep -r "hunter_pipeline" backend/

# 如果未使用，移到归档
mv backend/services/hunter_pipeline.py archive/services/

# 检查 run_xhs_worker 是否被使用
grep -r "run_xhs_worker" backend/

# 如果未使用，移到归档
mv backend/services/crawler/run_xhs_worker.py archive/services/
```

---

## 📊 核心配置文件 (.env)

### 关键配置项（不要改动）
```ini
# LLM 配置
LLM_MODE=local
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3.5:4b  # 或 deepseek-r1:7b
LLM_BASE_URL=http://localhost:11434/v1

# Miner（题目提取）配置
MINER_MODE=local
MINER_LOCAL_MODEL=deepseek-r1:7b
MINER_TEMPERATURE=0.3
MINER_MAX_RETRIES=3

# 调度器配置
SCHEDULER_ENABLE_NOWCODER=true
SCHEDULER_NOWCODER_HOURS=2,14
SCHEDULER_PROCESS_MINUTE=0
CRAWLER_PROCESS_BATCH_SIZE=50
CRAWLER_RECURSIVE_RETRY_MAX=3

# 日志配置
LLM_PROMPT_LOG_CSV=微调/llm_logs/llm_prompt_log.jsonl
```

---

## 🎯 总结

### 核心流程（不要改动）
1. ✅ run.py → backend/main.py
2. ✅ scheduler.py 定时任务
3. ✅ question_extractor.py 题目提取
4. ✅ miner_prompt.py 极简版 prompt
5. ✅ sqlite_service.py 数据存储
6. ✅ 日志路径：微调/llm_logs/{模型名}/

### 可以清理
1. ❌ ocr_service.py（旧版）
2. ❌ miner_prompt_old.py（旧版）
3. ❌ fix_*.py（临时脚本）
4. ❓ hunter_pipeline.py（需检查）
5. ❓ run_xhs_worker.py（需检查）

### 建议优化
1. 创建 archive/ 目录归档旧文件
2. 创建 scripts/fixes/ 目录存放修复脚本
3. 统一日志路径到 微调/llm_logs/{模型名}/
