# Agent配置优化方案 - 本地优先+远程备份

## 🎯 你的要求

> "ARCHITECT_TEMPERATURE=0.2和EXTRACTOR_TEMPERATURE=0.2有啥区别？？远程调用api和本地调用有啥区别？？我认为你应该在env中提供对应得配置。默认先加载本地，本地没有或者预热失败再使用对应的远程服务配置"

## 🔍 当前问题分析

### 1. ARCHITECT vs EXTRACTOR 的区别

**Architect Agent（独立Agent）：**
- 文件：`backend/agents/architect_agent.py`
- 使用：`HelloAgentsLLM` 框架
- 配置：有完整的6项配置（provider/model/api_key/base_url/timeout/temperature）
- 职责：知识架构、结构化解析、语义查重

**Extractor（服务层工具）：**
- 文件：`backend/services/crawler/question_extractor.py`
- 使用：直接调用 `OpenAI` 客户端
- 配置：**只有temperature，其他都用全局LLM配置**
- 职责：从面经原文中提取结构化题目

**问题：**
- ❌ Extractor不是独立Agent，而是服务层工具
- ❌ Extractor直接使用全局LLM配置（`settings.llm_model_id`, `settings.llm_api_key`）
- ❌ 无法为Extractor单独配置本地/远程

### 2. 本地/远程调用的区别

| 特性 | 本地（Ollama） | 远程（云端API） |
|------|---------------|----------------|
| **速度** | 快（无网络延迟） | 慢（网络延迟） |
| **成本** | 免费 | 按token计费 |
| **稳定性** | 依赖本地资源 | 依赖网络 |
| **模型能力** | 小模型（4B-14B） | 大模型（100B+） |
| **超时时间** | 30-60秒 | 180-300秒 |
| **适用场景** | 简单任务、高频调用 | 复杂任务、低频调用 |

---

## ✅ 解决方案：本地优先+远程备份

### 方案设计

```
1. 尝试本地LLM（Ollama）
   ↓ 失败（连接失败/超时/预热失败）
2. 自动切换到远程LLM（云端API）
   ↓ 成功
3. 记录日志，继续执行
```

### 配置结构

每个Agent/服务都有**两套完整配置**：

```bash
# 本地配置（优先使用）
XXX_LOCAL_PROVIDER=ollama
XXX_LOCAL_MODEL=qwen3:4b
XXX_LOCAL_API_KEY=ollama
XXX_LOCAL_BASE_URL=http://localhost:11434/v1
XXX_LOCAL_TIMEOUT=60

# 远程配置（备份）
XXX_REMOTE_PROVIDER=volcengine
XXX_REMOTE_MODEL=doubao-1-5-pro-32k-250115
XXX_REMOTE_API_KEY=your_api_key
XXX_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
XXX_REMOTE_TIMEOUT=300

# 通用配置
XXX_TEMPERATURE=0.2
XXX_FALLBACK_ENABLED=true  # 是否启用远程备份
```

---

## 📋 完整配置方案

### .env 配置示例

```bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 全局 LLM 配置（默认：本地优先）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 本地配置（优先）
LLM_LOCAL_PROVIDER=ollama
LLM_LOCAL_MODEL=qwen3:4b
LLM_LOCAL_API_KEY=ollama
LLM_LOCAL_BASE_URL=http://localhost:11434/v1
LLM_LOCAL_TIMEOUT=60

# 远程配置（备份）
LLM_REMOTE_PROVIDER=volcengine
LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115
LLM_REMOTE_API_KEY=your_api_key_here
LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_REMOTE_TIMEOUT=300

# 通用配置
LLM_TEMPERATURE=0.3
LLM_FALLBACK_ENABLED=true  # 本地失败时是否切换到远程

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Architect Agent（知识架构师）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 本地配置（留空使用全局）
ARCHITECT_LOCAL_PROVIDER=
ARCHITECT_LOCAL_MODEL=
ARCHITECT_LOCAL_BASE_URL=
ARCHITECT_LOCAL_TIMEOUT=

# 远程配置（留空使用全局）
ARCHITECT_REMOTE_PROVIDER=
ARCHITECT_REMOTE_MODEL=
ARCHITECT_REMOTE_BASE_URL=
ARCHITECT_REMOTE_TIMEOUT=

# 通用配置
ARCHITECT_TEMPERATURE=0.2
ARCHITECT_FALLBACK_ENABLED=true

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Interviewer Agent（面试官）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 本地配置
INTERVIEWER_LOCAL_PROVIDER=
INTERVIEWER_LOCAL_MODEL=
INTERVIEWER_LOCAL_TIMEOUT=

# 远程配置
INTERVIEWER_REMOTE_PROVIDER=
INTERVIEWER_REMOTE_MODEL=
INTERVIEWER_REMOTE_TIMEOUT=

# 通用配置
INTERVIEWER_TEMPERATURE=0.6
INTERVIEWER_FALLBACK_ENABLED=true
INTERVIEWER_MAX_STEPS=8

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Extractor（题目提取器）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 本地配置
EXTRACTOR_LOCAL_PROVIDER=
EXTRACTOR_LOCAL_MODEL=
EXTRACTOR_LOCAL_TIMEOUT=

# 远程配置
EXTRACTOR_REMOTE_PROVIDER=
EXTRACTOR_REMOTE_MODEL=
EXTRACTOR_REMOTE_TIMEOUT=

# 通用配置
EXTRACTOR_TEMPERATURE=0.2
EXTRACTOR_FALLBACK_ENABLED=true
EXTRACTOR_MAX_RETRIES=3

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. Finetune LLM（微调辅助）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 本地配置（通常不用本地）
FINETUNE_LOCAL_PROVIDER=
FINETUNE_LOCAL_MODEL=

# 远程配置（主要使用远程大模型）
FINETUNE_REMOTE_PROVIDER=volcengine
FINETUNE_REMOTE_MODEL=doubao-1-5-pro-32k-250115
FINETUNE_REMOTE_API_KEY=your_api_key
FINETUNE_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
FINETUNE_REMOTE_TIMEOUT=300

# 通用配置
FINETUNE_TEMPERATURE=0.2
FINETUNE_FALLBACK_ENABLED=false  # 微调通常只用远程
```

---

## 🔧 实现逻辑

### LLM调用包装器

```python
class LLMClient:
    """LLM客户端，支持本地优先+远程备份"""
    
    def __init__(self, config_prefix: str):
        """
        config_prefix: "LLM" / "ARCHITECT" / "INTERVIEWER" / "EXTRACTOR"
        """
        self.prefix = config_prefix
        self.load_config()
    
    def load_config(self):
        """加载本地和远程配置"""
        # 本地配置
        self.local_provider = settings.get(f"{self.prefix}_LOCAL_PROVIDER")
        self.local_model = settings.get(f"{self.prefix}_LOCAL_MODEL")
        self.local_base_url = settings.get(f"{self.prefix}_LOCAL_BASE_URL")
        self.local_timeout = settings.get(f"{self.prefix}_LOCAL_TIMEOUT")
        
        # 远程配置
        self.remote_provider = settings.get(f"{self.prefix}_REMOTE_PROVIDER")
        self.remote_model = settings.get(f"{self.prefix}_REMOTE_MODEL")
        self.remote_base_url = settings.get(f"{self.prefix}_REMOTE_BASE_URL")
        self.remote_timeout = settings.get(f"{self.prefix}_REMOTE_TIMEOUT")
        
        # 通用配置
        self.temperature = settings.get(f"{self.prefix}_TEMPERATURE")
        self.fallback_enabled = settings.get(f"{self.prefix}_FALLBACK_ENABLED")
    
    def call(self, messages: list) -> str:
        """调用LLM，本地优先，失败则切换远程"""
        
        # 1. 尝试本地
        if self.local_base_url:
            try:
                logger.info(f"[{self.prefix}] 尝试本地LLM: {self.local_model}")
                result = self._call_local(messages)
                logger.info(f"[{self.prefix}] 本地LLM调用成功")
                return result
            except Exception as e:
                logger.warning(f"[{self.prefix}] 本地LLM失败: {e}")
                
                # 如果不启用备份，直接抛出异常
                if not self.fallback_enabled:
                    raise
        
        # 2. 切换到远程
        if self.remote_base_url:
            try:
                logger.info(f"[{self.prefix}] 切换到远程LLM: {self.remote_model}")
                result = self._call_remote(messages)
                logger.info(f"[{self.prefix}] 远程LLM调用成功")
                return result
            except Exception as e:
                logger.error(f"[{self.prefix}] 远程LLM也失败: {e}")
                raise
        
        raise RuntimeError(f"[{self.prefix}] 本地和远程LLM都不可用")
    
    def _call_local(self, messages: list) -> str:
        """调用本地LLM"""
        client = OpenAI(
            api_key=self.local_api_key,
            base_url=self.local_base_url,
            timeout=self.local_timeout,
        )
        resp = client.chat.completions.create(
            model=self.local_model,
            messages=messages,
            temperature=self.temperature,
        )
        return resp.choices[0].message.content
    
    def _call_remote(self, messages: list) -> str:
        """调用远程LLM"""
        client = OpenAI(
            api_key=self.remote_api_key,
            base_url=self.remote_base_url,
            timeout=self.remote_timeout,
        )
        resp = client.chat.completions.create(
            model=self.remote_model,
            messages=messages,
            temperature=self.temperature,
        )
        return resp.choices[0].message.content
```

