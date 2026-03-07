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
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 日志：精简原始（不存完整 prompt/few-shot）、输出截断、JSONL 格式
_MAX_LOG_INPUT_PREVIEW = 1200   # 原始内容预览最大字符
_MAX_LOG_OUTPUT = 3000         # 输出最大字符
_OCR_PLACEHOLDER = "[OCR 省略]"  # 替换大段 OCR 噪音

# 每次提取最大字符数（避免超 token）
MAX_CONTENT_CHARS = 6000

# 重新提取所有时使用的时间戳后缀，写入独立文件；None 则用默认路径
_llm_log_run_suffix: Optional[str] = None

EXTRACT_SYSTEM_PROMPT = """你是面经结构化专家，从面经原文中精准提取所有面试题，输出严格的 JSON 数组。

## 核心规则
- 必须且仅从「面经原文」中提取，不编造、不输出原文不存在的题目
- 从叙述句中挖掘题目（如「问了 RAG 原理」→ 提取为「请介绍 RAG 的原理」）
- 从叙述句中提取答案片段（如「我说了 RDB 和 AOF」→ answer_text 填 "RDB、AOF"）
- 开放性问题若原文无答案，可基于知识给出实质性参考答案

## 题目边界识别
以下形式均表示独立面试题，必须逐条提取：
- **编号**：1. 2. ① ② 一、二、（1）（2）等
- **换行**：每行描述一个独立知识点或问题时，单独提取
- **分号**：「；」或「;」连接的多个问题，逐个拆分（如「问了 RAG；CoT 是什么；聊了 LoRA」→ 3 道题）
- **关键词**：「问了」「手写」「手撕」「聊了」「介绍一下」后跟的内容

## 无效内容过滤（一律不提取）
- 纯过渡语：「然后」「接下来」「还有」「另外」「问了一些」「聊了会儿」
- 情绪感叹：「好难啊」「麻了」「凉了」「还不错」「没答上来」
- 流程描述：「整体难度...」「面试官很和善」「共面了 XX 分钟」
- 少于 8 字且不含技术词汇的片段
- 不能独立作答的半截句子或上下文过渡

## answer_text 格式
分条列点，每条「1. 」「2. 」开头，换行分隔。示例：1. RDB 快照\\n2. AOF 日志追加

## 输出格式
- 仅输出 JSON，不加 markdown 代码块或任何解释
- 完全无关帖子（纯吐槽/广告）输出 {\"reason\":\"帖子与面经无关\"}
- 有题目时输出数组，无题目但内容相关时输出 []
- question_type 只能是：技术题 / 算法题 / 行为题 / 系统设计 / HR问题
- topic_tags：从题目中抽取 2～6 个具体技术标签，不要空数组
- company / position / difficulty：原文明确提及才填，否则填空字符串"""

EXTRACT_FORMAT_HINT = """
## JSON 格式提示
数组元素：{{"question_text":"题目","answer_text":"答案或空","difficulty":"easy/medium/hard或空","question_type":"技术题/算法题/行为题/系统设计/HR问题","topic_tags":["标签"],"company":"","position":""}}"""

EXTRACT_PROMPT_TEMPLATE = """## 帖子信息
- 平台：{platform}
- 公司：{company}
- 岗位：{position}
- 难度：{difficulty}

## 面经原文（必须且仅从此处提取）
{content}

## 任务
请从上面的「面经原文」中提取所有面试题，输出 JSON 数组。只输出原文中实际出现的题目。{format_hint}
"""


def _extract_content_for_log(user_prompt: str) -> str:
    """从 user_prompt 中提取「面经原文」部分，用于日志。不含系统提示词、不含模板、不含 few-shot。"""
    if not user_prompt:
        return ""
    # 匹配 ## 面经原文（...）\n 或 ## 面经原文\n 后的内容，直到 ## 任务
    m = re.search(r"## 面经原文[^\n]*\n(.*?)(?=\n## 任务|\Z)", user_prompt, re.DOTALL)
    content = (m.group(1).strip() if m else user_prompt)
    # 替换 [图片N OCR结果] 及后续大段 OCR 噪音为占位符
    content = re.sub(r"\[图片\d+ OCR结果\][^\[]*", _OCR_PLACEHOLDER + "\n", content)
    if len(content) > _MAX_LOG_INPUT_PREVIEW:
        content = content[:_MAX_LOG_INPUT_PREVIEW] + "...[截断]"
    return content


