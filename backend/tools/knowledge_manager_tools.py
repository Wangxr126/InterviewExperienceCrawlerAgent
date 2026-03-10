"""
知识管理器工具箱 (KnowledgeManager Tools) v2.0
负责：结构化解析 → 语义查重 → 双写入库（Neo4j + SQLite）
新增：MetaExtractor（元信息提取）、真实 Embedding 生成
"""
import logging
import json
import uuid
import re
import requests
from typing import List, Dict, Any, Optional

from hello_agents.tools import Tool, ToolParameter
from backend.config.config import settings
from backend.services.storage.neo4j_service import neo4j_service
from backend.services.storage.sqlite_service import sqlite_service

logger = logging.getLogger(__name__)


# ==============================================================================
# 工具函数：生成 Embedding（调用 DashScope text-embedding-v3）
# ==============================================================================

def generate_embedding(text: str) -> List[float]:
    """
    调用 DashScope 兼容模式生成文本向量（1024维）。
    失败时返回空列表（查重/检索功能降级）。
    """
    if not text or not text.strip():
        return []

    try:
        headers = {
            "Authorization": f"Bearer {settings.embed_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.embed_model_name,
            "input": text[:2048],   # 截断避免超长
            "encoding_format": "float"
        }
        resp = requests.post(
            f"{settings.embed_base_url}/embeddings",
            headers=headers,
            json=payload,
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["data"][0]["embedding"]
        else:
            logger.warning(f"Embedding API 返回错误: {resp.status_code} {resp.text[:200]}")
            return []
    except Exception as e:
        logger.error(f"generate_embedding 异常: {e}")
        return []


# ==============================================================================
# 工具函数：调用 LLM（JSON 模式）
# ==============================================================================

def _call_llm_json(prompt: str, system: str = "") -> Any:
    """调用火山引擎 LLM，要求返回 JSON。失败时返回 None。"""
    try:
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json"
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.architect_model,
            "messages": messages,
            "temperature": settings.architect_temperature,
            "max_tokens": settings.architect_max_tokens,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(
            f"{settings.llm_base_url}/chat/completions",
            headers=headers, json=payload, timeout=60
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            logger.warning(f"LLM 返回错误: {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"_call_llm_json 异常: {e}")
        return None


# ==============================================================================
# 1. 元信息提取器 (MetaExtractor)
# 提取来源平台、公司、岗位、业务线、帖子难度等结构化元信息
# 规则优先，LLM 兜底
# ==============================================================================

# 规则字典（来源：牛客网爬虫原型的匹配规则）
_COMPANY_RULES = {
    "字节跳动": ["字节", "bytedance", "tiktok", "抖音"],
    "阿里巴巴": ["阿里", "alibaba", "淘宝", "天猫", "蚂蚁"],
    "腾讯": ["腾讯", "tencent", "微信", "qq"],
    "百度": ["百度", "baidu"],
    "美团": ["美团", "meituan"],
    "京东": ["京东", "jd"],
    "华为": ["华为", "huawei"],
    "网易": ["网易", "netease"],
    "小米": ["小米", "xiaomi"],
    "快手": ["快手", "kuaishou"],
    "滴滴": ["滴滴", "didi"],
}
_POSITION_RULES = {
    "后端研发": ["后端", "server", "服务端", "java", "go", "python", "c++"],
    "前端研发": ["前端", "frontend", "web", "vue", "react"],
    "算法工程师": ["算法", "algorithm", "ml", "机器学习", "深度学习", "ai"],
    "数据开发": ["数据", "大数据", "hadoop", "spark", "hive", "flink"],
    "测试工程师": ["测试", "qa", "test"],
    "运维/SRE": ["运维", "devops", "sre", "k8s", "docker"],
}
_DIFFICULTY_RULES = {
    "hard": ["拷打", "深挖", "疯狂", "压力", "三轮", "四轮", "挂了", "血压"],
    "easy": ["简单", "基础", "轻松", "顺利", "offer"],
}


class MetaExtractor(Tool):
    """
    从面经文本中提取结构化元信息：公司、岗位、业务线、难度、帖子类型。
    策略：规则优先 → LLM 兜底补全。
    """
    def __init__(self):
        super().__init__(
            name="extract_meta",
            description="从面经原文中提取公司、岗位、业务线、难度等结构化元信息。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="raw_text", type="string", description="面经原文（含标题）", required=True),
            ToolParameter(name="source_platform", type="string",
                          description="来源平台: nowcoder / xiaohongshu", required=False)
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        raw_text = parameters.get("raw_text", "")
        source_platform = parameters.get("source_platform", "")
        text_lower = raw_text.lower()

        meta = {
            "source_platform": source_platform,
            "company": "",
            "position": "",
            "business_line": "",
            "difficulty": "medium",
            "post_type": "面经"
        }

        # 1. 规则匹配
        for company, keywords in _COMPANY_RULES.items():
            if any(kw in text_lower for kw in keywords):
                meta["company"] = company
                break

        for position, keywords in _POSITION_RULES.items():
            if any(kw in text_lower for kw in keywords):
                meta["position"] = position
                break

        for difficulty, keywords in _DIFFICULTY_RULES.items():
            if any(kw in raw_text for kw in keywords):
                meta["difficulty"] = difficulty
                break

        # 2. LLM 兜底（补全规则未命中的字段）
        missing = [k for k in ("company", "position") if not meta.get(k)]
        if missing:
            llm_result = _call_llm_json(
                prompt=f"""以下是一段面试经验帖的文本，请提取以下字段并以JSON返回：
- company: 面试公司名称（中文，如"字节跳动"，不确定填""）
- position: 求职岗位（如"后端研发"、"算法工程师"，不确定填""）
- business_line: 业务线（如"搜索"、"推荐"、"广告"，不确定填""）

文本：
{raw_text[:1000]}""",
                system="你是信息提取专家，只输出JSON，不加解释。"
            )
            if llm_result:
                for k in ("company", "position", "business_line"):
                    if not meta.get(k) and llm_result.get(k):
                        meta[k] = llm_result[k]

        logger.info(f"📌 [MetaExtractor] 提取完成: {meta}")
        return json.dumps(meta, ensure_ascii=False)


# ==============================================================================
# 2. 知识结构化解析器 (KnowledgeStructurer)
# 将面经原文 + 元信息 → 结构化题目JSON列表
# ==============================================================================

_STRUCTURE_SYSTEM = """你是面试题结构化专家。
请从面经文本中提取所有面试题，输出严格的JSON格式：
{
  "questions": [
    {
      "question": "题目原文",
      "answer": "参考答案（根据上下文整理，若无则填空字符串）",
      "tags": ["标签1", "标签2"],
      "difficulty": "easy|medium|hard",
      "question_type": "技术题|行为题|算法题|系统设计题"
    }
  ]
}
要求：
- tags 使用技术术语（如Redis、MySQL、JVM、Spring、分布式等）
- 每道题必须有 question 字段
- 只提取明确的面试题，不要提取闲聊或感想
"""


class KnowledgeStructurer(Tool):
    """
    将原始面经文本解析为结构化的面试题列表（Question / Answer / Tags / Difficulty）。
    """
    def __init__(self):
        super().__init__(
            name="structure_knowledge",
            description="将原始面经文本解析为结构化的面试题JSON列表（question/answer/tags/difficulty/question_type）。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="raw_text", type="string", description="面经原文", required=True),
            ToolParameter(name="meta_json", type="string",
                          description="MetaExtractor 提取的元信息 JSON 字符串", required=False)
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        raw_text = parameters.get("raw_text", "")
        meta_json = parameters.get("meta_json", "{}")

        if not raw_text.strip():
            return json.dumps({"questions": []}, ensure_ascii=False)

        result = _call_llm_json(
            prompt=f"请从以下面经文本中提取所有面试题：\n\n{raw_text[:4000]}",
            system=_STRUCTURE_SYSTEM
        )

        if not result or "questions" not in result:
            logger.warning("KnowledgeStructurer: LLM 返回结构异常")
            return json.dumps({"questions": []}, ensure_ascii=False)

        # 注入元信息到每道题
        try:
            meta = json.loads(meta_json) if meta_json else {}
        except json.JSONDecodeError:
            meta = {}

        for q in result["questions"]:
            q.setdefault("company", meta.get("company", ""))
            q.setdefault("position", meta.get("position", ""))
            q.setdefault("business_line", meta.get("business_line", ""))
            q.setdefault("source_platform", meta.get("source_platform", ""))

        logger.info(f"✅ [KnowledgeStructurer] 解析出 {len(result['questions'])} 道题")
        return json.dumps(result, ensure_ascii=False)


# ==============================================================================
# 3. 语义查重卫士 (DuplicateChecker)
# ==============================================================================

class DuplicateChecker(Tool):
    """
    语义查重：检查题目是否已存在（向量相似度 > 0.92）。
    """
    def __init__(self):
        super().__init__(
            name="check_duplicate",
            description="检查该问题是否在数据库中已存在（基于语义相似度）。返回 NEW 或 DUPLICATE|题目ID。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="question", type="string", description="待检查的面试问题文本", required=True),
            ToolParameter(name="threshold", type="number",
                          description="相似度阈值，默认0.92", required=False)
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        question = parameters.get("question", "")
        threshold = float(parameters.get("threshold", 0.92))

        if not question.strip():
            return "ERROR|问题文本为空"

        embedding = generate_embedding(question)
        if not embedding:
            logger.warning("DuplicateChecker: Embedding 为空，跳过查重")
            return "NEW|Embedding生成失败，跳过查重"

        duplicate = neo4j_service.check_duplicate(embedding, threshold=threshold)
        if duplicate:
            logger.info(f"🔁 [查重] 发现重复题目: {duplicate['id']} (相似度: {duplicate.get('score', '?')})")
            return f"DUPLICATE|{duplicate['id']}"
        return "NEW|无重复"


# ==============================================================================
# 4. 入库管理员 (BaseManager)
# 将结构化题目双写 Neo4j + SQLite
# ==============================================================================

class BaseManager(Tool):
    """
    将结构化好的面试题存入数据库（Neo4j 图谱 + SQLite 关系库）。
    """
    def __init__(self):
        super().__init__(
            name="save_knowledge",
            description="将结构化的面试题存入 Neo4j 和 SQLite。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="question", type="string", description="题目正文", required=True),
            ToolParameter(name="answer", type="string", description="参考答案", required=True),
            ToolParameter(name="tags", type="array", description="技术标签列表", required=True),
            ToolParameter(name="difficulty", type="string",
                          description="难度: easy/medium/hard", required=False),
            ToolParameter(name="question_type", type="string",
                          description="题目类型：技术题/行为题/算法题/系统设计题", required=False),
            ToolParameter(name="source_url", type="string", description="来源帖子链接", required=False),
            ToolParameter(name="source_platform", type="string",
                          description="来源平台: nowcoder/xiaohongshu", required=False),
            ToolParameter(name="company", type="string", description="公司名称", required=False),
            ToolParameter(name="position", type="string", description="岗位名称", required=False),
            ToolParameter(name="business_line", type="string", description="业务线", required=False),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        question = parameters.get("question", "").strip()
        answer = parameters.get("answer", "").strip()
        tags = parameters.get("tags", [])
        difficulty = parameters.get("difficulty", "medium")
        question_type = parameters.get("question_type", "技术题")
        source_url = parameters.get("source_url", "")
        source_platform = parameters.get("source_platform", "")
        company = parameters.get("company", "")
        position = parameters.get("position", "")
        business_line = parameters.get("business_line", "")

        if not question:
            return "❌ 题目内容为空，跳过入库"

        try:
            # 1. 生成唯一 ID
            prefix = (tags[0].upper()[:6] if tags else "COMMON").replace(" ", "")
            q_id = f"{prefix}-{uuid.uuid4().hex[:6]}"

            # 2. 生成 Embedding
            embedding = generate_embedding(question)

            # 3. 写入 Neo4j
            neo4j_service.add_question(
                q_id=q_id, text=question, answer=answer,
                tags=tags, embedding=embedding,
                metadata={
                    "difficulty": difficulty,
                    "source": source_url,
                    "company": company,
                    "position": position,
                    "question_type": question_type,
                    "source_platform": source_platform
                }
            )

            # 4. 写入 SQLite questions 表
            sqlite_service.upsert_question(
                q_id=q_id, question_text=question, answer_text=answer,
                difficulty=difficulty, question_type=question_type,
                source_platform=source_platform, source_url=source_url,
                company=company, position=position, business_line=business_line,
                topic_tags=tags
            )

            # 5. 写入 ingestion_log
            sqlite_service.log_ingestion(q_id=q_id, source_url=source_url, tags=tags)

            logger.info(f"✅ [入库] {q_id} | {question[:40]}...")
            return f"SUCCESS|{q_id}"

        except Exception as e:
            logger.error(f"❌ 入库失败: {e}")
            return f"❌ 入库失败: {str(e)}"
