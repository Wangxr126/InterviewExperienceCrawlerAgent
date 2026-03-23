"""
Miner Agent - 信息挖掘师（ReAct版）
职责：从面经原文中智能挖掘结构化信息

使用 hello-agents 框架的 ReActAgent，内置 Thought + Finish 工具。
按框架能力配置：Trace、熔断器、工具截断等。Miner 禁用 TodoWrite，DevLog 由配置开关控制。
"""
import logging
import re
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any, List, Tuple
import hashlib

from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.llm.chained_hello_llm import ChainedHelloAgentsLLM, build_miner_hello_llm_list
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
from backend.services.logging.agent_tool_runtime_stats import (
    agent_tool_runtime_stats,
    tool_execution_success_for_stats,
)
from backend.services.logging.hello_agent_logger import build_agent_logger
from backend.tools.miner_tools import OcrImagesTool, MarkUnrelatedTool, VerifyExtractionCountTool

logger = logging.getLogger(__name__)

# mark_unrelated 的特殊返回标记
UNRELATED_SIGNAL = "__UNRELATED__"


def _build_miner_session_id(task_id: str, user_input: str) -> str:
    """构造稳定会话键：优先 task_id；缺失时退化为输入摘要。"""
    tid = (task_id or "").strip()
    if tid:
        return f"miner:{tid}"
    digest = hashlib.sha1((user_input or "").encode("utf-8")).hexdigest()[:16]
    return f"miner:adhoc:{digest}"


