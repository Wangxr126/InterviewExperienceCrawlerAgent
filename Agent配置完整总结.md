# Agent 配置完整总结

## 🎯 问题解决

### 原始问题
> "我有时候根本不知道每个agent用的什么配置"

### 解决方案
✅ **所有配置都在 `.env` 文件中维护**
✅ **删除了未使用的 Hunter Agent 配置**
✅ **创建了配置验证脚本**

---

## 📋 Agent 配置清单

### 1️⃣ Interviewer Agent（面试官）

**文件位置**：`backend/agents/interviewer_agent.py`

**职责**：
- 自然对话、出题推荐策略
- 换个问法、筛选题目、笔记
- 掌握度查看、简历分析、知识推荐

**配置项**（在 `.env` 中）：
```bash
INTERVIEWER_MODEL=qwen3:4b           # 留空则使用 LLM_MODEL_ID
INTERVIEWER_API_KEY=                 # 留空则使用 LLM_API_KEY
INTERVIEWER_BASE_URL=                # 留空则使用 LLM_BASE_URL
INTERVIEWER_TEMPERATURE=0.5          # 对话需要创造性，建议 0.5-0.7
INTERVIEWER_MAX_STEPS=8              # 最大推理步数
```

**初始化逻辑**：
```python
# backend/agents/interviewer_agent.py
model = settings.interviewer_model or settings.llm_model_id
api_key = settings.interviewer_api_key or settings.llm_api_key
base_url = settings.interviewer_base_url or settings.llm_base_url
temperature = settings.interviewer_temperature
```

---

### 2️⃣ Architect Agent（知识架构师）

**文件位置**：`backend/agents/architect_agent.py`

**职责**：
- 元信息提取
- 结构化解析
- 语义查重
- 双写入库（Neo4j + SQLite）

**配置项**（在 `.env` 中）：
```bash
ARCHITECT_MODEL=qwen3:4b             # 留空则使用 LLM_MODEL_ID
ARCHITECT_API_KEY=                   # 留空则使用 LLM_API_KEY
ARCHITECT_BASE_URL=                  # 留空则使用 LLM_BASE_URL
ARCHITECT_TEMPERATURE=0.2            # 结构化任务需要精确，建议 0.0-0.2
```

**初始化逻辑**：
```python
# backend/agents/architect_agent.py
model = settings.architect_model
api_key = settings.architect_api_key or settings.llm_api_key
base_url = settings.architect_base_url or settings.llm_base_url
temperature = settings.architect_temperature
```

---

### 3️⃣ Question Extractor（题目提取器）

**文件位置**：`backend/services/crawler/question_extractor.py`

**职责**：
- 从面经原文中提取结构化题目
- LLM驱动的题目识别和分类

**配置项**（在 `.env` 中）：
```bash
EXTRACTOR_TEMPERATURE=0.2            # JSON输出需要精确，建议 0.0-0.2
EXTRACTOR_MAX_RETRIES=3              # 提取失败时的最大重试次数
```

**使用的LLM**：
- **直接使用全局LLM配置**（`LLM_MODEL_ID`, `LLM_API_KEY`, `LLM_BASE_URL`）
- 不是独立的Agent，而是服务层的LLM调用

---

### 4️⃣ Finetune LLM（微调辅助大模型）

**文件位置**：`backend/services/finetune_service.py`

**职责**：
- 微调页面调用远程大模型
- 辅助生成标注数据

**配置项**（在 `.env` 中）：
```bash
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=your_api_key_here
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_LLM_TEMPERATURE=0.2
```

**使用场景**：
- 通常使用云端大模型（更强大）
- 用于生成高质量的标注数据

---

### 5️⃣ Hunter Tools（资源猎人工具）

**文件位置**：`backend/tools/hunter_tools.py`

**职责**：
- 牛客网爬虫
- 小红书爬虫
- 网页内容抓取

**配置项**：
- ❌ **不需要LLM配置**
- ✅ 只是HTTP爬虫工具集合
- ✅ 已从 `config.py` 中删除未使用的配置

---

## 🔧 配置文件结构

### `.env` 文件（所有配置的唯一来源）

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

# Architect Agent（知识架构师）
ARCHITECT_MODEL=qwen3:4b
ARCHITECT_API_KEY=
ARCHITECT_BASE_URL=
ARCHITECT_TEMPERATURE=0.2

# Interviewer Agent（面试官）
INTERVIEWER_MODEL=qwen3:4b
INTERVIEWER_API_KEY=
INTERVIEWER_BASE_URL=
INTERVIEWER_TEMPERATURE=0.5
INTERVIEWER_MAX_STEPS=8

# 题目提取器
EXTRACTOR_TEMPERATURE=0.2
EXTRACTOR_MAX_RETRIES=3

