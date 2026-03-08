# 面试官 Agent 交互日志系统

## 概述

面试官 Agent 的所有交互都会被详细记录到 `interviewer_logs/` 目录，包括：
- 用户输入和 AI 回复
- 完整的推理过程（thinking steps）
- 工具调用详情

## 目录结构

```
interviewer_logs/
├── {model_name}/                    # 按模型名称分类
│   ├── chat_YYYYMMDD.jsonl         # 每日对话日志
│   ├── thinking_YYYYMMDD.jsonl     # 推理过程详细日志
│   └── tools_YYYYMMDD.jsonl        # 工具调用日志
```

例如：
```
interviewer_logs/
├── deepseek-r1_7b/
│   ├── chat_20260309.jsonl
│   ├── thinking_20260309.jsonl
│   └── tools_20260309.jsonl
├── qwen3.5_4b/
│   ├── chat_20260309.jsonl
│   └── thinking_20260309.jsonl
```

## 日志格式

### 1. 对话日志 (chat_*.jsonl)

每行一条 JSON 记录：

```json
{
  "timestamp": "2026-03-09T15:30:45.123456",
  "user_id": "Wangxr",
  "session_id": "sess_abc123",
  "user_message": "出一道 Redis 面试题",
  "ai_response": "好的，我来为你出一道 Redis 相关的面试题...",
  "response_length": 856,
  "thinking_steps_count": 3,
  "model": "deepseek-r1_7b",
  "metadata": {
    "has_resume": false,
    "resume_length": 0,
    "memory_context": null,
    "full_input_length": 245
  }
}
```

### 2. 推理日志 (thinking_*.jsonl)

记录模型的完整推理过程：

```json
{
  "timestamp": "2026-03-09T15:30:45.123456",
  "user_id": "Wangxr",
  "session_id": "sess_abc123",
  "user_message": "出一道 Redis 面试题",
  "model": "deepseek-r1_7b",
  "thinking_steps": [
    {
      "step": 1,
      "thought": "用户想要一道 Redis 面试题，我需要调用推荐引擎...",
      "action": "smart_recommend",
      "observation": "推荐了 3 道题目"
    },
    {
      "step": 2,
      "thought": "从推荐结果中选择最合适的一道...",
      "action": "filter_questions",
      "observation": "筛选出 1 道题"
    }
  ],
  "total_steps": 2
}
```

### 3. 工具调用日志 (tools_*.jsonl)

记录每次工具调用的详情：

```json
{
  "timestamp": "2026-03-09T15:30:45.123456",
  "user_id": "Wangxr",
  "session_id": "sess_abc123",
  "tool_name": "smart_recommend",
  "tool_input": {
    "user_id": "Wangxr",
    "strategy": "weak_tags",
    "limit": 3
  },
  "tool_output": "[{\"q_id\": \"q123\", \"question_text\": \"...\"}]",
  "success": true,
  "error": null,
  "model": "deepseek-r1_7b"
}
```

## 使用方法

### 自动记录

日志系统已集成到 `orchestrator.py` 的 `chat()` 方法中，每次对话都会自动记录，无需手动调用。

### 查看日志

```bash
# 查看今天的对话日志
cat interviewer_logs/deepseek-r1_7b/chat_20260309.jsonl

# 查看推理过程
cat interviewer_logs/deepseek-r1_7b/thinking_20260309.jsonl

# 统计今天的对话数量
wc -l interviewer_logs/deepseek-r1_7b/chat_20260309.jsonl
```

### 分析日志

可以使用 Python 脚本分析日志：

```python
import json

# 读取对话日志
with open('interviewer_logs/deepseek-r1_7b/chat_20260309.jsonl', 'r', encoding='utf-8') as f:
    chats = [json.loads(line) for line in f]

# 统计平均回复长度
avg_length = sum(c['response_length'] for c in chats) / len(chats)
print(f"平均回复长度: {avg_length:.0f} 字")

# 统计推理步骤分布
from collections import Counter
step_counts = Counter(c['thinking_steps_count'] for c in chats)
print(f"推理步骤分布: {dict(step_counts)}")
```

## 日志统计 API

可以通过代码获取日志统计信息：

```python
from backend.services.interviewer_logger import get_interviewer_logger

logger = get_interviewer_logger()
stats = logger.get_stats()

print(f"模型: {stats['model']}")
print(f"日志目录: {stats['log_dir']}")
print(f"今日对话数: {stats['files']['chat']['entries']}")
print(f"今日推理记录数: {stats['files']['thinking']['entries']}")
print(f"今日工具调用数: {stats['files']['tools']['entries']}")
```

## 与微调日志的区别

| 特性 | 面试官日志 (`interviewer_logs/`) | 微调日志 (`微调/llm_logs/`) |
|------|--------------------------------|---------------------------|
| 用途 | 记录面试官 Agent 的交互过程 | 记录爬虫提取的原始数据 |
| 内容 | 用户对话 + 推理过程 + 工具调用 | LLM 提取的题目数据 |
| 格式 | 结构化 JSON（chat/thinking/tools） | 单一 JSONL 文件 |
| 更新频率 | 每次对话实时记录 | 爬虫任务执行时批量写入 |
| 主要用途 | 调试、分析 Agent 行为 | 构造微调数据集 |

## 注意事项

1. **日志文件会持续增长**：建议定期清理或归档旧日志
2. **包含用户隐私信息**：日志中可能包含用户输入的简历等敏感信息，注意保护
3. **不影响主流程**：日志记录失败不会影响对话功能，只会输出警告日志
4. **按模型分类**：切换模型后会自动创建新的子目录

## 故障排查

如果日志没有生成：

1. 检查 `interviewer_logs/` 目录是否存在
2. 检查文件写入权限
3. 查看后端日志中是否有 "记录交互日志失败" 的警告
4. 确认 `orchestrator.py` 中的日志代码已正确插入

## 未来扩展

可以考虑添加：
- 日志可视化面板
- 自动分析报告（平均响应时间、工具使用频率等）
- 日志压缩和归档功能
- 敏感信息脱敏处理
