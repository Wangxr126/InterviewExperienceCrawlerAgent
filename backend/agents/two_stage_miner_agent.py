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

from hello_agents import ReActAgent
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

        self.rough_agent = ReActAgent(
            name="Rough Extractor",
            llm=self.rough_llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),
            max_steps=settings.miner_max_steps,
            config=_agent_config,
        )

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
    ) -> Tuple[str, bool, bool]:
        """
        两阶段提取

        Returns:
            (answer, ocr_called, is_unrelated)
            - answer: JSON 字符串（有题）/ UNRELATED_SIGNAL（无关）/ ""（失败）
            - ocr_called: 是否调用了 ocr_images
            - is_unrelated: 是否无关帖子
        """
        # ========== Stage 1：粗提取（本地） ==========
        logger.info("[TwoStageExtractor] 开始 Stage 1：粗提取（本地）")
        logger.info(
            "[TwoStageExtractor] 预计 2-5 分钟（OCR ~1 分钟 + 模型生成 1-3 分钟），请勿中断"
        )

        user_input = format_miner_user_prompt(
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
                rough_questions = self._parse_json_fallback(rough_result)
                if not rough_questions:
                    # 兜底：模型输出 Markdown 而非 JSON 时，尝试从 Markdown 提取题目
                    rough_questions = self._parse_markdown_to_questions(rough_result)
                if not rough_questions:
                    raise je
            logger.info(f"[TwoStageExtractor] Stage 1 完成，提取到 {len(rough_questions)} 道题")

        except Exception as e:
            logger.error(f"[TwoStageExtractor] Stage 1 异常: {e}")
            return "", self._ocr_called, False

        # ========== Stage 2：精加工（豆包 API，仅传题目文本） ==========
        logger.info("[TwoStageExtractor] 开始 Stage 2：精加工 model=%s", settings.miner_stage2_model)

        try:
            questions_text = "\n".join(
                f"{i+1}. {q.get('question_text', '')}"
                for i, q in enumerate(rough_questions)
                if isinstance(q, dict)
            )
            enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)

            enrich_result = self._call_doubao_enrich(
                system_prompt=ENRICH_SYSTEM_PROMPT,
                user_prompt=enrich_input,
            )

            if enrich_result:
                _preview = enrich_result 
                logger.info("[TwoStageExtractor] Stage 2 豆包原始结果:\n%s", _preview)
                enrich_result = self._strip_think_tags(enrich_result)
                enrich_result = self._extract_json_if_direct_reply(enrich_result)

                # 合并 Stage 2 的 answer_text 与 Stage 1 的元数据（下游需要完整 7 字段）
                enrich_result = self._merge_stage2_with_stage1(enrich_result, rough_questions)

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
                q["raw_answer"] = q.get("answer_text", "")
            return json.dumps(rough_questions, ensure_ascii=False), self._ocr_called, False
        except Exception:
            return rough_result, self._ocr_called, False

    def _merge_stage2_with_stage1(self, enrich_result: str, rough_questions: list) -> str:
        """合并 Stage 2 输出与 Stage 1 元数据，下游需要完整 7 字段"""
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
        except Exception:
            return enrich_result

    def _call_doubao_enrich(self, system_prompt: str, user_prompt: str) -> str:
        """调用豆包 API 进行精加工（OpenAI 兼容接口），使用 settings.miner_stage2_* 配置"""
        from openai import OpenAI

        api_key = settings.miner_stage2_api_key
        base_url = settings.miner_stage2_base_url
        model = settings.miner_stage2_model
        logger.debug("[TwoStageExtractor] Stage 2 请求 model=%s base_url=%s", model, base_url)

        if not base_url:
            raise ValueError("未配置 MINER_STAGE2_BASE_URL 或 MINER_REMOTE_BASE_URL，无法调用豆包")

        client = OpenAI(
            api_key=api_key or "sk-dummy",
            base_url=base_url,
            timeout=settings.miner_stage2_timeout,
        )

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.miner_stage2_temperature,
            max_tokens=settings.miner_stage2_max_tokens or 4096,
        )

        return (resp.choices[0].message.content or "").strip()

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
    def _parse_markdown_to_questions(text: str) -> list:
        """兜底：模型输出 Markdown 而非调用 Finish 时，从 Markdown 中提取题目列表"""
        import re

        # 分类标题黑名单（如 1. 项目经验类、2. 高级系统设计类），避免误提
        SECTION_HEADER_SUFFIXES = ("类", "题", "类问题", "问题")
        SECTION_HEADER_WHITELIST = (
            "项目经验类", "高级系统设计类", "数据库事务类", "数据库索引类",
            "网络协议类", "手撕编程题", "结构化面试问题列表", "字节后端开发实习二面问题",
        )

        def _is_section_header(qt: str) -> bool:
            qt = qt.strip()
            if len(qt) < 2 or len(qt) > 25:
                return False
            # XXX类、XXX题 结尾
            if qt.endswith(SECTION_HEADER_SUFFIXES) and len(qt) <= 12:
                return True
            if qt in SECTION_HEADER_WHITELIST:
                return True
            # 共N题、共22题 等
            if re.match(r"^共\d+[题道]?$", qt):
                return True
            return False

        def _make_item(qt: str) -> dict:
            qt = qt.strip()
            if len(qt) < 2 or _is_section_header(qt):
                return None
            return {
                "question_text": qt,
                "answer_text": f"（待补充）{qt[:50]}...",
                "difficulty": "medium",
                "question_type": "基础类",
                "topic_tags": [],
                "company": "",
                "position": "",
            }

        skip_patterns = (
            r"^#+\s",  # 标题
            r"^来自",  # 来自华为备忘录
            r"^NOTE\s*$",
            r"^字节\S*$",  # 纯「字节xxx」短行（如字节二面）
            r"^实习\S*$",
            r"^面经\s*$",
            r"^\*\*注\*\*",
            r"^>",
            r"^\*\*\d+[\.、]\s*[\u4e00-\u9fa5]+[类题]\s*\*\*",  # **1. 项目经验类** 等
            r"^\*\*[一二三四五六七八九十\d]+[\.、]",  # **一、**二、**1. 等小节标题
            r"^[\u4e00-\u9fa5]+[类题]\s*$",  # 纯「XXX类」「XXX题」短行
        )
        results = []
        seen = set()  # 去重：question_text 规范化后
        lines = text.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # ### 1. 题目 格式（豆包等模型常用，需在 skip 前处理）
            m = re.match(r"^#+\s*(\d+)[\.、]\s*(.+)$", stripped)
            if m:
                qt = m.group(2).strip().rstrip("。？?")
                if len(qt) >= 3:
                    item = _make_item(qt)
                    if item:
                        key = qt[:80]
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
                continue
            if any(re.match(p, stripped, re.I) for p in skip_patterns):
                continue
            # 1. 题目 或 9. 题目 或 10. 题目（排除 **1. 项目经验类** 等分类标题）
            m = re.match(r"^\s*(\d+)[\.、]\s*(.+)$", stripped)
            if m:
                qt = m.group(2).strip().rstrip("。？?")
                if len(qt) >= 3:
                    item = _make_item(qt)
                    if item:
                        key = qt[:80]  # 去重键
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
                continue
            # - **题目**：描述 或 * **题目**：描述
            m = re.match(r"^\s*[-*]\s*\*\*(.+?)\*\*[：:]\s*(.+)$", stripped)
            if m:
                title = m.group(1).strip()
                desc = m.group(2).strip()
                qt = f"{title}：{desc}" if desc else title
                if len(qt) >= 3:
                    item = _make_item(qt)
                    if item:
                        key = qt[:80]
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
                continue
            # 手撕：xxx
            m = re.match(r"^手撕[：:]\s*(.+)$", stripped)
            if m:
                qt = m.group(1).strip()
                if len(qt) >= 5:
                    item = _make_item(qt)
                    if item:
                        key = qt[:80]
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
                continue
            # - 纯文本题目（无 **），需像问句
            m = re.match(r"^\s*[-*]\s+(.+)$", stripped)
            if m:
                qt = m.group(1).strip().rstrip("。？?")
                if len(qt) >= 5 and any(
                    k in qt for k in ("?", "？", "什么", "如何", "为什么", "简述", "介绍", "说明", "项目")
                ):
                    item = _make_item(qt)
                    if item:
                        key = qt[:80]
                        if key not in seen:
                            seen.add(key)
                            results.append(item)
                continue

        if results:
            logger.info(f"[TwoStageExtractor] Markdown 兜底解析成功，提取到 {len(results)} 道题")
        return results

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
                                if isinstance(obj, dict) and obj.get("question_text"):
                                    results.append(obj)
                            except json.JSONDecodeError:
                                pass
                            break
                    j += 1
                i = j + 1
            else:
                i += 1
        return results

    @staticmethod
    def _repair_json(text: str) -> str:
        """修复 LLM 输出的常见 JSON 错误"""
        import re
        s = text
        # 修复 "raw:answer" -> "raw_answer"（常见 LLM 笔误）
        s = re.sub(r'"raw\s*:\s*answer"', '"raw_answer"', s, flags=re.IGNORECASE)
        # 修复 "question:type" -> "question_type" 等键名中的冒号
        s = re.sub(r'"question\s*:\s*type"', '"question_type"', s, flags=re.IGNORECASE)
        s = re.sub(r'"answer\s*:\s*text"', '"answer_text"', s, flags=re.IGNORECASE)
        # 移除尾随逗号（在 ] 或 } 前的逗号）
        s = re.sub(r',\s*([}\]])', r'\1', s)
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
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, list) and len(candidate) > len(best):
                                best = candidate
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
