"""
两阶段提取 Agent
- Stage 1：miner_prompt.py（Few-shot + verify_extraction_count）；端点由 MINER_STAGE1_MODE 决定：
  - local：MINER_STAGE1_LOCAL_*（或回退 MINER_LOCAL_*）
  - remote：MINER_STAGE1_REMOTE_*（或回退 MINER_REMOTE_*）+ MINER_STAGE1_FALLBACK_MODELS 故障转移
- Stage 2：MINER_STAGE2_* 豆包精加工（two_stage_prompts.py）
- 保存两阶段结果用于后续本地模型微调
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from hello_agents import SimpleAgent
from backend.agents.miner_react_agent import MinerReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.tools.miner_tools import OcrImagesTool, MarkUnrelatedTool, VerifyExtractionCountTool
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
from backend.agents.prompts.two_stage_prompts import (
    ENRICH_SYSTEM_PROMPT,
    ENRICH_USER_PROMPT_TEMPLATE,
)
from backend.services.finetune.stage_merge_utils import merge_stage2_with_stage1

logger = logging.getLogger(__name__)

UNRELATED_SIGNAL = "__UNRELATED__"


class _Stage1HelloAgentsLLM(HelloAgentsLLM):
    """
    two_stage Stage1 使用非流式 invoke_with_tools；通义等需在 extra_body 中声明 enable_thinking=false。
    本地 Ollama 等勿传未知字段：use_remote_extra_body=False 时不合并 miner_remote_stage1_extra_body。
    """

    def __init__(self, *args, use_remote_extra_body: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._use_remote_extra_body = use_remote_extra_body

    def invoke_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
        eb: dict = {}
        if self._use_remote_extra_body:
            eb = dict(settings.miner_remote_stage1_extra_body)
        if isinstance(kwargs.get("extra_body"), dict):
            eb.update(kwargs["extra_body"])
        if eb:
            kwargs = {**kwargs, "extra_body": eb}
        # 始终显式传入合法 max_tokens。hello_agents 的 HelloAgentsLLM.invoke_with_tools 在
        # self.max_tokens 为假时不会 pop 默认值；且 kwargs.pop("max_tokens", default) 在键存在且为
        # None 时会得到 None，部分网关会报 Range of max_tokens should be [1, 8192]。
        api_cap = settings.miner_stage1_api_max_tokens
        cap = max(1, int(settings.miner_stage1_max_tokens))
        if api_cap > 0:
            cap = min(cap, api_cap)
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            try:
                cap = max(1, min(int(kwargs["max_tokens"]), cap))
            except (TypeError, ValueError):
                pass
        kwargs.pop("max_tokens", None)
        kwargs["max_tokens"] = cap
        self.max_tokens = cap
        return super().invoke_with_tools(messages, tools, tool_choice, **kwargs)

# MinerReActAgent 在超时、步数用尽、LLM 异常时的自然语言兜底（无法当 JSON 解析）
_STAGE1_FAILURE_MARKERS = (
    "抱歉，Stage1 模型调用失败",
    "抱歉，本地模型调用失败",  # 兼容旧版 MinerReActAgent 文案
    "OpenAI Function Calling调用失败",  # 部分网关错误文案无「Stage1」前缀
    "抱歉，我无法在限定步数内完成这个任务",
    "抱歉，我无法回答这个问题",
)

# 模型输出非 JSON 时，重试注入的纠错指令
_JSON_RETRY_INSTRUCTION = """

