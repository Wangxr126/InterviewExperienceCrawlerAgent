# InterviewExperienceCrawlerAgent

面向面试题采集、结构化提取、智能练习与学习追踪的一体化 Agent 系统。  
项目将牛客/小红书等来源内容接入采集链路，经 `MinerAgent` 提取后入库，再由 `InterviewerAgent` 完成对话练习、评分反馈与学习建议。

---

## 项目定位

- **采集侧**：URL 收录、批量抓取、任务队列、重提取、Stage2 精答增强
- **理解侧**：`MinerAgent` + OCR + Schema 约束，输出结构化题目数据
- **练习侧**：`InterviewerAgent` 流式对话、答题评分、复盘反馈、推荐建议
- **存储侧**：SQLite（业务主库）+ Neo4j（知识图谱）+ Qdrant（向量检索）
- **可观测侧**：后端日志、子进程日志、推理轨迹、工具调用统计

---

## 前端效果总览

> 直接看本 README 可快速了解界面；全量图见 [`项目图片总览.md`](项目图片总览.md)。

### 核心业务页面

![题库浏览](docs/项目图片/01_题库浏览界面.png)
![练习对话](docs/项目图片/02_练习对话页面.png)
![答题流程-step2](docs/项目图片/03_答题流程-step2.png)
![答题流程-step3](docs/项目图片/04_答题流程-step3.png)
![答题流程-agent回复](docs/项目图片/05_答题流程-agent回复.png)
![答题流程-评分结果](docs/项目图片/06_答题流程-评分结果.png)
![个人薄弱点](docs/项目图片/07_个人薄弱点.png)
![智能联系](docs/项目图片/08_智能联系.png)

### 采集、训练与分析页面

![数据采集1](docs/项目图片/09_数据采集界面1.png)
![数据采集2](docs/项目图片/10_数据采集界面2.png)
![定时任务](docs/项目图片/11_定时任务截图.png)
![学习报告](docs/项目图片/12_学习报告截图.png)
![微调样本列表](docs/项目图片/13_微调标注-样本列表.png)
![微调标注编辑](docs/项目图片/14_微调标注-标注编辑.png)
![一键微调](docs/项目图片/15_微调标注-一键微调.png)
![工具统计](docs/项目图片/16_工具统计.png)
![GraphRAG知识图谱](docs/项目图片/17_GraphRAG知识图谱.png)
![模型对比](docs/项目图片/18_模型对比.png)

### 当前仍建议补充

- `19_收录面经页面.png`（对应 `web/src/views/IngestView.vue`）

---

## 最新系统架构（代码对齐）

```text
前端（Vue 3 + Vite，web/）
  └─ 生产构建到 backend/static/dist
          │
          ▼
FastAPI 主服务（backend/main.py）
  ├─ 题库 / 对话 / 评分 / 收录 / 报告 / 图谱 / 工具统计
  ├─ 采集链路与任务管理（crawler）
  ├─ 微调标注与模型对比接口（finetune / model bench）
  ├─ 定时任务 API（scheduler_api 挂载）
  └─ 推理轨迹 API（reasoning_api 挂载）
          │
          ├─ Agent 层：InterviewerAgent（对话编排）
          ├─ Agent 层：MinerAgent / MinerReActAgent（提取）
          ├─ 服务层：crawler / scheduling / finetune / storage / knowledge
          │
          ├─ SQLite（backend/data/local_data.db）
          ├─ Neo4j（docker compose）
          └─ Qdrant（docker compose）
```

---

## Agent 角色（真实命名）

### `MinerAgent`（采集与提取）

- 从采集内容中抽取题目、标签、知识点等结构化信息
- 支持 OCR 辅助、无关内容终止（`mark_unrelated`）等策略
- 与采集任务、批量重提取、Stage2 精答流程联动

### `InterviewerAgent`（对话与编排）

- 承担练习问答、流式回复、答题评分、学习建议
- 通过工具调用组织记忆、推荐、掌握度等业务能力
- 管理会话上下文与多轮对话编排（`get_orchestrator`）

---

## 前端页面（当前侧边栏）

`web/src/App.vue` 中当前导航项：

- `browse`：`BrowseView.vue`（题库浏览）
- `chat`：`ChatView.vue`（练习对话）
- `ingest`：`IngestView.vue`（收录面经）
- `collect`：`CollectView.vue`（数据采集）
- `scheduler`：`SchedulerView.vue`（定时任务）
- `report`：`ReportView.vue`（学习报告）
- `finetune`：`FinetuneView.vue`（微调标注）
- `tool_usage`：`ToolUsageView.vue`（工具统计）
- `graph_rag`：`GraphRagView.vue`（GraphRAG）
- `model_compare`：`ModelBenchView.vue`（模型对比）

---

## 核心能力清单

