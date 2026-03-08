# Agent 配置完整梳理与修复方案

## 🔍 当前问题

1. **Hunter Agent配置缺失**：`config.py`中定义了Hunter配置，但`.env`中没有
2. **配置不一致**：部分Agent有完整配置，部分只有部分配置
3. **配置不清晰**：不知道每个Agent用的什么模型和参数

---

## 📋 Agent 清单与配置映射

### 1. Interviewer Agent（面试官）
**文件位置**：`backend/agents/interviewer_agent.py`

**职责**：
- 自然对话、出题推荐策略
- 换个问法、筛选题目、笔记
- 掌握度查看、简历分析、知识推荐

**配置项**：
```bash
# .env 中的配置
INTERVIEWER_MODEL=qwen3:4b           # 模型名称
INTERVIEWER_API_KEY=                 # API Key（空则用全局）
INTERVIEWER_BASE_URL=                # Base URL（空则用全局）
INTERVIEWER_TEMPERATURE=0.5          # 温度（0.6推荐，对话需要创造性）
INTERVIEWER_MAX_STEPS=8              # 最大推理步数
```

**初始化代码**：
```python
llm = HelloAgentsLLM(
    provider=settings.llm_provider,
    model=settings.interviewer_model or settings.llm_model_id,
    api_key=settings.interviewer_api_key or settings.llm_api_key,
    base_url=settings.interviewer_base_url or settings.llm_base_url,
    temperature=settings.interviewer_temperature,
    timeout=settings.llm_timeout
)
```

---

### 2. Architect Agent（知识架构师）
**文件位置**：`backend/agents/architect_agent.py`

**职责**：
- 元信息提取
- 结构化解析
- 语义查重
- 双写入库（Neo4j + SQLite）

**配置项**：
```bash
# .env 中的配置
ARCHITECT_MODEL=qwen3:4b             # 模型名称
ARCHITECT_API_KEY=                   # API Key（空则用全局）
ARCHITECT_BASE_URL=                  # Base URL（空则用全局）
ARCHITECT_TEMPERATURE=0.2            # 温度（0.0推荐，结构化任务需要精确）
```

**初始化代码**：
```python
llm = HelloAgentsLLM(
    provider=settings.llm_provider,
    model=settings.architect_model,
    api_key=settings.architect_api_key or settings.llm_api_key,
    base_url=settings.architect_base_url or settings.llm_base_url,
    temperature=settings.architect_temperature,
    timeout=settings.llm_timeout
)
```

---

### 3. Hunter Agent（资源猎人）⚠️ 配置缺失
**文件位置**：`backend/tools/hunter_tools.py`

**职责**：
- 牛客网爬虫
- 小红书爬虫
- 网页内容抓取

**配置项**：
```bash
# config.py 中定义了，但 .env 中缺失！
HUNTER_MODEL=                        # ❌ 缺失
HUNTER_API_KEY=                      # ❌ 缺失
HUNTER_BASE_URL=                     # ❌ 缺失
HUNTER_TEMPERATURE=0.1               # ❌ 缺失
```

**问题**：
- Hunter Agent实际上是工具集合，不是独立的Agent
- 目前没有地方使用Hunter Agent的LLM配置
- 这些配置可能是预留的，但没有实际使用

---

### 4. 题目提取器（Question Extractor）
**文件位置**：`backend/services/crawler/question_extractor.py`

**职责**：
- 从面经原文中提取结构化题目
- LLM驱动的题目识别和分类

**配置项**：
```bash
# .env 中的配置
EXTRACTOR_TEMPERATURE=0.2            # 温度（0.0~0.2推荐，JSON输出需要精确）
EXTRACTOR_MAX_RETRIES=3              # 最大重试次数
```

**使用的LLM**：
- 使用**全局LLM配置**（`LLM_MODEL_ID`, `LLM_API_KEY`, `LLM_BASE_URL`）
- 不是独立的Agent，而是服务层的LLM调用

---

### 5. 微调辅助大模型
**文件位置**：`backend/services/finetune_service.py`

**职责**：
- 微调页面调用远程大模型
- 辅助生成标注数据

**配置项**：
```bash
# .env 中的配置
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=7e24e9d5-afc5-47f0-960b-c44b51993211
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_LLM_TEMPERATURE=0.2
```

---

## 🔧 修复方案

### 方案1：删除未使用的Hunter配置（推荐）

**原因**：
- Hunter Tools不是独立的Agent，而是工具集合
- 爬虫不需要LLM，只需要HTTP请求
- 这些配置从未被使用

**操作**：
1. 从`config.py`中删除Hunter相关配置
2. 不需要在`.env`中添加

