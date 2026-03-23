"""
topic_tags（技术标签）规范化：与 SQLite topic_tags JSON、Neo4j (:Tag) 名称对齐。

设计原则（写入 miner_prompt 4c 摘要）
------------------------------------
1. **去噪**：首尾空白、连续空白、全角空格统一；剔除无检索价值的泛化词（如单独「面试」「八股」）。
2. **同义合并**：常见错写、大小写、中英混写统一到 canonical（见 _SYNONYM_LOWER）。
3. **缩写规范**：RAG、LLM、API、RPC、HTTP、TCP、JWT、ES、K8s 等保持约定写法。
4. **数量**：保留 2～4 个（与 Miner 一致）；去重保序；不足 2 个时用 `question_type` 前缀补一条领域词（算法/工程/基础/软技能/AI）。
5. **禁止**单独作为唯一标签的极泛词；若去泛后为空则回退到领域前缀 +「综合」。

入库时由 two_stage `_normalize_question_item` 调用；全库批处理见
`python -m backend.scripts.normalize_topic_tags --apply`。
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Sequence

# 完全匹配则剔除（过小、无区分度）
_BANNED_EXACT_LOWER = frozenset(
    {
        "面试",
        "面经",
        "八股",
        "题目",
        "试题",
        "问题",
        "相关",
        "技术",
        "技术题",
        "考点",
        "知识",
        "基础",
        "综合",
        "other",
        "others",
        "n/a",
        "na",
        "无",
        "暂无",
        "待定",
        "unknown",
    }
)

# 常见同义 / 错写 → 规范名（键为小写 stripped）
_SYNONYM_LOWER: dict[str, str] = {
    # 数据库 / 存储
    "mysql": "MySQL",
    "mysq": "MySQL",
    "pgsql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "memcached": "Memcached",
    "es": "Elasticsearch",
    "elasticsearch": "Elasticsearch",
    "elastic search": "Elasticsearch",
    # 消息 / 中间件
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "rocketmq": "RocketMQ",
    "mq": "消息队列",
    "消息中间件": "消息队列",
    # 语言 / 框架
    "java": "Java",
    "spring": "Spring",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    "go": "Go",
    "golang": "Go",
    "linux": "Linux",
    "python": "Python",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "react": "React",
    "vue": "Vue",
    "vue.js": "Vue",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    # 云原生
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    # 网络
    "http": "HTTP",
    "https": "HTTPS",
    "tcp": "TCP",
    "udp": "UDP",
    "grpc": "gRPC",
    "rpc": "RPC",
    "websocket": "WebSocket",
    # AI
    "rag": "RAG",
    "llm": "LLM",
    "gpt": "GPT",
    "transformer": "Transformer",
    "embedding": "Embedding",
    "向量化": "Embedding",
    "agent": "Agent",
    "智能体": "Agent",
    "kvcache": "KV Cache",
    "kv cache": "KV Cache",
    "loss": "损失函数",
    "sse": "SSE",
    "qlora": "QLoRA",
    "multi-agent": "多智能体",
    "多agent": "多智能体",
    "cot": "CoT",
    "ppo": "PPO",
    # 面经里小写 react 多为 ReAct 范式；前端 React 题通常写作「React」或「前端」
    "react": "ReAct",
    "deepseek": "DeepSeek",
    # 工程术语
    "qps": "QPS",
    "tps": "TPS",
    "jvm": "JVM",
    "gc": "GC",
    "jwt": "JWT",
    "oauth": "OAuth",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    # 中文同义
    "动态规划": "动态规划",
    "dp": "动态规划",
    "二叉树": "二叉树",
    "链表": "链表",
    "哈希表": "哈希表",
    "哈希": "哈希表",
    "并发": "并发编程",
    "多线程": "多线程",
    "线程池": "线程池",
    "锁": "锁",
    "索引": "索引",
    "事务": "事务",
    "持久化": "持久化",
    "缓存": "缓存",
    "穿透": "缓存穿透",
    "雪崩": "缓存雪崩",
    "微服务": "微服务",
    "分布式": "分布式系统",
    "一致性": "一致性",
    "幂等": "幂等",
}


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def normalize_single_topic_tag(raw: str) -> str:
    """单标签规范化；无效则返回空串。"""
    if raw is None:
        return ""
    s = _nfkc(str(raw)).strip()
    s = re.sub(r"\s+", " ", s)
    if not s or len(s) > 32:
        return ""
    low = s.lower()
    if low in _BANNED_EXACT_LOWER:
        return ""
    if low in _SYNONYM_LOWER:
        return _SYNONYM_LOWER[low]
    # 已含大小写混排（ReAct、QLoRa、Qwen 等），保持模型原样
    if re.search(r"[a-z]", s) and re.search(r"[A-Z]", s) and re.fullmatch(r"[A-Za-z0-9\-]+", s):
        return s
    # 已是常见全大写缩写（2–6 位纯字母）
    if re.fullmatch(r"[A-Za-z]{2,6}", s):
        up = s.upper()
        special = {
            "MYSQL": "MySQL",
            "GRPC": "gRPC",
            "HTTP": "HTTP",
            "HTTPS": "HTTPS",
            "LINUX": "Linux",
            "JAVA": "Java",
            "REDIS": "Redis",
            "KAFKA": "Kafka",
        }
        return special.get(up, up)
    # 首字母大写其余小写（纯英文单词）
    if re.fullmatch(r"[A-Za-z][a-z]+", s):
        return s[0].upper() + s[1:].lower()
    return s


def _domain_fallback_tag(question_type: str) -> str:
    """从 question_type 前缀取领域词，保证至少有一个粗粒度锚点。"""
    if not question_type:
        return "综合"
    prefix = question_type.split("-", 1)[0].strip()
    if prefix in ("算法", "工程", "基础", "软技能", "AI"):
        return prefix
    return "综合"


def normalize_topic_tags_for_question(
    tags: Sequence[str],
    question_text: str = "",
    question_type: str = "",
    min_tags: int = 2,
    max_tags: int = 4,
) -> List[str]:
    """
    将 LLM 输出的 topic_tags 规范为可入库列表（去重、去噪、补全条数）。
    question_text 预留供后续做关键词兜底（当前以 question_type 补全为主）。
    """
    _ = question_text  # 预留
    out: List[str] = []
    seen_lower = set()
    for t in tags or []:
        c = normalize_single_topic_tag(t)
        if not c:
            continue
        low = c.lower()
        if low in seen_lower:
            continue
        seen_lower.add(low)
        out.append(c)
        if len(out) >= max_tags:
            break

    # 不足 min_tags：补领域词 +「综合」等
    domain = _domain_fallback_tag(question_type)
    while len(out) < min_tags:
        cand = domain if domain not in out else f"{domain}综合"
        if cand.lower() not in seen_lower:
            out.append(cand)
            seen_lower.add(cand.lower())
        else:
            out.append("技术要点")
            seen_lower.add("技术要点")
        if len(out) >= min_tags:
            break

    return out[:max_tags]


def tags_equal(a: Sequence[str], b: Sequence[str]) -> bool:
    if len(a) != len(b):
        return False
    return all(x == y for x, y in zip(a, b))
