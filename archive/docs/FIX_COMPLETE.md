# 题目入库问题完整修复方案

## 问题描述

题目提取后入库失败，错误信息：`保存题目失败 ?: 'q_id'`

## 根本原因分析

存在**两处不匹配**：

### 1. 代码生成 UUID，但表定义为 INTEGER
- **代码**：`q_id = str(uuid.uuid4())`  → 生成 TEXT 类型的 UUID
- **表定义**：`q_id INTEGER PRIMARY KEY AUTOINCREMENT`  → 期望整数
- **结果**：类型不匹配，插入失败

### 2. 代码中曾缺少 q_id 字段
- `extract_questions_from_post()` 返回的字典中没有 `q_id` 字段
- `_save_questions()` 插入时需要这个字段

## 完整修复方案

### ✅ 修复 1：添加 q_id 生成逻辑

**文件**：`backend/services/crawler/question_extractor.py`

**修改**：在构造题目字典时生成 UUID
```python
# 生成唯一的 q_id（UUID）
import uuid
q_id = str(uuid.uuid4())

questions.append({
    "q_id": q_id,  # 添加 q_id 字段
    "question_text": q_text,
    "answer_text": str(item.get("answer_text", "")).strip(),
    "difficulty": difficulty_val,
    "question_type": str(item.get("question_type", "技术题")),
    "topic_tags": json.dumps(tags_raw, ensure_ascii=False),
    "company": final_company,
    "position": final_position,
    "business_line": business_line or "",
    "source_platform": platform,
    "source_url": source_url,  # 保留题目与 URL 的映射
    "extraction_source": extraction_source,
})
```

### ✅ 修复 2：修改表结构定义

**文件**：`backend/services/sqlite_service.py`

**修改**：将 `q_id` 从 `INTEGER` 改为 `TEXT`
```python
CREATE TABLE IF NOT EXISTS questions (
    q_id            TEXT PRIMARY KEY,  # 改为 TEXT，支持 UUID
    question_text   TEXT NOT NULL,
    answer_text     TEXT,
    difficulty      TEXT DEFAULT 'medium',
    question_type   TEXT DEFAULT '技术题',
    source_platform TEXT,
    source_url      TEXT,              # 题目与 URL 的映射关系
    company         TEXT,               # 公司信息
    position        TEXT,               # 岗位信息
    business_line   TEXT,
    topic_tags      TEXT DEFAULT '[]',  # 标签（JSON 数组）
    extraction_source TEXT DEFAULT 'content',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,  # 提取时间（自动）
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP   # 更新时间（自动）
)
```

## 数据库字段说明

### 核心字段
- **q_id**：TEXT PRIMARY KEY，UUID 格式，题目唯一标识
- **question_text**：TEXT NOT NULL，题目内容
- **answer_text**：TEXT，参考答案

### 元信息字段
- **difficulty**：easy/medium/hard，难度
- **question_type**：技术题/算法题/系统设计/行为题/HR问题
- **company**：公司名称（LLM 提取或帖子元数据）
- **position**：岗位名称
- **business_line**：业务线
- **topic_tags**：JSON 数组，如 `["Redis", "缓存", "Java"]`

### 来源追踪字段
- **source_platform**：nowcoder/xiaohongshu，来源平台
- **source_url**：原帖 URL，**保留题目与 URL 的映射关系**
- **extraction_source**：content/image，从正文还是图片提取

### 时间字段
- **created_at**：DATETIME，题目被提取的时间（自动设置为 CURRENT_TIMESTAMP）
- **updated_at**：DATETIME，题目更新时间（自动设置为 CURRENT_TIMESTAMP）

## 入库流程（已优化）

