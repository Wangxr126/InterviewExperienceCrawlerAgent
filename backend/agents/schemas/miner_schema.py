"""
Miner Agent 数据模型（Pydantic Schema）
用于结构化输出和数据验证

question_type：一律为「小类」字符串（算法-/工程-/基础-/软技能-/AI-*），禁止笼统大类。
"""
import json
import re
from typing import List, Tuple
from pydantic import BaseModel, Field, RootModel, field_validator

# ---------------------------------------------------------------------------
# question_type 全量小类（唯一真源，与 miner_prompt 4b、归一化推断一致）
# ---------------------------------------------------------------------------
_QUESTION_TYPE_CHOICES: Tuple[str, ...] = (
    # —— 算法（编程/手撕）——
    "算法-动态规划",
    "算法-回溯与搜索",
    "算法-BFS与图遍历",
    "算法-贪心",
    "算法-图论",
    "算法-树与二叉树",
    "算法-链表",
    "算法-数组与字符串",
    "算法-排序与二分查找",
    "算法-堆与优先队列",
    "算法-位运算与数学",
    "算法-经典结构实现",
    "算法-其他",
    # —— 工程实践 ——
    "工程-系统设计与架构",
    "工程-数据库与SQL",
    "工程-缓存与Redis",
    "工程-消息队列",
    "工程-微服务与治理",
    "工程-并发与多线程",
    "工程-网络与RPC",
    "工程-性能与调优",
    "工程-稳定性与容灾",
    "工程-搜索与Elasticsearch",
    "工程-云原生与DevOps",
    "工程-安全与合规",
    "工程-前端工程",
    "工程-其他",
    # —— 基础理论 ——
    "基础-操作系统",
    "基础-计算机网络",
    "基础-数据结构",
    "基础-编程语言",
    "基础-其他",
    # —— 软技能 ——
    "软技能-项目深度",
    "软技能-行为与情景",
    "软技能-HR与职业规划",
    "软技能-沟通与协作",
    "软技能-管理与领导力",
    "软技能-其他",
    # —— AI / 大模型 ——
    "AI-Agent记忆",
    "AI-Agent上下文与窗口",
    "AI-Agent工具调用",
    "AI-RAG与检索增强",
    "AI-LLM原理与结构",
    "AI-多智能体与编排",
    "AI-推理与规划",
    "AI-可靠性与幻觉治理",
    "AI-训练微调与评估",
    "AI-其他",
)

ALLOWED_QUESTION_TYPES: frozenset[str] = frozenset(_QUESTION_TYPE_CHOICES)

LEGACY_AI_QUESTION_TYPES: frozenset[str] = frozenset(
    {
        "AI类",
        "AI",
        "AI/Agent类",
        "AI应用开发",
        "AI概念",
        "AI模型",
        "AI类/工程类",
    }
)

# 常见历史字符串 → 直接映射到小类（无法再细分时）
LEGACY_DIRECT_MAP: dict[str, str] = {
    "技术题": "工程-其他",
    "系统设计": "工程-系统设计与架构",
    "系统设计题": "工程-系统设计与架构",
    "算法题": "算法-其他",
    "行为题": "软技能-行为与情景",
    "HR问题": "软技能-HR与职业规划",
    "HR题": "软技能-HR与职业规划",
}

