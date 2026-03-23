"""
面经内容 → 独立题目 提取器（LLM 驱动）

输入：一篇面经原文（可能包含 10~30 道面试题混在叙述文字中）
输出：结构化的题目列表，每条含：
  - question_text    题目正文
  - answer_text      参考答案（从面经中提取，无则留空）
  - difficulty       easy / medium / hard
  - question_type    小类名：算法-/工程-/基础-/软技能-/AI-*（与 miner_prompt 4b、miner_schema 一致）
  - topic_tags       技术标签列表（如 ["Redis", "Java", "JVM"]）
  - company          公司（继承自帖子元数据）
  - position         岗位
  - business_line    业务线
  - source_platform  来源平台
  - source_url       原帖链接
"""
from backend.utils.time_utils import now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
from backend.utils.question_text_cleanup import strip_question_enumeration
from backend.utils.text_garbled import (
    company_should_be_cleared,
    is_unusable_after_repair,
    is_unusable_answer_after_repair,
    repair_text,
)
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from backend.services.company_normalization import normalize_company_field

logger = logging.getLogger(__name__)


class MinerFatalApiError(RuntimeError):
    """Miner 上游 API 配置或参数错误，继续批处理无意义（子进程应非零退出）。"""


def _is_miner_fatal_upstream_error(raw: Optional[str]) -> bool:
    """判断是否为重试无法修复的上游错误（鉴权、参数超范围、模型不存在等）。"""
    if not raw or not isinstance(raw, str):
        return False
    if "Stage1 模型调用失败" not in raw and "模型调用失败" not in raw and "OpenAI Function Calling调用失败" not in raw:
        return False
    markers = (
        "InvalidParameter",
        "Range of max_tokens",
        "invalid_request_error",
        "invalid_api_key",
        "Incorrect API key",
        "insufficient_quota",
        "Model Not Exist",
        "model_not_found",
        # 仅免费额度/控制台「仅用免费档」等：重试同一账号无意义，应中止批处理并让子进程非零退出
        "Error code: 403",
        "AllocationQuota",
        "FreeTierOnly",
    )
    return any(m in raw for m in markers)


# 日志：精简原始（不存完整 prompt/few-shot）、输出截断、JSONL 格式

# Miner Service配置打印标志（只打印一次）
_miner_config_printed = False

# 供重试提示：乱码校验等写入，替代已移除的两阶段模块中的同名变量
_last_extraction_error: Optional[str] = None


def _print_miner_config_once():
    """首次调用时打印Miner Service配置"""
    global _miner_config_printed
    if _miner_config_printed:
        return
    _miner_config_printed = True
    
    try:
        from backend.config.config import settings
        logger.info("─" * 60)
        logger.info("✅ Miner Service (题目提取) 初始化完成")
        logger.info("─" * 60)
        logger.info(f"   - Mode: {settings.miner_mode}")
        logger.info(f"   - Model: {settings.miner_model}")
        logger.info(f"   - Provider: {settings.miner_provider}")
        logger.info(f"   - Base URL: {settings.miner_base_url}")
        if (settings.miner_mode or "").lower() == "two_stage":
            n1 = len(settings.miner_stage1_models or [])
            s2n = [m.get("model", "") for m in (settings.miner_stage2_models or [])]
            logger.info(f"   - Two-stage Stage1: {settings.miner_stage1_mode}, endpoints={n1}")
            logger.info(f"   - Two-stage Stage2 models: {s2n or '(未配置，仅 Stage1)'}")
        elif (settings.miner_mode or "").lower() == "remote":
            n_ep = len(settings.miner_remote_models or [])
            if n_ep > 1:
                logger.info(f"   - Remote fallback chain: {n_ep} 个端点（MINER_REMOTE + MINER_REMOTE_FALLBACK_MODELS）")
        logger.info(f"   - Temperature: {settings.miner_temperature}")
        logger.info(f"   - Max Tokens: {settings.miner_max_tokens}")
        logger.info(f"   - Max Retries: {settings.miner_max_retries}")
        logger.info(f"   - Timeout: {settings.miner_timeout}s")
        logger.info("─" * 60)
    except Exception as e:
        logger.warning(f"无法打印Miner Service配置: {e}")
