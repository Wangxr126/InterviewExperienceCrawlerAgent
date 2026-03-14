"""
Miner Agent V3 - 整合版（Few-shot + 结构化输出 + 两阶段提取）
支持三种模式：
1. 单阶段模式（原有逻辑，使用精简 Prompt + Few-shot）
2. 两阶段模式（粗提取 + 精加工）
3. 结构化输出模式（使用 Pydantic Schema 强制格式）
"""
import logging
import re
import json
from typing import List, Tuple, Optional, Literal

from hello_agents import ReActAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.core.config import Config as HelloAgentsConfig
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
from backend.tools.miner_tools import OcrImagesTool, MarkUnrelatedTool
from backend.agents.two_stage_miner_agent import TwoStageExtractor

logger = logging.getLogger(__name__)

UNRELATED_SIGNAL = "__UNRELATED__"


class MinerAgentV3(ReActAgent):
    """
    信息挖掘师 Agent V3（整合版）
    
    三种工作模式：
    1. single_stage: 单阶段提取（使用精简 Prompt + Few-shot）
    2. two_stage: 两阶段提取（粗提取 + 精加工）
    3. structured: 结构化输出（使用 Pydantic Schema）
    
    三种结束路径：
    1. LLM 调用 Finish（内置）   → 返回 (JSON字符串, ocr_called, False)
    2. LLM 调用 mark_unrelated  → 返回 (UNRELATED_SIGNAL, ocr_called, True)
    3. 超过最大步数/异常         → 返回 ("", ocr_called, False)
    """

    def __init__(
        self,
        image_paths: List[str] = None,
        task_id: str = "",
        mode: Literal["single_stage", "two_stage", "structured"] = "single_stage"
    ):
        """
        初始化 MinerAgentV3
        
        Args:
            image_paths: 图片路径列表
            task_id: 任务 ID
            mode: 工作模式
                - single_stage: 单阶段提取（默认，使用精简 Prompt + Few-shot）
                - two_stage: 两阶段提取（粗提取 + 精加工，效果最好但成本高）
                - structured: 结构化输出（使用 Pydantic Schema，格式最稳定）
        """
        self._image_paths = image_paths or []
        self._task_id = task_id
        self._ocr_called = False
        self._mode = mode
        
        # 如果是两阶段模式，使用专门的两阶段提取器
        if mode == "two_stage":
            self._two_stage_extractor = TwoStageExtractor(
                image_paths=self._image_paths,
                task_id=self._task_id
            )
            # 两阶段模式不需要初始化 ReActAgent
            logger.info(f"[MinerAgentV3] 初始化完成 mode=two_stage")
            return
        
        # 单阶段模式和结构化输出模式：初始化 ReActAgent
        llm = HelloAgentsLLM(
            model=settings.miner_model,
            api_key=settings.miner_api_key,
            base_url=settings.miner_base_url,
            temperature=settings.miner_temperature,
            timeout=settings.miner_timeout,
        )

        registry = ToolRegistry()
        registry.register_tool(OcrImagesTool(image_paths=self._image_paths, task_id=self._task_id))
        registry.register_tool(MarkUnrelatedTool())

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

        max_steps = settings.miner_max_steps

        super().__init__(
            name="Miner Agent V3",
            llm=llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),  # 使用 miner_prompt（含 Few-shot 示例）
            max_steps=max_steps,
            config=_agent_config,
        )

        logger.info(
            f"[MinerAgentV3] 初始化完成 model={settings.miner_model} "
            f"mode={mode} max_steps={max_steps}"
        )

    def run(
        self,
        content: str,
        has_image: bool = False,
        company: str = "",
        position: str = "",
        user_input_override: str = None
    ) -> Tuple[str, bool, bool]:
        """
        运行 MinerAgentV3
        
        Args:
            content: 面经正文
            has_image: 是否有图片
            company: 公司名称
            position: 岗位名称
            user_input_override: 直接覆盖用户输入（用于重试时注入纠错指令）

        Returns:
            (answer, ocr_called, is_unrelated)
            - answer: JSON字符串（有题）/ UNRELATED_SIGNAL（无关）/ ""（失败）
            - ocr_called: 是否调用了 ocr_images
            - is_unrelated: LLM 是否主动调用了 mark_unrelated
        """
        # 两阶段模式：使用专门的两阶段提取器（支持重试时注入纠错指令）
        if self._mode == "two_stage":
            return self._two_stage_extractor.extract(
                content, has_image, company, position,
                user_input_override=user_input_override,
            )
        
        # 单阶段模式和结构化输出模式：使用 ReActAgent
        user_input = user_input_override or format_miner_user_prompt(
            content, has_image, company, position
        )

        self._ocr_called = False

        try:
            # 结构化输出模式：使用 Pydantic Schema（如果 LLM 支持）
            if self._mode == "structured":
                result = self._run_with_structured_output(user_input)
            else:
                # 单阶段模式：正常调用
                result = super().run(user_input)

            result_text = self._strip_think_tags(result)

            # 检查是否调用了 OCR
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
            if UNRELATED_SIGNAL in result_text or mark_unrelated_called:
                logger.debug(
                    f"[MinerAgentV3] 执行完成 mode={self._mode} "
                    f"ocr_called={self._ocr_called} is_unrelated=True"
                )
                return UNRELATED_SIGNAL, self._ocr_called, True

            # 提取 JSON
            result_text = self._extract_json_if_direct_reply(result_text)

            logger.debug(
                f"[MinerAgentV3] 执行完成 mode={self._mode} "
                f"output_length={len(result_text)} ocr_called={self._ocr_called}"
            )
            return result_text, self._ocr_called, False

        except Exception as e:
            logger.error(f"[MinerAgentV3] 执行异常: {e}")
            return "", self._ocr_called, False

    def _run_with_structured_output(self, user_input: str) -> str:
        """
        使用结构化输出模式运行（Pydantic Schema）
        
        注意：这需要 LLM 支持 response_format 参数（如 OpenAI GPT-4o）
        如果不支持，会降级到普通模式
        """
        try:
            from backend.agents.schemas.miner_schema import QuestionListSchema
            
            # 检查 LLM 是否支持结构化输出
            if not hasattr(self.llm, 'supports_structured_output') or \
               not self.llm.supports_structured_output():
                logger.warning(
                    "[MinerAgentV3] LLM 不支持结构化输出，降级到普通模式"
                )
                return super().run(user_input)
            
            # 使用结构化输出
            logger.info("[MinerAgentV3] 使用结构化输出模式")
            
            # 构建带 Schema 的提示词
            schema_prompt = f"""{user_input}

## 输出格式（结构化）
你的输出必须严格符合以下 JSON Schema：
{QuestionListSchema.model_json_schema()}

每个题目必须包含：
- question_text（至少 5 字）
- answer_text（至少 10 字）
- difficulty（easy/medium/hard）
- question_type（算法类/AI类/工程类/基础类/软技能）
- topic_tags（2-4 个标签）
- company（公司全称或空字符串）
- position（岗位名称或空字符串）
"""
            
            # 调用 LLM（带结构化输出）
            result = self.llm.chat_with_schema(
                messages=[{"role": "user", "content": schema_prompt}],
                schema=QuestionListSchema
            )
            
            # 解析结果
            if isinstance(result, str):
                return result
            elif hasattr(result, 'model_dump_json'):
                return result.model_dump_json()
            else:
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"[MinerAgentV3] 结构化输出失败: {e}，降级到普通模式")
            return super().run(user_input)

    @staticmethod
    def _extract_json_if_direct_reply(text: str) -> str:
        """提取 JSON 数组"""
        import json, re
        stripped = text.strip()
        if stripped.startswith('['):
            return stripped
        clean = re.sub(r'```(?:json)?\s*', '', stripped).strip().rstrip('`').strip()
        if clean.startswith('['):
            return clean
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
        """过滤推理模型的噪音标签"""
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


# ============================================================================
# 工厂函数：根据配置创建 MinerAgent
# ============================================================================

def create_miner_agent(
    image_paths: List[str] = None,
    task_id: str = "",
    mode: Optional[Literal["single_stage", "two_stage", "structured"]] = None
) -> MinerAgentV3:
    """
    创建 MinerAgent（工厂函数）
    
    Args:
        image_paths: 图片路径列表
        task_id: 任务 ID
        mode: 工作模式（None 时从配置读取）
            - single_stage: 单阶段提取（默认，使用精简 Prompt + Few-shot）
            - two_stage: 两阶段提取（粗提取 + 精加工，效果最好但成本高）
            - structured: 结构化输出（使用 Pydantic Schema，格式最稳定）
    
    Returns:
        MinerAgentV3 实例
    """
    # 从配置读取模式（如果未指定）
    if mode is None:
        mode = getattr(settings, 'miner_mode', 'single_stage')
    
    return MinerAgentV3(
        image_paths=image_paths,
        task_id=task_id,
        mode=mode
    )