### 方案2：补全Hunter配置（如果未来需要）

**如果Hunter将来需要LLM能力**（如智能解析网页内容），可以添加：

```bash
# .env 中添加
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2.5 Hunter Agent（资源猎人，用于智能网页解析）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HUNTER_MODEL=
HUNTER_API_KEY=
HUNTER_BASE_URL=
HUNTER_TEMPERATURE=0.1
```

---

## 📊 完整配置表

| Agent/服务 | 模型配置 | API Key | Base URL | Temperature | 用途 |
|-----------|---------|---------|----------|-------------|------|
| **全局LLM** | LLM_MODEL_ID | LLM_API_KEY | LLM_BASE_URL | 0.2 | 默认配置 |
| **Interviewer** | INTERVIEWER_MODEL | INTERVIEWER_API_KEY | INTERVIEWER_BASE_URL | 0.5 | 面试对话 |
| **Architect** | ARCHITECT_MODEL | ARCHITECT_API_KEY | ARCHITECT_BASE_URL | 0.2 | 知识架构 |
| **Hunter** | ❌ 未使用 | ❌ 未使用 | ❌ 未使用 | ❌ 未使用 | 爬虫工具 |
| **Extractor** | 使用全局 | 使用全局 | 使用全局 | 0.2 | 题目提取 |
| **Finetune** | FINETUNE_LLM_MODEL | FINETUNE_LLM_API_KEY | FINETUNE_LLM_BASE_URL | 0.2 | 微调辅助 |

---

## 🎯 推荐配置（统一使用本地Ollama）

```bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 全局 LLM（默认配置）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_TIMEOUT=180
LLM_TEMPERATURE=0.2

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 各 Agent 差异化配置（留空则使用全局配置）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Architect Agent（知识架构师）- 结构化任务，需要精确
ARCHITECT_MODEL=qwen3:4b
ARCHITECT_API_KEY=
ARCHITECT_BASE_URL=
ARCHITECT_TEMPERATURE=0.2

# Interviewer Agent（面试官）- 对话任务，需要创造性
INTERVIEWER_MODEL=qwen3:4b
INTERVIEWER_API_KEY=
INTERVIEWER_BASE_URL=
INTERVIEWER_TEMPERATURE=0.5
INTERVIEWER_MAX_STEPS=8

# 题目提取器 - 结构化JSON输出，需要精确
EXTRACTOR_TEMPERATURE=0.2
EXTRACTOR_MAX_RETRIES=3

# 微调辅助 - 使用云端大模型（更强大）
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=your_api_key_here
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_LLM_TEMPERATURE=0.2
```

---

## 🔍 配置优先级

每个Agent的配置优先级：

1. **Agent专属配置**（如`INTERVIEWER_MODEL`）
2. **全局配置**（如`LLM_MODEL_ID`）

示例：
```python
# Interviewer Agent 初始化
model = settings.interviewer_model or settings.llm_model_id
api_key = settings.interviewer_api_key or settings.llm_api_key
base_url = settings.interviewer_base_url or settings.llm_base_url
```

如果`INTERVIEWER_MODEL`为空，则使用`LLM_MODEL_ID`。

---

## 📝 配置建议

### 场景1：全部使用本地Ollama
```bash
# 只配置全局LLM，所有Agent留空
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_BASE_URL=http://localhost:11434/v1

ARCHITECT_MODEL=
INTERVIEWER_MODEL=
```

### 场景2：混合使用（本地+云端）
```bash
# 全局使用本地Ollama
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b

# 面试官使用云端大模型（更智能）
INTERVIEWER_MODEL=doubao-1-5-pro-32k-250115
INTERVIEWER_API_KEY=your_api_key
INTERVIEWER_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

### 场景3：全部使用云端
```bash
# 全局使用云端
LLM_PROVIDER=volcengine
LLM_MODEL_ID=doubao-1-5-pro-32k-250115
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 各Agent留空，使用全局配置
ARCHITECT_MODEL=
INTERVIEWER_MODEL=
```

---

## 🎉 总结

### 当前状态
- ✅ Interviewer Agent：配置完整
- ✅ Architect Agent：配置完整
- ❌ Hunter Agent：配置定义但未使用
- ✅ Extractor：使用全局配置
- ✅ Finetune：配置完整

### 建议操作
1. **删除Hunter配置**（从config.py中删除，因为未使用）
2. **统一配置管理**（所有配置都在.env中）
3. **添加配置文档**（说明每个Agent的用途和推荐配置）

### 下一步
我可以帮你：
1. 删除未使用的Hunter配置
2. 创建一个配置模板文件
3. 添加配置验证脚本
