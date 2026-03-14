# 多路召回 + 重排序架构优化

## 概述

优化推荐系统，从单一召回升级为**多路召回 + 重排序**架构，提升推荐质量和多样性。

## 架构设计

### 1. 召回阶段（Recall）

**目标**：从海量题库中快速筛选出候选集（Candidate Set）

#### 四路召回通道

| 召回通道 | 数据源 | 召回策略 | 优势 | 权重 |
|---------|--------|---------|------|------|
| **向量召回** | Neo4j 向量索引 | 基于用户画像/查询文本的语义检索 | 语义相似度高，理解用户意图 | 0.4 |
| **协同过滤** | SQLite study_records | 基于相似用户的高分题目 | 发现潜在兴趣，群体智慧 | 0.2 |
| **热门召回** | SQLite 统计 | 基于公司/岗位的高频题目 | 覆盖主流题目，保证基础 | 0.2 |
| **遗忘曲线** | SQLite SM-2 算法 | 基于复习时间的到期题目 | 巩固薄弱知识点，防遗忘 | 0.2 |

#### 召回流程

```
用户请求
    ↓
┌─────────────────────────────────────┐
│  多路并行召回（每路召回 2-3 倍候选） │
├─────────────────────────────────────┤
│  向量召回：30 条（top_n * 3）        │
│  协同过滤：20 条（top_n * 2）        │
│  热门召回：20 条（top_n * 2）        │
│  遗忘曲线：15 条（top_n * 1.5）      │
└─────────────────────────────────────┘
    ↓
去重合并（按权重融合分数）
    ↓
候选集（50-80 条）
```

### 2. 重排序阶段（Rerank）

**目标**：对候选集进行精排，选出最优 Top-N

#### 重排序策略

使用 **Ollama Qwen3-Reranker** 对候选集重排：

```python
# 输入：候选集 + 用户查询
candidates = [
    {"q_id": "q1", "question_text": "...", "recall_score": 0.8, "recall_sources": ["vector", "popular"]},
    {"q_id": "q2", "question_text": "...", "recall_score": 0.6, "recall_sources": ["cf"]},
    ...
]

# 重排序
reranked = rerank_candidates(
    query="用户查询文本",
    candidates=candidates,
    text_key="question_text",
    top_n=10
)

# 输出：按相关性排序的 Top-N
[
    {"q_id": "q1", "question_text": "...", "recall_score": 0.8, "rerank_score": 0.95},
    {"q_id": "q3", "question_text": "...", "recall_score": 0.5, "rerank_score": 0.88},
    ...
]
```

#### 重排序考虑因素

- **语义相关性**：题目与用户查询的语义匹配度
- **难度匹配**：题目难度与用户水平的匹配
- **标签掌握度**：用户对题目标签的掌握情况
- **时间衰减**：题目的新鲜度和时效性

### 3. 去重合并策略

**问题**：多路召回可能返回重复题目

**解决方案**：按权重融合分数

```python
def _merge_and_deduplicate(recall_results, weights):
    merged_dict = {}
    for source, results in recall_results.items():
        weight = weights.get(source, 0)
        for item in results:
            q_id = item["q_id"]
            recall_score = item.get("recall_score", 0) * weight
            
            if q_id in merged_dict:
                # 已存在，累加分数
                merged_dict[q_id]["recall_score"] += recall_score
                merged_dict[q_id]["recall_sources"].append(source)
            else:
                # 新题目
                merged_dict[q_id] = {
                    **item,
                    "recall_score": recall_score,
                    "recall_sources": [source]
                }
    
    return list(merged_dict.values())
```

**优势**：
- 多路命中的题目分数更高（说明质量好）
- 保留召回来源信息，便于分析和调试

## 实现细节

### 文件结构

```
backend/
├── services/
│   ├── multi_recall_recommender.py  # 多路召回推荐器（新增）
│   └── rerank_service.py            # 重排序服务（已有）
└── tools/
    └── interviewer_tools.py         # 面试官工具（更新）
```

### 核心类：MultiRecallRecommender

```python
class MultiRecallRecommender:
    def recommend(
        self,
        user_id: str,
        query: Optional[str] = None,
        company: Optional[str] = None,
        difficulty: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_n: int = 10,
        exclude_ids: Optional[Set[str]] = None,
        recall_weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        多路召回 + 重排序
        
        流程：
        1. 多路召回（并行）
        2. 去重合并
        3. 重排序
        4. 返回 Top-N
        """
```

### 调用示例

```python
from backend.services.multi_recall_recommender import multi_recall_recommender

# 推荐题目
questions = multi_recall_recommender.recommend(
    user_id="user123",
    query="Redis 缓存穿透",
    company="字节跳动",
    difficulty="medium",
    tags=["Redis", "缓存"],
    top_n=10,
    exclude_ids=seen_ids,
    recall_weights={"vector": 0.4, "cf": 0.2, "popular": 0.2, "review": 0.2}
)

# 返回结果
[
    {
        "q_id": "q123",
        "question_text": "如何解决 Redis 缓存穿透问题？",
        "answer_text": "...",
        "difficulty": "medium",
        "company": "字节跳动",
        "topic_tags": ["Redis", "缓存"],
        "recall_source": "vector",  # 主要召回来源
        "recall_sources": ["vector", "popular"],  # 所有召回来源
        "recall_score": 0.85,  # 召回分数
        "rerank_score": 0.92,  # 重排分数
    },
    ...
]
```

