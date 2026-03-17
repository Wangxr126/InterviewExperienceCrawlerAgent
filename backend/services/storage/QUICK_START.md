"""快速开始指南 - 推理过程追踪系统"""

# 推理过程追踪系统 - 快速开始

## 5 分钟快速上手

### 第 1 步：导入服务

```python
from backend.services.storage.reasoning_trace_capture import create_trace_capture
from backend.services.storage.reasoning_trace_service import reasoning_trace_service
```

### 第 2 步：创建和记录推理过程

```python
# 创建追踪器
trace = create_trace_capture(
    user_id="user123",
    question_id="q456",
    question_text="什么是 Linux 内核？"
)

# 开始会话
session_id = trace.start_session()

# 记录思考
trace.record_thinking("我需要解释 Linux 内核的定义和主要功能...")

# 记录行动
step_id = trace.record_action(
    action_name="search_knowledge",
    action_input="Linux 内核定义"
)

# 记录观察
trace.record_observation(
    observation="找到了关于 Linux 内核的详细信息",
    tool_result="Linux 内核是...",
    step_id=step_id
)

# 完成会话
trace.finish_session(
    final_answer="Linux 内核是操作系统的核心...",
    confidence_score=0.95
)

print(f"会话 ID: {session_id}")
```

### 第 3 步：查询推理过程

```python
# 获取完整追踪
full_trace = reasoning_trace_service.get_full_trace(session_id)
print(full_trace)

# 导出为 JSON
json_str = reasoning_trace_service.export_trace_json(session_id)
print(json_str)

# 获取统计信息
stats = reasoning_trace_service.get_session_stats(session_id)
print(f"总步骤: {stats['total_steps']}")
print(f"总 Token: {stats['total_tokens']}")
print(f"耗时: {stats['duration_seconds']:.2f}s")
```

## 在 Agent 中集成

### 示例 1：简单集成

```python
from backend.services.storage.reasoning_trace_capture import create_trace_capture

class MyAgent:
    async def chat(self, user_id: str, message: str):
        # 创建追踪
        trace = create_trace_capture(user_id=user_id)
        trace.start_session()
        
        try:
            # 你的 Agent 逻辑
            response = await self.process_message(message)
            
            # 完成追踪
            trace.finish_session(final_answer=response)
            
            return response
        except Exception as e:
            trace.update_session_status(trace.session_id, "error")
            raise
```

### 示例 2：详细集成（ReAct 循环）

```python
from backend.services.storage.reasoning_trace_capture import create_trace_capture

class ReActAgent:
    async def chat(self, user_id: str, message: str):
        trace = create_trace_capture(user_id=user_id, question_text=message)
        trace.start_session(model_name="deepseek", model_version="v3")
        
        step_count = 0
        
        while True:
            # 思考
            thinking = await self.llm.think(message)
            trace.record_thinking(thinking)
            
            # 决定行动
            action = await self.llm.decide_action(thinking)
            
            if action['type'] == 'finish':
                # 完成
                trace.finish_session(
                    final_answer=action['answer'],
                    confidence_score=0.95
                )
                return action['answer']
            
            # 执行行动
            step_id = trace.record_action(
                action_name=action['name'],
                action_input=action['input']
            )
            
            result = await self.execute_tool(action['name'], action['input'])
            
            # 记录观察
            trace.record_observation(
                observation=result,
                step_id=step_id
            )
            
            step_count += 1
            if step_count > 10:  # 防止无限循环
                break
```

### 示例 3：流式集成

```python
from backend.services.storage.reasoning_trace_capture import create_trace_capture

class StreamingAgent:
    async def chat_stream(self, user_id: str, message: str):
        trace = create_trace_capture(user_id=user_id, question_text=message)
        trace.start_session()
        
        try:
            async for chunk in self.llm.stream(message):
                # 实时发送给客户端
                yield chunk
                
                # 记录到追踪系统
                if chunk.get('type') == 'thinking':
                    trace.record_thinking(chunk['content'])
                elif chunk.get('type') == 'action':
                    trace.record_action(
                        action_name=chunk['action'],
                        action_input=chunk['input']
                    )
            
            # 完成
            trace.finish_session(final_answer=message)
            
        except Exception as e:
            trace.update_session_status(trace.session_id, "error")
            raise
```

## API 使用示例

### 使用 curl

```bash
# 列出所有会话
curl http://localhost:8000/api/reasoning/sessions

# 获取特定会话
curl http://localhost:8000/api/reasoning/sessions/reasoning-abc123def456

# 获取完整追踪
curl http://localhost:8000/api/reasoning/sessions/reasoning-abc123def456/trace

# 获取推理步骤
curl http://localhost:8000/api/reasoning/sessions/reasoning-abc123def456/steps

# 导出为 HTML
curl http://localhost:8000/api/reasoning/sessions/reasoning-abc123def456/export?format=html > report.html
```

