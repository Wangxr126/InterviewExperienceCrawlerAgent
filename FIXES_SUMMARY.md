# 🔧 问题修复总结

## 问题清单与修复状态

### ✅ 1. 工具调用展示不清晰（第一步多个工具无法对应）
**问题**：日志里显示"第 1 步"、"第 2 步"等，但实际上一个 LLM 决策可能包含多个工具调用，前端无法对应。

**修复**：
- 文件：`backend/agents/interviewer_agent.py`
- 添加了 `run()` 方法覆盖
- 现在输出格式：
  ```
  --- 第 1 步 ---
  📋 LLM 返回 4 个工具调用：
    1. recognize_intent(...)
    2. get_question_detail(...)
    3. submit_answer(...)
    4. submit_answer(...)
  
  --- 执行工具 1/4 ---
  🔧 recognize_intent
  👀 {...结果...}
  ```

---

### ✅ 2. reasoning_content 没有展示
**问题**：DeepSeek 的推理过程（reasoning_content）只在后端日志里，前端看不到。

**修复**：
- 文件：`backend/llm/deepseek_thinking_adapter.py`
- 添加了 `print(f"🤔 思考: {reasoning}")` 输出
- `ThinkingCapture` 会捕获这行，放入 `thinking_steps`
- 前端现在能看到完整推理过程

---

### ✅ 3. 分数问题（2.5 被记成 2）
**根本原因**：
1. `submit_answer` 工具里 `score = int(round(score_display))` 把 2.5 转成了 2
2. 调用 `add_study_record` 时传的是整数 `score`，而不是浮点数 `score_display`
3. 数据库表 `score` 字段定义为 `INTEGER`

**修复**：

#### 3.1 `backend/tools/interviewer_tools.py` (第 595-599 行)
```python
# 修复前
score = int(round(score_display))  # SM-2 用整数

# 修复后
score = int(score_display)  # SM-2 用整数（0-5）
# score_display 保持浮点数用于展示和存储
```

#### 3.2 `backend/tools/interviewer_tools.py` (第 676 行)
```python
# 修复前
sm2 = sqlite_service.add_study_record(
    ...
    score=score,  # ❌ 传整数
    ...
)

# 修复后
sm2 = sqlite_service.add_study_record(
    ...
    score=score_display,  # ✅ 传浮点数
    ...
)
```

#### 3.3 `backend/services/storage/sqlite_service.py` (第 97 行)
```sql
-- 修复前
score            INTEGER DEFAULT 0,

-- 修复后
score            REAL DEFAULT 0.0,
```

#### 3.4 `backend/services/storage/sqlite_service.py` (第 733 行)
```python
# 修复前
def add_study_record(self, user_id: str, question_id: str, score: int, ...):

# 修复后
def add_study_record(self, user_id: str, question_id: str, score: float, ...):
```

#### 3.5 `backend/services/storage/sqlite_service.py` (第 776 行)
```python
# 修复前
self.update_tag_mastery(user_id, tags, score_for_sm2)

# 修复后
self.update_tag_mastery(user_id, tags, score)  # 用原始浮点数
```

#### 3.6 `backend/services/storage/sqlite_service.py` (第 645 行)
```python
# 修复前
def update_tag_mastery(self, user_id: str, tags: List[str], score: int):

# 修复后
def update_tag_mastery(self, user_id: str, tags: List[str], score: float):
```

---

### ✅ 4. 时间信息不对（题库浏览里的作答时间错误）
**问题**：`get_study_records_by_question` 没有做时间转换，返回的是 UTC 时间。

**修复**：
- 文件：`backend/services/storage/sqlite_service.py` (第 893-925 行)
- 添加了时间转换逻辑：
```python
# ⚠️ 修复：转换 studied_at 到北京时间
sa = r.get("studied_at")
if sa:
    try:
        r["studied_at"] = timestamp_to_beijing(sa)
    except Exception:
        pass
```

---

### ✅ 5. 工具结果文字好看点
**修复**：
- 文件：`backend/agents/interviewer_agent.py`
- 结果超过 15 行时显示 `... (共 N 行)` 而不是完全截断
- JSON 格式化输出，更易读

---

### ✅ 6. 超时问题（一直显示"无法回答"）
**修复**：
- 文件：`backend/agents/orchestrator.py` (第 693-699 行)
- 把默认超时从 30 秒改成 60 秒
- 优先级：`INTERVIEWER_TIMEOUT` > `LLM_TIMEOUT` > 60 秒

---

## 📝 修改文件清单

| 文件 | 行号 | 修改内容 |
|------|------|--------|
| `interviewer_tools.py` | 595-599 | score 保持浮点数 |
| `interviewer_tools.py` | 676 | 传 score_display 而不是 score |
| `sqlite_service.py` | 97 | score 字段改为 REAL |
| `sqlite_service.py` | 645 | update_tag_mastery 参数改为 float |
| `sqlite_service.py` | 733-780 | add_study_record 接收 float score |
| `sqlite_service.py` | 776 | 传原始 score 到 update_tag_mastery |
| `sqlite_service.py` | 893-925 | get_study_records_by_question 添加时间转换 |
| `orchestrator.py` | 693-699 | 超时默认改为 60 秒 |
| `interviewer_agent.py` | 新增 | run() 方法清晰分组展示 |
| `deepseek_thinking_adapter.py` | 96-104 | reasoning_content 打印输出 |

---

## 🚀 验证步骤

1. **重启后端**：
   ```powershell
   conda activate NewCoderAgent
   python run.py
   ```

2. **测试分数**：
   - 在 chat 里提交答案，看分数是否显示为 2.5（而不是 2）
   - 在题库浏览里查看之前的作答记录，分数是否正确

3. **测试工具调用展示**：
   - 提交答案后，查看后端日志
   - 应该能看到清晰的"第 N 步"和"执行工具 X/Y"的分组

4. **测试时间信息**：
   - 题库浏览里的作答时间应该显示为北京时间

5. **测试超时**：
   - 复杂问题应该不会立即超时

---

## ⚠️ 注意事项

- 数据库表结构改变（score 从 INTEGER 改为 REAL）
- 如果数据库已有数据，SQLite 会自动转换，但建议备份
- 新的分数格式支持 0.5 间隔（0, 0.5, 1.0, ..., 5.0）