class MinerAgent(ReActAgent):
    _had_recent_failure = False

    """
    信息挖掘师 Agent（ReAct版）

    三种结束路径：
    1. LLM 调用 Finish（内置）   → 返回 (JSON字符串, ocr_called, False)
    2. LLM 调用 mark_unrelated  → 返回 (UNRELATED_SIGNAL, ocr_called, True)
    3. 超过最大步数/异常         → 返回 ("", ocr_called, False)
    """

    def __init__(self, image_paths: List[str] = None, task_id: str = ""):
        self._image_paths = image_paths or []
        self._task_id = task_id
        self._ocr_called = False

        # 构建 LLM：remote 时按 MINER_REMOTE_FALLBACK_MODELS 多端点故障转移
        _llms = build_miner_hello_llm_list(settings)
        if len(_llms) > 1:
            llm = ChainedHelloAgentsLLM(_llms, chain_name="miner")
        elif len(_llms) == 1:
            llm = _llms[0]
        else:
            llm = HelloAgentsLLM(
                model=settings.miner_model,
                api_key=settings.miner_api_key,
                base_url=settings.miner_base_url,
                temperature=settings.miner_temperature,
                timeout=settings.miner_timeout,
            )

        # 注册业务工具（ReActAgent 内置了 Thought + Finish，无需再注册 FinishTool）
        registry = ToolRegistry()
        registry.register_tool(OcrImagesTool(image_paths=self._image_paths, task_id=self._task_id))
        registry.register_tool(MarkUnrelatedTool(task_id=self._task_id))
        registry.register_tool(VerifyExtractionCountTool())

        # ── hello-agents Config（对齐框架 16 项能力）────────────────────
        _skills_dir = str(settings.backend_data_dir.parent.parent / ".claude" / "skills")
        _agent_config = HelloAgentsConfig(
            # 可观测性
            trace_enabled=settings.agent_trace_enabled,
            trace_dir=settings.agent_trace_dir,
            trace_sanitize=settings.agent_trace_sanitize,
            # 可选断点续跑（默认关闭，避免改变历史行为）
            session_enabled=settings.miner_session_enabled,
            session_dir="sqlite",
            auto_save_enabled=settings.miner_session_auto_save_enabled,
            auto_save_interval=settings.miner_session_auto_save_interval,
            # 上下文工程（单次提取输入较短，保留默认）
            context_window=settings.context_window,
            compression_threshold=settings.compression_threshold,
            min_retain_rounds=max(1, settings.min_retain_rounds),
            enable_smart_compression=settings.enable_smart_compression,
            summary_llm_provider=settings.summary_llm_provider,
            summary_llm_model=settings.summary_llm_model,
            summary_llm_api_key=settings.summary_llm_api_key,
            summary_llm_base_url=settings.summary_llm_base_url,
            summary_llm_timeout=settings.summary_llm_timeout,
            summary_max_tokens=settings.summary_max_tokens,
            summary_temperature=settings.summary_temperature,
            # TodoWrite 禁用：Miner 只需 ocr_images→Finish，避免模型误用任务规划工具占用步数
            todowrite_enabled=False,
            devlog_enabled=settings.miner_devlog_enabled,
            devlog_persistence_dir=settings.agent_devlog_dir,
            # Skills（可选，面经提取可复用）
            skills_enabled=True,
            skills_dir=_skills_dir,
            skills_auto_register=True,
            # 熔断器（OCR/LLM 失败时自动熔断）
            circuit_enabled=settings.miner_circuit_enabled,
            circuit_failure_threshold=settings.miner_circuit_failure_threshold,
            circuit_recovery_timeout=settings.miner_circuit_recovery_timeout,
            # 工具输出截断（OCR 结果可能很长）
            tool_output_max_lines=settings.agent_tool_output_max_lines,
            tool_output_max_bytes=settings.agent_tool_output_max_bytes,
            tool_output_dir=settings.agent_tool_output_dir,
            tool_output_truncate_direction=settings.agent_tool_output_truncate_direction,
            # 子代理（TaskTool，可选）
            subagent_enabled=False,
            # 异步
            async_enabled=True,
            max_concurrent_tools=2,
        )

        max_steps = settings.miner_max_steps
        self._agent_logger = build_agent_logger("MinerAgent", settings.agent_run_log_dir)

        # 初始化父类（ReActAgent）
        super().__init__(
            name="Miner Agent",
            llm=llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),
            max_steps=max_steps,
            config=_agent_config,
        )
        if _agent_config.session_enabled:
            from backend.services.storage.sqlite_session_store import SqliteSessionStore
            self.session_store = SqliteSessionStore(session_dir="sqlite")

        _n_ep = len(_llms) if settings.miner_mode == "remote" and _llms else (1 if settings.miner_mode != "remote" else 0)
        logger.info(
            f"[MinerAgent] 初始化完成 miner_mode={settings.miner_mode} model={settings.miner_model} "
            f"endpoints={_n_ep or 1} max_steps={max_steps} "
            f"circuit_enabled={settings.miner_circuit_enabled} "
            f"circuit_failure_threshold={settings.miner_circuit_failure_threshold} "
            f"circuit_recovery_timeout={settings.miner_circuit_recovery_timeout}s"
        )

    def _append_devlog(self, category: str, content: str, metadata: dict | None = None) -> None:
        """轻量运行时 DevLog：用于自动记录 Miner 的失败与恢复。"""
        if not settings.miner_devlog_enabled:
            return
        try:
            devlog_dir = Path(settings.agent_devlog_dir)
            devlog_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            payload = {
                "id": f"devlog-{now.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}",
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "category": category,
                "content": content,
                "metadata": metadata or {},
            }
            out = devlog_dir / f"{payload['id']}.json"
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("[MinerAgent] 写入 DevLog 失败（忽略）: %s", e)

    def run(
        self,
        content: str,
        has_image: bool = False,
        company: str = "",
        position: str = "",
        user_input_override: str = None,
        source_url: str = "",
        post_title: str = "",
        **kwargs: Any,
    ) -> Tuple[str, bool, bool]:
        """
        运行 MinerAgent。

        Args:
            content: 面经正文
            has_image: 是否有图片
            company: 公司名称
            position: 岗位名称
            user_input_override: 直接覆盖用户输入（用于重试时注入纠错指令），为 None 时自动格式化
            source_url/post_title: 由 question_extractor 传入，供后续扩展日志；当前不参与 ReAct 循环
            **kwargs: 吞掉调用方/框架多传参数，避免 TypeError 触发误降级

        Returns:
            (answer, ocr_called, is_unrelated)
            - answer       : JSON字符串（有题）/ UNRELATED_SIGNAL（无关）/ ""（失败）
            - ocr_called   : 是否调用了 ocr_images
            - is_unrelated : LLM 是否主动调用了 mark_unrelated 或输出了 unrelated 对象
        """
        if kwargs:
            logger.debug("[MinerAgent] run() 忽略额外参数: %s", sorted(kwargs.keys()))

        # 格式化用户输入（重试时使用外部传入的 override，含纠错指令）
        user_input = user_input_override or format_miner_user_prompt(content, has_image, company, position)

        # 重置状态
        self._ocr_called = False
        _session_id = _build_miner_session_id(self._task_id, user_input)

        try:
            if settings.miner_session_enabled:
                try:
                    self.load_session(_session_id, check_consistency=False)
                    logger.info("[MinerAgent] 已恢复会话: %s", _session_id)
                except FileNotFoundError:
                    pass
                except Exception as _e:
                    logger.warning("[MinerAgent] load_session 失败（忽略）: %s", _e)

            # 调用父类的 run 方法（ReActAgent 自动处理 Thought/Finish/工具循环）
            result = super().run(user_input)

            # 解析结果
            result_text = self._strip_think_tags(result)

            # 检查是否调用了 OCR（通过检查工具调用历史）
            for attr in ('_tool_call_history', 'tool_call_history', 'history'):
                history = getattr(self, attr, None)
                if history:
                    for tool_call in history:
                        name = (
                            tool_call.get('tool_name') or
                            tool_call.get('name') or
                            (tool_call.get('function', {}) or {}).get('name', '')
                        ) if isinstance(tool_call, dict) else getattr(tool_call, 'name', '')
                        if name == 'ocr_images':
                            self._ocr_called = True
                            break
                    break

            # 检查是否是无关信号（含 mark_unrelated 工具调用，LLM 可能只输出自然语言不含 __UNRELATED__）
            mark_unrelated_called = False
            for attr in ('_tool_call_history', 'tool_call_history', 'history'):
                history = getattr(self, attr, None)
                if history:
                    for tc in history:
                        name = (
                            tc.get('tool_name') or tc.get('name') or (tc.get('function') or {}).get('name', '')
                        ) if isinstance(tc, dict) else getattr(tc, 'name', '')
                        if name == 'mark_unrelated':
                            mark_unrelated_called = True
                            break
                    if mark_unrelated_called:
                        break
            
            # 检查是否输出了 unrelated 对象
            is_unrelated_obj = self._is_unrelated_object(result_text)
            
            if UNRELATED_SIGNAL in result_text or mark_unrelated_called or is_unrelated_obj:
                if MinerAgent._had_recent_failure:
                    self._append_devlog(
                        "solution",
                        "Miner 从失败状态恢复（当前任务成功判定为 unrelated）。",
                        {
                            "task_id": self._task_id,
                            "has_image": has_image,
                            "company": company,
                            "position": position,
                            "source_url": source_url,
                            "post_title": post_title,
                            "result_type": "unrelated",
                            "tags": ["miner", "recovery", "solution"],
                        },
                    )
                    MinerAgent._had_recent_failure = False
                logger.debug(f"[MinerAgent] 执行完成，输出长度: {len(result_text)}, ocr_called={self._ocr_called}, is_unrelated=True")
                return UNRELATED_SIGNAL, self._ocr_called, True

            # 如果 LLM 做了直接回复（未调用 Finish 工具）但结果中包含 JSON 数组，
            # 尝试从中提取 JSON 以避免整条记录被标记为 error
            result_text = self._extract_json_if_direct_reply(result_text)

            if not result_text:
                self._append_devlog(
                    "issue",
                    "Miner 执行返回空结果。",
                    {
                        "task_id": self._task_id,
                        "has_image": has_image,
                        "company": company,
                        "position": position,
                        "source_url": source_url,
                        "post_title": post_title,
                        "tags": ["miner", "empty-result", "issue"],
                    },
                )
                MinerAgent._had_recent_failure = True
            elif MinerAgent._had_recent_failure:
                self._append_devlog(
                    "solution",
                    "Miner 从失败状态恢复（当前任务返回有效结果）。",
                    {
                        "task_id": self._task_id,
                        "has_image": has_image,
                        "company": company,
                        "position": position,
                        "source_url": source_url,
                        "post_title": post_title,
                        "result_length": len(result_text),
                        "tags": ["miner", "recovery", "solution"],
                    },
                )
                MinerAgent._had_recent_failure = False

            logger.debug(f"[MinerAgent] 执行完成，输出长度: {len(result_text)}, ocr_called={self._ocr_called}, is_unrelated=False")
            return result_text, self._ocr_called, False

        except Exception as e:
            logger.error(f"[MinerAgent] 执行异常: {e}")
            self._append_devlog(
                "issue",
                "Miner 执行异常。",
                {
                    "task_id": self._task_id,
                    "has_image": has_image,
                    "company": company,
                    "position": position,
                    "source_url": source_url,
                    "post_title": post_title,
                    "error": str(e),
                    "tags": ["miner", "exception", "issue"],
                },
            )
            MinerAgent._had_recent_failure = True
            return "", self._ocr_called, False
        finally:
            if settings.miner_session_enabled:
                try:
                    self.save_session(_session_id)
                except Exception as _e:
                    logger.warning("[MinerAgent] save_session 失败（忽略）: %s", _e)

    def _execute_tool_call(self, tool_name: str, arguments):
        """统一记录 Miner 的工具调用统计（含子进程链路）。"""
        from backend.agents.context import get_current_user_id

        try:
            tool = self.tool_registry.get_tool(tool_name)
            if not tool:
                result = f"❌ 工具 {tool_name} 不存在"
                ok = False
                cost_ms = 0.0
            else:
                tool_response = tool.run_with_timing(arguments)
                result = tool_response.text
                ok = tool_execution_success_for_stats(
                    str(result),
                    response_status=getattr(tool_response, "status", None),
                )
                _stats = getattr(tool_response, "stats", None)
                _time_ms = _stats.get("time_ms") if isinstance(_stats, dict) else None
                cost_ms = float(_time_ms) if _time_ms is not None else 0.0
            agent_tool_runtime_stats.record(
                agent_name=self.name,
                tool_name=tool_name,
                success=ok,
                execution_time_ms=cost_ms,
                user_id=get_current_user_id(),
                params_input=arguments if isinstance(arguments, dict) else {},
            )
            return result
        except Exception:
            agent_tool_runtime_stats.record(
                agent_name=self.name,
                tool_name=tool_name,
                success=False,
                execution_time_ms=(time.time() - _t0) * 1000.0,
                user_id=get_current_user_id(),
            )
            raise

    @staticmethod
    def _is_unrelated_object(text: str) -> bool:
        """检查是否输出了 unrelated 对象 {"status":"unrelated",...}"""
        import json
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

    @staticmethod
    def _extract_json_if_direct_reply(text: str) -> str:
        """当 LLM 直接回复（未调用 Finish 工具）时，尝试从回复文本中提取 JSON 数组。
        如果提取到合法 JSON 数组则返回该数组字符串，否则返回空字符串（触发降级）。
        这是对「LLM 直接输出而非调用工具」行为的兜底处理。
        """
        import json, re
        # 已经是纯 JSON 数组，直接返回
        stripped = text.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            try:
                json.loads(stripped)
                return stripped  # 验证成功，直接返回
            except json.JSONDecodeError:
                pass
        
        # 去掉 markdown 代码块后尝试
        clean = re.sub(r'```(?:json)?\s*', '', stripped).strip().rstrip('`').strip()
        if clean.startswith('[') and clean.endswith(']'):
            try:
                json.loads(clean)
                return clean
            except json.JSONDecodeError:
                pass
        
        # 在文本中搜索第一个完整的 JSON 数组（贪婪匹配最长的 [...] 块）
        best = ''
        for m in re.finditer(r'\[', clean):
            start = m.start()
            depth, i, in_str, escape = 0, start, None, False
            while i < len(clean):
                c = clean[i]
                if in_str:
                    escape = (not escape and c == '\\')
                    if not escape and c == in_str:
                        in_str = None
                elif c in ('"', "'"):
                    in_str = c
                elif c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        candidate = clean[start:i + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, list) and len(candidate) > len(best):
                                best = candidate
                        except json.JSONDecodeError:
                            pass
                        break
                i += 1
        # 修复：无法提取有效 JSON 时返回空字符串，触发降级而非返回垃圾文本
        return best if best else ""

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """过滤推理模型的噪音标签/格式（DeepSeek-R1、qwen3 等模型）。"""
        # 去除 <think>...</think> 推理块
        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE)
        # 去除 qwen3 等模型输出的 \boxed{...} 格式（如 \boxed{No function call needed}）
        text = re.sub(r"\\boxed\{[^}]*\}", "", text)
        # 去除 "No function call needed" 等类似说明文字
        text = re.sub(
            r"(No function call needed\.?|无需函数调用\.?|任务不需要工具调用\.?|直接输出结果\.?)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        return text.strip()
