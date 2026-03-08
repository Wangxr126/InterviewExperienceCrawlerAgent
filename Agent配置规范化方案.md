# Agent 配置规范化方案

## 🚨 当前问题

### 1. 配置不完整
- ❌ 每个Agent缺少 `PROVIDER` 配置
- ❌ 每个Agent缺少 `TIMEOUT` 配置
- ❌ 配置项不统一

### 2. 本地/远程混用不清晰
- ❌ 无法明确区分哪个Agent用本地，哪个用远程
- ❌ 切换本地/远程需要修改多个配置项

### 3. 回退逻辑不明确
- ❌ 有些配置回退到全局，有些不回退
- ❌ 没有统一的规则

---

## ✅ 统一配置规范

### 每个Agent必须有的配置项

```bash
# Agent名称_PROVIDER    - 提供商（ollama/volcengine/openai等）
# Agent名称_MODEL       - 模型名称
# Agent名称_API_KEY     - API Key
# Agent名称_BASE_URL    - Base URL
# Agent名称_TIMEOUT     - 超时时间（秒）
# Agent名称_TEMPERATURE - 温度（0.0-1.0）
```

### 配置优先级

```
Agent专属配置 > 全局配置 > 默认值
```

---

## 📋 完整配置方案

### 方案A：统一规范（推荐）

```bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 全局 LLM 配置（默认配置）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_TIMEOUT=180
LLM_TEMPERATURE=0.3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Architect Agent（知识架构师）
#    留空则使用全局配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARCHITECT_PROVIDER=                  # 留空使用 LLM_PROVIDER
ARCHITECT_MODEL=                     # 留空使用 LLM_MODEL_ID
ARCHITECT_API_KEY=                   # 留空使用 LLM_API_KEY
ARCHITECT_BASE_URL=                  # 留空使用 LLM_BASE_URL
ARCHITECT_TIMEOUT=                   # 留空使用 LLM_TIMEOUT
ARCHITECT_TEMPERATURE=0.2            # 结构化任务，建议 0.0-0.2

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Interviewer Agent（面试官）
#    留空则使用全局配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERVIEWER_PROVIDER=                # 留空使用 LLM_PROVIDER
INTERVIEWER_MODEL=                   # 留空使用 LLM_MODEL_ID
INTERVIEWER_API_KEY=                 # 留空使用 LLM_API_KEY
INTERVIEWER_BASE_URL=                # 留空使用 LLM_BASE_URL
INTERVIEWER_TIMEOUT=                 # 留空使用 LLM_TIMEOUT
INTERVIEWER_TEMPERATURE=0.6          # 对话任务，建议 0.5-0.7
INTERVIEWER_MAX_STEPS=8              # 最大推理步数

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Extractor（题目提取器）
#    使用全局 LLM 配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTOR_TEMPERATURE=0.2            # JSON输出，建议 0.0-0.2
EXTRACTOR_MAX_RETRIES=3              # 最大重试次数

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Finetune LLM（微调辅助大模型）
#    通常使用云端大模型
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINETUNE_LLM_PROVIDER=volcengine
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=your_api_key_here
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_LLM_TIMEOUT=180
FINETUNE_LLM_TEMPERATURE=0.2
```

---

## 🔧 config.py 需要修改的地方

### 当前问题

```python
# ❌ 缺少 provider 和 timeout
@property
def architect_model(self) -> str:
    return _get("ARCHITECT_MODEL") or self.llm_model_id

@property
def architect_api_key(self) -> str:
    return _get("ARCHITECT_API_KEY") or self.llm_api_key

@property
def architect_base_url(self) -> str:
    return _get("ARCHITECT_BASE_URL") or self.llm_base_url

@property
def architect_temperature(self) -> float:
    return _get_float("ARCHITECT_TEMPERATURE", 0.0)
```

### 应该改为

```python
# ✅ 完整的配置项
@property
def architect_provider(self) -> str:
    return _get("ARCHITECT_PROVIDER") or self.llm_provider

@property
def architect_model(self) -> str:
    return _get("ARCHITECT_MODEL") or self.llm_model_id

@property
def architect_api_key(self) -> str:
    return _get("ARCHITECT_API_KEY") or self.llm_api_key

@property
def architect_base_url(self) -> str:
    return _get("ARCHITECT_BASE_URL") or self.llm_base_url

@property
def architect_timeout(self) -> int:
    return _get_int("ARCHITECT_TIMEOUT") or self.llm_timeout

@property
def architect_temperature(self) -> float:
    return _get_float("ARCHITECT_TEMPERATURE", 0.0)
```

---

## 📊 配置对比表

### 修改前（不完整）