- **题库管理**：筛选、分页、随机抽题、智能组题
- **对话练习**：SSE 流式问答，支持会话历史
- **答题评估**：异步/流式评分、学习反馈、记录沉淀
- **采集链路**：抓取、清洗、提取、批量重提取、任务可视化
- **定时调度**：APScheduler 可视化管理，支持运行/启停/CRUD
- **微调流程**：样本标注、训练数据生成、模型对比评测
- **知识图谱与推荐**：Neo4j 图谱、Qdrant 向量检索、学习建议

---

## 快速开始

### 1) 环境要求

- Python 3.12+
- Conda 环境：`NewCoderAgent`
- Docker Desktop（Neo4j / Qdrant）
- Node.js（前端开发模式）

### 2) 安装依赖

```bash
cd E:\Agent\AgentProject\wxr_agent
copy .env.example .env
conda activate NewCoderAgent
pip install -r requirements.txt
python -m spacy download zh_core_web_sm
python -m spacy download en_core_web_sm
```

### 3) 启动基础服务

```bash
docker compose up -d
```

### 4) 启动后端

```bash
python run.py
```

### 5) 启动前端（开发模式）

```bash
cd web
npm install
npm run dev
```

### 6) 访问地址

- API：<http://localhost:8000>
- Swagger：<http://localhost:8000/docs>
- 前端开发：<http://localhost:5173>
- Neo4j：<http://localhost:7474>
- Qdrant：<http://localhost:6333/dashboard>

---

## API 入口（高频）

- `GET /api/config`：运行配置
- `GET /api/questions`：题库查询
- `GET /api/questions/smart-practice`：智能练习组题
- `POST /api/chat/stream`：流式对话
- `POST /api/submit_answer/stream`：流式评分
- `POST /api/ingest`：URL 收录
- `GET /api/crawler/stats`：采集统计
- `GET/POST /api/scheduler/*`：定时任务管理
- `GET/POST /api/finetune/*`：微调与模型对比
- `GET /api/reasoning/*`：推理轨迹查询

更完整接口文档见 [`docs/系统梳理/API全量文档.md`](docs/系统梳理/API全量文档.md)。

---

## 目录结构（精简版）

```text
InterviewExperienceCrawlerAgent/
├─ backend/
│  ├─ main.py
│  ├─ api/                  # scheduler_api / reasoning_api
│  ├─ agents/               # interviewer_agent / miner_agent / miner_react_agent
│  ├─ services/             # crawler / scheduling / storage / finetune / knowledge
│  ├─ tools/
│  ├─ config/config.py
│  └─ data/                 # local_data.db / neo4j_data / qdrant_storage / logs 等
├─ web/                     # Vue3 + Vite
├─ docs/                    # 系统梳理与使用文档
├─ 微调/                    # 训练脚本与产物
├─ docker-compose.yml
├─ run.py
└─ requirements.txt
```

---

## 配置说明

- 配置来源：项目根目录 `.env`
- 配置读取：`backend/config/config.py`
- 支持本地/远程 LLM 双模式（`LLM_MODE=local|remote`）
- 推荐先参考：
  - [`docs/STARTUP_GUIDE.md`](docs/STARTUP_GUIDE.md)
  - [`docs/环境配置说明.md`](docs/环境配置说明.md)

---

## 文档导航

- 文档索引：[`docs/README.md`](docs/README.md)
- 页面功能说明：[`docs/系统梳理/页面功能与按钮说明.md`](docs/系统梳理/页面功能与按钮说明.md)
- Agent 全景：
  - [`docs/系统梳理/Agent-Interviewer全景文档.md`](docs/系统梳理/Agent-Interviewer全景文档.md)
  - [`docs/系统梳理/Agent-Miner全景文档.md`](docs/系统梳理/Agent-Miner全景文档.md)
- 模型对比：[`docs/系统梳理/模型对比页面说明.md`](docs/系统梳理/模型对比页面说明.md)
- MCP 与扩展：
  - [`docs/MCP服务详解.md`](docs/MCP服务详解.md)
  - [`docs/MCP构建与部署指南.md`](docs/MCP构建与部署指南.md)

---

## 常见问题

### 1) 为什么 `python run.py` 仍提示环境问题？

`run.py` 会尝试切换到固定的 `NewCoderAgent` 解释器路径；若路径变化，请修改 `run.py` 中的 `CONDA_ENV_PYTHON`。

### 2) Neo4j / Qdrant 连接失败怎么办？

优先检查：

- `docker compose ps`
- `docker compose logs neo4j`
- `docker compose logs qdrant`

并确认 `.env` 中连接地址与 `docker-compose.yml` 端口一致。

### 3) 页面能打开但流式卡住怎么办？

先用直连后端方式排查：前端设置 `VITE_STREAM_DIRECT=true`，绕过代理缓存验证 SSE。

---

## 致谢

- [hello-agents](https://github.com/datawhalechina/hello-agents)
- [DataWhale](https://datawhale.club)
- 火山引擎 / 阿里云 / Ollama 等模型与基础设施能力
