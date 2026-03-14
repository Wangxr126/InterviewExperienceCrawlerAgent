"""
两阶段提取 Agent
- Stage 1：使用 miner_prompt.py（原始 Prompt，含内嵌 Few-shot + verify_extraction_count）
- Stage 2：豆包 API，使用 two_stage_prompts.py 精加工
- 保存两阶段结果用于后续本地模型微调
"""
import json
import logging
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

logger = logging.getLogger(__name__)

UNRELATED_SIGNAL = "__UNRELATED__"

# 模型输出非 JSON 时，重试注入的纠错指令
_JSON_RETRY_INSTRUCTION = """

## ⚠️ 重要纠错（上次输出不符合要求）
你上次的输出不是合法的 JSON 格式（可能是 Markdown、解释性文字或带前缀/后缀）。
请严格按照以下要求重新输出：
- **必须是纯 JSON 数组**，直接以 `[` 开头、`]` 结尾
- **严禁** Markdown 格式（如 ###、####、-、*、** 等）
- **严禁** ```json 代码块包裹
- **严禁** 任何解释、说明、总结、洞察等自然语言
- 不管有多少道题（10道、30道、50道），都必须用 JSON 数组格式输出，禁止用 Markdown 列表
- 直接输出题目列表，不要任何前缀或后缀
"""

# 上次提取失败时的错误信息，供重试时注入 prompt
_last_extraction_error: str | None = None


