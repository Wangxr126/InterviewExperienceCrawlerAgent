"""
Miner Agent - 信息挖掘师（框架托管版）
职责：从面经原文中智能挖掘结构化信息

使用 hello-agents 框架的 SimpleAgent，工具描述由框架自动注入
"""
import logging
import re
from typing import List, Tuple

from hello_agents import SimpleAgent
from hello_agents.core.llm import HelloAgentsLLM
from hello_agents.tools import ToolRegistry

from backend.config.config import settings
from backend.agents.prompts.miner_prompt import get_miner_prompt, format_miner_user_prompt
from backend.tools.miner_tools import OcrImagesTool, MarkUnrelatedTool, FinishTool

logger = logging.getLogger(__name__)

# mark_unrelated 的特殊返回标记
UNRELATED_SIGNAL = "__UNRELATED__"


class MinerAgent(SimpleAgent):
    """
    信息挖掘师 Agent（框架托管版）

    三种结束路径：
    1. LLM 调用 Finish         → 返回 (JSON字符串, ocr_called, False)
    2. LLM 调用 mark_unrelated → 返回 (UNRELATED_SIGNAL, ocr_called, True)
    3. 超过最大步数/异常       → 返回 ("", ocr_called, False)
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

        # 注册工具
        registry = ToolRegistry()
        registry.register_tool(OcrImagesTool(image_paths=self._image_paths, task_id=self._task_id))
        registry.register_tool(MarkUnrelatedTool())
        registry.register_tool(FinishTool())

        # 初始化父类
        max_steps = getattr(settings, "miner_max_steps", 5)
        super().__init__(
            name="Miner Agent",
            llm=llm,
            tool_registry=registry,
            system_prompt=get_miner_prompt(),
            max_tool_iterations=max_steps,
        )

        # logger.info(f"[MinerAgent] 实例已创建（LLM 客户端将复用）")

    def run(self, content: str, has_image: bool = False, company: str = "", position: str = "") -> Tuple[str, bool, bool]:
        """
        运行 MinerAgent。

        Args:
            content: 面经正文
            has_image: 是否有图片
            company: 公司名称
            position: 岗位名称

        Returns:
            (answer, ocr_called, is_unrelated)
            - answer       : JSON字符串（有题）/ UNRELATED_SIGNAL（无关）/ ""（失败）
            - ocr_called   : 是否调用了 ocr_images
            - is_unrelated : LLM 是否主动调用了 mark_unrelated
        """
        # 格式化用户输入
        user_input = format_miner_user_prompt(content, has_image, company, position)

        # 重置状态
        self._ocr_called = False

        try:
            # 调用父类的 run 方法（框架自动处理工具循环）
            result = super().run(user_input)

            # 解析结果
            result_text = self._strip_think_tags(result)

            # 检查是否调用了 OCR（通过检查工具调用历史）
            if hasattr(self, '_tool_call_history'):
                for tool_call in self._tool_call_history:
                    if tool_call.get('tool_name') == 'ocr_images':
                        self._ocr_called = True
                        break

            # 检查是否是无关信号
            if UNRELATED_SIGNAL in result_text:
                logger.debug(f"[MinerAgent] 执行完成，输出长度: {len(result_text)}, ocr_called={self._ocr_called}, is_unrelated=True")
                return UNRELATED_SIGNAL, self._ocr_called, True

            logger.debug(f"[MinerAgent] 执行完成，输出长度: {len(result_text)}, ocr_called={self._ocr_called}, is_unrelated=False")
            return result_text, self._ocr_called, False

        except Exception as e:
            logger.error(f"[MinerAgent] 执行异常: {e}")
            return "", self._ocr_called, False

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        """过滤 <think>...</think> 推理标签（DeepSeek-R1 等模型）。"""
        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE)
        return text.strip()