# 微调/旧 prompt 中的英文式分类 → 小类
FINETUNE_STYLE_MAP: dict[str, str] = {
    "DP编程题": "算法-动态规划",
    "回溯编程题": "算法-回溯与搜索",
    "贪心编程题": "算法-贪心",
    "图算法题": "算法-图论",
    "树算法题": "算法-树与二叉树",
    "链表题": "算法-链表",
    "数组题": "算法-数组与字符串",
    "其他算法题": "算法-其他",
    "系统设计题": "工程-系统设计与架构",
    "数据库题": "工程-数据库与SQL",
    "缓存题": "工程-缓存与Redis",
    "消息队列题": "工程-消息队列",
    "微服务题": "工程-微服务与治理",
    "性能优化题": "工程-性能与调优",
    "并发编程题": "工程-并发与多线程",
    "操作系统题": "基础-操作系统",
    "计算机网络题": "基础-计算机网络",
    "数据结构题": "基础-数据结构",
    "编程语言题": "基础-编程语言",
    "项目经验题": "软技能-项目深度",
    "行为题": "软技能-行为与情景",
    "HR题": "软技能-HR与职业规划",
    "LLM原理题": "AI-LLM原理与结构",
    "LLM算法题": "AI-LLM原理与结构",
    "模型结构题": "AI-LLM原理与结构",
    "模型训练题": "AI-训练微调与评估",
    "RAG题": "AI-RAG与检索增强",
    "Agent题": "AI-推理与规划",
    "CV题": "AI-其他",
    "NLP题": "AI-其他",
}


def _blob(question_text: str, topic_tags: List[str]) -> str:
    parts = [question_text or ""]
    try:
        parts.append(json.dumps(topic_tags or [], ensure_ascii=False))
    except Exception:
        parts.append("")
    return "\n".join(parts)


def _is_non_other_fine(t: str) -> bool:
    if t not in ALLOWED_QUESTION_TYPES:
        return False
    return not (t.endswith("-其他") or t == "AI-其他")


def infer_algorithm_subtype(question_text: str, topic_tags: List[str]) -> str:
    """算法小类推断（顺序：先具体模式后兜底）。"""
    b = _blob(question_text, topic_tags)

    def has(*kw: str) -> bool:
        return any(k in b for k in kw)

    if has("动态规划", "DP", "背包", "状态压缩", "最长上升", "LIS", "LCS", "编辑距离"):
        return "算法-动态规划"
    if has("回溯", "N皇后", "全排列", "组合总和", "子集", "剪枝"):
        return "算法-回溯与搜索"
    if has("BFS", "广度优先", "层序遍历", "拓扑排序", "拓扑"):
        return "算法-BFS与图遍历"
    if has("贪心", "区间调度", "活动选择"):
        return "算法-贪心"
    if has("Dijkstra", "最短路", "最短路径", "并查集", "最小生成树", "Prim", "Kruskal", "图论"):
        return "算法-图论"
    if has("二叉树", "BST", "平衡树", "红黑树", "树遍历", "前序", "中序", "后序", "最近公共祖先", "LCA"):
        return "算法-树与二叉树"
    if has("链表", "反转链表", "环", "快慢指针") and "二叉树" not in b:
        return "算法-链表"
    if has("堆", "优先队列", "TopK", "第K大"):
        return "算法-堆与优先队列"
    if has("二分", "二分查找", "排序", "快排", "归并排序", "堆排序", "手撕快排", "手写快排"):
        return "算法-排序与二分查找"
    if has("位运算", "异或", "状态压缩位"):
        return "算法-位运算与数学"
    if has("LRU", "Trie", "前缀树", "最小栈", "栈实现队列", "循环队列", "经典结构"):
        return "算法-经典结构实现"
    if has(
        "滑动窗口",
        "双指针",
        "前缀和",
        "差分",
        "字符串匹配",
        "KMP",
        "数组",
        "子数组",
        "子串",
    ):
        return "算法-数组与字符串"
    if re.search(r"DFS|深度优先", b):
        return "算法-回溯与搜索"
    if has("岛屿", "网格", "矩阵", "迷宫") and ("图" in b or "BFS" in b or "DFS" in b):
        return "算法-图论"
    if has("算法", "编程题", "手撕", "代码", "O(n)", "时间复杂度"):
        return "算法-其他"
    return "算法-其他"