class TwoStageExtractor:
    """两阶段提取器：Stage1 本地粗提取 + Stage2 豆包精加工"""

    def __init__(self, image_paths: List[str] = None, task_id: str = ""):
        self._image_paths = image_paths or []
        self._task_id = task_id
        self._ocr_called = False

        # Stage 1：强制使用本地模型（Ollama）
        self.rough_llm = HelloAgentsLLM(
            model=settings.miner_local_model,
            api_key=_get_miner_local_api_key(),
            base_url=settings.miner_local_base_url,
            temperature=0.3,
            timeout=settings.miner_local_timeout,
        )

        # 注册工具（仅 Stage 1 需要）
        registry = ToolRegistry()
        registry.register_tool(OcrImagesTool(image_paths=self._image_paths, task_id=self._task_id))
        registry.register_tool(MarkUnrelatedTool())
        registry.register_tool(VerifyExtractionCountTool())

        _data_dir = str(settings.backend_data_dir / "memory")
        _skills_dir = str(settings.backend_data_dir.parent.parent / ".claude" / "skills")
        _agent_config = HelloAgentsConfig(
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
            tool_output_max_lines=500,
            tool_output_max_bytes=20480,
            tool_output_dir=f"{_data_dir}/tool-output",
            subagent_enabled=False,
            async_enabled=True,
            max_concurrent_tools=2,
        )

        self.rough_agent = MinerReActAgent(
            name="Rough Extractor",
            llm=self.rough_llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),
            max_steps=settings.miner_max_steps,
            config=_agent_config,
        )

        # Stage 2：SimpleAgent（纯对话，无工具），豆包精加工
        if settings.miner_stage2_base_url and settings.miner_stage2_model:
            self.enrich_llm = HelloAgentsLLM(
                model=settings.miner_stage2_model,
                api_key=settings.miner_stage2_api_key or "sk-dummy",
                base_url=settings.miner_stage2_base_url,
                temperature=settings.miner_stage2_temperature,
                timeout=settings.miner_stage2_timeout,
                max_tokens=settings.miner_stage2_max_tokens,
            )
            self.enrich_agent = SimpleAgent(
                name="Enrich Extractor",
                llm=self.enrich_llm,
                system_prompt=ENRICH_SYSTEM_PROMPT,
            )
        else:
            self.enrich_agent = None

        logger.info(
            "[TwoStageExtractor] 初始化完成 "
            f"stage1=local({settings.miner_local_model}) stage2=doubao({settings.miner_stage2_model})"
        )

    def extract(
        self,
        content: str,
        has_image: bool = False,
        company: str = "",
        position: str = "",
        user_input_override: str = None,
        _retry_count: int = 0,
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

        # ========== Stage 1：粗提取（本地） ==========
        logger.info("[TwoStageExtractor] 开始 Stage 1：粗提取（本地）")
        logger.info(
            "[TwoStageExtractor] 预计 2-5 分钟（OCR ~1 分钟 + 模型生成 1-3 分钟），请勿中断"
        )

        user_input = user_input_override or format_miner_user_prompt(
            content=content,
            has_image=has_image,
            company=company or "",
            position=position or "",
        )

        try:
            rough_result = self.rough_agent.run(user_input)
            rough_result = self._strip_think_tags(rough_result)

            self._check_ocr_called()

            # 检测 mark_unrelated 工具调用（LLM 可能只输出自然语言，不含 __UNRELATED__）
            if UNRELATED_SIGNAL in rough_result or self._check_mark_unrelated_called():
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

        # ========== Stage 2：精加工（SimpleAgent，豆包 API） ==========
        if not self.enrich_agent:
            logger.info("[TwoStageExtractor] 未配置 Stage 2，直接返回 Stage 1 结果")
            for q in rough_questions:
                if isinstance(q, dict):
                    q["raw_answer"] = q.get("answer_text", "")
            return json.dumps(rough_questions, ensure_ascii=False), self._ocr_called, False

        logger.info("[TwoStageExtractor] 开始 Stage 2：精加工 model=%s", settings.miner_stage2_model)
        try:
            questions_text = "\n".join(
                f"{i+1}. {q.get('question_text', '')}"
                for i, q in enumerate(valid_questions)
            )
            enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)
            enrich_result = self.enrich_agent.run(enrich_input)
            enrich_result = (enrich_result or "").strip()

            if enrich_result:
                _preview = enrich_result 
                logger.info("[TwoStageExtractor] Stage 2 豆包原始结果:\n%s", _preview)
                enrich_result = self._strip_think_tags(enrich_result)
                enrich_result = self._extract_json_if_direct_reply(enrich_result)

                # 合并 Stage 2 的 answer_text 与 Stage 1 的元数据（下游需要完整 7 字段）
                enrich_result = self._merge_stage2_with_stage1(enrich_result, valid_questions)

                # 保存两阶段对比数据（用于微调）
                self._save_two_stage_log(
                    content=content,
                    stage1_output=rough_result,
                    stage2_output=enrich_result,
                )

                logger.info("[TwoStageExtractor] Stage 2 完成，输出长度: %d", len(enrich_result))
                return enrich_result, self._ocr_called, False

        except Exception as e:
            logger.error(f"[TwoStageExtractor] Stage 2 异常: {e}，降级返回 Stage 1 结果")

        # 降级：返回 Stage 1 结果，补充 raw_answer（与 answer_text 相同）
        try:
            for q in rough_questions:
                if isinstance(q, dict):
                    q["raw_answer"] = q.get("answer_text", "")
            return json.dumps(rough_questions, ensure_ascii=False), self._ocr_called, False
        except Exception:
            return rough_result, self._ocr_called, False

    def _merge_stage2_with_stage1(self, enrich_result: str, rough_questions: list) -> str:
        """合并 Stage 2 输出与 Stage 1 元数据，下游需要完整 7 字段。
        解析失败时 re-raise，让外层触发 Stage 1 降级，避免返回无效 JSON 导致整体提取失败。
        """
        try:
            stage2_list = json.loads(enrich_result)
            if not isinstance(stage2_list, list):
                return enrich_result
            stage1_by_qt = {
                (q.get("question_text", "") if isinstance(q, dict) else ""): q
                for q in rough_questions
                if isinstance(q, dict)
            }
            merged = []
            for item in stage2_list:
                if not isinstance(item, dict):
                    continue
                qt = item.get("question_text", "")
                s1 = stage1_by_qt.get(qt, {})
                merged.append({
                    "question_text": qt or s1.get("question_text", ""),
                    "answer_text": item.get("answer_text") or s1.get("answer_text", ""),  # 豆包答案，用于展示
                    "raw_answer": s1.get("answer_text", ""),  # 原答案（Stage 1），入库保存
                    "difficulty": item.get("difficulty") or s1.get("difficulty", "medium"),
                    "question_type": item.get("question_type") or s1.get("question_type", "基础类"),
                    "topic_tags": item.get("topic_tags") or s1.get("topic_tags", []),
                    "company": item.get("company") or s1.get("company", ""),
                    "position": item.get("position") or s1.get("position", ""),
                })
            return json.dumps(merged, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError) as e:
            # 豆包返回截断/非法 JSON 时，必须 re-raise 以触发外层 fallback 到 Stage 1
            logger.warning(f"[TwoStageExtractor] Stage 2 输出解析失败（可能被截断）: {e}，将降级返回 Stage 1 结果")
            raise

    def _save_two_stage_log(
        self,
        content: str,
        stage1_output: str,
        stage2_output: str,
    ) -> None:
        """保存两阶段结果，用于后续本地模型微调（Stage1 vs Stage2 对比）"""
        log_path = settings.miner_two_stage_log_path
        if not log_path:
            return

        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)

            record = {
                "ts": datetime.now().isoformat(),
                "content_preview": content[:500] + ("..." if len(content) > 500 else ""),
                "stage1_output": stage1_output,
                "stage2_output": stage2_output,
                "stage1_model": settings.miner_local_model,
                "stage2_model": settings.miner_stage2_model,
            }

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            logger.debug(f"[TwoStageExtractor] 两阶段日志已保存: {log_path}")
        except Exception as e:
            logger.warning(f"[TwoStageExtractor] 保存两阶段日志失败: {e}")

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


def _get_miner_local_api_key() -> str:
    """Stage 1 本地模型 API Key（Ollama 通常为 ollama）"""
    import os

    return os.environ.get("MINER_LOCAL_API_KEY", "").strip() or settings.llm_local_api_key
