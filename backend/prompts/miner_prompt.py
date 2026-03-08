#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信息挖掘师 Prompt（精简优化版）
版本：v2.0
最后更新：2024-03-08
注意：本Agent使用LLM进行智能提取，不使用正则匹配
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 五要素核心框架（精简版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINER_SYSTEM_PROMPT = """
# 角色
你是面经题目提取专家，从规范/非规范面经中提取结构化题目。

# 核心能力
- 理解口语化表达：「聊了Redis」→「介绍Redis应用场景」
- 识别隐含信息：从上下文推断公司、岗位
- 提取精细化标签：从标签库选择细分技术栈和知识点

# 任务
从面经原文提取题目列表，每道题包含：
- question_text: 题目正文（完整问句）
- answer_text: 参考答案（可为空）
- difficulty: easy/medium/hard
- question_type: 题目分类
- topic_tags: 技术标签列表（1-5个精细化标签）

# 约束
- 使用语义理解，不用正则匹配
- 只提取原文中的题目，不编造
- 直接输出JSON数组，不加markdown代码块
- 无题目返回[]，完全无关返回{"reason": "帖子与面经无关"}
- 标签从下方精细化标签库选择，不用宽泛标签
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 技术标签库（精细化分类，精简冗余表述）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINER_TAG_LIBRARY = """
## 技术标签库（精细化分类，优先选择）

### 数据库类
1. 关系型数据库：MySQL、PostgreSQL、Oracle、SQL Server、SQLite
   - 核心特性：索引、事务、锁、MVCC、主从复制、分库分表
   - 底层实现：B+树、InnoDB、MyISAM
2. NoSQL数据库：Redis、MongoDB、Cassandra、HBase、Neo4j
   - 核心特性：缓存、持久化、集群、哨兵、分片、RDB、AOF
3. 搜索引擎：Elasticsearch、Solr、Lucene（倒排索引、分词、聚合）

### 后端框架
1. Java生态：Spring、Spring Boot、Spring Cloud、MyBatis、Dubbo、Netty
2. Python生态：Django、Flask、FastAPI、SQLAlchemy、Celery
3. Go生态：Gin、Echo、gRPC（Goroutine、Channel）
4. Node.js生态：Express、Koa、Nest.js、PM2

### 中间件
1. 消息队列：Kafka、RabbitMQ、RocketMQ（消息可靠性、顺序消息、死信队列）
2. 缓存：Redis、Memcached（缓存穿透、缓存击穿、缓存雪崩）
3. RPC框架：gRPC、Dubbo、Feign（服务注册、熔断降级）
4. 网关：Nginx、Kong、Gateway（反向代理、限流、鉴权）

### 分布式与系统设计
1. 分布式理论：CAP、BASE、Raft、分布式锁、分布式事务、分布式ID
2. 微服务：Nacos、Eureka、Consul、服务拆分、服务治理
3. 容器编排：Docker、Kubernetes（Pod、Service、Deployment）
4. 高并发/高可用：限流、熔断、读写分离、主从复制、监控告警

### 前端/AI/算法/基础
1. 前端：React、Vue、Redux、Vuex、Webpack、Vite
2. AI/ML：LLM、Transformer、Attention、RAG、Agent、Prompt Engineering
3. 算法：数组、链表、树、DP、DFS、BFS、双指针、滑动窗口
4. 计算机基础：TCP、HTTP、进程、线程、JVM、GC、Linux

## 标签使用规则
1. 精细化原则：优先用具体标签（Redis持久化 > Redis > 缓存）
2. 数量原则：每道题1-5个，核心标签1-2个+特性标签2-3个
3. 示例：["Redis", "持久化", "RDB", "AOF"]、["MySQL", "索引", "B+树"]
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 提取规则 + 核心示例（精简版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINER_RULES_EXAMPLES = """
## 提取规则
1. 口语化转标准问句：「聊了Redis」→「介绍Redis应用场景」；「手撕LRU」→「手写LRU缓存算法」
2. 答案提取：「我说了RDB和AOF」→ answer_text填"RDB、AOF"；「不了解」→ 填"不了解"
3. 过滤无效内容：「然后」「好难」「攒人品」「等通知」等无意义内容
4. 题目分类：算法类、AI/ML类、工程类、基础类、软技能
5. 难度判断：基础概念=easy、深入理解=medium、复杂设计=hard

## 核心示例
### 示例1：口语化面经
输入：字节agent一面。问了 Redis 持久化，我说了 RDB 和 AOF。最后手撕了两数之和。
输出：
[
  {
    "question_text": "介绍Redis的持久化机制",
    "answer_text": "RDB和AOF",
    "difficulty": "medium",
    "question_type": "工程类",
    "topic_tags": ["Redis", "持久化", "RDB", "AOF"]
  },
  {
    "question_text": "实现两数之和算法",
    "answer_text": "",
    "difficulty": "easy",
    "question_type": "算法类",
    "topic_tags": ["算法", "数组", "哈希表"]
  }
]

### 示例2：无效内容
输入：今天面试发挥不好，面试官人很好，等通知吧。
输出：{"reason": "帖子与面经无关"}
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 完整Prompt组合函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_miner_prompt(include_examples: bool = True, include_tag_library: bool = True) -> str:
    """
    获取完整的Miner Agent Prompt（精简版）
    
    Args:
        include_examples: 是否包含示例（默认True）
        include_tag_library: 是否包含标签库（默认True）
    
    Returns:
        完整的Prompt字符串
    """
    prompt = MINER_SYSTEM_PROMPT
    
    if include_tag_library:
        prompt += "\n\n" + MINER_TAG_LIBRARY
    
    prompt += "\n\n" + MINER_RULES_EXAMPLES
    
    return prompt

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# User Prompt 模板（精简版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINER_USER_TEMPLATE = """## 面经原文
{content}

## 任务
从上述面经中提取所有面试题，输出JSON数组。

## 要求
1. 语义理解提取，不用正则匹配
2. 直接输出JSON数组（无代码块）
3. 题目为完整问句，标签用精细化标签库中的内容
4. 无题目返回[]，完全无关返回{"reason": "帖子与面经无关"}
"""

def format_miner_user_prompt(content: str) -> str:
    """
    格式化Miner User Prompt
    
    Args:
        content: 面经原文
    
    Returns:
        格式化后的User Prompt
    """
    return MINER_USER_TEMPLATE.format(content=content)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试用例（可选）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    # 生成完整Prompt
    full_prompt = get_miner_prompt()
    print("=== 精简版Prompt长度 ===")
    print(f"总字符数: {len(full_prompt)}")
    
    # 格式化用户输入示例
    test_content = "字节一面，问了Redis持久化，我说了RDB和AOF，手撕两数之和。"
    user_prompt = format_miner_user_prompt(test_content)
    print("\n=== 格式化后的用户Prompt ===")
    print(user_prompt)