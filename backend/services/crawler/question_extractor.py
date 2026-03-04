"""
面经内容 → 独立题目 提取器（LLM 驱动）

输入：一篇面经原文（可能包含 10~30 道面试题混在叙述文字中）
输出：结构化的题目列表，每条含：
  - question_text    题目正文
  - answer_text      参考答案（从面经中提取，无则留空）
  - difficulty       easy / medium / hard
  - question_type    技术题 / 算法题 / 行为题 / 系统设计 / HR问题
  - topic_tags       技术标签列表（如 ["Redis", "Java", "JVM"]）
  - company          公司（继承自帖子元数据）
  - position         岗位
  - business_line    业务线
  - source_platform  来源平台
  - source_url       原帖链接
"""
import json
import logging
import uuid
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# 每次提取最大字符数（避免超 token）
MAX_CONTENT_CHARS = 6000

EXTRACT_SYSTEM_PROMPT = """你是一个专业的面试题结构化提取助手。你的任务是从面经帖子中提取所有面试题，并以严格的JSON格式输出。

输出格式要求：
- 必须输出一个合法的 JSON 数组
- 数组每个元素是一个对象，包含以下字段：
  - question_text: 字符串，面试官问的具体问题
  - answer_text: 字符串，原文中的回答或解析（没有则为空字符串""）
  - difficulty: 字符串，只能是 "easy"、"medium"、"hard" 之一
  - question_type: 字符串，只能是 "技术题"、"算法题"、"行为题"、"系统设计"、"HR问题" 之一
  - topic_tags: 字符串数组，技术标签，最多5个
- 不要输出任何 JSON 之外的文字，不要使用 markdown 代码块
- 如果没有找到面试题，输出空数组 []"""

EXTRACT_PROMPT_TEMPLATE = """帖子信息：
- 来源平台：{platform}
- 公司：{company}
- 岗位：{position}
- 难度：{difficulty}

面经原文：
{content}

请提取所有面试题，仅输出JSON数组，示例格式：
[{{"question_text":"Redis的持久化方式有哪些？","answer_text":"RDB和AOF","difficulty":"medium","question_type":"技术题","topic_tags":["Redis","持久化"]}},{{"question_text":"手写LRU缓存","answer_text":"","difficulty":"hard","question_type":"算法题","topic_tags":["算法","LRU","缓存"]}}]"""


def _call_llm(user_prompt: str) -> Optional[str]:
    """调用 LLM API，system+user 双消息，强制 JSON 输出。本地 Ollama 用 2×LLM_TIMEOUT。"""
    try:
        from openai import OpenAI
        from backend.config.config import settings
        base_timeout = settings.llm_timeout or 120
        timeout = max(base_timeout * 2, 180)
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=timeout,
        )
        messages = [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]
        # 尝试使用 JSON mode（Ollama 部分模型支持）
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model_id,
                messages=messages,
                temperature=0.0,
                timeout=timeout,
                response_format={"type": "json_object"},
            )
        except Exception:
            # 不支持 json_object 时回退到普通调用
            resp = client.chat.completions.create(
                model=settings.llm_model_id,
                messages=messages,
                temperature=0.0,
                timeout=timeout,
            )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return None


def _parse_json_from_llm(text: str) -> List[Dict]:
    """从 LLM 输出中提取 JSON 数组，兼容多种返回格式"""
    if not text:
        return []
    # 去掉 markdown 代码块（```json ... ``` 或 ``` ... ```）
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

    # 1. 直接解析整个文本
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # JSON mode 可能返回 {"questions": [...]} 或 {"items": [...]} 等
            for key in ("questions", "items", "results", "data", "list"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # 兜底：取第一个 list 值
            for v in data.values():
                if isinstance(v, list):
                    return v
    except json.JSONDecodeError:
        pass

    # 2. 提取文本中的 [...] 片段
    m = re.search(r"\[.*?\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # 3. 逐行尝试提取每行 JSON 对象，组合成列表
    results = []
    for line in text.splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "question_text" in obj:
                    results.append(obj)
            except json.JSONDecodeError:
                pass
    if results:
        return results

    logger.warning(f"LLM 返回内容无法解析为 JSON，前200字符: {text[:200]}")
    return []


def extract_questions_from_post(
    content: str,
    platform: str = "nowcoder",
    company: str = "",
    position: str = "",
    business_line: str = "",
    difficulty: str = "",
    source_url: str = "",
    post_title: str = "",
) -> List[Dict]:
    """
    从面经原文中用 LLM 提取结构化题目列表。

    content 过长时自动截断（6000 字符，约 3000 token）。
    返回完整的 question 字典列表，可直接写入数据库。
    """
    if not content or len(content.strip()) < 50:
        logger.warning(f"内容过短，跳过提取: {source_url}")
        return []

    # 截断过长内容
    truncated = content[:MAX_CONTENT_CHARS]
    if len(content) > MAX_CONTENT_CHARS:
        logger.info(f"内容截断: {len(content)} → {MAX_CONTENT_CHARS} chars")

    user_prompt = EXTRACT_PROMPT_TEMPLATE.format(
        platform="牛客网" if platform == "nowcoder" else "小红书",
        company=company or "未知",
        position=position or "未知",
        difficulty=difficulty or "适中",
        content=truncated,
    )

    raw = _call_llm(user_prompt)
    items = _parse_json_from_llm(raw)

    if not items:
        logger.warning(f"LLM 未提取到题目: {source_url}")
        return []

    questions: List[Dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        q_text = str(item.get("question_text", "")).strip()
        if not q_text or len(q_text) < 5:
            continue

        tags_raw = item.get("topic_tags", [])
        if not isinstance(tags_raw, list):
            tags_raw = [str(tags_raw)]

        questions.append({
            "q_id": f"Q-{uuid.uuid4().hex[:10].upper()}",
            "question_text": q_text,
            "answer_text": str(item.get("answer_text", "")).strip(),
            "difficulty": _normalize_difficulty(str(item.get("difficulty", "medium"))),
            "question_type": str(item.get("question_type", "技术题")),
            "topic_tags": json.dumps(tags_raw, ensure_ascii=False),
            "company": company or "",
            "position": position or "",
            "business_line": business_line or "",
            "source_platform": platform,
            "source_url": source_url,
        })

    logger.info(f"从帖子提取到 {len(questions)} 道题目: {post_title[:30] or source_url}")
    return questions


def _normalize_difficulty(d: str) -> str:
    d = d.lower().strip()
    if d in ("hard", "困难", "高", "困难/拷打"):
        return "hard"
    if d in ("easy", "简单", "低", "简单/常规"):
        return "easy"
    return "medium"