## 性能优化

### 1. 召回数量控制

- 向量召回：`top_n * 3`（30 条）
- 协同过滤：`top_n * 2`（20 条）
- 热门召回：`top_n * 2`（20 条）
- 遗忘曲线：`top_n * 1.5`（15 条）

**原因**：召回阶段追求召回率（Recall），重排序阶段追求精确率（Precision）

### 2. 并行召回

四路召回独立执行，互不阻塞：

```python
recall_results = {}

# 并行执行（Python 可用 ThreadPoolExecutor 优化）
if recall_weights.get("vector", 0) > 0:
    recall_results["vector"] = self._vector_recall(...)
if recall_weights.get("cf", 0) > 0:
    recall_results["cf"] = self._collaborative_filtering_recall(...)
if recall_weights.get("popular", 0) > 0:
    recall_results["popular"] = self._popular_recall(...)
if recall_weights.get("review", 0) > 0:
    recall_results["review"] = self._forgetting_curve_recall(...)
```

### 3. 降级策略

- **重排序失败**：降级为召回分数排序
- **某路召回失败**：不影响其他通道，继续执行
- **所有召回失败**：返回空列表，提示用户

```python
try:
    return rerank_candidates(query, candidates, top_n)
except Exception as e:
    logger.warning(f"[Rerank] 失败: {e}，降级返回原序")
    candidates.sort(key=lambda x: x.get("recall_score", 0), reverse=True)
    return candidates[:top_n]
```

## 配置参数

### 召回权重配置

```python
# 默认权重
recall_weights = {
    "vector": 0.4,    # 向量召回权重最高
    "cf": 0.2,        # 协同过滤
    "popular": 0.2,   # 热门召回
    "review": 0.2,    # 遗忘曲线
}

# 可根据场景调整
# 场景1：新用户（无历史数据）
recall_weights = {"vector": 0.5, "popular": 0.5, "cf": 0, "review": 0}

# 场景2：复习模式
recall_weights = {"review": 0.6, "vector": 0.2, "cf": 0.1, "popular": 0.1}

# 场景3：探索模式
recall_weights = {"vector": 0.3, "cf": 0.3, "popular": 0.4, "review": 0}
```

### 重排序配置

```python
# .env 配置
RERANK_ENABLED=true
RERANK_MODEL=qwen3-reranker
RERANK_OLLAMA_URL=http://localhost:11434
RERANK_TOP_N=10
RERANK_MAX_DOC_LENGTH=1024
RERANK_TIMEOUT=60
```

## 效果评估

### 评估指标

| 指标 | 定义 | 目标 |
|------|------|------|
| **召回率** | 相关题目被召回的比例 | > 90% |
| **精确率** | 召回题目中相关的比例 | > 80% |
| **多样性** | 召回题目的来源分布 | 均衡 |
| **响应时间** | 推荐接口响应时间 | < 500ms |

### A/B 测试方案

```python
# 对照组：单一向量召回
control_group = vector_recall(user_id, query, top_n=10)

# 实验组：多路召回 + 重排序
experiment_group = multi_recall_recommender.recommend(
    user_id, query, top_n=10
)

# 对比指标
metrics = {
    "click_rate": ...,      # 点击率
    "completion_rate": ..., # 完成率
    "avg_score": ...,       # 平均得分
    "diversity": ...,       # 多样性
}
```

## 未来优化方向

### 1. 深度学习排序

引入 LTR（Learning to Rank）模型：

- **特征工程**：用户特征、题目特征、交互特征
- **模型选择**：LambdaMART、XGBoost、深度神经网络
- **在线学习**：实时更新模型参数

### 2. 实时个性化

- **实时特征**：用户当前会话的行为特征
- **上下文感知**：考虑用户当前状态（疲劳度、时间段）
- **动态权重**：根据用户反馈动态调整召回权重

### 3. 冷启动优化

- **新用户**：基于注册信息（简历、目标岗位）的冷启动
- **新题目**：基于内容特征的冷启动
- **迁移学习**：利用相似用户/题目的数据

### 4. 多目标优化

- **主目标**：推荐相关性
- **辅助目标**：多样性、新颖性、难度适配
- **多目标融合**：帕累托最优、加权融合

## 总结

### 优化前

- **单一召回**：仅使用向量检索
- **覆盖不足**：无法发现潜在兴趣题目
- **缺乏复习**：未考虑遗忘曲线

### 优化后

- **多路召回**：向量 + 协同过滤 + 热门 + 遗忘曲线
- **精准重排**：使用 Reranker 模型精排
- **灵活配置**：支持权重调整和降级策略

### 核心优势

1. **召回率提升**：多路召回覆盖更多相关题目
2. **精确率提升**：重排序筛选出最优题目
3. **多样性提升**：不同召回通道提供不同视角
4. **鲁棒性提升**：单路失败不影响整体推荐

---

**文档版本**：v1.0  
**更新时间**：2025-01-XX  
**负责人**：推荐系统团队
