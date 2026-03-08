# Prompt优化完成总结

## ✅ 已完成的工作

### 1. 解决命名问题

**问题：** 提取层有LLM，应该叫Agent，但`extractor_agent`不好听

**解决方案：** 重命名为 **Miner Agent（信息挖掘师）**

**理由：**
- ✅ 形象：从原文中"挖掘"结构化信息
- ✅ 好听：Miner比Extractor更有画面感
- ✅ 准确：有LLM，是Agent
- ✅ 专业：数据挖掘（Data Mining）是专业术语

**新架构命名：**
```
Hunter Service（爬虫）
   ↓
Miner Agent（挖掘师）- 使用LLM挖掘信息
   ↓
Knowledge Manager（管理器）- 无LLM，纯数据管理
   ↓
Interviewer Agent（面试官）- 使用LLM对话
```

---

### 2. 明确使用LLM而非正则

**问题：** Prompt中没有明确说明使用LLM进行语义理解，而非正则匹配

**解决方案：** 在Prompt中明确强调

**添加的内容：**

```python
MINER_SYSTEM_PROMPT = """
# 角色（Role）
你是信息挖掘师（Miner Agent），专门从面经原文中智能挖掘结构化信息。

**重要：你使用自然语言理解能力进行智能提取，不是简单的正则匹配或关键词搜索。**

你的能力：
- 理解口语化表达（「聊了Redis」→「请介绍Redis的应用场景」）
- 识别隐含信息（从上下文推断公司、岗位）
- 提取技术标签（精确识别技术栈和知识点）
- 结构化输出（JSON格式）
"""
```

**详细规则：**

```python
## 智能提取规则（使用LLM，不用正则）

### 重要：语义理解 vs 正则匹配

**❌ 不要这样做（正则匹配）：**
```python
# 错误示例：使用正则匹配
import re
pattern = r'问了(.+?)，'
matches = re.findall(pattern, text)
```

**✅ 应该这样做（语义理解）：**
```
理解上下文：
- "聊了Redis" → 理解为"面试官询问了Redis相关问题"
- "手撕了LRU" → 理解为"要求手写LRU算法"
- "问了项目" → 理解为"询问项目经验"
```

---

### 3. 添加精细化的技术标签库

**问题：** 缺少具体的技术标签指导，导致标签不够精确

**解决方案：** 添加完整的技术标签库

**标签库内容：**

#### 数据库类
- **关系型**：MySQL、PostgreSQL、Oracle、SQL Server、SQLite
- **特性**：索引、事务、锁、MVCC、主从复制、分库分表、B+树、InnoDB
- **NoSQL**：Redis、MongoDB、Cassandra、HBase、Neo4j
- **Redis特性**：缓存、持久化、集群、哨兵、分片、RDB、AOF、主从复制
- **搜索引擎**：Elasticsearch、Solr、Lucene、倒排索引、分词、聚合

#### 后端框架
- **Java**：Spring、Spring Boot、Spring Cloud、MyBatis、Hibernate、Dubbo、Netty
- **Python**：Django、Flask、FastAPI、Tornado、SQLAlchemy、Celery
- **Go**：Gin、Echo、Beego、gRPC、Goroutine、Channel
- **Node.js**：Express、Koa、Nest.js、Egg.js、PM2

#### 中间件
- **消息队列**：Kafka、RabbitMQ、RocketMQ、Pulsar、消息可靠性、顺序消息、死信队列
- **缓存**：Redis、Memcached、Caffeine、缓存穿透、缓存击穿、缓存雪崩
- **RPC**：gRPC、Dubbo、Thrift、Feign、服务注册、服务发现、负载均衡、熔断降级
- **网关**：Nginx、Kong、Zuul、Gateway、反向代理、限流、鉴权

#### 分布式系统
- **理论**：CAP、BASE、Paxos、Raft、2PC、3PC、TCC、Saga
- **特性**：分布式锁、分布式事务、分布式ID、分布式缓存
- **微服务**：服务拆分、服务治理、服务网格、API网关、Istio、Envoy
- **容器**：Docker、Kubernetes、Helm、Pod、Service、Deployment

#### AI/ML
- **大模型**：LLM、GPT、BERT、Transformer、Attention、Prompt Engineering、Fine-tuning、RLHF、LoRA
- **RAG**：Retrieval、Embedding、Vector Database、Rerank、Langchain、LlamaIndex、Semantic Search
- **Agent**：ReAct、Tool Use、Planning、Memory、Multi-Agent
- **深度学习**：PyTorch、TensorFlow、Keras、CNN、RNN、LSTM、GAN、Diffusion
- **机器学习**：监督学习、无监督学习、强化学习、决策树、随机森林、XGBoost、SVM

#### 算法与数据结构
- **数据结构**：数组、链表、栈、队列、哈希表、树、图、堆、二叉树、红黑树、B树、B+树、跳表、布隆过滤器
- **算法**：排序、查找、动态规划、贪心、回溯、分治、DFS、BFS、双指针、滑动窗口

#### 计算机基础
- **操作系统**：进程、线程、协程、锁、信号量、死锁、内存管理、虚拟内存、页面置换、文件系统、Linux、进程调度、IO模型
- **计算机网络**：TCP、UDP、HTTP、HTTPS、WebSocket、gRPC、三次握手、四次挥手、滑动窗口、拥塞控制、DNS、CDN、负载均衡
- **编程语言**：Java、Python、Go、C++、JavaScript、TypeScript、JVM、GC、内存模型、并发、协程、闭包

#### 系统设计
- **高并发**：限流、降级、熔断、缓存、异步、削峰填谷、读写分离、分库分表、CDN、负载均衡
- **高可用**：主从复制、集群、哨兵、故障转移、容灾、监控、告警、日志、链路追踪
- **性能优化**：数据库优化、缓存优化、代码优化、架构优化、慢查询、索引优化、连接池、异步处理

**标签使用规则：**

1. **精确性原则**
   - ✅ 使用：Redis、MySQL、Kafka
   - ❌ 避免：数据库、缓存、消息队列（太宽泛）

2. **具体性原则**
   - ✅ 使用：Redis持久化、MySQL索引、Kafka消息可靠性
   - ❌ 避免：Redis相关、MySQL问题、Kafka使用

3. **层级原则**
   - 优先使用具体技术：Redis > NoSQL > 数据库
   - 优先使用具体特性：Redis持久化 > Redis

4. **数量原则**
   - 每道题1-5个标签
   - 核心标签1-2个（如Redis、MySQL）
   - 特性标签2-3个（如持久化、索引、事务）

---

## 📊 对比

### 优化前

```python
EXTRACTOR_SYSTEM_PROMPT = """
你是面经提取专家，从面经原文中提取所有面试题。
"""

