# Agent 配置梳理 - 最终总结

## 🎯 你的问题

> "目前看来就是agent在初始化时候有很大问题，我有时候根本不知道每个agent用的什么配置。你帮我梳理下agent对应的文件和.env中的配置以及backend\config\config.py。看看能不能所有的配置都放在.env中进行维护？？？？"

## ✅ 已完成

### 1. 梳理了所有Agent配置

| Agent/服务 | 文件位置 | 配置项 | 用途 |
|-----------|---------|-------|------|
| **Interviewer** | `backend/agents/interviewer_agent.py` | INTERVIEWER_MODEL<br>INTERVIEWER_TEMPERATURE<br>INTERVIEWER_MAX_STEPS | 面试对话<br>出题推荐<br>笔记管理 |
| **Architect** | `backend/agents/architect_agent.py` | ARCHITECT_MODEL<br>ARCHITECT_TEMPERATURE | 知识架构<br>结构化解析<br>语义查重 |
| **Extractor** | `backend/services/crawler/question_extractor.py` | EXTRACTOR_TEMPERATURE<br>EXTRACTOR_MAX_RETRIES | 题目提取<br>使用全局LLM |
| **Finetune** | `backend/services/finetune_service.py` | FINETUNE_LLM_MODEL<br>FINETUNE_LLM_API_KEY<br>FINETUNE_LLM_BASE_URL | 微调辅助<br>标注生成 |
| **Hunter** | `backend/tools/hunter_tools.py` | ❌ 无需LLM配置 | 爬虫工具<br>HTTP请求 |

### 2. 删除了未使用的配置

- ✅ 从 `config.py` 中删除了 Hunter Agent 的 LLM 配置
- ✅ Hunter Tools 只是爬虫工具集合，不需要 LLM

### 3. 确认所有配置都在 `.env` 中

**配置流程**：
```
.env 文件 → config.py 读取 → Agent 使用
```

**配置优先级**：
```
Agent专属配置 > 全局配置
```

**示例**：
```python
# Interviewer Agent 初始化
model = settings.interviewer_model or settings.llm_model_id
# 如果 INTERVIEWER_MODEL 为空，则使用 LLM_MODEL_ID
```

---

## 📋 完整配置清单

### `.env` 文件结构

```bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 全局 LLM（所有Agent的默认配置）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LLM_PROVIDER=ollama                  # 提供商：ollama/volcengine/openai
LLM_MODEL_ID=qwen3:4b                # 模型名称
LLM_API_KEY=ollama                   # API Key
LLM_BASE_URL=http://localhost:11434/v1  # Base URL
LLM_TIMEOUT=180                      # 超时时间（秒）
LLM_TEMPERATURE=0.2                  # 温度（0.0-1.0）

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Architect Agent（知识架构师）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARCHITECT_MODEL=qwen3:4b             # 留空则使用 LLM_MODEL_ID
ARCHITECT_API_KEY=                   # 留空则使用 LLM_API_KEY
ARCHITECT_BASE_URL=                  # 留空则使用 LLM_BASE_URL
ARCHITECT_TEMPERATURE=0.2            # 结构化任务，建议 0.0-0.2

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Interviewer Agent（面试官）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERVIEWER_MODEL=qwen3:4b           # 留空则使用 LLM_MODEL_ID
INTERVIEWER_API_KEY=                 # 留空则使用 LLM_API_KEY
INTERVIEWER_BASE_URL=                # 留空则使用 LLM_BASE_URL
INTERVIEWER_TEMPERATURE=0.5          # 对话任务，建议 0.5-0.7
INTERVIEWER_MAX_STEPS=8              # 最大推理步数

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Question Extractor（题目提取器）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTOR_TEMPERATURE=0.2            # JSON输出，建议 0.0-0.2
EXTRACTOR_MAX_RETRIES=3              # 最大重试次数

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Finetune LLM（微调辅助大模型）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINETUNE_LLM_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_LLM_API_KEY=your_api_key_here
FINETUNE_LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_LLM_TEMPERATURE=0.2
```

---

## 🔍 如何查看当前配置

### 方法1：运行验证脚本

```bash
python verify_agent_config.py
```

会显示：
- 全局LLM配置
- 每个Agent的配置
- 实际使用的配置（考虑回退）
- 配置问题和建议

### 方法2：查看启动日志

启动后端时，每个Agent会打印初始化日志：

```
Interviewer LLM: provider=ollama, model=qwen3:4b, base=http://localhost:11434/v1
```

---

## 📚 创建的文档

1. **Agent配置完整梳理.md** - 详细的配置说明和方案
2. **Agent配置完整总结.md** - 配置清单和使用指南
3. **verify_agent_config.py** - 配置验证脚本

---

## 🎯 温度（Temperature）建议

| 任务类型 | 推荐温度 | Agent |
|---------|---------|-------|
| **对话任务** | 0.5-0.7 | Interviewer |
| **结构化输出** | 0.0-0.2 | Architect, Extractor |
| **JSON生成** | 0.0-0.2 | Finetune |

**温度说明**：
- **0.0-0.2**：精确、确定性强，适合结构化任务
- **0.3-0.5**：平衡，适合一般任务
- **0.6-1.0**：创造性强，适合对话和创作

---

## ✅ 现在你可以

1. **清楚知道每个Agent的配置**
   - 在 `.env` 中统一管理
   - 配置优先级明确
   - 回退机制清晰

2. **灵活调整配置**
   - 全部使用本地Ollama
   - 混合使用（本地+云端）
   - 全部使用云端

3. **验证配置**
   - 运行 `verify_agent_config.py`
   - 查看启动日志
   - 检查配置文档

---

## 🎉 总结

### 问题
- ❌ 不知道每个Agent用什么配置
- ❌ 配置分散在多个地方
- ❌ 有未使用的配置

### 解决
- ✅ 所有配置都在 `.env` 中
- ✅ 删除了未使用的 Hunter 配置
- ✅ 创建了配置验证脚本
- ✅ 创建了完整的配置文档

### 现在
- ✅ 配置清晰明了
- ✅ 统一管理维护
- ✅ 灵活调整配置
- ✅ 随时验证配置

**所有配置都在 `.env` 中维护，一目了然！** 🎊