def infer_engineering_subtype(question_text: str, topic_tags: List[str]) -> str:
    b = _blob(question_text, topic_tags)

    def has(*kw: str) -> bool:
        return any(k in b for k in kw)

    if has("系统设计", "秒杀", "短链", "架构设计", "高可用", "高并发", "分布式系统", "QPS", "百万级"):
        return "工程-系统设计与架构"
    if has("MySQL", "SQL", "索引", "事务", "隔离级别", "分库", "分表", "B+树", "InnoDB"):
        return "工程-数据库与SQL"
    if has("Redis", "Memcached", "缓存", "缓存穿透", "缓存雪崩", "热 key"):
        return "工程-缓存与Redis"
    if has("Kafka", "RabbitMQ", "RocketMQ", "消息队列", "MQ", "消费者组"):
        return "工程-消息队列"
    if has("微服务", "服务治理", "注册中心", "配置中心", "熔断", "限流", "网关", "Dubbo", "gRPC 治理"):
        return "工程-微服务与治理"
    if has(
        "线程安全",
        "synchronized",
        "volatile",
        "CAS",
        "ThreadLocal",
        "并发",
        "多线程",
        "线程池",
        "锁",
        "死锁",
        "活锁",
        "饥饿",
        "协程",
    ):
        return "工程-并发与多线程"
    if has("HTTP", "HTTPS", "TCP", "UDP", "RPC", "gRPC", "REST", "WebSocket"):
        return "工程-网络与RPC"
    if has("慢查询", "性能优化", "调优", "Profiling", "火焰图", "GC", "JVM 调优"):
        return "工程-性能与调优"
    if has("降级", "容灾", "异地多活", "主从", "备份", "幂等", "重试"):
        return "工程-稳定性与容灾"
    if has("Elasticsearch", "ES", "倒排索引", "全文检索"):
        return "工程-搜索与Elasticsearch"
    if has("Docker", "Kubernetes", "K8s", "CI/CD", "Prometheus", "Grafana", "容器"):
        return "工程-云原生与DevOps"
    if has("安全", "鉴权", "OAuth", "JWT", "XSS", "CSRF", "加密", "脱敏"):
        return "工程-安全与合规"
    if has("React", "Vue", "前端", "Webpack", "浏览器", "渲染", "虚拟列表"):
        return "工程-前端工程"
    return "工程-其他"


def infer_basic_subtype(question_text: str, topic_tags: List[str]) -> str:
    b = _blob(question_text, topic_tags)

    def has(*kw: str) -> bool:
        return any(k in b for k in kw)

    if has(
        "ArrayList",
        "LinkedList",
        "HashMap",
        "ConcurrentHashMap",
        "LinkedHashMap",
        "TreeMap",
        "HashSet",
        "Hashtable",
        "StringBuilder",
        "StringBuffer",
        "包装类",
        "泛型",
        "equals",
        "hashCode",
    ):
        return "基础-编程语言"
    if has("进程", "线程", "虚拟内存", "页面置换", "死锁", "文件系统", "IO ", "磁盘", "调度"):
        return "基础-操作系统"
    if has("TCP", "HTTP", "HTTPS", "DNS", "CDN", "四次挥手", "三次握手", "OSI"):
        return "基础-计算机网络"
    if has("栈", "队列", "哈希表", "堆", "时间复杂度", "空间复杂度") and not has(
        "手撕", "实现", "编程题", "代码"
    ):
        return "基础-数据结构"
    if has("Java", "Python", "Go ", "C++", "泛型", "反射", "内存模型", "垃圾回收"):
        return "基础-编程语言"
    return "基础-其他"


