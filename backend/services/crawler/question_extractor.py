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
from backend.utils.time_utils import now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 日志：精简原始（不存完整 prompt/few-shot）、输出截断、JSONL 格式

# Miner Service配置打印标志（只打印一次）
_miner_config_printed = False

def _print_miner_config_once():
    """首次调用时打印Miner Service配置"""
    global _miner_config_printed
    if _miner_config_printed:
        return
    _miner_config_printed = True
    
    try:
        from backend.config.config import settings
        logger.info("=" * 60)
        logger.info("✅ Miner Service (题目提取) 初始化完成")
        logger.info("=" * 60)
        logger.info(f"   - Mode: {settings.miner_mode}")
        logger.info(f"   - Model: {settings.miner_model}")
        logger.info(f"   - Provider: {settings.miner_provider}")
        logger.info(f"   - Base URL: {settings.miner_base_url}")
        logger.info(f"   - Temperature: {settings.miner_temperature}")
        logger.info(f"   - Max Tokens: {settings.miner_max_tokens}")
        logger.info(f"   - Max Retries: {settings.miner_max_retries}")
        logger.info(f"   - Timeout: {settings.miner_timeout}s")
        logger.info("=" * 60)
    except Exception as e:
        logger.warning(f"无法打印Miner Service配置: {e}")
_MAX_LOG_INPUT_PREVIEW = 1200   # 原始内容预览最大字符
_MAX_LOG_OUTPUT = 3000         # 输出最大字符
_OCR_PLACEHOLDER = "[OCR 省略]"  # 替换大段 OCR 噪音

# 每次提取最大字符数（避免超 token）
MAX_CONTENT_CHARS = 6000

# 重新提取所有时使用的时间戳后缀，写入独立文件；None 则用默认路径
_llm_log_run_suffix: Optional[str] = None

EXTRACT_SYSTEM_PROMPT = """你是面经提取专家，从面经原文中提取所有面试题，输出 JSON 数组。

**重要：所有回答必须使用中文！题目、答案、分类等所有字段内容都必须用中文表达。**

## 提取规则
1. 只提取原文中的题目，不编造
2. 口语化题目改写为标准问题（如「聊了Redis」→「请介绍Redis的应用场景」）
3. 从叙述中提取答案片段（如「我说了RDB和AOF」→ answer_text填"RDB、AOF"）
4. 无答案的开放题可给出参考答案

## 题目识别
- 编号：1. 2. ① ② 一、二、
- 关键词：「问了」「手写」「手撕」「聊了」「介绍」
- 分号分隔：「问了RAG；CoT是什么」→ 2道题

## 过滤无效内容
- 过渡语：「然后」「接下来」「还有」
- 情绪：「好难」「麻了」「凉了」
- 流程：「面试官很和善」「共XX分钟」
- 少于8字且无技术词汇

## question_type分类
算法类：DP编程题、回溯编程题、贪心编程题、图算法题、树算法题、链表题、数组题、其他算法题
AI/ML：LLM原理题、LLM算法题、模型结构题、模型训练题、RAG题、Agent题、CV题、NLP题
工程类：系统设计题、数据库题、缓存题、消息队列题、微服务题、性能优化题、并发编程题
基础类：操作系统题、计算机网络题、数据结构题、编程语言题
软技能：项目经验题、行为题、HR题

## 输出格式
直接输出JSON数组，不加markdown代码块。**所有字段内容必须用中文。**
格式：[{"question_text":"题目（中文）","answer_text":"答案（中文）","difficulty":"easy/medium/hard","question_type":"分类","topic_tags":["标签"],"company":"","position":""}]

特殊情况：
- 完全无关帖子（广告/吐槽）：{"reason":"帖子与面经无关"}
- 无题目但相关：[]（空数组，不要返回空对象{}）"""


EXTRACT_PROMPT_TEMPLATE = """## 面经原文
{content}

## 任务
从上面原文提取所有面试题，输出JSON数组。

**重要信息**：
- 公司：{company}
- 岗位：{position}

**要求**：
1. 每道题目的company字段必须填写：{company}
2. 每道题目的position字段必须填写：{position}
3. 如果原文中提到其他公司或岗位，以原文为准
4. 所有内容必须用中文"""


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
    model_name = (settings.miner_model or "unknown").replace(":", "_").replace(" ", "_")
    date_str = now_beijing_str("%Y%m%d")
    log_dir = _PROJECT_ROOT / "微调" / "llm_logs" / model_name
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{source}_{date_str}.jsonl"