_MAX_LOG_INPUT_PREVIEW = 1200   # 原始内容预览最大字符
_MAX_LOG_OUTPUT = 3000         # 输出最大字符
_OCR_PLACEHOLDER = "[OCR 省略]"  # 替换大段 OCR 噪音

# 每次提取最大字符数（避免超 token）
MAX_CONTENT_CHARS = 65535*2

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

## question_type（须填「小类」完整字符串，禁止算法类/工程类等大类）
与主线 Miner 一致：算法-动态规划、算法-回溯与搜索、工程-缓存与Redis、工程-系统设计与架构、基础-操作系统、软技能-行为与情景、AI-RAG与检索增强 等；完整清单见项目 miner_prompt §4b 与 backend.agents.schemas.miner_schema.ALLOWED_QUESTION_TYPES。

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
                "标题": title[:100] if title else "",
                "链接": source_url or "",
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
_latest_miner_agent = None
_latest_two_stage_extractor = None


def get_latest_miner_runtime_handles() -> Dict[str, object]:
    """返回最近一次实际执行过的 Miner/TwoStage 运行时句柄（用于诊断接口）。"""
    return {
        "miner_agent": _latest_miner_agent,
        "two_stage_extractor": _latest_two_stage_extractor,
    }


def _get_miner_agent(image_paths: List[str] = None, task_id: str = ""):
    """获取或创建 MinerAgent 实例（单阶段 ReAct + 工具调用）。"""
    from backend.agents.miner_agent import MinerAgent
    return MinerAgent(image_paths=image_paths or [], task_id=task_id or "")


def _call_llm_with_agent(content: str, has_image: bool, company: str = "", position: str = "", 
                         image_paths: List[str] = None, task_id: str = "",
                         retry_hint: str = None, source_url: str = "", post_title: str = "") -> Tuple[str, bool, bool]:
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
    from backend.config.config import settings as _settings_mode
    global _latest_miner_agent, _latest_two_stage_extractor

    _REFUSE_QUICK = [
        r"^抱歉[，]?我无法",
        r"^对不起[，]?我(不能|无法)",
        r"^I('m| am) (sorry|unable)",
        r"^Sorry[，]? I (can'?t|cannot|am unable)",
        r"^抱歉，我不能",
    ]
    try:
        if (_settings_mode.miner_mode or "").lower() == "two_stage":
            from backend.agents.two_stage_miner_agent import TwoStageExtractor

            ext = TwoStageExtractor(image_paths=image_paths or [], task_id=task_id or "")
            _latest_two_stage_extractor = ext
            if retry_hint:
                result, ocr_called, is_unrelated = ext.extract(
                    content=content,
                    has_image=has_image,
                    company=company,
                    position=position,
                    user_input_override=retry_hint,
                    source_url=source_url,
                    post_title=post_title,
                )
            else:
                result, ocr_called, is_unrelated = ext.extract(
                    content=content,
                    has_image=has_image,
                    company=company,
                    position=position,
                    source_url=source_url,
                    post_title=post_title,
                )
            logger.info(
                f"[TwoStageExtractor] 执行完成，输出长度: {len(result)}, ocr_called={ocr_called}, is_unrelated={is_unrelated}"
            )
        else:
            agent = _get_miner_agent(image_paths=image_paths, task_id=task_id)
            _latest_miner_agent = agent
            if retry_hint:
                result, ocr_called, is_unrelated = agent.run(
                    content=content,
                    has_image=has_image,
                    company=company,
                    position=position,
                    user_input_override=retry_hint,
                    source_url=source_url,
                    post_title=post_title,
                )
            else:
                result, ocr_called, is_unrelated = agent.run(
                    content=content,
                    has_image=has_image,
                    company=company,
                    position=position,
                    source_url=source_url,
                    post_title=post_title,
                )
            logger.info(
                f"[MinerAgent] 执行完成，输出长度: {len(result)}, ocr_called={ocr_called}, is_unrelated={is_unrelated}"
            )
        # Agent 成功返回，但 result 是拒绝文本时降级为直接 LLM 调用
        if result and not is_unrelated:
            _stripped = result.strip()
            # 检测拒绝文本
            if any(re.search(p, _stripped, re.IGNORECASE) for p in _REFUSE_QUICK):
                logger.warning(f"[MinerAgent] Agent 返回拒绝文本，降级为直接 LLM 调用: {_stripped[:60]}")
                raise ValueError("model_refused_fallback")
            # 检测非 JSON 输出（自然语言 / Markdown 格式）
            _lstripped = _stripped.lstrip()
            if not _lstripped.startswith('[') and not _lstripped.startswith('{'):
                logger.warning(f"[MinerAgent] 返回非 JSON 格式，触发降级: {_stripped[:80]}")
                raise ValueError("non_json_output_fallback")
        return result, ocr_called, is_unrelated
    except MinerFatalApiError:
        raise
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
            if not (ocr_text or "").strip():
                logger.warning(
                    "[Miner降级] 共 %d 张图但 OCR 无可用文本（将仅按正文调 LLM）| task=%s | paths=%s",
                    len(image_paths),
                    task_id or "-",
                    image_paths,
                )

        # 使用 format_miner_user_prompt 格式化输入
        from backend.agents.prompts.miner_prompt import format_miner_user_prompt
        user_prompt = retry_hint or format_miner_user_prompt(content, has_image, company, position)
        if ocr_text:
            user_prompt += f"\n\n## 图片OCR识别内容\n{ocr_text}"

        return _call_llm_direct(user_prompt), bool(ocr_text), False


