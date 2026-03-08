# 系统流程梳理与问题修复总结

## ✅ 已完成的工作

### 1. 系统流程完整分析

已创建 `SYSTEM_FLOW_ANALYSIS.md`，详细记录了：
- 启动流程（run.py → FastAPI → scheduler）
- 爬虫管道（发现 → 抓取 → 提取 → 入库）
- 调度器逻辑（定时任务 + 递归重试）
- 数据存储（SQLite + Neo4j）
- 所有关键文件清单

**核心流程（不能修改）**：
```
python run.py
  → FastAPI 启动
  → scheduler.start()
  → 定时任务：
     - 牛客发现（每天 2:00/14:00）
     - 任务处理（每小时整点）
  → 处理流程：
     - pending → 抓取详情 → fetched
     - fetched → LLM 提取 → done/error
     - error → 递归重试 → done
  → 数据存储：SQLite（主）+ Neo4j（可选）
```

### 2. 项目清理方案

已创建 `cleanup_project.py` 自动清理脚本，识别出 **9 个可归档文件**：

**临时修复脚本（4个）**：
- fix_log_path.py
- fix_newline.py
- fix_llm_log.py
- fix_indent.py

**未使用的服务（2个）**：
- backend/services/hunter_pipeline.py
- backend/services/crawler/ocr_service.py

**旧的 Prompt（1个）**：
- backend/prompts/knowledge_manager_prompt.py

**临时工具（2个）**：
- analyze_usage.py
- cleanup.py

**执行清理**：
```bash
python cleanup_project.py
```
所有文件将移动到 `archived/` 目录（不删除）

### 3. 关键 Bug 修复

**问题**：题目提取后入库失败，错误 `'q_id'`

**原因**：`extract_questions_from_post()` 返回的题目字典缺少 `q_id` 字段

**修复**：在 `backend/services/crawler/question_extractor.py` 中为每个题目生成 UUID：
```python
import uuid
q_id = str(uuid.uuid4())

questions.append({
    "q_id": q_id,  # 添加 q_id 字段
    "question_text": q_text,
    # ... 其他字段
})
```

**验证**：重启服务后重新提取，题目应该能成功入库

---

## 📋 关键配置（.env）

```bash
# 调度器
SCHEDULER_ENABLE_NOWCODER=true
SCHEDULER_NOWCODER_HOURS=2,14
SCHEDULER_PROCESS_MINUTE=0

# 批处理
CRAWLER_PROCESS_BATCH_SIZE=10
CRAWLER_RECURSIVE_RETRY_MAX=3
CRAWLER_FETCH_MAX_RETRIES=3
CRAWLER_RETRY_DELAY=5

# LLM
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen2.5:7b
MINER_TEMPERATURE=0.1
MINER_MAX_TOKENS=4096
MINER_MAX_RETRIES=3
```

---

## 📁 核心文件（不能删除/修改）

### 启动与配置
- `run.py` - 启动脚本
- `backend/main.py` - FastAPI 主入口
- `backend/config/config.py` - 配置管理
- `.env` - 环境变量

### 调度器（核心）
- `backend/services/scheduler.py` - 爬虫调度器
  - `_run_nowcoder_discovery()` - 牛客发现
  - `_run_xhs_discovery()` - 小红书发现
  - `_process_pending_tasks()` - 任务处理（三步流程）
  - `_save_questions()` - 题目入库

### 爬虫服务
- `backend/services/crawler/nowcoder_crawler.py` - 牛客爬虫
- `backend/services/crawler/xhs_crawler.py` - 小红书爬虫
- `backend/services/crawler/run_xhs_worker.py` - XHS 独立进程
- `backend/services/crawler/question_extractor.py` - LLM 题目提取（已修复）
- `backend/services/crawler/image_utils.py` - 图片下载
- `backend/services/crawler/ocr_service_mcp.py` - OCR 识别

### 数据服务
- `backend/services/sqlite_service.py` - SQLite 数据库
- `backend/services/neo4j_service.py` - Neo4j 图数据库

### Agent
- `backend/agents/orchestrator.py` - 总编排器
- `backend/agents/interviewer_agent.py` - 面试官 Agent

### Prompt
- `backend/prompts/miner_prompt.py` - 题目提取 Prompt
- `backend/agents/prompts/interviewer_prompt.py` - 面试官 Prompt

---

## 🚀 下一步操作

### 1. 验证修复
```bash
# 重启服务
python run.py

# 前端触发重新提取
# 查看日志确认没有 'q_id' 错误
```

### 2. 执行清理（可选）
```bash
# 归档未使用的文件
python cleanup_project.py

# 确认后输入 yes
```

### 3. 测试完整流程
```bash
# 1. 手动触发牛客发现
# 2. 等待任务处理
# 3. 检查题目是否成功入库
# 4. 验证题目包含 q_id、created_at、source_url
```

---

## 📖 相关文档

- **SYSTEM_FLOW_ANALYSIS.md** - 完整系统流程分析（507行）
- **FIX_QID_SUMMARY.md** - q_id 问题修复详情
- **cleanup_project.py** - 自动清理脚本
- **CLEANUP_SUMMARY.md** - 本文档

---

## ⚠️ 重要提醒

1. **不要修改核心流程**：
   - `scheduler.py` 中的定时任务逻辑
   - `_process_pending_tasks()` 的三步处理流程
   - `question_extractor.py` 的 LLM 提取逻辑

2. **归档不是删除**：
   - 所有文件保留在 `archived/` 目录
   - 如需恢复，直接移回原位置

3. **数据库字段**：
   - `q_id`：题目唯一标识（UUID）
   - `source_url`：原帖 URL（映射关系）
   - `created_at`：提取时间（自动）
   - `updated_at`：更新时间（自动）

---

**创建时间**：2025-01-09  
**状态**：✅ 流程梳理完成，Bug 已修复，清理方案已就绪
