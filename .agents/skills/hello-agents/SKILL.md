---
name: hello-agents
description: Build, configure, and extend AI agents using the hello_agents framework. Use when creating agents, adding tools, configuring LLM providers, implementing ReAct/Reflection/PlanSolve patterns, enabling streaming, session persistence, tracing, sub-agents, TodoWrite, DevLog, or debugging hello_agents internals.
---

# hello_agents 框架开发指南

hello_agents 是基于 OpenAI 原生 API 构建的多智能体框架，支持 OpenAI、Anthropic、Gemini、DeepSeek 等多种 LLM。核心采用 **Function Calling** 模式，解析成功率 99%+。

---

## 一、快速开始

```python
from hello_agents import HelloAgentsLLM, ReActAgent, Config, ToolRegistry
from hello_agents.tools.builtin import CalculatorTool, ReadTool

llm = HelloAgentsLLM(provider="openai", model="gpt-4o")
registry = ToolRegistry()
registry.register_tool(CalculatorTool())
registry.register_tool(ReadTool(project_root="./"))

agent = ReActAgent(
    name="my_agent",
    llm=llm,
    tool_registry=registry,
    config=Config(trace_enabled=True)
)
result = agent.run("计算 123 * 456")
```

---

## 二、LLM 与 Agent 类型

### LLM 提供商

```python
# 支持：openai / anthropic / gemini / deepseek / ollama
llm = HelloAgentsLLM(provider="openai", model="gpt-4o")
llm = HelloAgentsLLM(provider="anthropic", model="Codex-3-5-sonnet-20241022")
llm = HelloAgentsLLM(provider="deepseek", model="deepseek-chat")
```

### 四种 Agent 范式


| 类型                | 适用场景         |
| ----------------- | ------------ |
| `SimpleAgent`     | 纯对话，无工具      |
| `ReActAgent`      | 工具调用，推理-行动循环 |
| `ReflectionAgent` | 需要自我反思和质量改进  |
| `PlanSolveAgent`  | 复杂任务，先规划再执行  |


### Function Calling 架构

所有 Agent 统一使用 `llm.invoke_with_tools()`，LLM 返回结构化 tool_calls，无需 Prompt 解析：

```python
# LLM 返回
response.tool_calls = [
    ToolCall(id="call_1", name="Read", arguments={"path": "config.py"}),
    ToolCall(id="call_2", name="Read", arguments={"path": "main.py"})
]
# Agent 并行执行工具
```

---

## 三、工具系统

### 自定义工具（标准类）

```python
from hello_agents.tools.base import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse
from hello_agents.tools.errors import ToolErrorCode

class MyTool(Tool):
    def __init__(self):
        super().__init__(name="MyTool", description="做某事")

    def get_parameters(self):
        return [ToolParameter("input", "string", "输入内容", required=True)]

    def run(self, parameters):
        if not parameters.get("input"):
            return ToolResponse.error(
                code=ToolErrorCode.INVALID_PARAM,
                message="参数 'input' 不能为空"
            )
        result = do_something(parameters["input"])
        return ToolResponse.success(text=result, data={"result": result})
```

### 三种实现方式

1. **函数式**：`registry.register_function(func, name, description)`
2. **标准类**：继承 `Tool`，实现 `run()` + `get_parameters()`
3. **可展开**：`expandable=True` + `@tool_action("子工具名", "描述")` 装饰器

### ToolResponse 协议

```python
# 成功
ToolResponse.success(text="...", data={...}, stats={"time_ms": 10})

# 错误（使用标准错误码）
ToolResponse.error(code=ToolErrorCode.NOT_FOUND, message="文件不存在")

# 部分成功
ToolResponse.partial(text="...", data={...}, reason="已截断")
```

**标准错误码**：NOT_FOUND, INVALID_PARAM, EXECUTION_ERROR, TIMEOUT, CONFLICT, CIRCUIT_OPEN, RATE_LIMIT 等。

**重要**：工具失败用 `ToolResponse.error()`，不要抛异常（熔断器依赖 `ToolStatus.ERROR`）。

### 文件工具（ReadTool / WriteTool / EditTool / MultiEditTool）

```python
from hello_agents.tools.builtin import ReadTool, WriteTool, EditTool, MultiEditTool

registry = ToolRegistry()
registry.register_tool(ReadTool(project_root="./", registry=registry))
registry.register_tool(WriteTool(project_root="./", registry=registry))
registry.register_tool(EditTool(project_root="./", registry=registry))

# 乐观锁：Read 后缓存 file_mtime_ms，Edit 时传入检测冲突
```