def _call_llm_direct(user_prompt: str) -> Optional[str]:
    """直接调用 LLM API（不走 Agent，作为降级方案）。remote 时按 MINER_REMOTE_FALLBACK_MODELS 依次切换端点。"""
    from openai import OpenAI
    from backend.config.config import settings

    endpoints = settings.miner_remote_models
    if not endpoints:
        logger.error(
            "Miner 直连无可用端点：请配置 MINER_LOCAL_* / MINER_REMOTE_*，"
            "two_stage 时 Stage1 需 MINER_STAGE1_* 或 MINER_REMOTE_*"
        )
        return None

    messages = [
        {"role": "system", "content": get_miner_prompt()},
        {"role": "user", "content": user_prompt},
    ]
    last_err: Exception | None = None
    for idx, ep in enumerate(endpoints):
        model = (ep.get("model") or "").strip()
        base = (ep.get("base_url") or "").strip().rstrip("/")
        key = (ep.get("api_key") or "").strip() or "sk-dummy"
        timeout = int(ep.get("timeout") or settings.miner_timeout or 180)
        if not model or not base:
            continue
        try:
            client = OpenAI(api_key=key, base_url=base, timeout=timeout)
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=settings.miner_temperature,
                timeout=timeout,
            )
            out = (resp.choices[0].message.content or "").strip()
            if out:
                if idx > 0:
                    logger.info("[Miner直连] 备用端点成功 model=%s (%d/%d)", model, idx + 1, len(endpoints))
                return out
            last_err = RuntimeError("empty completion content")
        except Exception as e:
            last_err = e
            logger.warning(
                "[Miner直连] 端点失败 model=%s (%d/%d): %s",
                model,
                idx + 1,
                len(endpoints),
                e,
            )
            if idx + 1 < len(endpoints):
                continue
        break
    if last_err:
        logger.error("LLM 直接调用全部端点失败: %s", last_err)
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


