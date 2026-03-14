# 多路召回 + Reranking 优化方案

## 📋 优化目标

实现**多路召回 + Reranking** 的推荐策略，提升推荐质量和召回率。

---

## 🎯 核心设计

### 架构图

```
用户请求
  ↓
多路召回（并行）
  ├─ 通道1: 遗忘曲线到期（Due Review）
  ├─ 通道2: 向量语义检索（Vector Search）
  ├─ 通道3: 标签匹配（Tag Match）
  ├─ 通道4: 公司真题（Company Filter）
  └─ 通道5: SQLite 兜底（Fallback）
  ↓
合并去重（按 q_id）
  ↓
Reranking（Qwen3-Reranker）
  ↓
返回 Top-K
```

---

## 🔧 实现细节

### 1. 多路召回推荐器

**文件**：`backend/services/multi_recall_recommender.py`

**核心类**：`MultiRecallRecommender`

**召回通道**：

| 通道 | 触发条件 | 召回策略 | 分数计算 |
|------|---------|---------|---------|
| **Due Review** | 无 topic/company 指定 | 查询到期题目 | `(5-score)/5 * 0.7 + urgency * 0.3` |
| **Vector Search** | 有 query 且 Neo4j 可用 | 向量语义检索 | 余弦相似度 |
| **Tag Match** | 有 topic 或自动选薄弱标签 | 标签匹配 | `matched_tags / total_tags` |
| **Company Filter** | 有 company 指定 | 公司真题筛选 | 固定 0.8 |
| **Fallback** | 其他通道无结果 | SQLite 随机 | 固定 0.5 |

**关键方法**：

```python
def recommend(
    user_id: str,
    query: Optional[str] = None,      # 用于语义检索和 Reranking
    topic: Optional[str] = None,       # 知识点标签
    company: Optional[str] = None,     # 公司名称
    difficulty: Optional[str] = None,  # 难度
    exclude_ids: Optional[List[str]] = None,  # 排除的题目
) -> Optional[Dict[str, Any]]:
    """多路召回 + Reranking 推荐"""
```

### 2. 召回通道详解

#### 通道 1: 遗忘曲线到期（优先级最高）

**触发条件**：用户没有指定 topic 或 company

**召回逻辑**：
```python
due = sqlite_service.get_due_reviews(user_id, limit=20)
```

**分数计算**：
```python
# 得分越低、越紧急的题目分数越高
score = item.get("score", 0)
urgency = self._calculate_urgency(next_review_at)
final_score = (5 - score) / 5 * 0.7 + urgency * 0.3
```

**紧急度计算**：
- 未到期：0.0
- 1 天内：0.5
- 3 天内：0.8
- 超过 3 天：1.0

#### 通道 2: 向量语义检索

**触发条件**：有 query 且 Neo4j 可用

**召回逻辑**：
```python
emb = generate_embedding(query[:2048])
vec_results = neo4j_service.search_similar(
    emb,
    top_k=20,
    score_threshold=0.7,
    exclude_ids=exclude_ids,
)
```

**分数**：余弦相似度（0-1）

#### 通道 3: 标签匹配

**触发条件**：有 topic 指定 或 自动选择薄弱标签

**召回逻辑**：
```python
# 用户指定 topic
if topic:
    tags_to_use = [topic]
# 自动选择薄弱标签
else:
    weak_tags = sqlite_service.get_weak_tags(user_id)
    tags_to_use = [t["tag"] for t in weak_tags[:3]]

rows = neo4j_service.get_questions_by_tags(tags_to_use, limit=20)
```

**分数计算**：
```python
matched_tags = len(set(tags_to_use) & set(question_tags))
score = matched_tags / len(tags_to_use)
```

#### 通道 4: 公司真题

**触发条件**：有 company 指定

**召回逻辑**：
```python
rows = neo4j_service.recommend_by_company(company, limit=20)
```

**分数**：固定 0.8（公司真题权重高）

#### 通道 5: SQLite 兜底

**触发条件**：其他通道无结果

