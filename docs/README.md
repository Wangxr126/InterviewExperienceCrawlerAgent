# 文档中心（`docs/`）

面向 **wxr_agent（面经 Agent）** 仓库的说明入口。环境变量与默认值以根目录 `.env` 与 [`backend/config/config.py`](../backend/config/config.py) 为准；代码结构若有变更，请优先对照源码更新本节。

---

## 仓库结构速查（与文档对应）

| 路径 | 说明 |
|------|------|
| [`run.py`](../run.py) | 后端启动包装；可按内置 `CONDA_ENV_PYTHON` 自动切到目标 Conda 解释器 |
| [`web/`](../web/) | Vue 3 + Vite；[`web/src/App.vue`](../web/src/App.vue) 定义侧边栏与 10 个视图 |
| [`backend/main.py`](../backend/main.py) | FastAPI 主应用，**绝大多数 HTTP 路由**在此注册 |
| [`backend/api/`](../backend/api/) | 独立路由模块：`scheduler_api.py`、`reasoning_api.py`，由 `main.py` 挂载 |
| [`backend/services/`](../backend/services/) | 业务服务层（如 `crawler/`、`finetune/`、`storage/`） |
| [`backend/agents/`](../backend/agents/) | Interviewer / Miner 等 Agent 与 [`prompts/`](../backend/agents/prompts/) |
| [`backend/config/config.py`](../backend/config/config.py) | 配置项定义（`.env` 映射） |
| [`backend/data/`](../backend/data/) | SQLite、爬虫与图片、记忆与 trace 等本地数据 |
| [`mcp/`](../mcp/) | 业务 MCP，如 [`mcp/mcp-content-extractor/`](../mcp/mcp-content-extractor/) |
| [`微调/`](../微调/) | `train_lora.py`、`labeled_data.jsonl`、`training_data_alpaca.jsonl`、`logs/train_run_*.log` |
| [`llm_observability/`](../llm_observability/) | DeepSeek 流式等探针脚本与专文（见下文「DeepSeek」） |
| [`docker-compose.yml`](../docker-compose.yml) | Neo4j、Qdrant 等依赖服务 |

---

## 前端视图一览（`App.vue`）

侧边栏 `navItems.key` → 页面组件（均在 `web/src/views/`）：

| `key` | 侧边栏名称 | 组件文件 |
|--------|------------|----------|
| `browse` | 题库浏览 | `BrowseView.vue` |
| `chat` | 练习对话 | `ChatView.vue` |
| `ingest` | 收录面经 | `IngestView.vue` |
| `collect` | 数据采集 | `CollectView.vue` |
| `scheduler` | 定时任务 | `SchedulerView.vue` |
| `report` | 学习报告 | `ReportView.vue` |
| `finetune` | 微调标注 | `FinetuneView.vue` |
| `tool_usage` | 工具统计 | `ToolUsageView.vue` |
| `graph_rag` | GraphRAG | `GraphRagView.vue` |
| `model_compare` | 模型对比 | `ModelBenchView.vue` |

前端 API 封装：[`web/src/api.js`](../web/src/api.js)。

---

## 文档地图

### `docs/` 根目录

| 文档 | 说明 |
|------|------|
| [README.md](README.md) | 本索引：结构速查 + 文档地图 |
| [STARTUP_GUIDE.md](STARTUP_GUIDE.md) | 启动顺序、Docker、Ollama、排障 |
| [环境配置说明.md](环境配置说明.md) | Conda、MCP、与 `.env` 的对应关系 |
| [微调模块技术解析.md](微调模块技术解析.md) | SFT / LoRA 理论与训练细节 |
| [MCP服务详解.md](MCP服务详解.md) | 三个 MCP 的能力、配置与示例 |
| [MCP独立部署指南.md](MCP独立部署指南.md) | 独立部署 TypeScript MCP |
| [MCP构建与部署指南.md](MCP构建与部署指南.md) | 构建与发布流程 |
| [图片识别.md](图片识别.md) | OCR 与图片路径数据流 |
| [DeepSeek流式输出与参数组合分析.md](DeepSeek流式输出与参数组合分析.md) | 入口页，正文在 `llm_observability/` |

### `docs/系统梳理/`

| 文档 | 说明 |
|------|------|
| [API全量文档.md](系统梳理/API全量文档.md) | HTTP API 分组清单与前端对应关系 |
| [SQL表结构与字段手册.md](系统梳理/SQL表结构与字段手册.md) | SQLite 等表结构 |
| [页面功能与按钮说明.md](系统梳理/页面功能与按钮说明.md) | 各页按钮、接口与效果图占位路径 |
| [模型对比页面说明.md](系统梳理/模型对比页面说明.md) | 模型对比预设、环境变量、接口 |
| [进程与子进程架构文档.md](系统梳理/进程与子进程架构文档.md) | 爬虫子进程与恢复 |
| [Agent-Miner全景文档.md](系统梳理/Agent-Miner全景文档.md) | Miner 两阶段与采集数据流 |
| [Agent-Interviewer全景文档.md](系统梳理/Agent-Interviewer全景文档.md) | 主对话 Agent 职责与工具 |
| [意图实现详解-最终版.md](系统梳理/意图实现详解-最终版.md) | 意图与路由实现 |
| [意图与推荐检索实现详解.md](系统梳理/意图与推荐检索实现详解.md) | 推荐与检索扩展说明 |
| [记忆机制全景文档.md](系统梳理/记忆机制全景文档.md) | 记忆写入与存储 |
| [自研MCP文档.md](系统梳理/自研MCP文档.md) | `mcp-content-extractor` 专述 |
| [案例-练习对话点评重复-面试稿.md](系统梳理/案例-练习对话点评重复-面试稿.md) | 问题案例记录 |

### `docs/系统梳理/placeholders/`

页面效果图占位图与 [placeholders/README.md](系统梳理/placeholders/README.md) 命名约定。

---

## 推荐阅读顺序

1. 仓库根目录 [README.md](../README.md)  
2. [STARTUP_GUIDE.md](STARTUP_GUIDE.md)  
3. [环境配置说明.md](环境配置说明.md)  
4. [系统梳理/API全量文档.md](系统梳理/API全量文档.md) + [页面功能与按钮说明.md](系统梳理/页面功能与按钮说明.md)  

微调与对比：[微调模块技术解析.md](微调模块技术解析.md)、[系统梳理/模型对比页面说明.md](系统梳理/模型对比页面说明.md)。
