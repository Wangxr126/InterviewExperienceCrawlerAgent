# 练习对话完整逻辑流程

> **重要说明**：本文档整理了练习对话（答题模式）的完整逻辑流程，包括前端交互、API 调用、后端处理等所有环节。

---

## 📋 目录

1. [核心流程概览](#核心流程概览)
2. [前端交互流程](#前端交互流程)
3. [后端 API 端点](#后端-api-端点)
4. [答题评估链](#答题评估链)
5. [对话交互链](#对话交互链)
6. [记忆系统集成](#记忆系统集成)
7. [错误处理机制](#错误处理机制)
8. [关键配置项](#关键配置项)

---

## 核心流程概览

练习对话有两条主要流程：

### 流程 A：自由对话（出题、解释、换题等）
```
前端发送消息
  ↓
POST /api/chat 或 /api/chat/stream
  ↓
orchestrator.chat()
  ↓
InterviewerAgent.run()
  ↓
返回回复 + 思考步骤
  ↓
前端显示（打字机效果）
```

### 流程 B：答题提交（评估、记忆、推荐）
```
前端提交答案
  ↓
POST /api/submit_answer
  ↓
orchestrator.submit_answer()
  ↓
确定性处理链（7个步骤）
  ↓
返回评估结果 + 推荐
  ↓
前端显示评分和反馈
```

---

## 前端交互流程

### 1. 开始练习

**用户操作**：点击"开始练习"按钮

**前端行为**：
```javascript
// 1. 获取随机题目
GET /api/questions/random?tag=Redis&difficulty=medium

// 2. 创建新 session
const sessionId = `sess_${generateUUID()}`;

// 3. 显示题目
displayQuestion(question);
```

### 2. 用户答题

**用户操作**：在输入框输入答案，点击"提交答案"

**前端行为**：
```javascript
// 提交答案到评估接口（不是 /api/chat）
POST /api/submit_answer
{
  "user_id": "default",
  "session_id": "sess_abc123",
  "question_id": "q_xyz789",
  "question_text": "Redis 持久化有哪些方式？",
  "user_answer": "RDB 和 AOF...",
  "question_tags": ["Redis", "持久化"]
}
```

### 3. 显示评估结果

**前端行为**：
```javascript
// 收到响应
{
  "score": 3,
  "feedback": "基本掌握，但有遗漏",
  "missed_points": ["未提到混合持久化", "AOF重写机制不清楚"],
  "strong_points": ["RDB和AOF的区别说清楚了"],
  "explanation": "你的得分：3/5\n\n答对的要点：...\n需要补充的点：...",
  "recommendation": "推荐学习资源：...",
  "tags": ["Redis", "持久化"]
}

// 显示评分和反馈
displayEvaluation(response);
```

### 4. 继续对话（可选）

**用户操作**：点击"换个问法"、"查看解析"等

**前端行为**：
```javascript
// 发送对话消息
POST /api/chat/stream
{
  "user_id": "default",
  "message": "换个问法问我这道题",
  "session_id": "sess_abc123"
}

// 接收 SSE 流式响应
data: {"thinking": [...]}
data: {"delta": "好的"}
data: {"delta": "，我"}
data: {"delta": "换个"}
...
data: [DONE]
```

### 5. 结束练习

**用户操作**：点击"结束练习"

**前端行为**：
```javascript
POST /api/session/end
{
  "user_id": "default",
  "session_id": "sess_abc123",
  "session_summary": "本次练习了 5 道 Redis 题目"
}
```

---

## 后端 API 端点

### 1. `/api/chat` - 自由对话（非流式）

**请求**：
```json
{
  "user_id": "default",
  "message": "给我出一道 Redis 的题",
  "resume": null,
  "session_id": "sess_abc123"
}
```

**响应**：
```json
{
  "reply": "好的，我给你出一道关于 Redis 持久化的题目...",
  "thinking": [
    {"thought": "用户想练习 Redis", "action": "search_questions", "observation": "..."}
  ]
}
```

**超时/重试机制**：
- 超时时间：90 秒
- 自动重试：连接错误/超时错误重试 2 次（共 3 次尝试）
- 429 错误：返回友好提示（火山引擎限额）

### 2. `/api/chat/stream` - 流式对话（SSE）

**请求**：同 `/api/chat`

**响应**（SSE 流）：
```
data: {"thinking": [{"thought": "...", "action": "...", "observation": "..."}]}

data: {"delta": "好"}
data: {"delta": "的"}
data: {"delta": "，"}
...
data: [DONE]
```

**特点**：
- 先等待 LLM 完整回复
- 然后按 3 字符/次推送（打字机效果）
- 每次推送间隔 15ms
- 支持自动重试（同 `/api/chat`）

### 3. `/api/submit_answer` - 答题提交

**请求**：
```json
{
  "user_id": "default",
  "session_id": "sess_abc123",
  "question_id": "q_xyz789",
  "question_text": "Redis 持久化有哪些方式？",
  "user_answer": "RDB 和 AOF，RDB 是快照...",
  "question_tags": ["Redis", "持久化"]
}
```

**响应**：
```json
{
  "score": 3,
  "feedback": "基本掌握，但有遗漏",
  "missed_points": ["未提到混合持久化", "AOF重写机制不清楚"],
  "strong_points": ["RDB和AOF的区别说清楚了"],
  "explanation": "✅ 你的得分：3/5\n\n**答对的要点：** ...\n**需要补充的点：** ...",
  "recommendation": "📚 推荐学习资源：...",
  "tags": ["Redis", "持久化"]
}
```

### 4. `/api/session/end` - 结束会话

**请求**：
```json
{
  "user_id": "default",
  "session_id": "sess_abc123",
  "session_summary": "本次练习了 5 道 Redis 题目，平均得分 3.2"
}
```

**响应**：
```json
{
  "status": "ok",
  "message": "Session 已结束，记忆已整合"
}
```

---

## 答题评估链

### orchestrator.submit_answer() - 7 步确定性处理

这是一个**完全确定性**的流程，每个步骤都无条件执行，不依赖 LLM 决定"要不要做"。

```python
async def submit_answer(
    user_id: str,
    session_id: str,
    question_id: str,
    question_text: str,
    user_answer: str,
    question_tags: Optional[List[str]] = None
) -> Dict[str, Any]:
```

#### Step A：结构化评估（LLM JSON mode）

```python
evaluation = _evaluate_answer_structured(question_text, user_answer)
# 返回：
# {
#   "score": 3,
#   "feedback": "基本掌握，但有遗漏",
#   "missed_points": ["未提到混合持久化"],
#   "strong_points": ["RDB和AOF的区别说清楚了"],
#   "tags": ["Redis", "持久化"]
# }
```

**关键点**：
- 直接调用 LLM（不走 ReAct 循环）
- 使用 JSON mode 确保结构化输出
- 评分标准：0-5 分
  - 0 = 完全不会
  - 1 = 基本不会
  - 2 = 大部分不会
  - 3 = 勉强会有遗漏
  - 4 = 基本掌握
  - 5 = 完全掌握有延伸

#### Step B：SM-2 更新（确定性）

```python
sqlite_service.add_study_record(
    user_id=user_id,
    question_id=question_id,
    score=score,
    user_answer=user_answer,
    ai_feedback=ai_feedback,
    session_id=session_id
)
```

**SM-2 算法**：
- 根据得分更新复习间隔
- 记录到 `user_answers` 表
- 更新 `study_sessions` 表

#### Step C：标签掌握度更新（确定性）

```python
if merged_tags:
    sqlite_service.update_tag_mastery(user_id, merged_tags, score)
```

**更新逻辑**：
- 更新 `tag_mastery` 表
- 记录每个标签的掌握度
- 用于后续推荐和复习

#### Step D：情景记忆（确定性）

```python
self._write_episodic(
    user_id=user_id,
    content=f"回答了题目【{question_text[:60]}】，得分 {score}/5。标签：{', '.join(merged_tags)}。",
    importance=0.65 + score * 0.05,
    event_type="study_record",
    question_id=question_id,
    score=score,
    session_id=session_id
)
```

**记忆类型**：
- **情景记忆**（episodic）：具体事件（答题记录）
- 重要性：0.65 + score * 0.05（得分越高越重要）

#### Step E：语义记忆更新（确定性）

```python
if score <= 2:
    self._write_semantic(
        user_id=user_id,
        content=f"用户对【{'、'.join(merged_tags)}】掌握薄弱（{score}/5），需重点加强",
        importance=0.82,
        knowledge_type="weakness"
    )
elif score >= 4:
    self._write_semantic(
        user_id=user_id,
        content=f"用户对【{'、'.join(merged_tags)}】掌握较好（{score}/5）",
        importance=0.75,
        knowledge_type="strength"
    )
```

**记忆类型**：
- **语义记忆**（semantic）：抽象知识（掌握度评估）
- 根据得分写入弱项或强项

#### Step F：连续薄弱检测 + 知识推荐（确定性计数器）

```python
if score <= 2 and merged_tags:
    # 更新本 session 内的标签失误计数
    for tag in merged_tags:
        self._session_weak_counts[user_id][session_id][tag] += 1

    # 触发条件：本次得分 ≤ 2（单次失误即推荐），或累计 ≥ 2 次
    trigger_tags = merged_tags
    consecutive_tags = [
        tag for tag in merged_tags
        if self._session_weak_counts[user_id][session_id][tag] >= 2
    ]

    # 调用知识推荐工具
    recommendation_text = _knowledge_recommender.run({
        "user_id": user_id,
        "tags": trigger_tags,
        "max_resources": 2,
        "max_mistakes": 3
    })
```

**推荐逻辑**：
- 单次失误（score ≤ 2）→ 立即推荐
- 连续失误（同标签 ≥ 2 次）→ 强化推荐 + 写入语义记忆

#### Step G：生成自然语言解释（LLM）

```python
explanation = _generate_explanation(question_text, evaluation, recommendation_text)
```

**生成内容**：
```
✅ 你的得分：3/5

**答对的要点：** RDB和AOF的区别说清楚了

**需要补充的点：** 
- 未提到混合持久化
- AOF重写机制不清楚

📚 推荐学习资源：
...
```

---

## 对话交互链

### orchestrator.chat() - 自由对话流程

```python
async def chat(
    user_id: str,
    message: str,
    resume: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple:
```

#### 流程步骤

**1. Session 管理**
```python
if not session_id:
    session_id = f"sess_{uuid.uuid4().hex[:8]}"

sqlite_service.ensure_session_exists(session_id, user_id)
sqlite_service.update_session_history(session_id, "user", message)
```

**2. 构建记忆上下文**
```python
memory_context = self._build_memory_context(user_id, message)
# 包含：
# - 语义记忆：用户技术栈、目标岗位、掌握程度
# - 情景记忆：近期相关学习记录
```

**3. 写入工作记忆**
```python
self._write_working(user_id, f"用户：{message}", session_id=session_id)
```

**4. 构建完整输入**
```python
context_prefix = "\n".join(filter(None, [
    f"[系统] user_id={user_id}, session_id={session_id}",
    memory_context,
    f"[简历]\n{resume}" if resume else "",
]))
full_input = f"{context_prefix}\n\n[用户消息]\n{message}"
```

**5. 调用 InterviewerAgent**
```python
from backend.agents.context import set_current_user_id
from backend.agents.thinking_capture import ThinkingCapture

set_current_user_id(user_id)  # 注入上下文

def _run_agent_with_capture():
    with ThinkingCapture() as tc:
        result = self.interviewer.run(full_input)
    return result, tc.get_steps()

response, thinking_steps = await loop.run_in_executor(None, _run_agent_with_capture)
```

**6. 入库 AI 回复**
```python
reasoning_summary = _format_thinking_for_db(thinking_steps)
sqlite_service.update_session_history(
    session_id, "assistant", response,
    reasoning=reasoning_summary or None
)
```

**7. 写入记忆**
```python
self._write_working(user_id, f"AI：{response[:200]}", session_id=session_id)
self._write_episodic(
    user_id=user_id,
    content=f"对话：「{message[:60]}」→「{response[:60]}」",
    importance=0.5,
    event_type="dialogue",
    session_id=session_id
)
```

**8. 返回结果**
```python
return response, thinking_steps
```

---

## 记忆系统集成

### 记忆类型

#### 1. 工作记忆（Working Memory）
- **用途**：临时存储当前 session 的对话
- **重要性**：0.5
- **生命周期**：session 结束后整合到情景记忆

```python
self._write_working(user_id, f"用户：{message}", session_id=session_id)
```

#### 2. 情景记忆（Episodic Memory）
- **用途**：具体事件（答题记录、对话记录）
- **重要性**：0.5 - 0.88（根据事件类型）
- **事件类型**：
  - `study_record`：答题记录
  - `dialogue`：对话记录
  - `content_ingestion`：收录面经
  - `session_complete`：session 结束

```python
self._write_episodic(
    user_id=user_id,
    content=f"回答了题目【{question_text[:60]}】，得分 {score}/5",
    importance=0.65 + score * 0.05,
    event_type="study_record",
    question_id=question_id,
    score=score,
    session_id=session_id
)
```

#### 3. 语义记忆（Semantic Memory）
- **用途**：抽象知识（用户画像、掌握度评估）
- **重要性**：0.75 - 0.92
- **知识类型**：
  - `user_profile`：用户技术栈、目标岗位
  - `weakness`：薄弱知识点
  - `strength`：掌握较好的知识点
  - `repeated_weakness`：连续失误的知识点

```python
self._write_semantic(
    user_id=user_id,
    content=f"用户对【{'、'.join(merged_tags)}】掌握薄弱（{score}/5）",
    importance=0.82,
    knowledge_type="weakness"
)
```

#### 4. 感知记忆（Perceptual Memory）
- **用途**：多模态输入（简历、图片等）
- **重要性**：0.7 - 0.8
- **模态**：text / image / audio

```python
self._write_perceptual(
    user_id, f"简历内容（{len(resume)}字）",
    modality="text", importance=0.8,
    session_id=session_id
)
```

### 记忆整合

**触发时机**：session 结束时

```python
def _consolidate_session_memories(self, user_id: str):
    mt = self._get_user_memory(user_id)
    if not mt:
        return
    try:
        # 工作记忆 → 情景记忆
        mt.execute("consolidate", from_type="working", to_type="episodic",
                   importance_threshold=0.65)
        # 遗忘低重要性记忆
        mt.execute("forget", strategy="importance_based", threshold=0.3)
        logger.info(f"✅ 用户 {user_id} session 记忆整合完成")
    except Exception as e:
        logger.warning(f"记忆整合失败: {e}")
```

---

## 错误处理机制

### 1. 超时处理

**超时时间**：90 秒

```python
try:
    reply, thinking_steps = await asyncio.wait_for(
        orchestrator.chat(...),
        timeout=90.0
    )
except asyncio.TimeoutError:
    return {"reply": "⚠️ 响应超时（90s），LLM 服务可能繁忙，请稍后重试。", "error": "timeout"}
```

### 2. 自动重试

**重试条件**：连接错误、超时错误

```python
def _is_retryable_error(e: Exception) -> bool:
    err = str(e).lower()
    return any(x in err for x in ["timeout", "connection", "refused", "reset", "econnrefused"])

for attempt in range(3):
    try:
        # 执行请求
        ...
    except Exception as e:
        if attempt < 2 and _is_retryable_error(e):
            logger.warning(f"连接错误，重试 {attempt + 2}/3")
            await asyncio.sleep(2)
            continue
        raise
```

### 3. 429 限额错误

**特殊处理**：返回友好提示

```python
if "429" in err_msg or "SetLimitExceeded" in err_msg:
    return {
        "reply": (
            "⚠️ **API 限额已到**（429 SetLimitExceeded）\n\n"
            "原因：火山引擎「安全体验模式」限制了每日调用次数。\n\n"
            "**解决方法**（两步）：\n"
            "1. 打开 https://console.volcengine.com/\n"
            "2. 进入「模型推理」→「安全体验模式」→ 关闭或调高限制\n\n"
            "关闭后刷新页面即可恢复正常使用。"
        ),
        "error": "rate_limit"
    }
```

### 4. LLM 解析失败

**记录到日志**：`llm_failures/answer_eval.jsonl`

```python
def _save_eval_failure(input_preview: str, raw_output: str, error: str):
    from backend.services.llm_parse_failures import save_failure
    save_failure(
        source="answer_eval",
        input_preview=input_preview,
        raw_output=raw_output,
        error=error,
        metadata={},
    )
```

---

## 关键配置项

### LLM 配置（.env）

```bash
# LLM 提供商
LLM_PROVIDER=ollama              # ollama / openai / dashscope

# 模型配置
LLM_MODEL_ID=qwen2.5:7b          # 模型名称
LLM_BASE_URL=http://localhost:11434  # API 地址

# Miner Agent（题目提取）
MINER_TEMPERATURE=0.1            # 温度（更确定性）
MINER_MAX_TOKENS=4096            # 最大输出 token

# Interviewer Agent（对话）
INTERVIEWER_TEMPERATURE=0.7      # 温度（更自然）
INTERVIEWER_MAX_TOKENS=2048      # 最大输出 token
INTERVIEWER_MAX_STEPS=10         # 最大思考步数
```

### 用户配置（.env）

```bash
# 默认用户 ID
DEFAULT_USER_ID=default
```

### 数据库配置（.env）

```bash
# SQLite 数据库路径
SQLITE_DB_PATH=backend/data/interview_agent.db

# Neo4j 配置（可选）
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

---

## 常见问题排查

### 问题 1：对话无响应

**可能原因**：
1. LLM 服务未启动（Ollama / OpenAI API）
2. 网络连接问题
3. API Key 配置错误

**排查步骤**：
```bash
# 1. 检查 LLM 服务
curl http://localhost:11434/api/tags  # Ollama

# 2. 检查配置
cat .env | grep LLM_

# 3. 查看日志
tail -f backend/logs/backend.log
```

### 问题 2：答题评估失败

**可能原因**：
1. LLM 返回格式不符合 JSON
2. 评估 Prompt 需要调整

**排查步骤**：
```bash
# 查看解析失败日志
cat llm_failures/answer_eval.jsonl | tail -5
```

### 问题 3：记忆系统不工作

**可能原因**：
1. hello-agents 未安装
2. 数据库连接失败

**排查步骤**：
```bash
# 检查 hello-agents
python -c "from hello_agents.tools import MemoryTool; print('OK')"

# 查看日志
grep "MemoryTool" backend/logs/backend.log
```

### 问题 4：Session 历史丢失

**可能原因**：
1. session_id 未正确传递
2. 数据库写入失败

**排查步骤**：
```bash
# 查询 session 记录
sqlite3 backend/data/interview_agent.db "SELECT * FROM study_sessions WHERE session_id='sess_xxx';"
```

---

## 总结

### 两条主要流程

1. **自由对话**（`/api/chat`）：
   - 出题、解释、换题等
   - 由 InterviewerAgent 处理
   - 支持流式响应（SSE）

2. **答题提交**（`/api/submit_answer`）：
   - 7 步确定性处理链
   - 评估 → SM-2 → 记忆 → 推荐
   - 完全由代码控制，不依赖 LLM 决策

### 关键设计原则

- **确定性流程用代码**：答题评估链、记忆整合
- **判断性行为用 LLM**：自由对话、出题推荐
- **记忆系统集成**：4 种记忆类型，自动整合
- **错误处理完善**：超时重试、429 友好提示

### 可扩展点

1. **评估算法**：可替换 SM-2 为其他算法
2. **推荐策略**：可调整推荐触发条件
3. **记忆整合**：可自定义整合策略
4. **LLM 提供商**：支持 Ollama / OpenAI / DashScope

---

**文档版本**：v1.0  
**创建时间**：2025-01-09  
**最后更新**：2025-01-09