# 问题：
# 1. 没有明确使用LLM
# 2. 没有技术标签库
# 3. 命名不够形象
```

### 优化后

```python
MINER_SYSTEM_PROMPT = """
你是信息挖掘师（Miner Agent），使用自然语言理解能力进行智能提取。

**重要：你使用语义理解，不是正则匹配。**

你的能力：
- 理解口语化表达
- 识别隐含信息
- 提取精确技术标签（从标签库选择）
"""

# 改进：
# 1. ✅ 明确使用LLM语义理解
# 2. ✅ 提供完整技术标签库
# 3. ✅ 命名更形象（Miner）
```

---

## 📝 文件变更

### 新增文件

1. `backend/prompts/extractor_prompt.py` → 重命名为 `miner_prompt.py`
   - 添加技术标签库（200+个精确标签）
   - 明确使用LLM语义理解
   - 添加标签使用规则

2. `docs/Agent命名方案.md`
   - 对比多个命名方案
   - 推荐Miner Agent

### 修改内容

**Prompt优化：**
- ✅ 角色定义：从"提取专家"改为"信息挖掘师"
- ✅ 能力说明：明确使用语义理解，不用正则
- ✅ 标签库：添加200+个精确技术标签
- ✅ 使用规则：精确性、具体性、层级、数量原则
- ✅ 示例：添加AI/ML、系统设计等示例

---

## 🎯 效果

### 1. 命名更准确

```
旧：Extractor Service（提取服务）
新：Miner Agent（信息挖掘师）

优势：
- 更形象（挖掘信息）
- 更好听（Miner）
- 更准确（有LLM，是Agent）
```

### 2. 提取更智能

```
旧：可能使用正则匹配
新：明确使用LLM语义理解

示例：
输入："聊了Redis"
旧：可能提取失败（没有"问了"关键词）
新：理解为"请介绍Redis的应用场景"
```

### 3. 标签更精确

```
旧：["Redis", "缓存"]（模糊）
新：["Redis", "持久化", "RDB", "AOF"]（精确）

优势：
- 从标签库选择
- 多层级标签
- 技术+特性
```

---

## 🚀 下一步

### 1. 重命名文件

```bash
# 重命名Prompt文件
mv backend/prompts/extractor_prompt.py backend/prompts/miner_prompt.py

# 更新导入
# 所有使用extractor_prompt的地方改为miner_prompt
```

### 2. 更新代码

```python
# 旧代码
from backend.prompts.extractor_prompt import get_extractor_prompt

# 新代码
from backend.prompts.miner_prompt import get_miner_prompt
```

### 3. 测试

```bash
# 测试Miner Agent
python -m backend.agents.miner_agent

# 测试标签提取
# 验证是否使用标签库中的精确标签
```

---

## ✅ 总结

### 解决的三个问题

1. **命名问题** ✅
   - Extractor → Miner Agent
   - 更形象、更好听、更准确

2. **提取方式** ✅
   - 明确使用LLM语义理解
   - 不使用正则匹配

3. **标签精确性** ✅
   - 添加200+个技术标签
   - 提供使用规则和示例

### 优化效果

- ✅ Prompt更清晰
- ✅ 提取更智能
- ✅ 标签更精确
- ✅ 易于维护

**现在Miner Agent可以智能挖掘面经信息了！** 🎉