def infer_soft_skill_subtype(question_text: str, topic_tags: List[str]) -> str:
    b = _blob(question_text, topic_tags)

    def has(*kw: str) -> bool:
        return any(k in b for k in kw)

    if has("职业规划", "薪资", "加班", "离职", "为什么选我们公司", "期望", "到岗"):
        return "软技能-HR与职业规划"
    if has("冲突", "压力", "失败", "困难", "团队合作", "STAR", "情景", "同事", "领导"):
        return "软技能-行为与情景"
    if has("沟通", "跨部门", "对齐", "表达", "说服"):
        return "软技能-沟通与协作"
    if has("管理", "Leader", "带人", "团队规模", "优先级"):
        return "软技能-管理与领导力"
    if has("项目", "难点", "挑战", "负责", "角色", "贡献", "实习", "经历"):
        return "软技能-项目深度"
    return "软技能-其他"


def infer_ai_question_subtype(question_text: str, topic_tags: List[str]) -> str:
    """AI/大模型小类（与此前逻辑一致）。"""
    blob = _blob(question_text, topic_tags)
    low = blob.lower()

    def _has(*keys: str) -> bool:
        return any(k in blob for k in keys)

    def _has_re(pat: str) -> bool:
        return re.search(pat, blob, re.I) is not None

    if _has("工具调用", "Function Call", "function calling", "插件调用", "MCP") or _has_re(r"\btool\b"):
        return "AI-Agent工具调用"
    if _has("RAG", "检索增强", "向量检索", "Embedding 检索", "embedding检索"):
        return "AI-RAG与检索增强"
    if _has(
        "长期记忆",
        "短期记忆",
        "记忆机制",
        "记忆管理",
        "记忆压缩",
        "向量数据库",
        "向量库",
    ) or (
        _has("记忆")
        and _has(
            "Agent",
            "智能体",
            "LLM",
            "大模型",
            "RAG",
            "对话",
            "聊天",
            "上下文",
            "多轮",
        )
    ):
        return "AI-Agent记忆"
    if _has(
        "上下文",
        "上下文窗口",
        "上下文污染",
        "上下文隔离",
        "token 限制",
        "token限制",
        "窗口长度",
    ):
        return "AI-Agent上下文与窗口"
    if _has("多智能体", "Multi-Agent", "multi agent", "智能体编排", "Agent 编排"):
        return "AI-多智能体与编排"
    # 禁止用单独「安全」匹配：会误伤「线程安全」「内存安全」等 Java/工程语境
    if _has("幻觉", "越狱", "提示注入", "对抗攻击", "对抗样本", "红队", "模型安全", "Prompt 注入", "prompt注入"):
        return "AI-可靠性与幻觉治理"
    if _has("对齐", "RLHF", "人类反馈"):
        return "AI-训练微调与评估"
    if _has("可靠性") and _has("LLM", "大模型", "模型", "Agent", "RAG", "生成式"):
        return "AI-可靠性与幻觉治理"
    if _has("ReAct", "CoT", "思维链", "推理链", "规划", "Agent 设计模式"):
        return "AI-推理与规划"
    if _has(
        "Transformer",
        "Attention",
        "注意力",
        "Tokenizer",
        "分词",
        "LLM 原理",
        "大模型原理",
        "模型结构",
        "KV Cache",
        "kv cache",
    ):
        return "AI-LLM原理与结构"
    if _has("微调", "LoRA", "RLHF", "SFT", "预训练", "损失函数", "评估指标", "评测"):
        return "AI-训练微调与评估"
    if _has("Agent", "智能体", "agent") or "agent" in low:
        return "AI-推理与规划"
    return "AI-其他"


def infer_unified_best_subtype(question_text: str, topic_tags: List[str]) -> str:
    """未知类型时按内容多路推断，优先非「-其他」的小类。
    AI 类最后判断，避免「线程安全」等工程/基础题被误归入 AI。
    """
    for fn in (
        infer_algorithm_subtype,
        infer_engineering_subtype,
        infer_basic_subtype,
        infer_soft_skill_subtype,
        infer_ai_question_subtype,
    ):
        sub = fn(question_text, topic_tags)
        if _is_non_other_fine(sub):
            return sub
    # 第二轮：允许兜底小类
    for fn in (
        infer_algorithm_subtype,
        infer_engineering_subtype,
        infer_basic_subtype,
        infer_soft_skill_subtype,
        infer_ai_question_subtype,
    ):
        sub = fn(question_text, topic_tags)
        if sub in ALLOWED_QUESTION_TYPES:
            return sub
    return "基础-其他"


