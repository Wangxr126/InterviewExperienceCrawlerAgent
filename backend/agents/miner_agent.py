"""
Miner Agent - 信息挖掘师（ReAct版）
职责：从面经原文中智能挖掘结构化信息

使用 hello-agents 框架的 ReActAgent，内置 Thought + Finish 工具。
按框架 16 项能力配置：Trace、熔断器、工具截断、TodoWrite、DevLog、子代理等。
"""
import logging
import re
from typing import List, Tuple

from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
from backend.tools.miner_tools import OcrImagesTool, MarkUnrelatedTool

logger = logging.getLogger(__name__)

# mark_unrelated 的特殊返回标记
UNRELATED_SIGNAL = "__UNRELATED__"


class MinerAgent(ReActAgent):
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

        # 构建 LLM
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
        registry.register_tool(MarkUnrelatedTool())

        # ── hello-agents Config（对齐框架 16 项能力）────────────────────
        _data_dir = str(settings.backend_data_dir / "memory")
        _skills_dir = str(settings.backend_data_dir.parent.parent / ".claude" / "skills")
        _agent_config = HelloAgentsConfig(
            # 可观测性
            trace_enabled=True,
            trace_dir=f"{_data_dir}/traces",
            trace_sanitize=True,
            # Miner 为单次任务，无会话持久化
            session_enabled=False,
            # 上下文工程（单次提取输入较短，保留默认）
            context_window=128000,
            compression_threshold=0.8,
            min_retain_rounds=5,
            # TodoWrite + DevLog（多步提取可记录进度）
            todowrite_enabled=True,
            todowrite_persistence_dir=f"{_data_dir}/todos",
            devlog_enabled=True,
            devlog_persistence_dir=f"{_data_dir}/devlogs",
            # Skills（可选，面经提取可复用）
            skills_enabled=True,
            skills_dir=_skills_dir,
            skills_auto_register=True,
            # 熔断器（OCR/LLM 失败时自动熔断）
            circuit_enabled=True,
            circuit_failure_threshold=3,
            # 工具输出截断（OCR 结果可能很长）
            tool_output_max_lines=500,
            tool_output_max_bytes=20480,
            tool_output_dir=f"{_data_dir}/tool-output",
            # 子代理（TaskTool，可选）
            subagent_enabled=False,
            # 异步
            async_enabled=True,
            max_concurrent_tools=2,
        )

        max_steps = getattr(settings, "miner_max_steps", 5)

        # 初始化父类（ReActAgent）
        super().__init__(
            name="Miner Agent",
            llm=llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),
            max_steps=max_steps,
            config=_agent_config,
        )

        logger.info(
            f"[MinerAgent] 初始化完成 model={settings.miner_model} "
            f"max_steps={max_steps} trace_enabled"
        )

    def run(self, content: str, has_image: bool = False, company: str = "", position: str = "",
              user_input_override: str = None) -> Tuple[str, bool, bool]:
        """
        运行 MinerAgent。

        Args:
            content: 面经正文
            has_image: 是否有图片
            company: 公司名称
            position: 岗位名称
            user_input_override: 直接覆盖用户输入（用于重试时注入纠错指令），为 None 时自动格式化

        Returns:
            (answer, ocr_called, is_unrelated)
            - answer       : JSON字符串（有题）/ UNRELATED_SIGNAL（无关）/ ""（失败）
            - ocr_called   : 是否调用了 ocr_images
            - is_unrelated : LLM 是否主动调用了 mark_unrelated
        """
        # 格式化用户输入（重试时使用外部传入的 override，含纠错指令）
        user_input = user_input_override or format_miner_user_prompt(content, has_image, company, position)

        # 重置状态
        self._ocr_called = False

        try:
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

            # 检查是否是无关信号
            if UNRELATED_SIGNAL in result_text:
                logger.debug(f"[MinerAgent] 执行完成，输出长度: {len(result_text)}, ocr_called={self._ocr_called}, is_unrelated=True")
                return UNRELATED_SIGNAL, self._ocr_called, True

            # 如果 LLM 做了直接回复（未调用 Finish 工具）但结果中包含 JSON 数组，
            # 尝试从中提取 JSON 以避免整条记录被标记为 error
            result_text = self._extract_json_if_direct_reply(result_text)

            logger.debug(f"[MinerAgent] 执行完成，输出长度: {len(result_text)}, ocr_called={self._ocr_called}, is_unrelated=False")
            return result_text, self._ocr_called, False

        except Exception as e:
            logger.error(f"[MinerAgent] 执行异常: {e}")
            return "", self._ocr_called, False

    @staticmethod
    def _extract_json_if_direct_reply(text: str) -> str:
        """当 LLM 直接回复（未调用 Finish 工具）时，尝试从回复文本中提取 JSON 数组。
        如果提取到合法 JSON 数组则返回该数组字符串，否则返回原文。
        这是对「LLM 直接输出而非调用工具」行为的兜底处理。
        """
        import json, re
        # 已经是纯 JSON 数组，直接返回
        stripped = text.strip()
        if stripped.startswith('['):
            return stripped
        # 去掉 markdown 代码块后尝试
        clean = re.sub(r'```(?:json)?\s*', '', stripped).strip().rstrip('`').strip()
        if clean.startswith('['):
            return clean
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
        return best if best else text

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
