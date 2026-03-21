# 面经 Agent 启动与排障指南

面向本地开发：后端（FastAPI）、前端（Vite）、可选本地 LLM（Ollama）、Docker 中的 Neo4j 与 Qdrant。

---

## 启动前检查

**Windows（PowerShell）示例：**

```powershell
conda activate NewCoderAgent
curl.exe -s http://localhost:11434/api/tags
curl.exe -s -o NUL -w "HTTP %{http_code}`n" http://localhost:8000/docs
```

- 未启动后端时，第二项非 200 属正常。
- Ollama 正常时应返回已安装模型的 JSON；后端就绪后 `/docs` 应为 HTTP 200。

---

## 依赖服务一览

| 服务 | 默认地址 | 说明 |
|------|----------|------|
| Neo4j | Bolt `bolt://localhost:7687`，浏览器 `http://localhost:7474` | `docker compose up -d` 中的 `neo4j` 服务 |
| Qdrant | `http://localhost:6333` | `docker compose` 中的 `qdrant`；向量记忆依赖 |
| Ollama（可选） | `http://localhost:11434` | `LLM_MODE=local` 时使用 |
| 后端 | `http://localhost:8000` | `python run.py` |
| 前端开发 | `http://localhost:5173` | `cd web && npm run dev` |

---

## 推荐启动顺序

### 1. Docker（Neo4j + Qdrant）

在项目根目录：

```bash
docker compose up -d
```

默认 Neo4j 账号见根目录 `docker-compose.yml` 中 `NEO4J_AUTH`；本地 `.env` 中 `NEO4J_URI` / `NEO4J_PASSWORD` 需与之一致。

### 2. 后端

**方式 A（推荐，Windows）：** 根目录 `run.py` 会检测当前解释器；若不是 `NewCoderAgent` 环境，会用脚本内配置的 `CONDA_ENV_PYTHON` 重新拉起进程（通常**无需**先手动 `conda activate`）。若你的 Conda 路径不同，请编辑 `run.py` 中的 `CONDA_ENV_PYTHON`。

**方式 B：** 手动激活后启动：

```bash
conda activate NewCoderAgent
cd E:\Agent\AgentProject\wxr_agent
python run.py
```

常用参数：`--reload`（开发热重载）、`--port 8000`、`--workers N`（生产多进程；开发一般用 1）。

启动成功后控制台会打印 API、`/docs`、Neo4j、Ollama 等提示。

### 3. 本地 LLM（`LLM_MODE=local` 时）

```bash
ollama serve
# 另开终端按需：ollama pull <模型名>
```

### 4. 前端（开发模式）

```bash
cd web
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。生产形态可将 `web` 构建到 `backend/static/dist`，由后端同端口托管（见 `README.md`）。

---

## 常见问题

### 前端提示初始化失败 / 无法连接后端

1. 确认后端已启动：`curl http://localhost:8000/api/config` 应返回 JSON。
2. 浏览器 F12 → Network：查看 `/api/config`、`/api/questions/meta` 是否 200。
3. 查看 `backend/logs/backend.log` 是否有 LLM / 数据库连接错误。

### Ollama 连接失败

- 确认 `11434` 端口监听：`netstat -ano | findstr :11434`（Windows）。
- `.env` 中 `LLM_LOCAL_BASE_URL` 默认 `http://localhost:11434/v1`。

### 模型不存在

```bash
ollama pull qwen3:4b
ollama list
```

可在 `.env` 中调整 `LLM_LOCAL_MODEL`。

### 前端依赖异常

```bash
cd web
rmdir /s /q node_modules
del package-lock.json
npm install
```

### 紧急重启（Windows）

关闭各终端 Ctrl+C 后，按需结束占用端口的进程，再按上文顺序重启。避免在未保存工作时强杀正在写入 SQLite 的进程。

---

## 配置要点（`.env`）

与启动强相关的项（完整列表以 `backend/config/config.py` 为准）：

```env
LLM_MODE=local
LLM_LOCAL_MODEL=qwen3:4b
LLM_LOCAL_BASE_URL=http://localhost:11434/v1

INTERVIEWER_MODE=
MINER_MODE=

NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=hello_agents_vectors

DEFAULT_USER_ID=Wangxr
```

修改 `.env` 后需**重启后端**。

---

## 性能相关（可选）

```env
SMART_PRACTICE_KNOWLEDGE_GAP_COUNT=5
SMART_PRACTICE_RANDOM_COUNT=5
LLM_LOCAL_MODEL=qwen3:1b
RERANK_ENABLED=false
WARMUP_EMBEDDING_RERANK_OCR=false
```

---

## 文档与接口

- OpenAPI：`http://localhost:8000/docs`
- 接口分组说明：`docs/系统梳理/API全量文档.md`
- 子进程与恢复：`docs/系统梳理/进程与子进程架构文档.md`
