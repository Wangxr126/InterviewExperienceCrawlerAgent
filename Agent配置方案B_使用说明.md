# Agent 配置方案B - 本地/远程手动切换

## 🎯 实现完成

已实现方案B：简化方案 - 添加LOCAL和REMOTE配置，手动切换

---

## 📋 配置结构

### .env 文件配置

```bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. LLM 配置（支持本地/远程切换）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 使用模式：local（本地）或 remote（远程）
LLM_MODE=local

# ── 本地配置（Ollama）────────────────────────────────────────
LLM_LOCAL_PROVIDER=ollama
LLM_LOCAL_MODEL=qwen3:4b
LLM_LOCAL_API_KEY=ollama
LLM_LOCAL_BASE_URL=http://localhost:11434/v1
LLM_LOCAL_TIMEOUT=60

# ── 远程配置（云端API）───────────────────────────────────────
LLM_REMOTE_PROVIDER=volcengine
LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115
LLM_REMOTE_API_KEY=your_api_key_here
LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_REMOTE_TIMEOUT=300

# ── 通用配置 ─────────────────────────────────────────────────
LLM_TEMPERATURE=0.2
```

---

## 🔧 工作原理

### config.py 自动选择逻辑

```python
@property
def llm_mode(self) -> str:
    """LLM使用模式：local（本地）或 remote（远程），默认local"""
    return _get("LLM_MODE", "local").lower()

@property
def llm_provider(self) -> str:
    return self.llm_local_provider if self.llm_mode == "local" else self.llm_remote_provider

@property
def llm_model_id(self) -> str:
    return self.llm_local_model if self.llm_mode == "local" else self.llm_remote_model

@property
def llm_base_url(self) -> str:
    return self.llm_local_base_url if self.llm_mode == "local" else self.llm_remote_base_url

@property
def llm_timeout(self) -> int:
    return self.llm_local_timeout if self.llm_mode == "local" else self.llm_remote_timeout
```

**工作流程：**
1. 读取 `LLM_MODE` 配置（local 或 remote）
2. 根据 mode 自动选择对应的配置
3. Agent 使用 `settings.llm_provider`, `settings.llm_model_id` 等属性
4. 这些属性会自动返回 LOCAL 或 REMOTE 的值

---

## 🎯 使用方式

### 场景1：使用本地Ollama

```bash
# 修改 .env 文件
LLM_MODE=local

# 确保本地配置正确
LLM_LOCAL_MODEL=qwen3:4b
LLM_LOCAL_BASE_URL=http://localhost:11434/v1
```

**重启后端：**
```bash
python run.py
```

**效果：**
- 所有Agent使用本地Ollama
- 快速响应（无网络延迟）
- 免费使用

### 场景2：切换到远程API

```bash
# 修改 .env 文件
LLM_MODE=remote

# 确保远程配置正确
LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115
LLM_REMOTE_API_KEY=your_real_api_key
LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

**重启后端：**
```bash
python run.py
```

**效果：**
- 所有Agent使用远程API
- 更强大的模型能力
- 按token计费

### 场景3：临时切换（不修改.env）

```bash
# 设置环境变量（临时）
export LLM_MODE=remote  # Linux/Mac
set LLM_MODE=remote     # Windows

# 启动后端
python run.py
```

---

## 📊 配置对比

### 修改前（单一配置）

```bash
LLM_PROVIDER=ollama
LLM_MODEL_ID=qwen3:4b
LLM_BASE_URL=http://localhost:11434/v1
```

**问题：**
- ❌ 切换本地/远程需要修改多个配置
- ❌ 容易出错（忘记修改某个配置）
- ❌ 无法保存两套配置

### 修改后（双配置）

```bash
LLM_MODE=local  # 只需修改这一行！

# 本地配置（保存）
LLM_LOCAL_MODEL=qwen3:4b
LLM_LOCAL_BASE_URL=http://localhost:11434/v1

# 远程配置（保存）
LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115
LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

**优点：**
- ✅ 只需修改一行（LLM_MODE）
- ✅ 两套配置都保存，随时切换
- ✅ 不会出错

---

## 🔍 各Agent的配置

### 当前实现

所有Agent都使用全局LLM配置：
- Architect Agent → 使用 `settings.llm_provider`, `settings.llm_model_id`
- Interviewer Agent → 使用 `settings.llm_provider`, `settings.llm_model_id`
- Extractor → 使用 `settings.llm_provider`, `settings.llm_model_id`
- Finetune → 使用 `settings.finetune_llm_provider`, `settings.finetune_llm_model`

### 切换效果

**修改 `LLM_MODE=local`：**
- 所有Agent自动使用本地配置

**修改 `LLM_MODE=remote`：**
- 所有Agent自动使用远程配置

---

## 📝 配置清单

### 必须配置的项

**本地配置：**
- ✅ `LLM_LOCAL_MODEL` - 本地模型名称
- ✅ `LLM_LOCAL_BASE_URL` - 本地服务地址

**远程配置：**
- ✅ `LLM_REMOTE_MODEL` - 远程模型名称
- ✅ `LLM_REMOTE_API_KEY` - 远程API密钥
- ✅ `LLM_REMOTE_BASE_URL` - 远程服务地址

### 可选配置

- `LLM_LOCAL_TIMEOUT` - 本地超时（默认60秒）
- `LLM_REMOTE_TIMEOUT` - 远程超时（默认300秒）
- `LLM_TEMPERATURE` - 温度（默认0.2）

---

## ⚠️ 注意事项

### 1. 重启后端生效

修改 `.env` 文件后，必须重启后端：
```bash
python run.py
```

### 2. 检查配置

启动后端时，会打印当前使用的配置：
```
LLM Mode: local
LLM Provider: ollama
LLM Model: qwen3:4b
LLM Base URL: http://localhost:11434/v1
```

### 3. 本地Ollama必须运行

如果 `LLM_MODE=local`，确保Ollama正在运行：
```bash
# 检查Ollama是否运行
curl http://localhost:11434/api/tags

# 启动Ollama（如果未运行）
ollama serve
```

### 4. 远程API Key必须有效

如果 `LLM_MODE=remote`，确保API Key有效：
```bash
# 测试API Key
curl -X POST https://ark.cn-beijing.volces.com/api/v3/chat/completions \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"model":"doubao-1-5-pro-32k-250115","messages":[{"role":"user","content":"test"}]}'
```

---

## 🎉 总结

### 实现的功能

1. ✅ **双配置保存**：本地和远程配置都保存在.env中
2. ✅ **一键切换**：只需修改 `LLM_MODE` 即可切换
3. ✅ **自动选择**：config.py自动根据mode选择配置
4. ✅ **统一应用**：所有Agent自动使用选中的配置

### 使用方式

```bash
# 使用本地
LLM_MODE=local

# 使用远程
LLM_MODE=remote

# 重启后端
python run.py
```

### 优点

- ✅ 改动小，风险低
- ✅ 配置清晰，易于理解
- ✅ 手动控制，可预测
- ✅ 两套配置都保存，随时切换

---

## 📚 相关文件

1. **配置文件**：
   - `.env` - 配置值（已更新）
   - `backend/config/config.py` - 配置读取器（已更新）

2. **文档**：
   - `Agent配置优化方案_本地远程.md` - 完整方案说明
   - `Agent配置方案B_使用说明.md` - 本文档

3. **脚本**：
   - `add_local_remote_config.py` - 修改config.py的脚本
   - `update_env_local_remote.py` - 修改.env的脚本

---

**现在只需修改一行配置（LLM_MODE），即可在本地和远程之间切换！** 🎊
