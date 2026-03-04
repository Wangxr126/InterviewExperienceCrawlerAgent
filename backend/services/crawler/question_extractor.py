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

EXTRACT_SYSTEM_PROMPT = """你是「知识架构师」—— 面经结构化专家。你的唯一职责是从面经原文中精准提取所有面试题，并输出为严格的 JSON 数组。

## 角色设定
- 你熟悉技术面试（八股、算法、系统设计、行为面、HR 面）
- 你能区分「面试官问的问题」与「候选人叙述/吐槽/无关内容」
- 你会从叙述中挖掘隐含问题（如「问了 OOM 怎么解决」→ 提取为「项目中是否遇到过 OOM？如何解决？」）
- 你会从叙述中提取答案片段（如「我说了 RDB 和 AOF」→ answer_text 填 "RDB、AOF"）
- 对于**开放性问题**（如 OOM 如何解决、项目实现细节等），若原文无答案，请基于你的知识给出**实质性参考答案**（如 JVM OOM 的排查思路、常见解决方案），不要写「无具体回答」「可结合项目经验说明」等无效表述
- 你不会遗漏任何可独立作答的题目

## 输出格式（必须严格遵守）
- 仅输出一个 JSON 数组，不要 markdown 代码块，不要 ```，不要任何解释
- 每个元素必须包含：question_text, answer_text, difficulty, question_type, topic_tags
- 无面试题时输出 []
- difficulty 只能是 "easy"、"medium"、"hard" 之一
- question_type 只能是 "技术题"、"算法题"、"行为题"、"系统设计"、"HR问题" 之一
- topic_tags 是字符串数组，如 ["Redis","持久化"]"""

# 多例 few-shot，覆盖不同面经风格
EXTRACT_FEW_SHOT = """
## 示例 1（叙述中隐含问题，开放题需补充参考答案）
输入：8-11 1面 30分钟。上来自我介绍和项目经验。后面问项目实现细节，问了是否遇到 OOM 以及如何解决，无八股。8-15 2面 深挖项目，手写 LRU。
输出：[{"question_text":"项目中是否遇到过 OOM？如何解决的？","answer_text":"常见排查：堆内存溢出用 -Xmx 调大、mat 分析 dump；栈溢出检查递归；Metaspace 溢出检查类加载。解决：优化代码、增加堆内存、排查内存泄漏。","difficulty":"medium","question_type":"技术题","topic_tags":["Java","JVM","OOM"]},{"question_text":"手写 LRU 缓存","answer_text":"HashMap + 双向链表，get 时移到头，put 时若满则删尾节点","difficulty":"hard","question_type":"算法题","topic_tags":["算法","LRU","缓存"]}]

## 示例 2（有明确问答）
输入：问了 Redis 持久化，我说了 RDB 和 AOF。然后问了 MySQL 索引，B+树、聚簇索引。最后手撕了两数之和。
输出：[{"question_text":"Redis 持久化方式有哪些？","answer_text":"RDB 和 AOF","difficulty":"medium","question_type":"技术题","topic_tags":["Redis","持久化"]},{"question_text":"MySQL 索引原理？B+树、聚簇索引","answer_text":"","difficulty":"medium","question_type":"技术题","topic_tags":["MySQL","索引","B+树"]},{"question_text":"两数之和","answer_text":"","difficulty":"easy","question_type":"算法题","topic_tags":["算法","哈希"]}]

## 示例 3（行为面+HR）
输入：自我介绍、项目深挖、为什么离职、期望薪资。无八股。
输出：[{"question_text":"自我介绍","answer_text":"","difficulty":"easy","question_type":"行为题","topic_tags":["自我介绍"]},{"question_text":"项目深挖（实现细节）","answer_text":"","difficulty":"medium","question_type":"行为题","topic_tags":["项目"]},{"question_text":"为什么离职？","answer_text":"","difficulty":"easy","question_type":"HR问题","topic_tags":["离职"]},{"question_text":"期望薪资？","answer_text":"","difficulty":"easy","question_type":"HR问题","topic_tags":["薪资"]}]
"""

EXTRACT_PROMPT_TEMPLATE = """## 帖子信息
- 平台：{platform}
- 公司：{company}
- 岗位：{position}
- 难度：{difficulty}

## 面经原文
{content}

## 任务
请提取以上面经中的**所有面试题**，仅输出 JSON 数组，不要任何解释。{few_shot}
"""


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


def _dig_question_arrays(obj, depth=0, max_depth=10) -> List[List[Dict]]:
    """递归查找所有包含 question_text 对象的数组"""
    if depth > max_depth:
        return []
    found = []
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and "question_text" in obj[0]:
            found.append(obj)
        for v in obj:
            found.extend(_dig_question_arrays(v, depth + 1, max_depth))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.extend(_dig_question_arrays(v, depth + 1, max_depth))
    return found


