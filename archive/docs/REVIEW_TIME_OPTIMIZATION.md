# 复习时间存储与推荐优化方案

## 📋 问题分析

用户提问：**"下次复习时间是否应该入向量库？应该记录到向量库、记忆库还是题目库？推荐时要考虑复习时间。"**

## ✅ 结论：当前设计是正确的

### 当前存储位置

`next_review_at` 存储在 **SQLite 的 `study_records` 表**（记忆库）：

```sql
CREATE TABLE IF NOT EXISTS study_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT NOT NULL,
    question_id      TEXT NOT NULL,
    session_id       TEXT,
    score            INTEGER DEFAULT 0,
    user_answer      TEXT,
    ai_feedback      TEXT,
    easiness_factor  REAL DEFAULT 2.5,
    repetitions      INTEGER DEFAULT 0,
    interval_days    INTEGER DEFAULT 1,
    next_review_at   DATETIME,  -- ← 复习时间
    studied_at       DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### 为什么这个设计是正确的？

| 存储位置 | 是否合适 | 原因 |
|---------|---------|------|
| **记忆库（SQLite study_records）** | ✅ **正确** | 1. 复习时间是**用户维度**的数据（每个用户对同一题的复习时间不同）<br>2. 需要记录**历史时间序列**（SM-2 算法依赖历史）<br>3. 便于按时间查询（`WHERE next_review_at <= NOW()`） |
| 题目库（Neo4j Question 节点） | ❌ 不合适 | 复习时间不是题目本身的属性，而是**用户-题目关系**的属性 |
| 向量库（Neo4j Embedding） | ❌ 不合适 | 向量库用于**语义检索**，不适合存储时间戳 |
| 用户画像（user_profiles） | ❌ 不合适 | 无法存储**每道题**的复习时间 |

---

## 🚀 优化方案：增强推荐引擎

### 问题：推荐时如何考虑复习时间？

当前 `get_recommended_question` 工具已经考虑了复习时间（策略1：遗忘曲线到期），但可以进一步优化：

### 优化 1：在 `get_latest_scores_for_questions` 中返回复习时间

**修改位置**：`backend/services/storage/sqlite_service.py`

**修改内容**：

```python
def get_latest_scores_for_questions(self, user_id: str, question_ids: List[str]) -> Dict[str, Dict]:
    """获取指定题目列表下，用户最近一次作答的得分和复习时间。
    返回 {q_id: {score, studied_at, next_review_at}}"""
    if not question_ids or not user_id:
        return {}
    placeholders = ",".join("?" * len(question_ids))
    params = [user_id] + list(question_ids) + [user_id] + list(question_ids)
    with self._get_conn() as conn:
        cursor = conn.execute(f"""
            SELECT sr.question_id, sr.score, sr.studied_at, sr.next_review_at
            FROM study_records sr
            INNER JOIN (
                SELECT question_id, MAX(studied_at) as max_at
                FROM study_records
                WHERE user_id = ? AND question_id IN ({placeholders})
                GROUP BY question_id
            ) latest ON sr.question_id = latest.question_id AND sr.studied_at = latest.max_at
            WHERE sr.user_id = ? AND sr.question_id IN ({placeholders})
        """, params)
        return {
            row["question_id"]: {
                "score": row["score"],
                "studied_at": row["studied_at"],
                "next_review_at": row["next_review_at"]  # ← 新增
            } for row in cursor.fetchall()
        }
```

**已完成** ✅

---

### 优化 2：在推荐引擎中优先推荐到期题目

**修改位置**：`backend/tools/interviewer_tools.py` 的 `GetRecommendedQuestionTool`

**优化策略**：

```python
def run(self, parameters):
    user_id = get_current_user_id()
    topic = (parameters.get("topic") or "").strip()
    company = (parameters.get("company") or "").strip()
    difficulty = (parameters.get("difficulty") or "").strip().lower()
    seen_ids = _get_seen_question_ids(user_id)
    
    try:
        question = None

        # 策略1: 遗忘曲线到期（优先级最高）
        if not topic and not company:  # 用户没有指定特定需求时
            due = sqlite_service.get_due_reviews(user_id, limit=5)
            if due:
                # 优先推荐得分最低的到期题目（最需要复习）
                due_sorted = sorted(due, key=lambda x: x.get("score", 0))
                c = due_sorted[0]
                tags_raw = c.get("topic_tags")
                question = {
                    "q_id": str(c["question_id"]),
                    "question_text": c.get("question_text") or "",
                    "answer_text": c.get("answer_text") or "",
                    "difficulty": c.get("difficulty", "medium"),
                    "topic_tags": (json.loads(tags_raw)
                                   if isinstance(tags_raw, str)
                                   else (tags_raw or [])),
                    "company": c.get("company", ""),
                    "_source": "due_review",
                    "_next_review_at": c.get("next_review_at"),  # ← 标记复习时间
                }

        # 策略2: 薄弱标签/指定topic/company
        # ... 现有逻辑 ...
