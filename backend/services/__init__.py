"""
backend/services/ — 服务层

按职责分为六个子模块：

┌─ storage/    基础存储层 ───────────────────────────────────────
│  sqlite_service.py       SQLite 主库（crawl_tasks / questions 等核心表）
│  neo4j_service.py        Neo4j 知识图谱 + 向量检索（可降级，不阻塞启动）
│
├─ scheduling/ 调度层 ───────────────────────────────────────────
│  scheduler.py            APScheduler 主调度器：发现任务 / 处理任务 / 单任务重试
│  scheduler_service.py   scheduled_jobs 表 CRUD（定时任务配置持久化）
│
├─ knowledge/  知识管理层 ───────────────────────────────────────
│  knowledge_manager.py    元信息提取 / 查重 / 双写入库
│
├─ finetune/   微调数据层 ───────────────────────────────────────
│  finetune_service.py     从日志导入样本 / 标注 / 导出 JSONL
│
├─ logging/    日志层 ───────────────────────────────────────────
│  interviewer_logger.py   面试官 Agent 交互日志（按模型/日期分文件）
│  llm_parse_failures.py   LLM 返回无法解析时保存样本（用于后期微调）
│
├─ warmup/     预热层 ───────────────────────────────────────────
│  llm_warmup.py           启动时预热 Ollama 本地模型，避免首次超时
│
└─ crawler/    爬虫子模块 ───────────────────────────────────────
   xhs_crawler.py          小红书爬虫（Playwright）
   nowcoder_crawler.py     牛客网爬虫（Playwright）
   question_extractor.py   LLM 题目提取器（MinerAgent 入口）
   ocr_service_mcp.py      图片 OCR（Qwen-VL / Claude Vision / MCP 三选一）
   image_utils.py          图片下载工具，返回相对路径列表
   crawl_helpers.py        爬虫公共工具函数
   run_xhs_worker.py       小红书子进程 Worker 入口
"""