def _get_latest_trace_session_id() -> Optional[str]:
    """获取最近一次 Miner Agent 运行的 trace session_id（用于关联帖子与推理过程）"""
    try:
        from backend.config.config import settings
        trace_dir = Path(settings.backend_data_dir) / "memory" / "traces"
        if not trace_dir.exists():
            return None
        files = sorted(trace_dir.glob("trace-s-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        stem = files[0].stem  # trace-s-20260314-142242-0644
        return stem.replace("trace-", "", 1) if stem.startswith("trace-") else stem
    except Exception as e:
        logger.debug(f"获取 trace session_id 失败: {e}")
        return None


def _parse_json_from_llm(text: str, user_prompt_for_debug: str = None) -> Tuple[List[Dict], str]:
    """从 LLM 输出中提取 JSON 数组，兼容多种返回格式。返回 (items, status)，status 为 ok/unrelated/empty/parse_error"""
    if not text:
        return [], "empty"
    # 去掉 markdown 代码块（```json ... ``` 或 ``` ... ```）
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    text = text.lstrip("\ufeff")
    # 模型常在 JSON 前后加说明，整段 json.loads 失败；先识别无关声明（与 prompt 的 unrelated 对象一致）
    if re.search(r'"status"\s*:\s*"unrelated"', text, re.IGNORECASE):
        logger.info("LLM 输出中含 status=unrelated（可能带前后缀非 JSON），标记为无关帖")
        return [], "unrelated"
    # 去掉 deepseek-r1 的 <think>...</think> 推理块（Ollama 本地部署时混在 content 里）
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE).strip()
    # 去掉 qwen3 等模型输出的 \boxed{...} 格式噪音
    text = re.sub(r"\\boxed\{[^}]*\}", "", text).strip()
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

    # 0a. 检测模型拒绝响应（内容安全/能力限制），这类响应重试无效，直接返回 model_refused
    _REFUSE_PATTERNS = [
        r"^抱歉[，,]?我无法",
        r"^对不起[，,]?我(不能|无法)",
        r"^I('m| am) (sorry|unable)",
        r"^Sorry[，,]? I (can'?t|cannot|am unable)",
        r"无法在限定步数内完成",
        r"^抱歉，我不能",
    ]
    _text_stripped = text.strip()
    for _pat in _REFUSE_PATTERNS:
        if re.search(_pat, _text_stripped, re.IGNORECASE):
            logger.warning(f"LLM 拒绝响应（model_refused），内容: {_text_stripped[:80]}")
            return [], "model_refused"

    # 0b. 检测 NO_RELATED_CONTENT 特殊标识（prompt 要求模型在完全无关时输出此值，不应重试）
    if _text_stripped == "NO_RELATED_CONTENT":
        logger.info("LLM 明确返回 NO_RELATED_CONTENT，帖子与面经无关")
        return [], "unrelated"

    # 0b. 检测工具调用格式（模型输出了 ocr_images/mark_unrelated 但框架未执行）
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # 与 prompt 一致：{"status":"unrelated","reason":"..."} 表示无面经题，应标记 unrelated 而非 parse_error
            _su = (data.get("status") or "").strip().lower()
            if _su == "unrelated":
                logger.info("LLM 返回无关帖（JSON 对象）: %s", (data.get("reason") or "")[:200])
                return [], "unrelated"
            tool_name = data.get("name") or data.get("tool") or data.get("function")
            if tool_name == "ocr_images":
                logger.warning("LLM 返回 ocr_images 工具调用格式但未被执行，将触发手动 OCR 降级")
                return [], "ocr_tool_call_format"
            if tool_name == "mark_unrelated":
                return [], "unrelated"
            if tool_name == "Finish":
                # 尝试从 arguments.answer 提取答案
                args = data.get("arguments") or {}
                if isinstance(args, dict) and args.get("answer"):
                    text = args["answer"]
                elif isinstance(args, str):
                    text = args
                else:
                    text = ""
                if text.strip().startswith("["):
                    try:
                        arr = json.loads(text)
                        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and "question_text" in arr[0]:
                            return arr, "ok"
                    except json.JSONDecodeError:
                        pass
    except json.JSONDecodeError:
        pass

    # 0c. 检测「帖子与面经无关」或空对象，或 LLM 把原文包裹进对象返回
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            _st = (data.get("status") or "").strip().lower()
            if _st in ("foreign_language_source", "non_chinese_source", "foreign_language"):
                logger.info(
                    "LLM 声明原帖主体非中文，跳过后续重试: %s",
                    (data.get("reason") or "")[:120],
                )
                return [], "foreign_language"
            if _st == "unrelated":
                logger.info("LLM 返回无关帖（0c）: %s", (data.get("reason") or "")[:200])
                return [], "unrelated"
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
            _st1 = (data.get("status") or "").strip().lower()
            if _st1 in ("foreign_language_source", "non_chinese_source", "foreign_language"):
                logger.info(
                    "LLM 声明原帖主体非中文（嵌套 JSON）: %s",
                    (data.get("reason") or "")[:120],
                )
                return [], "foreign_language"
            if _st1 == "unrelated":
                logger.info("LLM 返回无关帖（整段 JSON）: %s", (data.get("reason") or "")[:200])
                return [], "unrelated"
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


def _apply_miner_chinese_locale_guard(
    items: List[Dict],
    status: str,
    full_content: str,
    source_url: str,
) -> Tuple[List[Dict], str]:
    """开启 miner_enforce_chinese_output 时：检查题干/答案/标签是否含明显乱码，失败则清空并返回 chinese_guard_failed 供 ReAct 重试。"""
    if status != "ok" or not items:
        return items, status
    from backend.config.config import settings

    if not getattr(settings, "miner_enforce_chinese_output", True):
        return items, status
    from backend.services.crawler.miner_output_locale_guard import validate_chinese_extraction

    ok_cn, cn_reason = validate_chinese_extraction(items, full_content)
    if ok_cn:
        return items, status
    logger.warning(
        "乱码校验未通过，将触发 ReAct 重试: %s | url=%s",
        cn_reason,
        source_url,
    )
    global _last_extraction_error
    _last_extraction_error = f"[乱码校验] {cn_reason}"
    return [], "chinese_guard_failed"


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
) -> Tuple[List[Dict], str, bool, bool, Optional[str]]:
    """
    从面经原文中用 LLM 提取结构化题目列表。

    content 过长时自动截断（6000 字符，约 3000 token）。
    返回 (questions, status, agent_used_tool, agent_succeeded, trace_session_id)。
    status: ok/unrelated/empty/parse_error。
    agent_used_tool: MinerAgent 是否调用了 ocr_images 工具（True=是，False=否）。
    agent_succeeded: Miner 成功提取则 True；降级为直接 LLM 成功则 False（此时不写入 Graph）。

    若正文无题目且有图片，MinerAgent 会自主调用 ocr_images 工具获取图片内容后再提取。
    """
    _print_miner_config_once()

    global _last_extraction_error
    _last_extraction_error = None

    # 只检查是否完全为空（不检查长度）
    if not content and not image_paths:
        logger.warning(f"内容和图片均为空，跳过提取 | url={source_url} | title={post_title[:30] if post_title else ''}")
        return [], "empty", False, True, None

    # 不截断，保留完整内容
    full_content = f"【标题】{post_title}\n\n【正文】\n{content}" if post_title else content

    # 使用新的 Prompt 系统
    user_prompt = format_miner_user_prompt(full_content, has_image=bool(image_paths), company=company, position=position)
    if os.environ.get("WXR_WORKER_SUBPROCESS") == "1":
        logger.info(
            "[题目提取][子进程] url=%s | 原始正文=%d字 | 标题=%s | 图=%d张 | miner用户消息约%d字",
            source_url,
            len(content or ""),
            (post_title or "")[:120],
            len(image_paths or []),
            len(user_prompt),
        )

    from backend.config.config import settings
    max_retries = settings.miner_max_retries
    refusal_retries = settings.miner_refusal_retries

    # 正文提取（带重试）
    # 统一走 MinerAgent（框架托管版）：LLM 自主判断是否调用 ocr_images 工具
    # - 正文有题目 → LLM 直接调用 Finish 返回 JSON
    # - 正文无题目但有图片 → LLM 自主调用 ocr_images → 再调用 Finish 返回 JSON
    items, status = [], "empty"
    agent_used_tool: bool = False
    agent_succeeded: bool = True  # Miner 成功为 True，降级成功为 False
    refusal_count = 0  # Miner 拒绝次数，用尽 refusal_retries 后再降级
    trace_session_id: Optional[str] = None
    from backend.agents.miner_agent import UNRELATED_SIGNAL
    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        # 重试时在 user_prompt 末尾追加纠错指令
        attempt_prompt = user_prompt
        if attempt > 1:
            # 情况A：上次 Miner 拒绝，重试时强调必须输出 JSON
            if status == "model_refused":
                attempt_prompt = user_prompt + (
                    f"\n\n【第{attempt}次重试 - Miner 拒绝后重试】"
                    "上次返回了拒绝类回复。这次必须按要求提取面经题目并输出 JSON 数组，"
                    "直接以 [ 开头、以 ] 结尾，不要有任何拒绝或说明。"
                )
            # 情况B：上次解析失败（空/格式错误）
            elif not items or status != "ok":
                _err_hint = ""
                if _last_extraction_error:
                    _err_hint = f"\n\n**上次失败原因**：{_last_extraction_error}\n请针对上述错误修正输出，确保 JSON 合法。"
                attempt_prompt = user_prompt + (
                    f"\n\n【第{attempt}次重试 - 重要纠错】"
                    "上一次你的回复不是合法的 JSON 数组，解析失败。"
                    "这次必须只输出 JSON 数组本身，直接以 [ 开头、以 ] 结尾，"
                    "不要有任何前缀、说明、Markdown 格式或代码块。"
                    "即使面经是叙述性格式，也必须从中归纳题目并输出 JSON 数组。"
                    f"{_err_hint}"
                )
            # 情况C：其他重试
            else:
                _err_hint = ""
                if _last_extraction_error:
                    _err_hint = f"\n\n**上次失败原因**：{_last_extraction_error}\n请针对上述错误修正输出。"
                attempt_prompt = user_prompt + (
                    f"\n\n【第{attempt}次重试 - 重要纠错】"
                    "上一次提取的题目数量不足或格式有误。"
                    "这次必须只输出 JSON 数组本身，直接以 [ 开头、以 ] 结尾，确保提取所有题目。"
                    f"{_err_hint}"
                )
        raw, ocr_called, is_unrelated = _call_llm_with_agent(
            content=full_content,
            has_image=bool(image_paths),
            company=company,
            position=position,
            image_paths=image_paths,
            task_id=task_id,
            retry_hint=attempt_prompt if attempt > 1 else None,
            source_url=source_url,
            post_title=post_title,
        )
        if _is_miner_fatal_upstream_error(raw):
            _msg = (raw or "")[:2000]
            logger.error(
                "Miner 上游致命错误（配置或 API），中止批处理 | url=%s | 预览=%s",
                source_url,
                _msg[:400],
            )
            raise MinerFatalApiError(_msg)
        trace_session_id = _get_latest_trace_session_id()
        llm_response_time_sec = time.perf_counter() - t0
        if ocr_called:
            agent_used_tool = True

        # LLM 主动调用 mark_unrelated 工具 → 直接标记无关，不再解析 JSON
        if is_unrelated or raw == UNRELATED_SIGNAL:
            logger.info(f"LLM 主动标记帖子无关（mark_unrelated）: {source_url}")
            _append_llm_log_to_csv(user_prompt, "[mark_unrelated]", llm_response_time_sec,
                                   source=platform, title=post_title, source_url=source_url)
            return [], "unrelated", agent_used_tool, True, trace_session_id

        items, status = _parse_json_from_llm(raw, user_prompt_for_debug=user_prompt)

        _append_llm_log_to_csv(user_prompt, raw or "", llm_response_time_sec, source=platform,
                               title=post_title, source_url=source_url)

        if status == "foreign_language":
            logger.info(
                "原帖被判定为非中文主体，不按面经入库（避免英文整句题库）| url=%s",
                source_url,
            )
            return [], "unrelated", agent_used_tool, True, trace_session_id

        if status == "unrelated":
            logger.info(f"LLM 判定帖子与面经无关: {source_url}")
            return [], "unrelated", agent_used_tool, True, trace_session_id

        # 模型拒绝响应：先重试 Miner refusal_retries 次，用尽后再降级为直接 LLM 调用
        if status == "model_refused":
            refusal_count += 1
            if refusal_count < refusal_retries:
                logger.warning(f"Miner 拒绝响应，第 {refusal_count}/{refusal_retries} 次，继续重试 Miner: {source_url}")
                if attempt < max_retries:
                    time.sleep(1)
                continue
            # 用尽 Miner 重试，降级为直接 LLM 调用
            logger.warning(f"Miner 已重试 {refusal_retries} 次仍拒绝，降级为直接 LLM 调用: {source_url}")
            try:
                _direct_raw = _call_llm_direct(user_prompt)
                if _direct_raw:
                    items, status = _parse_json_from_llm(_direct_raw, user_prompt_for_debug=user_prompt)
                    items, status = _apply_miner_chinese_locale_guard(
                        items, status, full_content, source_url
                    )
                    if status == "ok" and items:
                        logger.info(f"直接 LLM 调用降级成功: {len(items)} 道题目（不写入 Graph）")
                        agent_succeeded = False
                        break
                    elif status == "model_refused":
                        logger.warning(f"直接 LLM 调用仍拒绝响应，放弃: {source_url}")
                        return [], "model_refused", agent_used_tool, True, trace_session_id
            except Exception as _de:
                logger.warning(f"直接 LLM 调用降级失败: {_de}")
            return [], "model_refused", agent_used_tool, True, trace_session_id

        # 模型输出了 ocr_images 工具调用格式但框架未执行 → 手动 OCR + 直接 LLM 降级
        if status == "ocr_tool_call_format" and image_paths and not agent_used_tool:
            logger.warning(f"模型尝试调用 ocr_images 但未被执行，手动 OCR 后降级为直接 LLM: {source_url}")
            try:
                from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
                ocr_text = ocr_images_to_text(image_paths, task_id) or ""
                if ocr_text:
                    _prompt_with_ocr = user_prompt + f"\n\n## 图片OCR识别内容\n{ocr_text}"
                    _direct_raw = _call_llm_direct(_prompt_with_ocr)
                else:
                    _direct_raw = _call_llm_direct(user_prompt)
                if _direct_raw:
                    items, status = _parse_json_from_llm(_direct_raw, user_prompt_for_debug=user_prompt)
                    items, status = _apply_miner_chinese_locale_guard(
                        items, status, full_content, source_url
                    )
                    if status == "ok" and items:
                        logger.info(f"手动 OCR + 直接 LLM 降级成功: {len(items)} 道题目（不写入 Graph）")
                        agent_succeeded = False
                        break
            except Exception as _de:
                logger.warning(f"手动 OCR 降级失败: {_de}")
            # 降级失败则继续重试
            if attempt < max_retries:
                time.sleep(1)
            continue

        items, status = _apply_miner_chinese_locale_guard(items, status, full_content, source_url)

        if status == "ok" and items:
            if attempt > 1:
                logger.info(f"重试成功（第 {attempt} 次）: 提取到 {len(items)} 道题目")
            break

        if attempt < max_retries:
            logger.warning(f"提取失败（第 {attempt} 次，状态: {status}），{max_retries - attempt} 次重试机会剩余")
        if attempt < max_retries:
            time.sleep(1)
        else:
            logger.warning(f"提取失败，已达最大重试次数 {max_retries} | url={source_url} | title={post_title[:30] if post_title else ''}")
            if raw:
                logger.info(f"LLM 原始返回（前500字）: {raw[:500]}")

    if not items:
        # 多轮重试后 status 可能仍为 parse_error，但最后一次 raw 实为 unrelated 对象
        if status == "parse_error" and (raw or "").strip():
            _salvage_items, _salvage_st = _parse_json_from_llm(raw, user_prompt_for_debug=None)
            if _salvage_st == "unrelated":
                logger.info("兜底：重试耗尽后从原始输出识别为无关帖 | url=%s", source_url)
                return [], "unrelated", agent_used_tool, True, trace_session_id
        logger.warning(f"LLM 未提取到题目 | url={source_url} | title={post_title[:30] if post_title else ''}")
        return [], status, agent_used_tool, True, trace_session_id

    questions: List[Dict] = []
    for item in items:
        logger.debug(f"处理 item: {type(item)}")
        if not isinstance(item, dict):
            logger.debug(f"跳过非字典项: {type(item)}")
            continue
        
        # 兼容多种字段名：question_text / question
        q_text = strip_question_enumeration(
            str(item.get("question_text") or item.get("question", "")).strip()
        )
        q_text, _ = repair_text(q_text)
        if is_unusable_after_repair(q_text):
            logger.warning("题干疑似乱码已跳过 | preview=%s", (q_text or "")[:80])
            continue

        # 放宽过滤条件：只过滤完全为空的题目
        if not q_text:
            logger.warning(f"题目为空被过滤")
            continue

        # 兼容 topic_tags / tags，缺失时用空数组
        tags_raw = item.get("topic_tags") or item.get("tags", [])
        if not isinstance(tags_raw, list):
            tags_raw = [str(tags_raw)] if tags_raw else []

        # 公司/岗位/难度：LLM 不确定时填空，不猜测；优先用 LLM 输出，其次用帖子元数据；"未知" 视为空
        item_company = str(item.get("company", "")).strip()
        post_company = (company or "").strip() if (company or "").strip() != "未知" else ""
        final_company = item_company or post_company or ""
        try:
            from backend.services.company_normalization import normalize_company_field

            final_company = normalize_company_field(
                final_company,
                post_title=post_title or "",
                hint_text=q_text[:1200],
            )
        except Exception:
            pass
        final_company, _ = repair_text(final_company)
        if company_should_be_cleared(final_company):
            final_company = ""
        item_position = str(item.get("position", "")).strip()
        post_position = (position or "").strip() if (position or "").strip() != "未知" else ""
        final_position = item_position or post_position or ""
        item_difficulty = str(item.get("difficulty", "")).strip()
        difficulty_val = _normalize_difficulty(item_difficulty) if item_difficulty else ""
        
        # 生成唯一的 q_id（UUID）
        import uuid
        q_id = str(uuid.uuid4())
        
        # 兼容多种字段名：answer_text/answer, question_type/type/role
        q_type = str(item.get("question_type") or item.get("type") or item.get("role", "技术题")).strip() or "技术题"
        ans = str(item.get("answer_text") or item.get("answer", "")).strip()
        raw_a = str(item.get("raw_answer", "")).strip()
        ans, _ = repair_text(ans)
        raw_a, _ = repair_text(raw_a)
        if is_unusable_answer_after_repair(ans):
            ans = ""
        if is_unusable_answer_after_repair(raw_a):
            raw_a = ""
        questions.append({
            "q_id": q_id,
            "question_text": q_text,
            "answer_text": ans,
            "raw_answer": raw_a,
            "difficulty": difficulty_val,
            "question_type": q_type,
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
        logger.info(f"✅ 提取成功: {len(questions)} 道题目 | title={post_title[:30] if post_title else ''} | url={source_url}")
    return questions, "ok", agent_used_tool, agent_succeeded, trace_session_id



def _normalize_difficulty(d: str) -> str:
    """将难度归一化，空或不确定时返回空字符串。兼容 low/high 等非标准值。"""
    d = (d or "").strip()
    if not d or d.lower() in ("不确定", "unknown", "?"):
        return ""
    d = d.lower()
    if d in ("hard", "困难", "高", "困难/拷打", "high"):
        return "hard"
    if d in ("easy", "简单", "低", "简单/常规", "low"):
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