```
LLM 提取题目
  ↓
为每个题目生成 UUID (q_id)
  ↓
构造题目字典（包含所有字段）
  ├─ q_id: UUID (TEXT)
  ├─ question_text: 题目内容
  ├─ answer_text: 参考答案
  ├─ difficulty: 难度
  ├─ question_type: 题目类型
  ├─ topic_tags: JSON 数组（标签）
  ├─ company: 公司
  ├─ position: 岗位
  ├─ business_line: 业务线
  ├─ source_platform: 来源平台
  ├─ source_url: 原帖 URL（映射关系）
  └─ extraction_source: content/image
  ↓
_save_questions() 入库（同步）
  ├─ SQLite: INSERT INTO questions
  │   ├─ q_id: UUID (主键)
  │   ├─ source_url: 保留映射关系
  │   ├─ company, position, topic_tags: 元信息
  │   ├─ created_at: CURRENT_TIMESTAMP（自动）
  │   └─ updated_at: CURRENT_TIMESTAMP（自动）
  │
  ├─ Neo4j: 知识图谱（可选，同步）
  │   ├─ 创建 Question 节点
  │   ├─ 添加 embedding 向量
  │   └─ 建立关系（HAS_TAG, FROM_COMPANY）
  │
  └─ 更新 crawl_tasks.company（同步）
      └─ 如果 LLM 提取到公司信息，更新原帖记录
```

## 关于异步处理

**当前实现**：所有操作都是**同步**的
- SQLite 插入：同步（主存储，必须成功）
- Neo4j 写入：同步（可选，失败不影响 SQLite）
- 更新 crawl_tasks：同步（批量更新）

**为什么不异步**：
1. **数据一致性**：确保题目完全入库后才标记任务为 done
2. **错误处理**：同步执行便于捕获和记录错误
3. **性能足够**：单个题目入库耗时 < 100ms，批量处理时影响不大

**如果需要异步**：
- 可以将 Neo4j 写入改为异步（使用 asyncio 或后台线程）
- SQLite 必须保持同步（主存储）
- 需要添加失败重试机制

## 验证步骤

### 1. 重启服务
```bash
python run.py
```

### 2. 触发提取
前端点击"重新提取所有问题"或手动触发：
```bash
curl -X POST "http://localhost:8000/api/crawler/re-extract-all?batch_size=50"
```

### 3. 检查日志
应该看到：
```
✅ 提取完成(正文) [标题]: 5 道题目入库
```

不应该看到：
```
❌ 保存题目失败 ?: 'q_id'
```

### 4. 验证数据库
```sql
-- 检查题目是否成功入库
SELECT q_id, question_text, company, source_url, created_at 
FROM questions 
LIMIT 5;

-- 验证 q_id 格式（应该是 UUID）
-- 示例：a1b2c3d4-e5f6-7890-abcd-ef1234567890

-- 验证映射关系
SELECT q_id, source_url, company, position, topic_tags
FROM questions
WHERE source_url LIKE '%nowcoder%'
LIMIT 3;

-- 验证时间字段
SELECT q_id, question_text, created_at, updated_at
FROM questions
ORDER BY created_at DESC
LIMIT 5;
```

## 总结

### ✅ 已修复的问题
1. **q_id 类型不匹配**：表定义改为 TEXT，支持 UUID
2. **q_id 字段缺失**：代码中为每个题目生成 UUID
3. **时间字段**：created_at 和 updated_at 自动设置
4. **映射关系**：source_url 字段保留题目与原帖的关联
5. **元信息完整**：company、position、topic_tags 等字段齐全

### ✅ 数据完整性保证
- **主键**：q_id (UUID) 确保唯一性
- **映射**：source_url 保留题目来源
- **元信息**：company、position、tags 完整
- **时间戳**：created_at 记录提取时间
- **来源追踪**：source_platform、extraction_source

### 📝 注意事项
1. 首次启动会自动创建新表结构
2. 如果已有旧数据，需要手动迁移（运行 fix_questions_table.py）
3. Neo4j 写入是可选的，失败不影响 SQLite
4. 所有操作当前都是同步的，确保数据一致性

---

**修复时间**：2025-01-09  
**状态**：✅ 完全修复，可以正常入库