| Agent | Provider | Model | API Key | Base URL | Timeout | Temperature |
|-------|----------|-------|---------|----------|---------|-------------|
| Architect | ❌ 缺失 | ✅ | ✅ | ✅ | ❌ 缺失 | ✅ |
| Interviewer | ❌ 缺失 | ✅ | ✅ | ✅ | ❌ 缺失 | ✅ |
| Finetune | ❌ 缺失 | ✅ | ✅ | ✅ | ❌ 缺失 | ✅ |

### 修改后（完整）

| Agent | Provider | Model | API Key | Base URL | Timeout | Temperature |
|-------|----------|-------|---------|----------|---------|-------------|
| Architect | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Interviewer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Finetune | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 🎯 使用场景

### 场景1：全部使用本地Ollama

```bash
# 全局配置
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_BASE_URL=http://localhost:11434/v1
LLM_TIMEOUT=180

# 各Agent留空，自动使用全局配置
ARCHITECT_PROVIDER=
ARCHITECT_MODEL=
ARCHITECT_BASE_URL=
ARCHITECT_TIMEOUT=

INTERVIEWER_PROVIDER=
INTERVIEWER_MODEL=
INTERVIEWER_BASE_URL=
INTERVIEWER_TIMEOUT=
```

### 场景2：Interviewer用云端，其他用本地

```bash
# 全局配置（本地）
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_BASE_URL=http://localhost:11434/v1
LLM_TIMEOUT=180

# Architect 留空（使用本地）
ARCHITECT_PROVIDER=
ARCHITECT_MODEL=

# Interviewer 使用云端
INTERVIEWER_PROVIDER=volcengine
INTERVIEWER_MODEL=doubao-1-5-pro-32k-250115
INTERVIEWER_API_KEY=your_key
INTERVIEWER_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
INTERVIEWER_TIMEOUT=300  # 云端可能需要更长超时
```

### 场景3：全部使用云端

```bash
# 全局配置（云端）
LLM_PROVIDER=volcengine
LLM_MODEL_ID=doubao-1-5-pro-32k-250115
LLM_API_KEY=your_key
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_TIMEOUT=300

# 各Agent留空，自动使用全局配置
ARCHITECT_PROVIDER=
INTERVIEWER_PROVIDER=
```

---

## 🔍 为什么需要每个Agent都有完整配置？

### 1. Provider 很重要
不同provider的API格式可能不同：
- `ollama`: 本地服务，需要特殊处理
- `volcengine`: 火山引擎，有特定的认证方式
- `openai`: OpenAI兼容接口

### 2. Timeout 很重要
不同场景需要不同的超时时间：
- **本地Ollama**: 30-60秒（快速响应）
- **云端API**: 180-300秒（网络延迟）
- **复杂任务**: 300-600秒（长时间推理）

### 3. 灵活性
- 可以让某个Agent用本地，其他用云端
- 可以给不同Agent设置不同的超时时间
- 可以根据任务类型调整配置

---

## 📝 需要修改的文件

### 1. `.env` 文件
添加缺失的配置项：
- `ARCHITECT_PROVIDER`
- `ARCHITECT_TIMEOUT`
- `INTERVIEWER_PROVIDER`
- `INTERVIEWER_TIMEOUT`
- `FINETUNE_LLM_PROVIDER`
- `FINETUNE_LLM_TIMEOUT`

### 2. `backend/config/config.py`
为每个Agent添加：
- `xxx_provider` 属性
- `xxx_timeout` 属性

### 3. Agent初始化代码
使用完整的配置：
```python
llm = HelloAgentsLLM(
    provider=settings.interviewer_provider,  # ✅ 添加
    model=settings.interviewer_model or settings.llm_model_id,
    api_key=settings.interviewer_api_key or settings.llm_api_key,
    base_url=settings.interviewer_base_url or settings.llm_base_url,
    timeout=settings.interviewer_timeout,    # ✅ 添加
    temperature=settings.interviewer_temperature,
)
```

---

## 🎉 修改后的好处

1. ✅ **配置完整**：每个Agent都有所有必需的配置项
2. ✅ **统一规范**：所有Agent使用相同的配置结构
3. ✅ **灵活切换**：可以轻松切换本地/远程
4. ✅ **独立控制**：每个Agent可以独立配置超时时间
5. ✅ **清晰明了**：一眼就能看出每个Agent的配置

---

## 🚀 下一步

我可以帮你：
1. 修改 `config.py`，添加缺失的 provider 和 timeout 属性
2. 更新 `.env` 文件，添加完整的配置项
3. 修改 Agent 初始化代码，使用完整配置
4. 创建配置验证脚本，检查配置完整性

你想让我开始修改吗？