---

## 四、异步与流式

### 异步执行

```python
import asyncio
result = await agent.arun("分析项目结构")
```

### 流式输出

```python
from hello_agents.core.streaming import StreamEventType

async for event in agent.arun_stream("分析项目"):
    if event.type == StreamEventType.LLM_CHUNK:
        print(event.data["content"], end="", flush=True)
    elif event.type == StreamEventType.TOOL_CALL_START:
        print(f"🔧 {event.data['tool_name']}")
    elif event.type == StreamEventType.TOOL_CALL_FINISH:
        print(f"✅ {event.data['tool_name']}")
```

### 8 种流式事件

AGENT_START, AGENT_FINISH, STEP_START, STEP_FINISH, TOOL_CALL_START, TOOL_CALL_FINISH, LLM_CHUNK, THINKING, ERROR

### FastAPI SSE 集成

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/stream")
async def chat_stream(message: str):
    async def gen():
        async for event in agent.arun_stream(message):
            yield event.to_sse()
    return StreamingResponse(gen(), media_type="text/event-stream")
```

### 生命周期钩子

```python
from hello_agents.core.lifecycle import LifecycleHook, AgentEvent

class MyHook(LifecycleHook):
    async def on_start(self, event: AgentEvent): ...
    async def on_step(self, event: AgentEvent): ...
    async def on_tool_call(self, event: AgentEvent): ...
    async def on_finish(self, event: AgentEvent): ...
    async def on_error(self, event: AgentEvent): ...

agent.register_hook(MyHook())
```

### 工具并行

- **用户工具**：并行执行
- **内置工具**（Thought、Finish）：串行执行

---

## 五、上下文工程

### 自动历史压缩

```python
config = Config(
    context_window=128000,
    compression_threshold=0.8,    # 80% 时压缩
    min_retain_rounds=10,         # 保留最近 10 轮
    enable_smart_compression=False  # 简单摘要（0 Token）或智能摘要（需 LLM）
)
```

### 工具输出截断

```python
config = Config(
    tool_output_max_lines=2000,
    tool_output_max_bytes=51200,
    tool_output_truncate_direction="head"  # head / tail / head_tail
)
```

### 缓存友好设计

HistoryManager 只追加不编辑，保持 KV Cache 有效。

---

## 六、会话持久化

```python
config = Config(session_enabled=True, session_dir="memory/sessions")

# 保存
agent.save_session("my-session")

# 恢复
agent.load_session("memory/sessions/my-session.json")

# 列出
sessions = agent.list_sessions()
```

**ReActAgent 异常保护**：Ctrl+C 或异常时自动保存为 `session-interrupted.json` / `session-error.json`。

---

## 七、可观测性（TraceLogger）

```python
config = Config(
    trace_enabled=True,
    trace_output_dir="memory/traces",
    trace_sanitize=True
)

# 自动生成 memory/traces/trace-xxx.jsonl 和 trace-xxx.html
# HTML 可直接在浏览器查看，含统计面板、事件时间线
```

**事件类型**：session_start, session_end, step_start, step_end, tool_call, tool_result, llm_request, llm_response, error, compression, circuit_breaker

---

## 八、子代理机制

```python
config = Config(subagent_enabled=True)

# TaskTool 自动注册，Agent 可直接调用
agent.run("使用 Task 工具探索项目结构")

# 手动调用
from hello_agents.tools.tool_filter import ReadOnlyFilter, FullAccessFilter

result = agent.run_as_subagent(
    task="探索 hello_agents/core/",
    tool_filter=ReadOnlyFilter(),  # 只读：Read, Search 等
    return_summary=True
)
```

**TaskTool 参数**：task, agent_type (react/reflection/plan/simple), tool_filter (readonly/full/none), max_steps

**成本优化**：子代理可用轻量模型（如 DeepSeek），节省 70% Token。

---

## 九、熔断器

默认启用，连续失败 3 次后熔断，5 分钟后恢复。

```python
config = Config(
    circuit_enabled=True,
    circuit_failure_threshold=5,
    circuit_recovery_timeout=600
)

