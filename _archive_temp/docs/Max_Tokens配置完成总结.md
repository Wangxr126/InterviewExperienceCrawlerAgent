# Max Tokens 配置完成总结

## ✅ 已完成的工作

### 1. 修改 config.py

**添加的配置属性：**
- `llm_max_tokens` - 全局最大输出token（默认4096）
- `architect_max_tokens` - Architect最大token（留空使用全局）
- `interviewer_max_tokens` - Interviewer最大token（留空使用全局）
- `extractor_max_tokens` - Extractor最大token（留空使用全局）
- `finetune_llm_max_tokens` - Finetune最大token（留空使用全局）

### 2. 更新 .env

**添加的配置项：**
```bash
LLM_MAX_TOKENS=4096                  # 全局默认
ARCHITECT_MAX_TOKENS=                # 留空使用全局
INTERVIEWER_MAX_TOKENS=              # 留空使用全局
EXTRACTOR_MAX_TOKENS=8192            # 题目提取需要更多token
```

### 3. 更新代码使用 max_tokens

**question_extractor.py：**
```python
temp = settings.extractor_temperature
max_tokens = settings.extractor_max_tokens  # 添加

resp = client.chat.completions.create(
    model=settings.llm_model_id,
    messages=messages,
    temperature=temp,
    timeout=timeout,
    max_tokens=max_tokens,  # 添加
    response_format={"type": "json_object"},
)
```

**architect_tools.py：**
```python
payload = {
    "model": settings.architect_model,
    "messages": messages,
    "temperature": settings.architect_temperature,
    "max_tokens": settings.architect_max_tokens,  # 添加
    "response_format": {"type": "json_object"}
}
```

---

## 📊 配置说明

### 推荐配置

| 组件 | max_tokens | 说明 |
|------|-----------|------|
| **全局LLM** | 4096 | 默认值，适合大多数场景 |
| **Extractor** | 8192 | 题目提取可能输出很多题目，需要更多token |
| **Architect** | 留空 | 使用全局配置（4096） |
| **Interviewer** | 留空 | 使用全局配置（4096） |

### 为什么需要 max_tokens？

**问题：**
- LLM输出可能被截断
- 截断的JSON无法解析
- 导致提取失败

**解决：**
- 设置足够大的 max_tokens
- Extractor设置为8192（可能提取10-30道题）
- 避免输出截断

### 不同模型的 max_tokens 限制

| 模型 | 最大输出token |
|------|--------------|
| **qwen3:4b** | 8192 |
| **gemma3:4b** | 8192 |
| **doubao-1-5-pro** | 4096 |
| **gpt-4** | 4096 |

**注意：** 不要设置超过模型支持的最大值！

---

## 🔧 配置优先级

```
Agent专属配置 > 全局配置 > 默认值
```

**示例：**
```python
# Extractor的max_tokens
max_tokens = settings.extractor_max_tokens or settings.llm_max_tokens

# 如果 EXTRACTOR_MAX_TOKENS=8192
max_tokens = 8192

# 如果 EXTRACTOR_MAX_TOKENS 为空
max_tokens = 4096  # 使用 LLM_MAX_TOKENS
```

---

## 🎯 使用场景

### 场景1：题目提取（需要大量输出）

```bash
EXTRACTOR_MAX_TOKENS=8192
```

**原因：**
- 一篇面经可能包含10-30道题
- 每道题包含：题目、答案、分类、标签
- 需要足够的token避免截断

### 场景2：元信息提取（输出较少）

```bash
ARCHITECT_MAX_TOKENS=  # 留空，使用全局4096
```

**原因：**
- 元信息只包含：公司、岗位、业务线、难度
- 输出较少，4096足够

### 场景3：面试对话（中等输出）

```bash
INTERVIEWER_MAX_TOKENS=  # 留空，使用全局4096
```

**原因：**
- 对话回复通常不会太长
- 4096足够

---

## ⚠️ 注意事项

### 1. 不要设置过大

**问题：**
- 超过模型限制会报错
- 浪费计算资源

**建议：**
- 根据实际需求设置
- 不要超过模型最大值

### 2. 监控输出长度

**方法：**
```python
response = client.chat.completions.create(...)
output_tokens = response.usage.completion_tokens
logger.info(f"输出token数: {output_tokens}")
```

**如果经常接近max_tokens：**
- 考虑增加max_tokens
- 或者优化prompt减少输出

### 3. 本地模型 vs 云端模型

**本地模型（Ollama）：**
- 通常支持更大的max_tokens（8192+）
- 速度较快

**云端模型：**
- 可能有更严格的限制（4096）
- 按token计费，设置过大会增加成本

---

## 📝 验证配置

### 方法1：检查配置值

```bash
python -c "import sys; sys.path.insert(0, 'backend'); from backend.config.config import settings; print('LLM_MAX_TOKENS:', settings.llm_max_tokens); print('EXTRACTOR_MAX_TOKENS:', settings.extractor_max_tokens)"
```

**输出：**
```
LLM_MAX_TOKENS: 4096
EXTRACTOR_MAX_TOKENS: 8192
```

### 方法2：查看日志

启动后端后，查看LLM调用日志：
```
[INFO] LLM调用: max_tokens=8192
```

### 方法3：测试提取

运行题目提取，检查是否有截断：
```bash
python -m backend.services.crawler.question_extractor
```

---

## 🎉 总结

### 修改的文件

1. ✅ `backend/config/config.py` - 添加max_tokens配置属性
2. ✅ `.env` - 添加max_tokens配置值
3. ✅ `backend/services/crawler/question_extractor.py` - 使用max_tokens
4. ✅ `backend/tools/architect_tools.py` - 使用max_tokens

### 配置建议

- **全局：** 4096（默认）
- **Extractor：** 8192（题目提取需要更多）
- **其他：** 留空（使用全局）

### 效果

- ✅ 避免输出截断
- ✅ 避免JSON解析错误
- ✅ 提高提取成功率

**现在LLM输出不会被截断了！** 🎊