def refine_question_type_coarse_to_fine(
    question_text: str, topic_tags: List[str], raw_type: str
) -> str:
    """
    将模型或历史输出规范为「单题」小类：
    - 已在白名单 → 原样返回
    - 历史大类 / 脏字符串 → 按题干+topic_tags 推断
    """
    r = (raw_type or "").strip()
    if r in ALLOWED_QUESTION_TYPES:
        return r
    if r in LEGACY_DIRECT_MAP:
        mapped = LEGACY_DIRECT_MAP[r]
        if mapped.endswith("-其他") or mapped == "AI-其他":
            return infer_unified_best_subtype(question_text, topic_tags)
        return mapped
    if r in FINETUNE_STYLE_MAP:
        return FINETUNE_STYLE_MAP[r]
    if r in LEGACY_AI_QUESTION_TYPES or r == "AI类":
        return infer_ai_question_subtype(question_text, topic_tags)
    if r == "算法类":
        return infer_algorithm_subtype(question_text, topic_tags)
    if r == "工程类":
        return infer_engineering_subtype(question_text, topic_tags)
    if r == "基础类":
        return infer_basic_subtype(question_text, topic_tags)
    if r == "软技能":
        return infer_soft_skill_subtype(question_text, topic_tags)
    return infer_unified_best_subtype(question_text, topic_tags)


def recompute_question_type_from_content(question_text: str, topic_tags: List[str]) -> str:
    """
    全表扫描 / 逐题修正用：忽略库里旧的 question_type，仅根据题干与 topic_tags 重新推断小类。
    与 refine_question_type_coarse_to_fine(..., \"\") 等价；可纠正「已是合法小类但分错」的行。
    """
    return refine_question_type_coarse_to_fine(question_text, topic_tags, "")


def _validate_allowed_question_type(v: str) -> str:
    s = (v or "").strip()
    if s not in ALLOWED_QUESTION_TYPES:
        raise ValueError(
            "question_type 必须是题库「小类」之一（算法-/工程-/基础-/软技能-/AI-*），"
            f"禁止笼统大类。当前值: {s!r}"
        )
    return s