### 使用 Python requests

```python
import requests

# 列出会话
response = requests.get('http://localhost:8000/api/reasoning/sessions', 
                       params={'user_id': 'user123', 'limit': 50})
sessions = response.json()['sessions']

# 获取完整追踪
session_id = sessions[0]['session_id']
response = requests.get(f'http://localhost:8000/api/reasoning/sessions/{session_id}/trace')
trace = response.json()

# 打印步骤
for step in trace['steps']:
    print(f"步骤 {step['step_number']}: {step['step_type']}")
    if step.get('thinking'):
        print(f"  思考: {step['thinking'][:100]}")
    if step.get('observation'):
        print(f"  观察: {step['observation'][:100]}")
```

## 迁移历史数据

### 从 JSONL 文件迁移

```bash
# 自动检测格式
python backend/scripts/migrate_reasoning_data.py path/to/old_data.jsonl

# 指定格式
python backend/scripts/migrate_reasoning_data.py path/to/old_data.jsonl react
python backend/scripts/migrate_reasoning_data.py path/to/old_data.jsonl simple
python backend/scripts/migrate_reasoning_data.py path/to/old_data.jsonl deepseek
```

### 从 Python 代码迁移

```python
from backend.scripts.migrate_reasoning_data import migrate_from_generic_jsonl

# 迁移数据
migrated, errors = migrate_from_generic_jsonl('path/to/old_data.jsonl', format_type='react')
print(f"迁移完成: {migrated} 成功, {errors} 失败")
```

## 常见操作

### 获取用户的所有推理会话

```python
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

sessions = reasoning_trace_service.list_sessions(user_id='user123', limit=100)
for session in sessions:
    print(f"{session['session_id']}: {session['question_text']}")
```

### 导出所有会话为 JSON

```python
import json
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

sessions = reasoning_trace_service.list_sessions(limit=1000)
all_traces = []

for session in sessions:
    trace = reasoning_trace_service.get_full_trace(session['session_id'])
    all_traces.append(trace)

with open('all_traces.json', 'w', encoding='utf-8') as f:
    json.dump(all_traces, f, ensure_ascii=False, indent=2, default=str)
```

### 统计推理过程

```python
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

sessions = reasoning_trace_service.list_sessions(limit=1000)

total_steps = 0
total_tokens = 0
total_duration = 0

for session in sessions:
    total_steps += session.get('total_steps', 0)
    total_tokens += session.get('total_tokens', 0)
    total_duration += session.get('duration_seconds', 0)

print(f"总会话数: {len(sessions)}")
print(f"总步骤数: {total_steps}")
print(f"总 Token 数: {total_tokens}")
print(f"总耗时: {total_duration:.2f}s")
print(f"平均每会话步骤: {total_steps / len(sessions):.1f}")
print(f"平均每会话 Token: {total_tokens / len(sessions):.0f}")
```

### 查找特定类型的步骤

```python
from backend.services.storage.reasoning_trace_service import reasoning_trace_service

session_id = 'reasoning-abc123def456'
steps = reasoning_trace_service.get_steps(session_id)

# 找出所有思考步骤
thinking_steps = [s for s in steps if s['step_type'] == 'thinking']
print(f"思考步骤数: {len(thinking_steps)}")

# 找出所有行动步骤
action_steps = [s for s in steps if s['step_type'] == 'action']
print(f"行动步骤数: {len(action_steps)}")

# 找出所有工具调用
tool_calls = reasoning_trace_service.get_tool_calls(session_id)
print(f"工具调用数: {len(tool_calls)}")
```

## 性能提示

1. **批量操作**: 使用 `list_sessions()` 时指定合理的 `limit`
2. **定期清理**: 使用迁移脚本中的 `cleanup_old_sessions()` 清理旧数据
3. **索引优化**: 为常用查询字段添加数据库索引
4. **异步操作**: 在 FastAPI 中使用异步操作避免阻塞

## 故障排除

### 问题：找不到会话
```python
# 检查会话是否存在
session = reasoning_trace_service.get_session(session_id)
if not session:
    print("会话不存在")
else:
    print(f"会话状态: {session['status']}")
```

### 问题：数据库锁定
```python
# 增加超时时间
import sqlite3
conn = sqlite3.connect(db_path, timeout=30)  # 30 秒超时
```

### 问题：查询缓慢
```python
# 添加索引
with reasoning_trace_service._get_conn() as conn:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON reasoning_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON reasoning_sessions(created_at)")
    conn.commit()
```

## 下一步

- 📊 在前端添加推理过程可视化
- 🔍 实现推理过程搜索功能
- 📈 创建推理过程分析仪表板
- 🤖 支持推理过程对比分析
- 🔗 集成向量数据库用于语义搜索