def _append_llm_log_to_csv(user_prompt: str, llm_response: str, response_time_sec: float = None,
                            source: str = "nowcoder", title: str = "", source_url: str = "") -> None:
    """
    将 LLM 交互写入两个位置：
    1. 旧路径（LLM_PROMPT_LOG_CSV）—— 兼容现有调试查看
    2. 微调日志（微调/llm_logs/模型/来源_日期.jsonl）—— 只存 content + llm_raw + ts
    """
    content = _extract_content_for_log(user_prompt)
    llm_raw = (llm_response or "")

    # ── 1. 旧路径（调试用，使用模型名子目录）──
    try:
        from backend.config.config import settings
        path = settings.llm_prompt_log_csv
        if path:
            p = Path(path)
            # 使用模型名子目录
            _PROJECT_ROOT = Path(__file__).resolve().parents[3]
            model_name = (settings.miner_model or "unknown").replace(":", "_").replace(" ", "_")
            log_dir = _PROJECT_ROOT / "微调" / "llm_logs" / model_name
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取原始文件名
            if str(p).lower().endswith(".csv"):
                filename = p.stem + ".jsonl"
            else:
                filename = p.name
            
            if _llm_log_run_suffix:
                filename = f"{Path(filename).stem}_{_llm_log_run_suffix}{Path(filename).suffix}"
            
            p = log_dir / filename
            
            record = {
                "原始": content[:_MAX_LOG_INPUT_PREVIEW],
                "输出": llm_raw[:_MAX_LOG_OUTPUT],
                "操作时间": round(response_time_sec, 2) if response_time_sec is not None else None,
            }
            with open(p, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("LLM 调试日志写入失败: %s", e)

    # ── 2. 微调日志（按模型+来源+日期分文件，包含完整 system prompt）──
    try:
        from backend.config.config import settings
        ft_path = _get_finetune_log_path(source)
        ft_record = {
            "ts": now_beijing_str(),
            "model": settings.miner_model or "unknown",
            "source": source,
            "title": title[:100] if title else "",
            "source_url": source_url,
            "system_prompt": get_miner_prompt(),  # 完整的 system prompt（不含标题和正文）
            "user_content": content,  # 提取的原始内容
            "llm_response": llm_raw,
            "response_time_sec": round(response_time_sec, 2) if response_time_sec is not None else None,
        }
        with open(ft_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(ft_record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("微调日志写入失败: %s", e)


# 模块级复用 MinerAgent（LLM 客户端只初始化一次）
_shared_miner_agent = None


def _get_miner_agent(image_paths: List[str] = None, task_id: str = ""):
    """获取或创建 MinerAgent 实例。
    注意：由于改用框架托管，每次都需要创建新实例（工具状态绑定在实例上）。
    """
    from backend.agents.miner_agent import MinerAgent
    # 框架托管版本：每次创建新实例（工具注册时已绑定 image_paths）
    return MinerAgent(image_paths=image_paths or [], task_id=task_id or "")


def _call_llm_with_agent(content: str, has_image: bool, company: str = "", position: str = "", 
                         image_paths: List[str] = None, task_id: str = "") -> Tuple[str, bool, bool]:
    """
    使用 MinerAgent（框架托管版）提取题目。
    LLM 自主通过工具调用决策：
    - 正文有题目 → 调用 Finish 返回 JSON
    - 正文无题但有图片 → 调用 ocr_images → 再调用 Finish
    - 正文+图片均无题 → 调用 mark_unrelated → 返回 UNRELATED_SIGNAL

    Returns:
        (result, ocr_called, is_unrelated)
    """
    from backend.agents.miner_agent import UNRELATED_SIGNAL
    try:
        agent = _get_miner_agent(image_paths=image_paths, task_id=task_id)
        result, ocr_called, is_unrelated = agent.run(
            content=content,
            has_image=has_image,
            company=company,
            position=position
        )
        logger.info(f"[MinerAgent] 执行完成，输出长度: {len(result)}, ocr_called={ocr_called}, is_unrelated={is_unrelated}")
        return result, ocr_called, is_unrelated
    except Exception as e:
        logger.warning(f"[MinerAgent] 执行失败，降级为直接 LLM 调用: {e}")
        # 降级：手动 OCR + 直接调用 LLM
        ocr_text = ""
        if image_paths:
            try:
                from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
                ocr_text = ocr_images_to_text(image_paths, task_id) or ""
            except Exception as ocr_e:
                logger.warning(f"[OCR] 降级 OCR 也失败: {ocr_e}")
        
        # 使用 format_miner_user_prompt 格式化输入
        from backend.agents.prompts.miner_prompt import format_miner_user_prompt
        user_prompt = format_miner_user_prompt(content, has_image, company, position)
        if ocr_text:
            user_prompt += f"\n\n## 图片OCR识别内容\n{ocr_text}"
        
        return _call_llm_direct(user_prompt), bool(ocr_text), False


def _call_llm_direct(user_prompt: str) -> Optional[str]:
    """直接调用 LLM API（不走 Agent，作为降级方案）。使用 Miner 专属配置。"""
    try:
        from openai import OpenAI
        from backend.config.config import settings
        timeout = settings.miner_timeout or 180
        model = settings.miner_model
        if not model:
            logger.error("Miner 模型未配置（miner_model 为空），请检查 .env 中 MINER_LOCAL_MODEL 或 MINER_REMOTE_MODEL")
            return None
        client = OpenAI(
            api_key=settings.miner_api_key,
            base_url=settings.miner_base_url,
            timeout=timeout,
        )
        messages = [
            {"role": "system", "content": get_miner_prompt()},
            {"role": "user",   "content": user_prompt},
        ]
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=settings.miner_temperature,
            timeout=timeout,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM 直接调用失败: {e}")
        return None


def _call_llm(user_prompt: str) -> Optional[str]:
    """调用 LLM API，system+user 双消息，强制 JSON 输出。使用 Miner 专属配置。"""
    return _call_llm_direct(user_prompt)


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
    # 去掉 deepseek-r1 的 <think>...</think> 推理块（Ollama 本地部署时混在 content 里）
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE).strip()
    # 去掉 qwen3 等模型的 <function-call>...</function-call> 包裹，提取内部 JSON
    _fc = re.search(r"<function-call>([\s\S]*?)</function-call>", text, flags=re.IGNORECASE)
    if _fc:
        try:
            _fc_data = json.loads(_fc.group(1).strip())
            if isinstance(_fc_data, dict) and _fc_data.get("name") == "Finish":
                text = _fc_data.get("arguments", {}).get("answer", "") or ""
            elif isinstance(_fc_data, dict) and "answer" in _fc_data:
                text = _fc_data["answer"]
        except (json.JSONDecodeError, AttributeError):
            text = _fc.group(1).strip()

    # 0a. 检测 NO_RELATED_CONTENT 特殊标识（prompt 要求模型在完全无关时输出此值，不应重试）
    if text.strip() == "NO_RELATED_CONTENT":
        logger.info("LLM 明确返回 NO_RELATED_CONTENT，帖子与面经无关")
        return [], "unrelated"

    # 0b. 检测「帖子与面经无关」或空对象，或 LLM 把原文包裹进对象返回
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("reason") == "帖子与面经无关":
                return [], "unrelated"
            # 处理空对象 {} 的情况（LLM有时返回空对象表示无题目）
            if not data:
                logger.warning("⚠️ LLM 返回空对象 {}，判定为无题目（应返回空数组[]）")
                return [], "empty"
            # LLM 有时把输入原文包裹返回，如 {"面经原文": "..."}，这不是题目列表
            if set(data.keys()) <= {"面经原文", "title", "正文", "content", "原文", "text"}:
                logger.warning(f"⚠️ LLM 返回原文包裹对象（keys={list(data.keys())}），判定为无题目")
                return [], "empty"
    except json.JSONDecodeError:
        pass

    # 1. 直接解析整个文本
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return (data, "ok") if data else ([], "empty")
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
        from backend.services.logging.llm_parse_failures import save_failure
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
    image_paths: List[str] = None,
    task_id: str = "",
) -> Tuple[List[Dict], str, bool]:
    """
    从面经原文中用 LLM 提取结构化题目列表。

    content 过长时自动截断（6000 字符，约 3000 token）。
    返回 (questions, status, agent_used_tool)，status 为 ok/unrelated/empty/parse_error。
    agent_used_tool: MinerAgent 是否调用了 ocr_images 工具（True=是，False=否）。

    若正文无题目且有图片，MinerAgent 会自主调用 ocr_images 工具获取图片内容后再提取。
    """
    _print_miner_config_once()
    
    # 只检查是否完全为空（不检查长度）
    if not content and not image_paths:
        logger.warning(f"内容和图片均为空，跳过提取: {source_url}")
        return [], "empty", False

    # 截断过长内容
    truncated = content[:MAX_CONTENT_CHARS] if content else ""
    if content and len(content) > MAX_CONTENT_CHARS:
        logger.info(f"内容截断: {len(content)} → {MAX_CONTENT_CHARS} chars")

    # 拼接标题和内容
    full_content = f"【标题】{post_title}\n\n【正文】\n{truncated}" if post_title else truncated

    # 使用新的 Prompt 系统
    user_prompt = format_miner_user_prompt(full_content, has_image=bool(image_paths), company=company, position=position)

    from backend.config.config import settings
    max_retries = settings.miner_max_retries

    # 正文提取（带重试）
    # 统一走 MinerAgent（框架托管版）：LLM 自主判断是否调用 ocr_images 工具
    # - 正文有题目 → LLM 直接调用 Finish 返回 JSON
    # - 正文无题目但有图片 → LLM 自主调用 ocr_images → 再调用 Finish 返回 JSON
    items, status = [], "empty"
    agent_used_tool: bool = False
    from backend.agents.miner_agent import UNRELATED_SIGNAL
    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        raw, ocr_called, is_unrelated = _call_llm_with_agent(
            content=full_content,
            has_image=bool(image_paths),
            company=company,
            position=position,
            image_paths=image_paths,
            task_id=task_id
        )
        llm_response_time_sec = time.perf_counter() - t0
        if ocr_called:
            agent_used_tool = True

        # LLM 主动调用 mark_unrelated 工具 → 直接标记无关，不再解析 JSON
        if is_unrelated or raw == UNRELATED_SIGNAL:
            logger.info(f"LLM 主动标记帖子无关（mark_unrelated）: {source_url}")
            _append_llm_log_to_csv(user_prompt, "[mark_unrelated]", llm_response_time_sec,
                                   source=platform, title=post_title, source_url=source_url)
            return [], "unrelated", agent_used_tool

        items, status = _parse_json_from_llm(raw, user_prompt_for_debug=user_prompt)

        _append_llm_log_to_csv(user_prompt, raw or "", llm_response_time_sec, source=platform,
                               title=post_title, source_url=source_url)

        if status == "unrelated":
            logger.info(f"LLM 判定帖子与面经无关: {source_url}")
            return [], "unrelated", agent_used_tool

        if status == "ok" and items:
            if attempt > 1:
                logger.info(f"重试成功（第 {attempt} 次）: 提取到 {len(items)} 道题目")
            break

        if attempt < max_retries:
            logger.warning(f"提取失败（第 {attempt} 次，状态: {status}），{max_retries - attempt} 次重试机会剩余")
            time.sleep(1)
        else:
            logger.warning(f"提取失败，已达最大重试次数 {max_retries}: {source_url}")
            if raw:
                logger.info(f"LLM 原始返回（前500字）: {raw[:500]}")

    if not items:
        logger.warning(f"LLM 未提取到题目: {source_url}")
        return [], status, agent_used_tool

    questions: List[Dict] = []
    for item in items:
        logger.debug(f"处理 item: {type(item)}")
        if not isinstance(item, dict):
            logger.debug(f"跳过非字典项: {type(item)}")
            continue
        
        # 兼容多种字段名：question_text / question
        q_text = str(item.get("question_text") or item.get("question", "")).strip()
        
        # 放宽过滤条件：只过滤完全为空的题目
        if not q_text:
            logger.warning(f"题目为空被过滤")
            continue

        tags_raw = item.get("topic_tags") or item.get("tags", [])
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
        
        # 生成唯一的 q_id（UUID）
        import uuid
        q_id = str(uuid.uuid4())
        
        # 兼容多种字段名：answer_text / answer, question_type / type
        questions.append({
            "q_id": q_id,  # 添加 q_id 字段
            "question_text": q_text,
            "answer_text": str(item.get("answer_text") or item.get("answer", "")).strip(),
            "difficulty": difficulty_val,
            "question_type": str(item.get("question_type") or item.get("type", "技术题")),
            "topic_tags": json.dumps(tags_raw, ensure_ascii=False),
            "company": final_company,
            "position": final_position,
            "business_line": business_line or "",
            "source_platform": platform,
            "source_url": source_url,
            "extraction_source": extraction_source,
        })

    # 只在成功提取到题目时输出日志
    if questions:
        logger.info(f"✅ 提取成功: {len(questions)} 道题目 | {post_title[:30] or source_url}")
    return questions, "ok", agent_used_tool



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
            api_key=settings.miner_api_key,
            base_url=settings.miner_base_url,
            timeout=settings.miner_timeout or 180,
        )
        resp = client.chat.completions.create(
            model=settings.miner_model,
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




