"""推理过程追踪系统 - 使用指南"""

# 推理过程追踪系统 v1.0

## 概述

这是一个完整的推理过程持久化存储系统，用于记录和追踪所有 chat 的推理过程（thinking、actions、observations）。

### 核心特性

- ✅ **自动捕获**: 自动记录 Agent 的每一步推理过程
- ✅ **持久化存储**: 所有数据存储在 SQLite 数据库中
- ✅ **完整追踪**: 记录思考、行动、观察、工具调用等全过程
- ✅ **灵活查询**: 支持按用户、时间、状态等多维度查询
- ✅ **导出功能**: 支持导出为 JSON 和 HTML 报告
- ✅ **向后兼容**: 支持加载历史数据，新数据自动保存

## 系统架构

### 数据库表结构

```
reasoning_sessions      - 推理会话表（每个 chat 对应一个会话）
reasoning_steps         - 推理步骤表（ReAct 循环中的每一步）
reasoning_results       - 推理结果表（最终输出）
reasoning_tool_calls    - 工具调用记录表
```

### 核心模块

1. **reasoning_trace_service.py** - 核心服务层
   - 数据库操作
   - 会话管理
   - 步骤记录
   - 结果保存

2. **reasoning_trace_capture.py** - 捕获集成模块
   - 自动捕获推理过程
   - 简化的 API 接口
   - 工厂函数

3. **reasoning_api.py** - REST API 端点
   - 查询会话
   - 导出报告
   - 统计信息

## 使用方法

### 1. 在 Agent 中集成推理追踪

```python
from backend.services.storage.reasoning_trace_capture import create_trace_capture

# 创建追踪器
trace = create_trace_capture(
    user_id="user123",
    question_id="q456",
    question_text="什么是 Linux 内核？",
    interview_session_id="session789"
)

# 开始会话
session_id = trace.start_session(
    model_name="deepseek",
    model_version="v3",
    chat_type="chat"
)

# 记录思考过程
trace.record_thinking("我需要解释 Linux 内核的定义和主要功能...")

# 记录行动
step_id = trace.record_action(
    action_name="search_knowledge",
    action_input="Linux 内核定义",
    action_type="tool_call"
)

# 记录观察结果
trace.record_observation(
    observation="找到了关于 Linux 内核的详细信息",
    tool_result="Linux 内核是...",
    step_id=step_id
)

# 记录工具调用
trace.record_tool_call(
    tool_name="search_knowledge",
    tool_input="Linux 内核",
    tool_output="...",
    execution_time_ms=150
)

# 完成会话
trace.finish_session(
    final_answer="Linux 内核是操作系统的核心...",
    answer_type="text",
    confidence_score=0.95,
    reasoning_summary="通过搜索和分析得出答案",
    key_insights=["内核定义", "主要功能", "架构特性"]
)

# 获取完整追踪
full_trace = trace.get_trace()
json_str = trace.export_json()
```

### 2. 查询推理过程

#### 列出所有会话
```bash
curl http://localhost:8000/api/reasoning/sessions?user_id=user123&limit=50
```

#### 获取会话详情
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}
```

#### 获取完整推理追踪
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/trace
```

#### 获取推理步骤
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/steps
```

#### 获取推理结果
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/result
```

#### 获取工具调用记录
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/tool-calls
```

#### 获取会话统计
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/stats
```

#### 导出为 JSON
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/export?format=json
```

#### 导出为 HTML 报告
```bash
curl http://localhost:8000/api/reasoning/sessions/{session_id}/export?format=html
```

### 3. 在现有 Agent 中集成

在 `interviewer_agent.py` 的 `chat` 或 `chat_stream` 方法中添加：

```python
from backend.services.storage.reasoning_trace_capture import create_trace_capture

async def chat(self, user_id: str, session_id: str, message: str, ...):
    # 创建推理追踪
    trace = create_trace_capture(
        user_id=user_id,
        question_id=self.current_question_id,
        question_text=self.current_question_text,
        interview_session_id=session_id
    )
    
    trace.start_session(model_name="deepseek", model_version="v3")
    
    try:
        # 在 ReAct 循环中记录每一步
        # ... 现有的 Agent 逻辑 ...
        
        # 完成会话
        trace.finish_session(
            final_answer=final_response,
            confidence_score=0.9
        )
    except Exception as e:
        trace.update_session_status(trace.session_id, "error")
        raise