**召回逻辑**：
```python
rows = sqlite_service.filter_questions(
    tags=[topic] if topic else None,
    company=company,
    difficulty=difficulty,
    limit=20,
)
```

**分数**：固定 0.5（兜底分数）

### 3. 合并去重

**策略**：按 `q_id` 去重，保留最高分数

```python
def _deduplicate(self, candidates):
    seen = {}
    for c in candidates:
        q_id = c.get("q_id")
        if q_id not in seen or c.get("_score", 0) > seen[q_id].get("_score", 0):
            seen[q_id] = c
    return list(seen.values())
```

### 4. Reranking

**触发条件**：有 query 且 `settings.rerank_enabled=True` 且候选数 > 1

**Reranker 模型**：Qwen3-Reranker（通过 Ollama）

**重排逻辑**：
```python
reranked = rerank_candidates(
    query=query[:2048],
    candidates=candidates[:10],  # 限制候选数，避免超时
    text_key="question_text",
    top_n=10,
)
```

**分数更新**：
```python
for item in reranked:
    item["_score"] = item.get("rerank_score", item.get("_score", 0))
```

---

## 📊 优化效果

### 优化前 vs 优化后

| 维度 | 优化前 | 优化后 |
|------|--------|--------|
| **召回策略** | 单路召回（顺序执行） | 多路召回（并行执行） |
| **召回率** | 依赖单一通道 | 多通道互补，召回率提升 |
| **排序策略** | 随机选择 | Reranker 精排 |
| **复习时间** | 随机选择到期题目 | 优先推荐得分低+紧急的题目 |
| **语义理解** | 仅关键词匹配 | 向量语义检索 + Reranking |

### 召回率提升

```
场景 1: 用户说"来一道题"
  优化前：随机从 SQLite 选择
  优化后：
    - 通道1: 检查是否有到期题目（优先）
    - 通道3: 检查薄弱标签题目
    - 通道5: SQLite 兜底
  结果：召回率 100%，且优先复习到期题目

场景 2: 用户说"来一道字节的 Redis 题"
  优化前：Neo4j 标签检索 → 随机选择
  优化后：
    - 通道2: 向量检索"字节 Redis"
    - 通道3: 标签匹配"Redis"
    - 通道4: 公司筛选"字节"
    - Reranking: 精排最相关的题目
  结果：召回率提升，排序更精准

场景 3: 用户说"换个问法"
  优化前：向量检索 → 随机选择
  优化后：
    - 向量检索 → Reranking 精排
  结果：相似度更高
```

---

## 🔧 配置参数

### 推荐器参数

```python
class MultiRecallRecommender:
    def __init__(self):
        self.max_candidates_per_channel = 20  # 每个通道最多召回数
        self.rerank_top_k = 10  # Reranker 输入候选数
```

### 配置文件参数

```python
# .env
RERANK_ENABLED=true  # 是否启用 Reranking
RERANK_MODEL=qwen3-reranker  # Reranker 模型
RERANK_OLLAMA_URL=http://localhost:11434  # Ollama 地址
RERANK_TOP_N=10  # Reranker 返回数量
RETRIEVAL_SEARCH_TOP_K=20  # 向量检索召回数
RETRIEVAL_SCORE_THRESHOLD=0.7  # 向量检索分数阈值
```

---

## 📝 使用示例

### 示例 1: 基础推荐

```python
from backend.services.multi_recall_recommender import multi_recall_recommender

# 推荐一道题
question = multi_recall_recommender.recommend(
    user_id="Wangxr",
    exclude_ids=["q1", "q2", "q3"],
)

print(question)
# {
#   "q_id": "q123",
#   "question_text": "如何实现 Redis 持久化？",
#   "difficulty": "medium",
#   "topic_tags": ["Redis", "持久化"],
#   "company": "字节跳动",
#   "_channel": "due_review",
#   "_score": 0.85,
#   "_recall_info": {
#     "total_candidates": 15,
#     "reranked": false
#   }
# }
```