### 使用示例

```python
# Extractor 中使用
extractor_llm = LLMClient("EXTRACTOR")
result = extractor_llm.call(messages)

# Architect Agent 中使用
architect_llm = LLMClient("ARCHITECT")
result = architect_llm.call(messages)
```

---

## 📊 配置对比

### 当前配置（单一配置）

```bash
ARCHITECT_MODEL=qwen3:4b
ARCHITECT_BASE_URL=http://localhost:11434/v1
ARCHITECT_TEMPERATURE=0.2
```

**问题：**
- ❌ 本地失败就完全失败
- ❌ 无法自动切换到远程
- ❌ 需要手动修改配置

### 新配置（本地+远程）

```bash
# 本地（优先）
ARCHITECT_LOCAL_MODEL=qwen3:4b
ARCHITECT_LOCAL_BASE_URL=http://localhost:11434/v1

# 远程（备份）
ARCHITECT_REMOTE_MODEL=doubao-1-5-pro-32k-250115
ARCHITECT_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# 通用
ARCHITECT_TEMPERATURE=0.2
ARCHITECT_FALLBACK_ENABLED=true
```

**优点：**
- ✅ 本地失败自动切换远程
- ✅ 提高系统可用性
- ✅ 灵活控制是否启用备份

---

## 🎯 使用场景

### 场景1：开发环境（本地优先）

```bash
# 全局配置
LLM_LOCAL_MODEL=qwen3:4b
LLM_LOCAL_BASE_URL=http://localhost:11434/v1
LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115
LLM_FALLBACK_ENABLED=true

# 所有Agent留空，使用全局配置
ARCHITECT_LOCAL_MODEL=
INTERVIEWER_LOCAL_MODEL=
```

**效果：**
- 本地Ollama正常时，全部使用本地（快速、免费）
- 本地Ollama故障时，自动切换远程（保证可用性）

### 场景2：生产环境（远程优先）

```bash
# 全局配置
LLM_LOCAL_MODEL=
LLM_LOCAL_BASE_URL=
LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115
LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_FALLBACK_ENABLED=false

# 所有Agent使用远程
```

**效果：**
- 直接使用远程大模型（稳定、强大）
- 不依赖本地资源

### 场景3：混合模式

```bash
# 简单任务用本地
EXTRACTOR_LOCAL_MODEL=qwen3:4b
EXTRACTOR_FALLBACK_ENABLED=true

# 复杂任务用远程
INTERVIEWER_LOCAL_MODEL=
INTERVIEWER_REMOTE_MODEL=doubao-1-5-pro-32k-250115
INTERVIEWER_FALLBACK_ENABLED=false
```

---

## 🎉 总结

### 你的要求
1. ❓ ARCHITECT_TEMPERATURE和EXTRACTOR_TEMPERATURE有啥区别？
2. ❓ 远程调用api和本地调用有啥区别？
3. ❓ 应该提供本地+远程配置
4. ❓ 默认先加载本地，失败再用远程

### 我的方案
1. ✅ **明确区分**：Architect是Agent，Extractor是服务工具
2. ✅ **本地vs远程**：速度、成本、稳定性、模型能力都不同
3. ✅ **双配置**：每个Agent/服务都有LOCAL和REMOTE两套配置
4. ✅ **自动切换**：本地失败自动切换远程，可配置是否启用

### 下一步
我可以帮你：
1. 修改 `config.py`，添加LOCAL和REMOTE配置
2. 创建 `LLMClient` 包装器，实现自动切换
3. 修改所有Agent和服务，使用新的配置
4. 更新 `.env` 文件模板

你想让我开始实现吗？