## ⚠️ 重要纠错（上次输出不符合要求）
你上次的输出不是合法的 JSON 格式（可能是 Markdown 包裹、解释性文字或带前缀/后缀）。
请严格按照以下要求重新输出：
- **必须是纯 JSON 数组**，直接以 `[` 开头、`]` 结尾
- **严禁**在 JSON 整体外使用 Markdown：禁止 ###、####、```json 代码块、Markdown 列表等包裹
- **严禁** 任何解释、说明、总结、洞察等自然语言
- **仅 answer_text 字段内**允许 **加粗**、1.2.3. 分条、换行等格式
- 直接输出题目列表，不要任何前缀或后缀
- **JSON 对象边界只能是单反花括号**：每个题目用 `{"question_text":...}` 包裹，**禁止**写成 `{{"question_text":...}}`（双双花括号会导致解析失败）
"""

# 上次提取失败时的错误信息，供重试时注入 prompt
_last_extraction_error: str | None = None


def _is_quota_or_rate_limit_error(err: Exception) -> bool:
    """判断是否为额度超限或限流错误，应切换备用模型"""
    msg = (str(err) or "").lower()
    return any(kw in msg for kw in ("429", "quota", "ratelimitexceeded", "quotaexceeded", "额度", "限流"))


def _stage1_failure_suggests_try_next_endpoint(rough_result: str) -> bool:
    """401/额度/限流/连接类失败时尝试下一远程端点；步数用尽等不换端点。"""
    if not rough_result:
        return False
    if "限定步数内完成" in rough_result or "我无法在限定步数" in rough_result:
        return False
    if "我无法回答这个问题" in rough_result:
        return False
    t = rough_result.lower()
    return any(
        kw in t
        for kw in (
            "401",
            "403",
            "429",
            "invalid_api_key",
            "incorrect api key",
            "insufficient_quota",
            "quota",
            "ratelimit",
            "rate_limit",
            "allocationquota",
            "freetier",
            "free tier",
            "exhausted",
            "connection refused",
            "connection reset",
            "remote end closed",
            "timed out",
            "timeout",
        )
    )


class TwoStageExtractor:
    """两阶段提取器：Stage1 粗提取（MINER_STAGE1_*）+ Stage2 豆包精加工"""

    def __init__(self, image_paths: List[str] = None, task_id: str = ""):
        self._image_paths = image_paths or []
        self._task_id = task_id
        self._ocr_called = False
        self._stage1_model_used = ""
        self._stage1_models: List[dict] = list(settings.miner_stage1_models)
        self._s1_mt = settings.miner_stage1_max_tokens
        if settings.miner_max_tokens > settings.miner_remote_max_tokens_cap:
            logger.debug(
                "[TwoStageExtractor] Stage1 max_tokens 已从 %s 钳制为 %s（远程上限 %s）",
                settings.miner_max_tokens,
                self._s1_mt,
                settings.miner_remote_max_tokens_cap,
            )

        # 工具与 Agent 配置（Stage1 每次换端点时重建 MinerReActAgent）
        self._registry = ToolRegistry()
        self._registry.register_tool(OcrImagesTool(image_paths=self._image_paths, task_id=self._task_id))
        self._registry.register_tool(MarkUnrelatedTool())
        self._registry.register_tool(VerifyExtractionCountTool())

        _data_dir = str(settings.backend_data_dir / "memory")
        _skills_dir = str(settings.backend_data_dir.parent.parent / ".claude" / "skills")
        self._agent_config = HelloAgentsConfig(
            trace_enabled=True,
            trace_dir=f"{_data_dir}/traces",
            trace_sanitize=True,
            session_enabled=False,
            context_window=128000,
            compression_threshold=0.8,
            min_retain_rounds=5,
            todowrite_enabled=False,
            devlog_enabled=False,
            skills_enabled=True,
            skills_dir=_skills_dir,
            skills_auto_register=True,
            circuit_enabled=True,
            circuit_failure_threshold=3,
            tool_output_max_lines=99999,
            tool_output_max_bytes=10485760,
            tool_output_dir=f"{_data_dir}/tool-output",
            subagent_enabled=False,
            async_enabled=True,
            max_concurrent_tools=2,
        )

        if not self._stage1_models:
            sm = settings.miner_stage1_mode
            logger.error(
                "[TwoStageExtractor] Stage1 未配置可用端点：MINER_STAGE1_MODE=%s "
                "（local 需 MINER_STAGE1_LOCAL_MODEL+BASE_URL；remote 需 MINER_STAGE1_REMOTE_* 或 MINER_REMOTE_*）",
                sm,
            )
            self._build_stage1_placeholder()
        else:
            self._build_stage1_agent(self._stage1_models[0])

        # Stage 2：模型列表（主 + 备用），额度超限时按序切换
        self._stage2_models = settings.miner_stage2_models
        _stage2_names = [m["model"] for m in self._stage2_models] if self._stage2_models else []
        _s1_desc = (
            f"{settings.miner_stage1_mode}({len(self._stage1_models)} ep)"
            if self._stage1_models
            else f"{settings.miner_stage1_mode}(未配置)"
        )
        logger.info(
            "[TwoStageExtractor] 初始化完成 stage1=%s stage2=%s",
            _s1_desc,
            _stage2_names or "未配置",
        )
        if (
            settings.miner_stage1_mode == "remote"
            and getattr(settings, "miner_stage1_fallback_models_in_env", False)
            and len(self._stage1_models) <= 1
        ):
            logger.warning(
                "[TwoStageExtractor] 环境变量中有 MINER_STAGE1_FALLBACK_MODELS，但解析后 Stage1 仍仅 %d 个端点："
                "请检查是否为单行合法 JSON 数组、每项至少含 model，且勿与 MINER_STAGE2_FALLBACK_MODELS 混用。",
                len(self._stage1_models),
            )

    def _build_stage1_placeholder(self) -> None:
        """未配置 Stage1 时占位，避免 import 即崩。"""
        self._stage1_model_used = "(unconfigured)"
        self.rough_llm = _Stage1HelloAgentsLLM(
            model="miner-stage1-unconfigured",
            api_key="miner-stage1-missing",
            base_url="http://127.0.0.1:1/v1",
            temperature=float(settings.miner_temperature),
            timeout=60,
            max_tokens=max(1, int(self._s1_mt)),
            use_remote_extra_body=True,
        )
        self.rough_agent = MinerReActAgent(
            name="Rough Extractor",
            llm=self.rough_llm,
            tool_registry=self._registry,
            system_prompt=get_miner_prompt(),
            max_steps=settings.miner_max_steps,
            config=self._agent_config,
        )

    def _build_stage1_agent(self, cfg: dict) -> None:
        """按单条端点配置重建 Stage1 LLM + ReAct Agent。"""
        kind = (cfg.get("kind") or "remote").lower()
        use_extra = kind == "remote"
        timeout = int(cfg.get("timeout") or settings.miner_stage1_remote_timeout)
        model = (cfg.get("model") or "").strip()
        base = (cfg.get("base_url") or "").strip().rstrip("/")
        key = (cfg.get("api_key") or "").strip() or ("ollama" if kind == "local" else "sk-dummy")
        self._stage1_model_used = model
        self.rough_llm = _Stage1HelloAgentsLLM(
            model=model,
            api_key=key,
            base_url=base,
            temperature=float(settings.miner_temperature),
            timeout=timeout,
            max_tokens=max(1, int(self._s1_mt)),
            use_remote_extra_body=use_extra,
        )
        self.rough_agent = MinerReActAgent(
            name="Rough Extractor",
            llm=self.rough_llm,
            tool_registry=self._registry,
            system_prompt=get_miner_prompt(),
            max_steps=settings.miner_max_steps,
            config=self._agent_config,
        )

    def extract(
        self,
        content: str,
        has_image: bool = False,
        company: str = "",
        position: str = "",
        user_input_override: str = None,
        _retry_count: int = 0,
        source_url: str = "",
        post_title: str = "",
    ) -> Tuple[str, bool, bool]:
        """
        两阶段提取

        Args:
            user_input_override: 重试时注入的纠错指令（含上次失败原因），为 None 时自动格式化
            _retry_count: 内部重试计数，防止无限递归

        Returns:
            (answer, ocr_called, is_unrelated)
            - answer: JSON 字符串（有题）/ UNRELATED_SIGNAL（无关）/ ""（失败）
            - ocr_called: 是否调用了 ocr_images
            - is_unrelated: 是否无关帖子
        """
        global _last_extraction_error
        _last_extraction_error = None

        # ========== Stage 1：粗提取 ==========
        logger.info(
            "[TwoStageExtractor] 开始 Stage 1：粗提取（MINER_STAGE1_MODE=%s，端点数=%d）",
            settings.miner_stage1_mode,
            len(self._stage1_models),
        )
        logger.info(
            "[TwoStageExtractor] 预计 1-4 分钟（OCR 仍可能本地 + LLM 生成），请勿中断"
        )

        user_input = user_input_override or format_miner_user_prompt(
            content=content,
            has_image=has_image,
            company=company or "",
            position=position or "",
        )

        try:
            from backend.services.crawler.question_extractor import (
                MinerFatalApiError,
                _is_miner_fatal_upstream_error,
            )

            rough_result = ""
            if not self._stage1_models:
                logger.error("[TwoStageExtractor] Stage1 端点未配置，跳过")
                return "", self._ocr_called, False

            stage1_got_valid_reply = False
            n_ep = len(self._stage1_models)
            for ep_idx, cfg in enumerate(self._stage1_models):
                self._build_stage1_agent(cfg)
                logger.info(
                    "[TwoStageExtractor] Stage1 端点 %d/%d model=%s base=%s",
                    ep_idx + 1,
                    n_ep,
                    cfg.get("model"),
                    (cfg.get("base_url") or "")[:72] + ("…" if len(cfg.get("base_url") or "") > 72 else ""),
                )
                rough_result = self.rough_agent.run(user_input)
                rough_result = self._strip_think_tags(rough_result or "")

                has_fail_msg = bool(rough_result) and any(m in rough_result for m in _STAGE1_FAILURE_MARKERS)

                if has_fail_msg:
                    suggest_next = _stage1_failure_suggests_try_next_endpoint(rough_result)
                    can_next = (ep_idx + 1 < n_ep) and suggest_next
                    if can_next:
                        logger.warning(
                            "[TwoStageExtractor] Stage1 端点失败，尝试下一备用 | 预览=%s",
                            (rough_result[:220] + "…") if len(rough_result) > 220 else rough_result,
                        )
                        continue
                    if _is_miner_fatal_upstream_error(rough_result):
                        logger.critical(
                            "[TwoStageExtractor] Stage1 上游致命错误，中止批处理 | 预览=%s",
                            (rough_result[:400] + "…") if len(rough_result) > 400 else rough_result,
                        )
                        raise MinerFatalApiError((rough_result or "")[:2000])
                    # 未切换备用：要么是链上只有 1 个端点，要么是错误类型不允许换端点
                    if suggest_next and ep_idx + 1 >= n_ep:
                        logger.warning(
                            "[TwoStageExtractor] 当前错误（如 403/额度）本应换备用，但 Stage1 端点链仅有 %d 条。"
                            "备用须配在 .env 的 MINER_STAGE1_FALLBACK_MODELS（单行 JSON），"
                            "不是 MINER_STAGE2_FALLBACK_MODELS。",
                            n_ep,
                        )
                    elif not suggest_next:
                        logger.warning(
                            "[TwoStageExtractor] Stage1 失败且未匹配「换端点」关键词（步数用尽等不切换）| n_ep=%d idx=%d | 预览=%s",
                            n_ep,
                            ep_idx + 1,
                            (rough_result[:180] + "…") if len(rough_result) > 180 else rough_result,
                        )
                    logger.warning(
                        "[TwoStageExtractor] Stage1 本端点失败且不再切换 | 预览=%s",
                        (rough_result[:200] + "…") if len(rough_result) > 200 else rough_result,
                    )
                    return "", self._ocr_called, False

                # 修复：原先在「无失败文案」时无条件 break，导致空输出也会跳出 for，后续端点永不尝试
                if not (rough_result or "").strip():
                    if ep_idx + 1 < n_ep:
                        logger.warning(
                            "[TwoStageExtractor] Stage1 返回空输出，尝试下一端点 (%d/%d)",
                            ep_idx + 1,
                            n_ep,
                        )
                        continue
                    logger.warning("[TwoStageExtractor] Stage1 最后一端点仍返回空输出，本帖失败")
                    return "", self._ocr_called, False

                stage1_got_valid_reply = True
                break

            if not stage1_got_valid_reply:
                logger.error("[TwoStageExtractor] Stage1 端点链未得到有效回复（逻辑异常）")
                return "", self._ocr_called, False

            self._check_ocr_called()

            # 检测 mark_unrelated 工具调用或 unrelated 对象输出
            if UNRELATED_SIGNAL in rough_result or self._check_mark_unrelated_called() or self._is_unrelated_object(rough_result):
                logger.info("[TwoStageExtractor] Stage 1 判定为无关帖子")
                return UNRELATED_SIGNAL, self._ocr_called, True

            rough_result = self._extract_json_if_direct_reply(rough_result)

            if not rough_result or rough_result == "[]":
                logger.warning("[TwoStageExtractor] Stage 1 未提取到题目")
                return "", self._ocr_called, False

            rough_result = self._repair_json(rough_result)
            try:
                parsed = json.loads(rough_result)
                if not isinstance(parsed, list):
                    logger.warning(
                        "[TwoStageExtractor] Stage 1 解析结果非题目列表（可能是工具调用 JSON），已忽略"
                    )
                    return "", self._ocr_called, False
                rough_questions = parsed
            except json.JSONDecodeError as je:
                # 解析失败时写入调试文件，便于排查（如全角冒号、乱码等）
                _debug_path = settings.backend_data_dir / "memory" / "json_parse_fail_debug.txt"
                try:
                    _debug_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(_debug_path, "w", encoding="utf-8") as f:
                        f.write(f"# Error: {je}\n# Position: line {je.lineno} col {je.colno}\n\n")
                        f.write(rough_result[:8000])
                except Exception:
                    pass
                rough_questions = self._parse_json_fallback(rough_result)
                if not rough_questions and _retry_count == 0:
                    # 不兜底 Markdown，改为强制重试：要求模型用 JSON 重新输出
                    logger.warning("[TwoStageExtractor] Stage 1 输出非 JSON，触发重试（禁止 Markdown）")
                    retry_prompt = format_miner_user_prompt(
                        content=content,
                        has_image=has_image,
                        company=company or "",
                        position=position or "",
                    ) + _JSON_RETRY_INSTRUCTION
                    return self.extract(
                        content=content,
                        has_image=has_image,
                        company=company,
                        position=position,
                        user_input_override=retry_prompt,
                        _retry_count=1,
                    )
                if not rough_questions:
                    raise je
            logger.info(f"[TwoStageExtractor] Stage 1 完成，提取到 {len(rough_questions)} 道题")

        except Exception as e:
            _last_extraction_error = str(e)
            logger.error(f"[TwoStageExtractor] Stage 1 异常: {e}")
            return "", self._ocr_called, False

        # 规范化字段名：模型可能返回 question/answer/category，需映射为 question_text/answer_text/question_type
        rough_questions = [self._normalize_question_item(q) for q in rough_questions if isinstance(q, dict)]
        rough_questions = [q for q in rough_questions if q]

        # 仅当提取到有效题目 > 0 时才执行 Stage 2
        valid_questions = [q for q in rough_questions if q.get("question_text")]
        if not valid_questions:
            logger.info("[TwoStageExtractor] Stage 1 无有效题目，跳过 Stage 2，直接返回")
            for q in rough_questions:
                if isinstance(q, dict):
                    q["raw_answer"] = q.get("answer_text", "")
            return json.dumps(rough_questions, ensure_ascii=False), self._ocr_called, False

        # ========== 异步模式：入队 stage2_pending，达到 batch_size 触发 ==========
        if settings.miner_stage2_async_enabled and self._stage2_models:
            # 稳定 q_id：Stage1 结束即入库；Stage2 仅 UPDATE 同一 q_id 的 answer_text 等字段
            for v in valid_questions:
                if not v.get("q_id"):
                    v["q_id"] = str(uuid.uuid4())
                if company and not (str(v.get("company") or "").strip()):
                    v["company"] = company
                if position and not (str(v.get("position") or "").strip()):
                    v["position"] = position
                _at = v.get("answer_text")
                _ans = (_at if isinstance(_at, str) else str(_at or "")).strip()
                v["raw_answer"] = _ans
            rough_with_ids = json.dumps(valid_questions, ensure_ascii=False)
            questions_text = "\n".join(
                f"{i+1}. {q.get('question_text', '')}"
                for i, q in enumerate(valid_questions)
            )
            enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)
            from backend.services.storage import sqlite_service
            from backend.services.stage2_processor import trigger_stage2_if_ready
            # 需要 task_id，从 self 获取（TwoStageExtractor 由 MinerAgentV3 创建时传入）
            task_id = getattr(self, "_task_id", "") or ""
            trace_session_id = ""
            try:
                from backend.services.crawler.question_extractor import _get_latest_trace_session_id
                trace_session_id = _get_latest_trace_session_id() or ""
            except Exception:
                pass
            if task_id and (source_url or "").strip():
                _n = sqlite_service.persist_stage1_questions_rough(
                    task_id=task_id,
                    source_url=(source_url or "").strip(),
                    question_items=valid_questions,
                    ocr_called=self._ocr_called,
                )
                if _n > 0:
                    logger.info(
                        "[TwoStageExtractor] Stage1 粗题已入库 %d 道（Stage2 将按 q_id 更新精答案）",
                        _n,
                    )
            ok = sqlite_service.add_stage2_pending(
                task_id=task_id,
                content=content,
                stage1_output=rough_with_ids,
                rough_questions=rough_with_ids,
                enrich_input=enrich_input,
                company=company or "",
                position=position or "",
                source_url=source_url or "",
                post_title=post_title or "",
                trace_session_id=trace_session_id,
                agent_used_tool=1 if getattr(self, "_agent_used_tool", False) else 0,
                ocr_called=1 if self._ocr_called else 0,
            )
            if ok:
                trigger_stage2_if_ready()
                # 返回特殊信号，让上层知道已入队，需更新 task 为 stage2_pending
                return "__STAGE2_PENDING__", self._ocr_called, False
            # 入队失败则降级同步执行

        # ========== Stage 2：精加工（多模型回退，额度超限时切换） ==========
        if not self._stage2_models:
            logger.info("[TwoStageExtractor] 未配置 Stage 2，直接返回 Stage 1 结果")
            for q in rough_questions:
                if isinstance(q, dict):
                    q["raw_answer"] = q.get("answer_text", "")
            return json.dumps(rough_questions, ensure_ascii=False), self._ocr_called, False

        questions_text = "\n".join(
            f"{i+1}. {q.get('question_text', '')}"
            for i, q in enumerate(valid_questions)
        )
        enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)
        last_error: Exception | None = None

        for idx, cfg in enumerate(self._stage2_models):
            model_name = cfg["model"]
            logger.info("[TwoStageExtractor] 开始 Stage 2：精加工 model=%s (%d/%d)", model_name, idx + 1, len(self._stage2_models))
            try:
                enrich_llm = HelloAgentsLLM(
                    model=cfg["model"],
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"],
                    temperature=settings.miner_stage2_temperature,
                    timeout=settings.miner_stage2_timeout,
                    max_tokens=settings.miner_stage2_max_tokens,
                )
                enrich_agent = SimpleAgent(
                    name="Enrich Extractor",
                    llm=enrich_llm,
                    system_prompt=ENRICH_SYSTEM_PROMPT,
                )
                enrich_result = enrich_agent.run(enrich_input)
                enrich_result = (enrich_result or "").strip()

                if enrich_result:
                    _preview = enrich_result
                    logger.info("[TwoStageExtractor] Stage 2 豆包原始结果:\n%s", _preview)
                    enrich_result = self._strip_think_tags(enrich_result)
                    enrich_result = self._extract_json_if_direct_reply(enrich_result)

                    # 合并 Stage 2 的 answer_text 与 Stage 1 的元数据（下游需要完整 7 字段，支持 Stage1 旧格式 title/answer/type/tags）
                    enrich_result = merge_stage2_with_stage1(enrich_result, json.dumps(valid_questions, ensure_ascii=False))

                    # 保存两阶段对比数据（用于微调）
                    self._save_two_stage_log(
                        content=content,
                        stage1_output=rough_result,
                        stage2_output=enrich_result,
                        stage2_model_used=model_name,
                        source_url=source_url or "",
                        post_title=post_title or "",
                    )

                    logger.info("[TwoStageExtractor] Stage 2 完成 model=%s，输出长度: %d", model_name, len(enrich_result))
                    return enrich_result, self._ocr_called, False

            except Exception as e:
                last_error = e
                if _is_quota_or_rate_limit_error(e) and idx + 1 < len(self._stage2_models):
                    logger.warning("[TwoStageExtractor] Stage 2 model=%s 额度/限流: %s，切换备用模型", model_name, e)
                else:
                    logger.error("[TwoStageExtractor] Stage 2 model=%s 异常: %s", model_name, e)
                    break

        if last_error:
            logger.error("[TwoStageExtractor] Stage 2 全部模型失败，降级返回 Stage 1 结果: %s", last_error)

        # 降级：返回 Stage 1 结果，补充 raw_answer（与 answer_text 相同）
        try:
            for q in rough_questions:
                if isinstance(q, dict):
                    q["raw_answer"] = q.get("answer_text", "")
            return json.dumps(rough_questions, ensure_ascii=False), self._ocr_called, False
        except Exception:
            return rough_result, self._ocr_called, False

    def _save_two_stage_log(
        self,
        content: str,
        stage1_output: str,
        stage2_output: str,
        stage2_model_used: str = "",
        source_url: str = "",
        post_title: str = "",
    ) -> None:
        """保存两阶段结果，用于后续本地模型微调（Stage1 vs Stage2 对比）"""
        log_path = settings.miner_two_stage_log_path
        if not log_path:
            return

        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)

            record = {
                "ts": datetime.now().isoformat(),
                "content_preview": content,
                "title": post_title or "",
                "source_url": source_url or "",
                "stage1_output": stage1_output,
                "stage2_output": stage2_output,
                "stage1_model": (getattr(self, "_stage1_model_used", "") or settings.miner_stage1_remote_model or settings.miner_stage1_local_model or "").strip(),
                "stage2_model": stage2_model_used or settings.miner_stage2_model,
            }

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            logger.debug(f"[TwoStageExtractor] 两阶段日志已保存: {log_path} | url={source_url} | title={post_title[:30] if post_title else ''}")
        except Exception as e:
            logger.warning(f"[TwoStageExtractor] 保存两阶段日志失败: {e} | url={source_url} | title={post_title[:30] if post_title else ''}")

    def _check_mark_unrelated_called(self) -> bool:
        """检查是否调用了 mark_unrelated 工具（LLM 调用后可能只输出自然语言，不含 __UNRELATED__）"""
        for attr in ("_tool_call_history", "tool_call_history", "history", "_history"):
            history = getattr(self.rough_agent, attr, None)
            if history:
                for tool_call in history:
                    name = (
                        tool_call.get("tool_name")
                        or tool_call.get("name")
                        or (tool_call.get("function", {}) or {}).get("name", "")
                    ) if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                    if name == "mark_unrelated":
                        return True
        # 检查 trace 文件
        try:
            trace_dir = settings.backend_data_dir / "memory" / "traces"
            if trace_dir.exists():
                trace_files = sorted(trace_dir.glob("trace-s-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                if trace_files:
                    with open(trace_files[0], "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                event = json.loads(line)
                                if event.get("event") == "tool_call":
                                    tool_name = (event.get("payload") or {}).get("tool_name", "")
                                    if tool_name == "mark_unrelated":
                                        return True
                            except Exception:
                                continue
        except Exception:
            pass
        return False

    @staticmethod
    def _is_unrelated_object(text: str) -> bool:
        """检查是否输出了 unrelated 对象 {"status":"unrelated",...}"""
        import re
        
        stripped = text.strip()
        # 尝试直接解析
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict) and obj.get('status') == 'unrelated':
                    return True
            except json.JSONDecodeError:
                pass
        
        # 尝试从文本中提取 {...} 对象
        for m in re.finditer(r'\{', stripped):
            start = m.start()
            depth, i, in_str, escape = 0, start, None, False
            while i < len(stripped):
                c = stripped[i]
                if in_str:
                    escape = not escape and c == '\\'
                    if not escape and c == in_str:
                        in_str = None
                elif c in ('"', "'"):
                    in_str = c
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = stripped[start:i + 1]
                        try:
                            obj = json.loads(candidate)
                            if isinstance(obj, dict) and obj.get('status') == 'unrelated':
                                return True
                        except json.JSONDecodeError:
                            pass
                        break
                i += 1
        
        return False

    def _check_ocr_called(self):
        """检查是否调用了 OCR - 改进版，支持多种追踪方式"""
        # 方式1：检查 agent 的历史记录
        for attr in ("_tool_call_history", "tool_call_history", "history", "_history"):
            history = getattr(self.rough_agent, attr, None)
            if history:
                for tool_call in history:
                    name = (
                        tool_call.get("tool_name")
                        or tool_call.get("name")
                        or (tool_call.get("function", {}) or {}).get("name", "")
                    ) if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                    if name == "ocr_images":
                        self._ocr_called = True
                        logger.debug("[TwoStageExtractor] OCR 调用已追踪（通过历史记录）")
                        return
        
        # 方式2：检查 trace 文件（如果启用了 trace）
        try:
            trace_dir = settings.backend_data_dir / "memory" / "traces"
            if trace_dir.exists():
                # 查找最新的 trace 文件
                trace_files = sorted(trace_dir.glob("trace-s-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                if trace_files:
                    latest_trace = trace_files[0]
                    with open(latest_trace, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                event = json.loads(line)
                                if event.get("event_type") == "tool_call":
                                    tool_name = event.get("data", {}).get("tool_name", "")
                                    if tool_name == "ocr_images":
                                        self._ocr_called = True
                                        logger.debug("[TwoStageExtractor] OCR 调用已追踪（通过 trace 文件）")
                                        return
                            except:
                                continue
        except Exception as e:
            logger.debug(f"[TwoStageExtractor] 无法从 trace 追踪 OCR: {e}")
        
        # 方式3：检查工具注册表的调用计数（如果工具支持）
        try:
            ocr_tool = self.rough_agent.tool_registry.get_tool("ocr_images")
            if ocr_tool and hasattr(ocr_tool, "_call_count"):
                if getattr(ocr_tool, "_call_count", 0) > 0:
                    self._ocr_called = True
                    logger.debug("[TwoStageExtractor] OCR 调用已追踪（通过工具计数）")
                    return
        except Exception as e:
            logger.debug(f"[TwoStageExtractor] 无法从工具计数追踪 OCR: {e}")

    @staticmethod
    def _parse_json_fallback(text: str) -> list:
        """JSON 解析失败时，尝试逐对象提取（括号匹配）"""
        results = []
        i = 0
        while i < len(text):
            if text[i] == "{":
                depth, j = 1, i + 1
                in_str, escape = None, False
                while j < len(text) and depth > 0:
                    c = text[j]
                    if in_str:
                        if escape:
                            escape = False
                        elif c == "\\":
                            escape = True
                        elif c == in_str:
                            in_str = None
                    elif c in ('"', "'"):
                        in_str = c
                    elif c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            chunk = TwoStageExtractor._repair_json(text[i : j + 1])
                            try:
                                obj = json.loads(chunk)
                                if isinstance(obj, dict) and (obj.get("question_text") or obj.get("question")):
                                    results.append(obj)
                            except json.JSONDecodeError:
                                pass
                            break
                    j += 1
                i = j + 1
            else:
                i += 1
        return results

    def _normalize_question_item(self, q: dict) -> dict | None:
        """规范化题目字段，仅做最小必要映射（prompt 已规定格式，错误时靠重试+错误信息修正）"""
        if not isinstance(q, dict):
            return None
        # 仅保留 question/answer 作为最小兼容（prompt 已禁止，但部分模型仍会误用）
        qt = q.get("question_text") or q.get("question") or ""
        if not qt or not isinstance(qt, str):
            return None
        at = q.get("answer_text") or q.get("answer") or ""
        # 仅接受标准 question_type 值，非法则置基础类（由重试+错误信息引导修正）
        qtype = q.get("question_type") or q.get("type") or "基础类"
        if qtype not in ("算法类", "AI类", "工程类", "基础类", "软技能"):
            qtype = "基础类"
        diff = q.get("difficulty")
        if isinstance(diff, str):
            diff = {"低": "easy", "中": "medium", "高": "hard"}.get(diff.strip(), diff)
        if diff not in ("easy", "medium", "hard"):
            diff = "medium"
        tags = q.get("topic_tags") if isinstance(q.get("topic_tags"), list) else q.get("tags")
        tags = tags if isinstance(tags, list) else []
        return {
            "question_text": qt.strip(),
            "answer_text": (at if isinstance(at, str) else str(at)).strip() or f"（待补充）{qt[:50]}",
            "difficulty": diff,
            "question_type": qtype,
            "topic_tags": tags,
            "company": q.get("company") or "",
            "position": q.get("position") or q.get("job") or "",
        }

    @staticmethod
    def _repair_json(text: str) -> str:
        """修复 LLM 输出的常见 JSON 错误"""
        import re
        s = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
        # 模型曾仿照错误 Prompt 示例输出 {{ / }} 作为对象定界符；收拢为合法 JSON（仅常见缩进形态，避免全局 replace 破坏嵌套对象）
        if "{{" in s and s.lstrip().startswith("["):
            t = s.replace("{{\n", "{\n")
            t = t.replace("\n  }},", "\n  },")
            t = t.replace("\n  }}\n]", "\n  }\n]")
            if t != s:
                s = t
        # 修复 "raw:answer" -> "raw_answer"（常见 LLM 笔误）
        s = re.sub(r'"raw\s*:\s*answer"', '"raw_answer"', s, flags=re.IGNORECASE)
        # 修复 "question:type" -> "question_type" 等键名中的冒号
        s = re.sub(r'"question\s*:\s*type"', '"question_type"', s, flags=re.IGNORECASE)
        s = re.sub(r'"answer\s*:\s*text"', '"answer_text"', s, flags=re.IGNORECASE)
        # 移除尾随逗号（在 ] 或 } 前的逗号）
        s = re.sub(r',\s*([}\]])', r'\1', s)
        # 不再修复 question/answer 无效值：原正则会误伤合法值（如 "question_text": "有..." 中冒号后的空格被误判），
        # 无效值由重试+错误信息引导修正
        # 修复缺失逗号："" 与下一键 "key" 之间无逗号时补上（支持无空格，如 "value""key"）
        s = re.sub(r'""\s*"', r' "", "', s)
        # 修复数组元素间缺失逗号：} 与 { 之间（如 }  { 或 }\n{）
        s = re.sub(r'}\s*{', r'},{', s)
        # 替换字符串内的中文引号/智能引号，避免解析为 JSON 边界
        s = s.replace("\u201c", '"').replace("\u201d", '"')
        # 全角冒号 U+FF1A -> 半角，否则 json.loads 报 Expecting ':' delimiter
        s = s.replace("\uFF1A", ":")
        # 移除 { 与 "key" 之间的乱码（如 "назад"），仅当 { 为对象开头时（前有 [ , }）避免误伤字符串内的 {
        s = re.sub(r'(?<=[,\[\]}])\s*{\s*[^"\s\[\]{}]+', ' {', s)
        return s

    @staticmethod
    def _extract_json_if_direct_reply(text: str) -> str:
        """提取 JSON 数组"""
        import re

        stripped = text.strip()
        if stripped.startswith("["):
            return stripped
        clean = re.sub(r"```(?:json)?\s*", "", stripped).strip().rstrip("`").strip()
        if clean.startswith("["):
            return clean
        best = ""
        for m in re.finditer(r"\[", clean):
            start = m.start()
            depth, i, in_str, escape = 0, start, None, False
            while i < len(clean):
                c = clean[i]
                if in_str:
                    escape = not escape and c == "\\"
                    if not escape and c == in_str:
                        in_str = None
                elif c in ('"', "'"):
                    in_str = c
                elif c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = clean[start : i + 1]
                        repaired = TwoStageExtractor._repair_json(candidate)
                        try:
                            parsed = json.loads(repaired)
                            if isinstance(parsed, list) and len(repaired) > len(best):
                                best = repaired
                        except json.JSONDecodeError:
                            pass
                        break
                i += 1
        return best if best else text

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """过滤推理模型的噪音标签"""
        import re

        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\\boxed\{[^}]*\}", "", text)
        text = re.sub(
            r"(No function call needed\.?|无需函数调用\.?|任务不需要工具调用\.?|直接输出结果\.?)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return text.strip()