# 微调辅助大模型
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=your_api_key_here
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_LLM_TEMPERATURE=0.2
```

### `backend/config/config.py`（只读取.env）

```python
class _Settings:
    # 1. 全局 LLM
    @property
    def llm_provider(self) -> str:
        return _get("LLM_PROVIDER", "volcengine")
    
    @property
    def llm_model_id(self) -> str:
        return _get("LLM_MODEL_ID")
    
    # 2. Architect Agent
    @property
    def architect_model(self) -> str:
        return _get("ARCHITECT_MODEL") or self.llm_model_id
    
    # 3. Interviewer Agent
    @property
    def interviewer_model(self) -> str:
        return _get("INTERVIEWER_MODEL") or self.llm_model_id
    
    # ... 其他配置
```

---

## 📊 配置优先级

```
Agent专属配置 > 全局配置
```

**示例**：
```python
# 如果 INTERVIEWER_MODEL 为空
model = settings.interviewer_model or settings.llm_model_id
# 则使用 LLM_MODEL_ID

# 如果 INTERVIEWER_MODEL = "qwen3:4b"
model = settings.interviewer_model or settings.llm_model_id
# 则使用 "qwen3:4b"
```

---

## 🎨 推荐配置方案

### 方案1：全部使用本地Ollama（推荐）

```bash
# 全局配置
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_BASE_URL=http://localhost:11434/v1

# 各Agent留空，使用全局配置
ARCHITECT_MODEL=
INTERVIEWER_MODEL=

# 微调使用云端大模型
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=your_key
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

### 方案2：混合使用（本地+云端）

```bash
# 全局使用本地Ollama
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_BASE_URL=http://localhost:11434/v1

# 面试官使用云端大模型（更智能）
INTERVIEWER_MODEL=doubao-1-5-pro-32k-250115
INTERVIEWER_API_KEY=your_key
INTERVIEWER_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 架构师使用本地（留空）
ARCHITECT_MODEL=
```

### 方案3：全部使用云端

```bash
# 全局使用云端
LLM_PROVIDER=volcengine
LLM_MODEL_ID=doubao-1-5-pro-32k-250115
LLM_API_KEY=your_key
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 各Agent留空，使用全局配置
ARCHITECT_MODEL=
INTERVIEWER_MODEL=
```

---

## 🔍 如何查看当前配置

### 方法1：运行验证脚本

```bash
python verify_agent_config.py
```

输出示例：
```
[1] 全局 LLM 配置
  Provider:    ollama
  Model:       qwen3:4b
  Base URL:    http://localhost:11434/v1
  Temperature: 0.2

[2] Interviewer Agent
  Model:       qwen3:4b
  Temperature: 0.5
  实际使用:
    - Model:   qwen3:4b
    - URL:     http://localhost:11434/v1
```

### 方法2：查看日志

启动后端时，每个Agent初始化都会打印日志：

```
Interviewer LLM: provider=ollama, model=qwen3:4b, base=http://localhost:11434/v1
```

---

## ✅ 配置检查清单

- [ ] `.env` 文件中 `LLM_MODEL_ID` 已配置
- [ ] `.env` 文件中 `LLM_BASE_URL` 已配置
- [ ] Interviewer temperature 在 0.5-0.7 之间
- [ ] Architect temperature 在 0.0-0.2 之间
- [ ] Extractor temperature 在 0.0-0.2 之间
- [ ] OCR 的 `ANTHROPIC_API_KEY` 已配置（如果使用Claude Vision）
- [ ] 删除了未使用的 Hunter 配置

---

## 📝 相关文件

1. **配置文件**：
   - `.env` - 所有配置的唯一来源
   - `backend/config/config.py` - 配置读取器

2. **Agent文件**：
   - `backend/agents/interviewer_agent.py` - 面试官
   - `backend/agents/architect_agent.py` - 知识架构师

3. **服务文件**：
   - `backend/services/crawler/question_extractor.py` - 题目提取器
   - `backend/services/finetune_service.py` - 微调辅助

4. **工具文件**：
   - `backend/tools/hunter_tools.py` - 爬虫工具（不需要LLM）

5. **验证脚本**：
   - `verify_agent_config.py` - 配置验证脚本
   - `Agent配置完整梳理.md` - 详细文档

---

## 🎉 总结

### 修复内容
1. ✅ 删除了 `config.py` 中未使用的 Hunter 配置
2. ✅ 所有配置都在 `.env` 中维护
3. ✅ 创建了配置验证脚本
4. ✅ 创建了完整的配置文档

### 配置原则
1. **单一来源**：所有配置都在 `.env` 中
2. **优先级明确**：Agent专属 > 全局
3. **回退机制**：Agent配置为空时使用全局配置
4. **温度建议**：
   - 对话任务（Interviewer）：0.5-0.7
   - 结构化任务（Architect, Extractor）：0.0-0.2

### 现在你可以：
- ✅ 清楚知道每个Agent用的什么配置
- ✅ 在 `.env` 中统一管理所有配置
- ✅ 运行验证脚本查看当前配置
- ✅ 根据需求灵活调整配置