```

## 数据格式

### 推理会话 (reasoning_sessions)

```json
{
  "session_id": "reasoning-abc123def456",
  "user_id": "user123",
  "question_id": "q456",
  "question_text": "什么是 Linux 内核？",
  "model_name": "deepseek",
  "model_version": "v3",
  "total_steps": 5,
  "total_tokens": 2048,
  "reasoning_tokens": 1024,
  "completion_tokens": 1024,
  "status": "completed",
  "duration_seconds": 12.5,
  "created_at": "2026-03-18 10:30:00"
}
```

### 推理步骤 (reasoning_steps)

```json
{
  "step_id": "step-abc123",
  "session_id": "reasoning-abc123def456",
  "step_number": 1,
  "step_type": "thinking",
  "thinking": "我需要解释 Linux 内核的定义...",
  "status": "success",
  "tokens_used": 256,
  "duration_ms": 1500,
  "created_at": "2026-03-18 10:30:01"
}
```

### 推理结果 (reasoning_results)

```json
{
  "result_id": "result-xyz789",
  "session_id": "reasoning-abc123def456",
  "final_answer": "Linux 内核是操作系统的核心...",
  "answer_type": "text",
  "confidence_score": 0.95,
  "reasoning_summary": "通过搜索和分析得出答案",
  "key_insights": ["内核定义", "主要功能", "架构特性"],
  "created_at": "2026-03-18 10:30:15"
}
```

## 迁移历史数据

如果你有之前的推理过程数据（例如 JSONL 文件），可以创建迁移脚本：

```python
import json
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

def migrate_from_jsonl(file_path: str):
    """从 JSONL 文件迁移历史数据"""
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            
            # 创建会话
            session_id = reasoning_trace_service.create_session(
                user_id=data.get('user_id'),
                question_id=data.get('question_id'),
                question_text=data.get('question_text'),
                model_name=data.get('model_name', 'deepseek')
            )
            
            # 添加步骤
            for i, step in enumerate(data.get('steps', []), 1):
                reasoning_trace_service.add_step(
                    session_id=session_id,
                    step_number=i,
                    step_type=step.get('type'),
                    thinking=step.get('thinking'),
                    action_name=step.get('action'),
                    observation=step.get('observation'),
                    tokens_used=step.get('tokens', 0)
                )
            
            # 保存结果
            result = data.get('result', {})
            reasoning_trace_service.save_result(
                session_id=session_id,
                final_answer=result.get('answer'),
                confidence_score=result.get('confidence', 0.0)
            )
            
            # 更新会话状态
            reasoning_trace_service.update_session_status(
                session_id=session_id,
                status="completed",
                total_steps=len(data.get('steps', [])),
                total_tokens=data.get('total_tokens', 0)
            )

# 使用
migrate_from_jsonl('path/to/old_reasoning_data.jsonl')
```

## 性能优化

### 索引建议

```sql
CREATE INDEX idx_reasoning_sessions_user_id ON reasoning_sessions(user_id);
CREATE INDEX idx_reasoning_sessions_created_at ON reasoning_sessions(created_at);
CREATE INDEX idx_reasoning_steps_session_id ON reasoning_steps(session_id);
CREATE INDEX idx_reasoning_tool_calls_session_id ON reasoning_tool_calls(session_id);
```

### 数据清理

```python
from datetime import datetime, timedelta

def cleanup_old_sessions(days: int = 30):
    """清理超过指定天数的会话"""
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    with reasoning_trace_service._get_conn() as conn:
        # 删除旧的工具调用记录
        conn.execute(
            "DELETE FROM reasoning_tool_calls WHERE session_id IN "
            "(SELECT session_id FROM reasoning_sessions WHERE created_at < ?)",
            (cutoff_date,)
        )
        
        # 删除旧的步骤
        conn.execute(
            "DELETE FROM reasoning_steps WHERE session_id IN "
            "(SELECT session_id FROM reasoning_sessions WHERE created_at < ?)",
            (cutoff_date,)
        )
        
        # 删除旧的结果
        conn.execute(
            "DELETE FROM reasoning_results WHERE session_id IN "
            "(SELECT session_id FROM reasoning_sessions WHERE created_at < ?)",
            (cutoff_date,)
        )
        
        # 删除旧的会话
        conn.execute(
            "DELETE FROM reasoning_sessions WHERE created_at < ?",
            (cutoff_date,)
        )
        
        conn.commit()
```

## 常见问题

### Q: 如何在现有的 chat 中添加推理追踪？
A: 在 `chat` 方法的开始创建 `ReasoningTraceCapture` 实例，在关键步骤调用相应的记录方法，最后调用 `finish_session`。

### Q: 推理过程数据会占用多少空间？
A: 平均每个会话约 10-50KB（取决于步骤数和内容长度）。建议定期清理旧数据。

### Q: 如何导出所有用户的推理过程？
A: 使用 `list_sessions()` 获取所有会话，然后逐个导出为 JSON。

### Q: 能否实时流式传输推理过程？
A: 可以，在 `chat_stream` 中每次记录步骤时发送事件。

## 下一步

1. ✅ 在 `interviewer_agent.py` 中集成推理追踪
2. ✅ 在前端添加推理过程查看器
3. ✅ 创建推理过程分析仪表板
4. ✅ 支持推理过程对比分析
5. ✅ 集成向量数据库用于语义搜索