def _parse_json_from_llm(text: str, user_prompt_for_debug: str = None) -> List[Dict]:
    """从 LLM 输出中提取 JSON 数组，兼容多种返回格式（含嵌套 job.project_detail 等）"""
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
            # 常见顶层 key 或嵌套 job.project_detail
            for key in ("questions", "items", "results", "data", "list", "output"):
                if key in data and isinstance(data[key], list):
                    arr = data[key]
                    if arr and isinstance(arr[0], dict) and "question_text" in arr[0]:
                        return arr
            if "job" in data and isinstance(data["job"], dict):
                for sub in ("project_detail", "questions", "interview_questions", "items"):
                    arr = data["job"].get(sub)
                    if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "question_text" in arr[0]:
                        return arr
            if "question" in data and isinstance(data["question"], str):
                return [{"question_text": data["question"], "answer_text": "", "difficulty": "medium",
                         "question_type": "技术题", "topic_tags": []}]
            # 递归查找嵌套数组（如 job.project_detail）
            arrays = _dig_question_arrays(data)
            if arrays:
                return max(arrays, key=len)
            for v in data.values():
                if isinstance(v, list):
                    return v
    except json.JSONDecodeError:
        pass

    # 2. 提取文本中的 [...] 片段（多次尝试，取能解析的最长片段）
    for m in re.finditer(r"\[", text):
        start = m.start()
        depth, i, in_str = 0, start, None
        escape = False
        while i < len(text):
            c = text[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == in_str:
                    in_str = None
                i += 1
                continue
            if c in ('"', "'"):
                in_str = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[start : i + 1])
                        if isinstance(data, list):
                            return data
                    except json.JSONDecodeError:
                        pass
                    break
            i += 1

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

    logger.warning("LLM 返回内容无法解析为 JSON")
    print("\n" + "=" * 80 + "\n[question_extractor] LLM 返回无法解析\n" + "=" * 80)
    print("\n--- LLM 返回（完整）---\n")
    print(text)
    if user_prompt_for_debug:
        print("\n--- 对应的提问（用户消息，不含系统提示词）---\n")
        print(user_prompt_for_debug)
    print("\n" + "=" * 80 + "\n")
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
        few_shot=EXTRACT_FEW_SHOT,
    )

    raw = _call_llm(user_prompt)
    items = _parse_json_from_llm(raw, user_prompt_for_debug=user_prompt)

    if not items:
        logger.warning(f"LLM 未提取到题目: {source_url}")
        if raw:
            logger.info(f"LLM 原始返回（前500字）: {raw[:500]}")
        # 规则兜底：从正文中抽取明显的问题表述
        items = _fallback_extract_questions(truncated, company, position, platform, source_url)
    if not items:
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


def _fallback_extract_questions(
    content: str,
    company: str,
    position: str,
    platform: str,
    source_url: str,
) -> List[Dict]:
    """
    规则兜底：当 LLM 未返回有效结果时，用正则从正文中抽取明显的问题表述。
    """
    if not content or len(content) < 30:
        return []
    questions = []
    seen = set()

    # 模式：问了xxx、问xxx、xxx怎么、手写xxx、介绍一下、深挖xxx、实现xxx
    patterns = [
        r"问了[：:]?\s*([^。，！？\n]+)",
        r"问[了过]?\s*([^。，！？\n]{4,50})",
        r"([^。，\n]{4,40})(?:怎么|如何|是什么|有哪些|原理)",
        r"手写[：:]?\s*([^。，！？\n]{2,30})",
        r"手撕[：:]?\s*([^。，！？\n]{2,30})",
        r"(?:介绍|讲讲|说说)\s*([^。，！？\n]{4,40})",
        r"深挖[：:]?\s*([^。，！？\n]{4,40})",
        r"实现[：:]?\s*([^。，！？\n]{4,40})",
    ]
    for pat in patterns:
        for m in re.finditer(pat, content):
            q = m.group(1).strip()
            q = re.sub(r"^(了|的|一下|细节)\s*", "", q)
            if len(q) >= 4 and len(q) <= 80 and q not in seen:
                seen.add(q)
                questions.append({
                    "question_text": q,
                    "answer_text": "",
                    "difficulty": "medium",
                    "question_type": "技术题",
                    "topic_tags": [],
                })
    if questions:
        logger.info(f"规则兜底提取到 {len(questions)} 道题目: {source_url[:60]}")
    return questions


def _normalize_difficulty(d: str) -> str:
    d = d.lower().strip()
    if d in ("hard", "困难", "高", "困难/拷打"):
        return "hard"
    if d in ("easy", "简单", "低", "简单/常规"):
        return "easy"
    return "medium"
