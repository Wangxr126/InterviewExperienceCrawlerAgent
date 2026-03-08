# 面经 Agent

> 基于 [hello-agents](https://github.com/datawhalechina/hello-agents) 框架构建的智能面试复习助手。
> 自动爬取牛客/小红书面经、构建知识图谱、用 SM-2 算法跟踪掌握程度，并提供 AI 面试对话练习。


---

## ⚙️ 运行环境

**Conda环境：** `NewCoderAgent`

```bash
# 激活环境
conda activate NewCoderAgent

# 启动后端
python run.py
```

**注意：** 所有Python命令都需要先激活此环境！
---

## 功能概览

| 模块 | 功能 |
|------|------|
| **题库浏览** | 按公司、难度、标签、关键词筛选题目；随机抽题 |
| **面试对话** | 与 AI 面试官实时对话，支持换个问法、举一反三 |
| **答题评测** | 提交答案后获得评分（0-5）、强弱点分析、AI 解析 |
| **掌握度追踪** | SM-2 算法计算复习周期，弱点标签自动识别 |
| **知识推荐** | 针对薄弱点推荐学习资源和知识章节 |
| **记忆系统** | hello-agents 四层记忆（工作/情节/语义）持久化对话上下文 |
| **面经收录** | 输入牛客/小红书帖子 URL，自动爬取并入库 |
| **笔记功能** | 对任意题目添加个人笔记 |

---

## 技术架构

```
┌─────────────────────────────────────────────────────┐
│                   前端 (Vue 3 + Vite + Element Plus)  │
│                   web/ → backend/static/dist          │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (localhost:8000)
┌──────────────────────▼──────────────────────────────┐
│              FastAPI 后端 (backend/main.py)           │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │          InterviewSystemOrchestrator        │   │
│  │  ┌────────────┐  ┌──────────────────────┐  │   │
│  │  │ Architect  │  │   InterviewerAgent   │  │   │
│  │  │  (ReAct)   │  │     (ReAct)          │  │   │
│  │  └────────────┘  └──────────────────────┘  │   │
│  │       HunterPipeline（确定性爬虫流水线）      │   │
│  └─────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────┘
          ┌────────────┼────────────────┐
   ┌──────▼──────┐ ┌───▼────┐ ┌────────▼────────┐
   │  Neo4j      │ │ Qdrant │ │    SQLite        │
   │ (知识图谱)   │ │(记忆)  │ │ (用户/题库/记录) │
   │ localhost   │ │ Cloud  │ │  local_data.db   │
   │ :7687       │ │        │ │                  │
   └─────────────┘ └────────┘ └──────────────────┘
```

---

## 环境要求

| 组件 | 版本 / 要求 |
|------|------------|
| Python | 3.12+ |
| Conda 环境 | `NewCoderAgent` |
| Docker Desktop | 需运行（用于本地 Neo4j） |
| 操作系统 | Windows 10/11（已测试） |

---

## 快速开始

### 第一步：克隆 / 进入项目

```powershell
cd E:\Agent\AgentProject\wxr_agent
```

### 第二步：安装依赖

```powershell
# 激活 conda 环境
conda activate NewCoderAgent

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 spaCy 语言模型（仅首次）
python -m spacy download zh_core_web_sm
python -m spacy download en_core_web_sm
```

### 第三步：启动 Neo4j（本地 Docker）

```powershell
# 首次需拉取镜像（约 400MB，需 Docker Desktop 运行且网络正常）
docker compose up -d

# 验证 Neo4j 是否就绪（等待约 30 秒后执行）
python check_neo4j.py
```

浏览器访问 http://localhost:7474 可打开 Neo4j 管理界面（用户名/密码见 `CREDENTIALS.md`）。

### 第四步：启动后端

```powershell
python run.py
```

`run.py` 会自动切换到 `NewCoderAgent` conda 环境，无需手动 `conda activate`。

启动成功后终端输出：
```
✅ Neo4j (localhost:7687) 连接正常
╔══════════════════════════════════════════════════════╗
║            面经 Agent 后端已启动                      ║
╠══════════════════════════════════════════════════════╣
║  Python 环境：NewCoderAgent                          ║
║  API 地址  ：http://localhost:8000
║  API 文档  ：http://localhost:8000/docs
╚══════════════════════════════════════════════════════╝
```

### 第五步：构建并打开前端

```powershell
cd web
npm install
npm run build
```

构建完成后，访问 http://localhost:8000 即可使用。开发模式可运行 `npm run dev`，访问 http://localhost:5173。

---

## 目录结构

```
wxr_agent/
├── run.py                  # 启动脚本（自动切换 conda 环境）
├── check_neo4j.py          # Neo4j 知识图谱检查工具
├── debug_test.py           # 后端功能 CLI 调试工具
├── docker-compose.yml      # Neo4j 本地 Docker 配置
├── requirements.txt        # Python 依赖
├── .env                    # 环境变量（密钥配置）
├── CREDENTIALS.md          # 密钥与服务配置清单（勿公开）
│
├── backend/
│   ├── main.py             # FastAPI 入口
│   ├── config/config.py    # 统一配置
│   ├── data/               # 后端数据（SQLite、memory、neo4j、qdrant 等）
│   ├── static/dist/        # 前端构建产物（由 web 构建生成）
│   ├── agents/
│   │   ├── orchestrator.py      # 系统编排器（主控）
│   │   ├── interviewer_agent.py # 面试官 Agent（ReAct）
│   │   ├── architect_agent.py   # 知识架构师 Agent（ReAct）
│   │   └── prompts/             # 各 Agent 提示词
│   ├── services/
│   │   ├── neo4j_service.py     # 知识图谱服务
│   │   ├── sqlite_service.py    # 本地数据服务
│   │   └── hunter_pipeline.py   # 面经爬虫流水线
│   └── tools/
│       ├── hunter_tools.py      # 爬虫工具集
│       ├── interviewer_tools.py # 面试工具集
│       └── architect_tools.py   # 知识结构化工具集
│
└── web/                    # Vue 3 + Vite 前端工程（npm run build → backend/static/dist）
```

---

## 主要 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/questions` | 列出/筛选题目（company/tag/difficulty/keyword/random/limit） |
| `GET` | `/api/questions/random` | 随机取一道题 |
| `GET` | `/api/questions/meta` | 获取所有公司、标签、岗位（用于前端筛选器） |
| `POST` | `/api/chat` | 与面试官 Agent 对话 |
| `POST` | `/api/submit_answer` | 提交答案（结构化评分 + SM-2 更新 + 记忆写入） |
| `POST` | `/api/ingest` | 收录面经（输入 URL，触发爬虫流水线） |
| `GET` | `/api/user/{id}/mastery` | 获取用户掌握度报告 |
| `GET` | `/api/user/{id}/reviews` | 获取今日应复习题目（SM-2） |
| `GET` | `/api/resources` | 获取知识资源推荐（按标签） |
| `POST` | `/api/notes` | 添加笔记 |
| `POST` | `/api/session/end` | 结束会话（触发本轮评估） |

完整接口文档：http://localhost:8000/docs（后端启动后访问）

---

## 常见问题

### Q: 如何配置默认用户和 Agent 步数？
在 `.env` 中添加：
- `DEFAULT_USER_ID=user_001`：前端默认用户 ID（未填写时使用）
- `INTERVIEWER_MAX_STEPS=8`：Interviewer Agent 最大思考步数（默认 8）

### Q: `MemoryTool 初始化失败`
`.env` 文件没有被 `hello_agents` 读取。确认项目根目录存在 `.env` 文件，且 `backend/main.py` 开头有 `load_dotenv(override=True)`。

### Q: Neo4j DNS 解析失败（云端）
改用本地 Docker：`docker compose up -d`，并修改 `backend/config/config.py` 中 `neo4j_uri` 为 `bolt://localhost:7687`。

### Q: Docker 拉取镜像失败（代理问题）
检查 Windows IE 代理注册表：
```powershell
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" | Select ProxyEnable, ProxyServer
# ProxyEnable 应为 0
Set-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -Name ProxyEnable -Value 0
```
然后重启 Docker Desktop。

### Q: `SetLimitExceeded (429)` LLM 限流
进入火山引擎控制台 → 模型推理 → 在线推理 → 关闭「安全体验模式」或提升推理配额。

### Q: 开发模式（代码改动自动重启）
```powershell
python run.py --reload
```

---

## 数据说明

| 数据 | 存储位置 | 说明 |
|------|----------|------|
| 面试题目、知识图谱 | Neo4j（本地 Docker） | 通过「收录面经」功能入库 |
| 用户记录、SM-2 参数 | SQLite (`local_data.db`) | 自动创建 |
| 四层记忆（对话上下文） | Qdrant Cloud + Neo4j | hello-agents 框架管理 |
| 学习资源 | SQLite | 首次启动自动预置 |

---

## 致谢

- [hello-agents](https://github.com/datawhalechina/hello-agents)：Agent 框架
- [DataWhale](https://datawhale.club)：开源社区
- 火山引擎 Doubao / 阿里云 DashScope：LLM & Embedding 服务