def _get_finetune_log_path(source: str = "nowcoder") -> Path:
    """
    返回微调日志写入路径：微调/llm_logs/{模型名}/{来源}_{日期}.jsonl
    模型名中 : 和空格替换为 _，避免文件系统问题。
    """
    from backend.config.config import settings
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
    model_name = (settings.llm_model_id or "unknown").replace(":", "_").replace(" ", "_")
    date_str = datetime.now().strftime("%Y%m%d")
    log_dir = _PROJECT_ROOT / "微调" / "llm_logs" / model_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{source}_{date_str}.jsonl"


def _append_llm_log_to_csv(user_prompt: str, llm_response: str, response_time_sec: float = None,
                            source: str = "nowcoder") -> None:
    """
    将 LLM 交互写入两个位置：
    1. 旧路径（LLM_PROMPT_LOG_CSV）—— 兼容现有调试查看
    2. 微调日志（微调/llm_logs/模型/来源_日期.jsonl）—— 只存 content + llm_raw + ts
    """
    content = _extract_content_for_log(user_prompt)
    llm_raw = (llm_response or "")

    # ── 1. 旧路径（调试用，保持不变）──
    try:
        from backend.config.config import settings
        path = settings.llm_prompt_log_csv
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if str(p).lower().endswith(".csv"):
                p = p.with_suffix(".jsonl")
            if _llm_log_run_suffix:
                p = p.parent / f"{p.stem}_{_llm_log_run_suffix}{p.suffix}"
            record = {
                "原始": content[:_MAX_LOG_INPUT_PREVIEW],
                "输出": llm_raw[:_MAX_LOG_OUTPUT],
                "操作时间": round(response_time_sec, 2) if response_time_sec is not None else None,
            }
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("LLM 调试日志写入失败: %s", e)

    # ── 2. 微调日志（按模型+来源+日期分文件）──
    try:
        ft_path = _get_finetune_log_path(source)
        ft_record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "content": content,
            "llm_raw": llm_raw,
        }
        with open(ft_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(ft_record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("微调日志写入失败: %s", e)


def _call_llm(user_prompt: str) -> Optional[str]:
    """调用 LLM API，system+user 双消息，强制 JSON 输出。超时 3 分钟。"""
    try:
        from openai import OpenAI
        from backend.config.config import settings
        timeout = settings.llm_timeout or 180
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
        temp = settings.extractor_temperature
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model_id,
                messages=messages,
                temperature=temp,
                timeout=timeout,
                response_format={"type": "json_object"},
            )
        except Exception:
            # 不支持 json_object 时回退到普通调用
            resp = client.chat.completions.create(
                model=settings.llm_model_id,
                messages=messages,
                temperature=temp,
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


def _parse_json_from_llm(text: str, user_prompt_for_debug: str = None) -> Tuple[List[Dict], str]:
    """从 LLM 输出中提取 JSON 数组，兼容多种返回格式。返回 (items, status)，status 为 ok/unrelated/empty/parse_error"""
    if not text:
        return [], "empty"
    # 去掉 markdown 代码块（```json ... ``` 或 ``` ... ```）
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

    # 0. 检测「帖子与面经无关」
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("reason") == "帖子与面经无关":
            return [], "unrelated"
    except json.JSONDecodeError:
        pass

    # 1. 直接解析整个文本
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data, "ok" if data else "empty"
        if isinstance(data, dict):
            # 常见顶层 key 或嵌套 job.project_detail
            for key in ("questions", "items", "results", "data", "list", "output"):
                if key in data and isinstance(data[key], list):
                    arr = data[key]
                    if arr and isinstance(arr[0], dict) and "question_text" in arr[0]:
                        return arr, "ok"
            if "job" in data and isinstance(data["job"], dict):
                for sub in ("project_detail", "questions", "interview_questions", "items"):
                    arr = data["job"].get(sub)
                    if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "question_text" in arr[0]:
                        return arr, "ok"
            if "question" in data and isinstance(data["question"], str):
                return [{"question_text": data["question"], "answer_text": "", "difficulty": "",
                         "question_type": "技术题", "topic_tags": [], "company": "", "position": ""}], "ok"
            # 递归查找嵌套数组（如 job.project_detail）
            arrays = _dig_question_arrays(data)
            if arrays:
                return max(arrays, key=len), "ok"
            # 兜底：LLM 返回 {"题目1": {...}, "题目2": [...]} 格式，转为 [{question_text, ...}]
            items = []
            for k, v in data.items():
                if not isinstance(k, str) or len(k.strip()) < 3 or k in ("reason", "job"):
                    continue
                if isinstance(v, list):
                    for x in v:
                        if isinstance(x, dict) and (x.get("question_text") or k):
                            items.append({
                                "question_text": str(x.get("question_text", k)).strip(),
                                "answer_text": str(x.get("answer_text", "")).strip(),
                                "difficulty": str(x.get("difficulty", "")).strip(),
                                "question_type": str(x.get("question_type", "技术题")).strip() or "技术题",
                                "topic_tags": x.get("topic_tags") if isinstance(x.get("topic_tags"), list) else [],
                                "company": str(x.get("company", "")).strip(),
                                "position": str(x.get("position", "")).strip(),
                            })
                elif isinstance(v, dict):
                    q_text = str(v.get("question_text", k)).strip() or k.strip()
                    items.append({
                        "question_text": q_text,
                        "answer_text": str(v.get("answer_text", "")).strip(),
                        "difficulty": str(v.get("difficulty", "")).strip(),
                        "question_type": str(v.get("question_type", "技术题")).strip() or "技术题",
                        "topic_tags": v.get("topic_tags") if isinstance(v.get("topic_tags"), list) else [],
                        "company": str(v.get("company", "")).strip(),
                        "position": str(v.get("position", "")).strip(),
                    })
            if items:
                return items, "ok"
            for v in data.values():
                if isinstance(v, list):
                    return v, "ok"
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
                            return data, "ok"
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
        return results, "ok"

    logger.error("LLM 返回内容无法解析为 JSON 数组，提取失败（已入库 status=error）")
    try:
        from backend.services.llm_parse_failures import save_failure
        save_failure(
            source="question_extract",
            input_preview=user_prompt_for_debug or "",
            raw_output=text,
            error="无法解析为 JSON 数组",
            metadata={"text_len": len(text) if text else 0},
        )
    except Exception as e:
        logger.debug(f"保存解析失败记录异常: {e}")
    logger.error(f"[提取失败] LLM 返回无法解析，source_url 见上方输入 | 原始返回前500字: {(text or '')[:500]}")
    logger.debug("LLM 返回（完整）: %s", text)
    if user_prompt_for_debug:
        logger.debug("对应的提问（用户消息，不含系统提示词）: %s", user_prompt_for_debug[:1500])
    return [], "parse_error"


def extract_questions_from_post(
    content: str,
    platform: str = "nowcoder",
    company: str = "",
    position: str = "",
    business_line: str = "",
    difficulty: str = "",
    source_url: str = "",
    post_title: str = "",
    extraction_source: str = "content",
) -> Tuple[List[Dict], str]:
    """
    从面经原文中用 LLM 提取结构化题目列表。

    content 过长时自动截断（6000 字符，约 3000 token）。
    返回 (questions, status)，status 为 ok/unrelated/empty。
    """
    if not content or len(content.strip()) < 50:
        logger.warning(f"内容过短，跳过提取: {source_url}")
        return [], "empty"

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
        format_hint=EXTRACT_FORMAT_HINT,
    )

    t0 = time.perf_counter()
    raw = _call_llm(user_prompt)
    llm_response_time_sec = time.perf_counter() - t0

    items, status = _parse_json_from_llm(raw, user_prompt_for_debug=user_prompt)

    _append_llm_log_to_csv(user_prompt, raw or "", llm_response_time_sec, source=platform)

    if status == "unrelated":
        logger.info(f"LLM 判定帖子与面经无关: {source_url}")
        return [], "unrelated"

    if not items:
        logger.warning(f"LLM 未提取到题目: {source_url}")
        if raw:
            logger.info(f"LLM 原始返回（前500字）: {raw[:500]}")
        return [], "empty"

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

        # 公司/岗位/难度：LLM 不确定时填空，不猜测；优先用 LLM 输出，其次用帖子元数据；"未知" 视为空
        item_company = str(item.get("company", "")).strip()
        post_company = (company or "").strip() if (company or "").strip() != "未知" else ""
        final_company = item_company or post_company or ""
        item_position = str(item.get("position", "")).strip()
        post_position = (position or "").strip() if (position or "").strip() != "未知" else ""
        final_position = item_position or post_position or ""
        item_difficulty = str(item.get("difficulty", "")).strip()
        difficulty_val = _normalize_difficulty(item_difficulty) if item_difficulty else ""
        questions.append({
            "q_id": f"Q-{uuid.uuid4().hex[:10].upper()}",
            "question_text": q_text,
            "answer_text": str(item.get("answer_text", "")).strip(),
            "difficulty": difficulty_val,
            "question_type": str(item.get("question_type", "技术题")),
            "topic_tags": json.dumps(tags_raw, ensure_ascii=False),
            "company": final_company,
            "position": final_position,
            "business_line": business_line or "",
            "source_platform": platform,
            "source_url": source_url,
            "extraction_source": extraction_source,
        })

    logger.info(f"从帖子提取到 {len(questions)} 道题目: {post_title[:30] or source_url}")
    return questions, "ok"



def _normalize_difficulty(d: str) -> str:
    """将难度归一化，空或不确定时返回空字符串"""
    d = (d or "").strip()
    if not d or d.lower() in ("不确定", "unknown", "?"):
        return ""
    d = d.lower()
    if d in ("hard", "困难", "高", "困难/拷打"):
        return "hard"
    if d in ("easy", "简单", "低", "简单/常规"):
        return "easy"
    if d in ("medium", "适中", "中", "中等"):
        return "medium"
    return ""


# ══════════════════════════════════════════════════════════════
# 清洗数据：批量判断内容是否与面经相关
# ══════════════════════════════════════════════════════════════

CLEAN_CHECK_PROMPT = """你负责判断内容是否与「面经」（技术面试、求职经验、八股、算法题、行为面、HR 面等）相关。

下面有 {n} 段内容，请逐段判断。仅输出一个 JSON 数组，如 [true, false, true]，按顺序对应每段。
- true：与面经相关（含面试题、面经分享、求职经验、技术讨论等）
- false：与面经无关（纯吐槽、广告、生活、无关话题等）

## 内容列表
{contents}

## 输出
仅输出 JSON 数组，不要任何解释。"""


def check_contents_related_batch(contents: List[str], max_chars_per_item: int = 800) -> List[bool]:
    """
    批量判断多段内容是否与面经相关。返回 [True, False, ...] 与 contents 一一对应。
    单段内容过长时截断以节省 token。
    """
    if not contents:
        return []
    from backend.config.config import settings
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai 未安装，清洗功能不可用")
        return [True] * len(contents)  # 无法判断时默认保留

    parts = []
    for i, c in enumerate(contents):
        s = (c or "").strip()[:max_chars_per_item]
        if len(s) < 20:
            parts.append(f"[{i+1}] （内容过短）")
        else:
            parts.append(f"[{i+1}]\n{s}")

    body = "\n\n---\n\n".join(parts)
    user_prompt = CLEAN_CHECK_PROMPT.format(n=len(contents), contents=body)

    raw = ""
    llm_response_time_sec = None
    t0 = time.perf_counter()
    try:
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout or 180,
        )
        resp = client.chat.completions.create(
            model=settings.llm_model_id,
            messages=[
                {"role": "system", "content": "你输出严格的 JSON 数组，如 [true, false, true]。"},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        llm_response_time_sec = time.perf_counter() - t0
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        if isinstance(data, list) and len(data) == len(contents):
            _append_llm_log_to_csv(user_prompt, raw, llm_response_time_sec)
            return [bool(x) for x in data]
        logger.warning(f"LLM 返回格式异常，长度不匹配: {len(data)} vs {len(contents)}")
        _append_llm_log_to_csv(user_prompt, raw, llm_response_time_sec)
        return [True] * len(contents)
    except Exception as e:
        logger.error(f"清洗判断 LLM 调用失败: {e}")
        llm_response_time_sec = time.perf_counter() - t0
        _append_llm_log_to_csv(user_prompt, raw if raw else str(e), llm_response_time_sec)
        return [True] * len(contents)