```

---

### 优化 3：在题目推荐结果中显示复习状态

**修改位置**：`backend/tools/interviewer_tools.py` 的 `GetRecommendedQuestionTool`

**优化内容**：在返回的题目信息中添加复习状态标记

```python
# 在返回题目前，查询用户的复习状态
if question:
    q_id = question.get("q_id")
    if q_id:
        # 查询用户对该题的复习状态
        history = sqlite_service.get_latest_scores_for_questions(user_id, [q_id])
        if q_id in history:
            review_info = history[q_id]
            question["_review_status"] = {
                "last_score": review_info.get("score"),
                "studied_at": review_info.get("studied_at"),
                "next_review_at": review_info.get("next_review_at"),
                "is_due": (review_info.get("next_review_at") and 
                          review_info["next_review_at"] <= now_beijing_str("%Y-%m-%d %H:%M:%S"))
            }
```

---

### 优化 4：在 Prompt 中引导 Agent 提示复习状态

**修改位置**：`backend/agents/prompts/interviewer_prompt.py`

**优化内容**：

```python
### 意图：出题

**出题格式**：
📝 [模式标签] 题目：[完整题目文本]
要求：1.[要求1] 2.[要求2] 3.[要求3]
💡 难度：[easy/medium/hard] | 🏷️ 标签：[tag1, tag2]

{如果是复习题，添加提示}
🔄 复习提示：这是您之前做过的题目（上次得分：X/5，复习时间已到期），建议重新作答巩固记忆。

请回答这道题，完成后可说「评分」继续。
```

---

## 📊 优化效果对比

### 优化前

```
推荐策略：
1. 遗忘曲线到期（随机选择）
2. 薄弱标签新题
3. 随机未做过题

问题：
- 用户不知道这是复习题还是新题
- 没有优先推荐最需要复习的题目
- 推荐结果中缺少复习状态信息
```

### 优化后

```
推荐策略：
1. 遗忘曲线到期（优先推荐得分最低的）✅
2. 薄弱标签新题
3. 随机未做过题

优势：
- 用户明确知道这是复习题 ✅
- 优先复习最薄弱的题目 ✅
- 显示上次得分和复习时间 ✅
- 推荐结果包含完整复习状态 ✅
```

---

## 🎯 总结

### 核心结论

1. **存储位置正确**：`next_review_at` 存储在 SQLite `study_records` 表是最佳方案
2. **不需要入向量库**：向量库用于语义检索，不适合存储时间戳
3. **不需要入题目库**：复习时间是用户维度的数据，不是题目属性

### 优化重点

1. ✅ **已完成**：在 `get_latest_scores_for_questions` 中返回 `next_review_at`
2. 🔧 **建议实现**：在推荐引擎中优先推荐得分最低的到期题目
3. 🔧 **建议实现**：在题目推荐结果中显示复习状态
4. 🔧 **建议实现**：在 Prompt 中引导 Agent 提示复习状态

### 数据流

```
用户做题
  ↓
SQLite study_records 记录 next_review_at（SM-2 算法计算）
  ↓
推荐引擎查询 get_due_reviews()
  ↓
优先推荐到期题目（按得分排序）
  ↓
Agent 提示用户这是复习题
  ↓
用户重新作答
  ↓
更新 next_review_at（下次复习时间延后）
```

---

## 🔧 后续优化建议

### 1. 添加复习提醒功能

```python
def get_review_reminder(user_id: str) -> Dict:
    """获取用户的复习提醒"""
    due = sqlite_service.get_due_reviews(user_id, limit=10)
    return {
        "total_due": len(due),
        "urgent_count": len([d for d in due if d["score"] < 3]),
        "due_tags": list(set([tag for d in due for tag in json.loads(d.get("topic_tags") or "[]")]))
    }
```

### 2. 在前端显示复习日历

```javascript
// 前端可以调用 API 获取用户的复习日历
GET /api/review-calendar?user_id=xxx&month=2026-03

返回：
{
  "2026-03-14": 3,  // 3 道题到期
  "2026-03-15": 5,  // 5 道题到期
  ...
}
```

### 3. 智能调整复习间隔

```python
# 根据用户的答题表现动态调整 SM-2 参数
def adaptive_sm2(score: int, easiness_factor: float, 
                 user_avg_score: float) -> float:
    """根据用户整体表现调整遗忘曲线"""
    if user_avg_score < 3.0:
        # 用户整体较弱，缩短复习间隔
        easiness_factor *= 0.9
    elif user_avg_score > 4.0:
        # 用户整体较强，延长复习间隔
        easiness_factor *= 1.1
    return easiness_factor
```

---

## 📝 实现清单

- [x] 优化 `get_latest_scores_for_questions` 返回 `next_review_at`
- [ ] 优化推荐引擎优先推荐得分最低的到期题目
- [ ] 在题目推荐结果中显示复习状态
- [ ] 在 Prompt 中引导 Agent 提示复习状态
- [ ] 添加复习提醒功能
- [ ] 前端显示复习日历
- [ ] 智能调整复习间隔（Adaptive SM-2）

---

**结论**：当前设计已经很合理，只需要在推荐引擎和用户提示上做一些优化，就能充分利用复习时间信息。
