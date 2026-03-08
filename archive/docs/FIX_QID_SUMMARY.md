# 问题修复总结

## 问题描述

在题目提取入库时出现错误：`保存题目失败 ?: 'q_id'`

## 根本原因

`extract_questions_from_post()` 函数返回的题目字典中**缺少 `q_id` 字段**，导致 `_save_questions()` 函数在插入 SQLite 时失败。

## 修复方案

### 1. 添加 q_id 生成逻辑

在 `backend/services/crawler/question_extractor.py` 的 `extract_questions_from_post()` 函数中，为每个题目生成唯一的 UUID 作为 q_id：

```python
# 生成唯一的 q_id（UUID）
import uuid
q_id = str(uuid.uuid4())

questions.append({
    "q_id": q_id,  # 添加 q_id 字段
    "question_text": q_text,
    "answer_text": str(item.get("answer_text", "")).strip(),
    # ... 其他字段
})
```

### 2. 确保时间字段

SQLite 的 `questions` 表已经有 `created_at` 和 `updated_at` 字段，在插入时自动设置为 `CURRENT_TIMESTAMP`。

### 3. 保持题目与 URL 的映射

每个题目都包含 `source_url` 字段，保持了题目与原帖的映射关系。

## 修复后的完整流程

```
LLM 提取题目
  ↓
为每个题目生成 UUID (q_id)
  ↓
构造题目字典（包含所有必需字段）
  ├─ q_id: UUID
  ├─ question_text: 题目内容
  ├─ answer_text: 参考答案
  ├─ difficulty: easy/medium/hard
  ├─ question_type: 题目类型
  ├─ topic_tags: JSON 数组
  ├─ company: 公司
  ├─ position: 岗位
  ├─ business_line: 业务线
  ├─ source_platform: 来源平台
  ├─ source_url: 原帖 URL（映射关系）
  └─ extraction_source: content/image
  ↓
_save_questions() 入库
  ├─ SQLite: INSERT INTO questions (主存储)
  │   ├─ created_at: CURRENT_TIMESTAMP（自动）
  │   └─ updated_at: CURRENT_TIMESTAMP（自动）
  ├─ Neo4j: 知识图谱（可选，异步）
  └─ 更新 crawl_tasks.company（如果 LLM 提取到）
```

## 验证

修复后重新运行提取任务，应该能看到：
- 题目成功入库
- 每个题目有唯一的 q_id
- 题目包含 created_at 时间戳
- 题目与原帖 URL 保持映射关系

## 相关文件

- `backend/services/crawler/question_extractor.py` - 题目提取逻辑（已修复）
- `backend/services/scheduler.py` - 调度器，调用 `_save_questions()`
- `backend/services/sqlite_service.py` - 数据库服务

## 测试建议

1. 重启服务：`python run.py`
2. 触发重新提取：前端点击"重新提取所有问题"
3. 查看日志：确认没有 `'q_id'` 错误
4. 检查数据库：`SELECT q_id, question_text, created_at FROM questions LIMIT 5;`

---

**修复时间**：2025-01-09  
**状态**：✅ 已完成