class QuestionSchema(BaseModel):
    """单个面试题的结构化模型"""

    question_text: str = Field(
        description="标准问句（中文，完整），如：请介绍 Redis 的持久化机制",
        min_length=5,
    )

    answer_text: str = Field(
        description=(
            "参考答案（中文，完整）。要求：\n"
            "1. 至少 20 字（特殊情况可放宽至 10 字）\n"
            "2. 包含定义 + 核心原理 + 应用场景/优缺点\n"
            "3. 原文有答案时完整提取，无答案时补充详细参考回答\n"
            "4. 系统设计题需保留架构分层、技术选型、实现逻辑"
        ),
        min_length=10,
    )

    difficulty: str = Field(description="easy / medium / hard")
    question_type: str = Field(
        description=(
            "题目类型小类：须为 miner 提示词 4b 所列「算法-/工程-/基础-/软技能-/AI-*」之一，"
            "每道题选最主要的一个考查点，禁止算法类/工程类等笼统大类。"
        )
    )

    topic_tags: List[str] = Field(
        description="2-4 个主题标签，如 ['Redis', '持久化', 'RDB', 'AOF']",
        min_length=2,
        max_length=4,
    )

    company: str = Field(
        default="",
        description=(
            "公司规范全称（优先从标题提取，无则 \"\"）。"
            "字节/ByteDance→字节跳动；腾讯/Tencent→腾讯。"
            "阿里系：标题出现淘宝/天猫/淘天/菜鸟/阿里云/蚂蚁/饿了么/高德/钉钉/飞猪/闲鱼/盒马等时，"
            "须填对应主体（如「菜鸟」「阿里云」），禁止一律写「阿里巴巴」；"
            "仅泛指集团且无更细主体时用「阿里巴巴」。"
            "禁止「大厂」「互联网公司」等模糊表述。"
        ),
    )

    position: str = Field(
        default="",
        description="岗位名称（不确定填空字符串），如：后端开发、算法工程师",
    )

    @field_validator("difficulty")
    @classmethod
    def _v_diff(cls, v: str) -> str:
        if v not in ("easy", "medium", "hard"):
            raise ValueError("difficulty 只能是 easy / medium / hard")
        return v

    @field_validator("question_type")
    @classmethod
    def _v_qtype(cls, v: str) -> str:
        return _validate_allowed_question_type(v)

    @field_validator("answer_text")
    @classmethod
    def validate_answer_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError(f"答案过短（{len(v)} 字），至少需要 10 字。请补充完整答案（定义+原理+应用）")
        return v.strip()

    @field_validator("topic_tags")
    @classmethod
    def validate_tags_count(cls, v: List[str]) -> List[str]:
        if not (2 <= len(v) <= 4):
            raise ValueError(f"标签数量错误（{len(v)} 个），必须是 2-4 个")
        return v

    @field_validator("company")
    @classmethod
    def validate_company(cls, v: str) -> str:
        forbidden = ["大厂", "互联网公司", "某公司", "XX公司"]
        if v and any(word in v for word in forbidden):
            raise ValueError(f"公司名称不能使用模糊表述：{v}。请填写具体公司全称或留空")
        return v.strip()


class QuestionListSchema(BaseModel):
    """面试题列表的结构化模型"""

    questions: List[QuestionSchema] = Field(
        description="提取到的所有面试题列表",
        min_length=1,
    )

    @field_validator("questions")
    @classmethod
    def validate_questions_not_empty(cls, v: List[QuestionSchema]) -> List[QuestionSchema]:
        if not v:
            raise ValueError("至少需要提取 1 道面试题")
        return v


class RoughQuestionSchema(BaseModel):
    """第一阶段：粗提取模型（只提取题目和原始答案片段）"""

    question_text: str = Field(
        description="标准问句（中文，完整）",
        min_length=5,
    )

    raw_answer: str = Field(
        description="原文中的答案片段（原样提取，不补充）。如果原文无答案，填空字符串",
        default="",
    )

    difficulty: str = Field(description="难度等级 easy/medium/hard")

    question_type: str = Field(
        description="题目类型小类（算法-/工程-/基础-/软技能-/AI-*），与 QuestionSchema 一致"
    )

    topic_tags: List[str] = Field(
        description="2-4 个主题标签",
        min_length=2,
        max_length=4,
    )

    company: str = Field(default="", description="公司全称")
    position: str = Field(default="", description="岗位名称")

    @field_validator("difficulty")
    @classmethod
    def _v_diff_r(cls, v: str) -> str:
        if v not in ("easy", "medium", "hard"):
            raise ValueError("difficulty 只能是 easy / medium / hard")
        return v

    @field_validator("question_type")
    @classmethod
    def _v_qtype_r(cls, v: str) -> str:
        return _validate_allowed_question_type(v)


class RoughQuestionListSchema(BaseModel):
    """第一阶段：粗提取列表"""

    questions: List[RoughQuestionSchema] = Field(
        description="粗提取的面试题列表",
        min_length=1,
    )


class Stage2QuestionSchema(BaseModel):
    """Stage 2 单题输出（FAQ 格式）"""

    question_text: str = Field(description="标准问句")
    answer_text: str = Field(description="完整参考答案（至少 20 字）")


class Stage2OutputSchema(RootModel[List[Stage2QuestionSchema]]):
    """Stage 2 输出格式：纯 JSON 数组，每项为 FAQ 格式"""