# 手动控制
registry.circuit_breaker.open("tool_name")
registry.circuit_breaker.close("tool_name")
registry.circuit_breaker.get_status("tool_name")
```

---

## 十、TodoWrite 与 DevLog

### TodoWriteTool

```python
config = Config(todowrite_enabled=True)

# Agent 调用
# 声明式覆盖，最多 1 个 in_progress
# 自动生成 Recap：📋 [2/5] 进行中: xxx. 待处理: xxx
```

### DevLogTool

```python
config = Config(devlog_enabled=True)

# 7 种类别：decision, progress, issue, solution, refactor, test, performance
# 保存到 memory/devlogs/
```

---

## 十一、Skills 知识外化

```python
# 创建 skills/pdf/SKILL.md
# ---
# name: pdf
# description: Process PDF files. Use when reading, creating, or merging PDFs.
# ---
# 详细内容...
# $ARGUMENTS

config = Config(
    skills_enabled=True,
    skills_dir="skills",
    skills_auto_register=True
)
# 按需加载，节省 85% Token
```

---

## 十二、Config 关键字段速查

```python
Config(
    context_window=128000,
    compression_threshold=0.8,
    min_retain_rounds=10,
    tool_output_max_lines=2000,
    tool_output_max_bytes=51200,
    trace_enabled=True,
    trace_output_dir="memory/traces",
    session_enabled=True,
    session_dir="memory/sessions",
    subagent_enabled=True,
    todowrite_enabled=True,
    devlog_enabled=True,
    circuit_enabled=True,
    circuit_failure_threshold=3,
    skills_enabled=True,
    skills_dir="skills",
)
```

---

## 十三、日志系统（四种范式）


| 范式          | 用途         | Agent 可用 |
| ----------- | ---------- | -------- |
| TraceLogger | 执行轨迹审计     | ❌        |
| AgentLogger | Agent 运行日志 | ❌        |
| DevLogTool  | 开发决策记录     | ✅        |
| 标准 logging  | 通用日志       | ❌        |


---

## 十四、开发规范

1. 自定义工具继承 `Tool`，`run()` 返回 `ToolResponse.success()` / `.error()` / `.partial()`
2. 工具失败用 `ToolResponse.error()`，不抛异常
3. 长任务用 `TodoWriteTool`，重要决策用 `DevLogTool`
4. 生产环境开启 `trace_enabled=True`
5. 子代理探索用 `tool_filter="readonly"`，实现用 `"full"`
6. 文件工具需传递 `registry` 以启用乐观锁

---

## 十五、完整文档（本 skill 的 docs/ 目录）

**所有文档已复制到本 skill 文件夹，路径：`C:\Users\Wangxr\.cursor\skills\hello-agents\docs\`**

| 文档 | 说明 |
|------|------|
| [docs/async-agent-guide.md](docs/async-agent-guide.md) | 异步执行、流式、生命周期钩子 |
| [docs/function-calling-architecture.md](docs/function-calling-architecture.md) | Function Calling 架构 |
| [docs/context-engineering-guide.md](docs/context-engineering-guide.md) | 上下文压缩、Token 计数、截断 |
| [docs/session-persistence-guide.md](docs/session-persistence-guide.md) | 会话保存与恢复 |
| [docs/streaming-sse-guide.md](docs/streaming-sse-guide.md) | 流式输出与 SSE |
| [docs/observability-guide.md](docs/observability-guide.md) | TraceLogger 可观测性 |
| [docs/subagent-guide.md](docs/subagent-guide.md) | 子代理机制 |
| [docs/circuit-breaker-guide.md](docs/circuit-breaker-guide.md) | 熔断器 |
| [docs/todowrite-usage-guide.md](docs/todowrite-usage-guide.md) | TodoWrite |
| [docs/devlog-guide.md](docs/devlog-guide.md) | DevLog |
| [docs/skills-quickstart.md](docs/skills-quickstart.md) | Skills 快速开始 |
| [docs/skills-usage-guide.md](docs/skills-usage-guide.md) | Skills 使用指南 |
| [docs/custom_tools_guide.md](docs/custom_tools_guide.md) | 自定义工具 |
| [docs/tool-response-protocol.md](docs/tool-response-protocol.md) | ToolResponse 协议 |
| [docs/file_tools.md](docs/file_tools.md) | 文件工具、乐观锁 |
| [docs/logging-system-guide.md](docs/logging-system-guide.md) | 日志系统 |