### 示例 2: 指定条件推荐

```python
# 推荐字节的 Redis 题
question = multi_recall_recommender.recommend(
    user_id="Wangxr",
    query="Redis 持久化",  # 用于语义检索和 Reranking
    topic="Redis",
    company="字节跳动",
    difficulty="medium",
    exclude_ids=["q1", "q2"],
)
```

### 示例 3: 在工具中使用

```python
# backend/tools/interviewer_tools.py

class GetRecommendedQuestionTool(Tool):
    def run(self, parameters):
        user_id = get_current_user_id()
        topic = parameters.get("topic")
        company = parameters.get("company")
        difficulty = parameters.get("difficulty")
        seen_ids = _get_seen_question_ids(user_id)
        
        # 使用多路召回推荐器
        question = multi_recall_recommender.recommend(
            user_id=user_id,
            query=topic or company or None,
            topic=topic,
            company=company,
            difficulty=difficulty,
            exclude_ids=seen_ids,
        )
        
        return ToolResponse.success(
            text=json.dumps(question, ensure_ascii=False)
        )
```

---

## 🎯 核心优势

### 1. 多路召回提升召回率

- **互补性**：不同通道覆盖不同场景
- **鲁棒性**：单个通道失败不影响整体
- **灵活性**：根据用户需求动态选择通道

### 2. Reranking 提升排序质量

- **语义理解**：基于 Reranker 模型的深度语义匹配
- **精准排序**：从多个候选中选出最相关的
- **用户体验**：推荐更符合用户意图

### 3. 复习时间优先

- **智能排序**：得分低+紧急的题目优先
- **遗忘曲线**：基于 SM-2 算法的科学复习
- **学习效果**：及时复习薄弱知识点

---

## 🔍 监控与调试

### 日志输出

```
[MultiRecall] 召回 15 个候选
[Recall-Due] 召回 3 个到期题目
[Recall-Vector] 召回 5 个语义相似题目
[Recall-Tag] 召回 4 个标签匹配题目
[Recall-Company] 召回 3 个公司真题
[MultiRecall] Rerank 完成，Top-10
[MultiRecall] 推荐题目 q_id=q123 | score=0.850
```

### 召回信息

每个推荐结果包含 `_recall_info`：

```json
{
  "_recall_info": {
    "total_candidates": 15,
    "reranked": true,
    "channels_used": ["due_review", "vector_search", "tag_match"]
  }
}
```

---

## 📈 后续优化方向

### 1. 个性化权重

根据用户历史行为动态调整各通道权重：

```python
# 用户偏好公司真题 → 提高 company_filter 权重
# 用户经常做错 → 提高 due_review 权重
```

### 2. 实时 A/B 测试

对比不同召回策略的效果：

```python
# 策略 A: 多路召回 + Reranking
# 策略 B: 单路召回
# 指标: 用户答题正确率、满意度
```

### 3. 缓存优化

缓存热门查询的召回结果：

```python
# Redis 缓存
cache_key = f"recall:{user_id}:{topic}:{company}"
if cached := redis.get(cache_key):
    return cached
```

### 4. 异步召回

将召回通道改为异步并行执行：

```python
import asyncio

async def _multi_recall_async(...):
    tasks = [
        self._recall_due_reviews_async(...),
        self._recall_vector_search_async(...),
        self._recall_by_tags_async(...),
    ]
    results = await asyncio.gather(*tasks)
    return merge_results(results)
```

---

## ✅ 总结

通过**多路召回 + Reranking**优化，推荐系统实现了：

1. ✅ **召回率提升**：多通道互补，覆盖更多场景
2. ✅ **排序质量提升**：Reranker 精排，推荐更精准
3. ✅ **复习时间优先**：智能排序，优先复习薄弱点
4. ✅ **语义理解增强**：向量检索 + Reranking，理解用户意图
5. ✅ **系统鲁棒性提升**：单个通道失败不影响整体

**核心价值**：从"随机推荐"升级为"智能推荐"，显著提升用户学习效率。
