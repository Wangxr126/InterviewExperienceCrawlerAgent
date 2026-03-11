"""
Miner Agent 工具箱
提供三个工具：OCR识别、标记无关、完成提取
"""
import logging
from typing import List, Dict, Any

from hello_agents.tools import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse

logger = logging.getLogger(__name__)


class OcrImagesTool(Tool):
    """
    图片 OCR 识别工具。
    当面经正文内容过于笼统、无法提取题目时，调用此工具识别图片中的文字，
    再尝试从图片内容中提取面试题。
    run() 返回字符串（空字符串表示无内容或失败）。
    """

    def __init__(self, image_paths: List[str] = None, task_id: str = ""):
        super().__init__(
            name="ocr_images",
            description=(
                "对面经帖子中的图片进行 OCR 文字识别。"
                "调用时机：正文内容无有效面试题 且 有图片时调用。"
                "返回所有图片识别出的文字拼接结果，供后续提取面试题使用。"
                "无图片或识别失败时返回空字符串。"
            ),
        )
        self._image_paths = image_paths or []
        self._task_id = task_id

    def get_parameters(self) -> List[ToolParameter]:
        return []  # 图片路径由 Agent 初始化时注入，无需 LLM 传参

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        """执行 OCR，返回 ToolResponse 对象。"""
        if not self._image_paths:
            logger.info("[OcrTool] 无图片可识别")
            return ToolResponse.success(text="", data={"image_count": 0})

        logger.info(f"[OcrTool] 开始 OCR，共 {len(self._image_paths)} 张图片")
        try:
            from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
            result = ocr_images_to_text(self._image_paths, self._task_id)
            if result:
                logger.info(f"[OcrTool] OCR 成功，识别字符数: {len(result)}")
                return ToolResponse.success(
                    text=result,
                    data={"image_count": len(self._image_paths), "char_count": len(result)}
                )
            else:
                logger.warning("[OcrTool] OCR 未识别到文字")
                return ToolResponse.success(text="", data={"image_count": len(self._image_paths), "char_count": 0})
        except Exception as e:
            logger.error(f"[OcrTool] OCR 失败: {e}")
            return ToolResponse.error(code="OCR_FAILED", message=f"OCR 执行失败: {str(e)}")


class MarkUnrelatedTool(Tool):
    """
    标记无关帖子工具（终止工具）。
    当正文和图片均无面试题时调用，标记后任务立即结束。
    """

    def __init__(self):
        super().__init__(
            name="mark_unrelated",
            description=(
                "【终止操作】标记当前帖子与面经无关（如求内推、纯吐槽、广告、生活分享等）。"
                "调用时机：① 正文无题且无图片；② 正文无题且 OCR 后图片也无题。"
                "调用后任务立即结束，无需再调用其他工具。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="reason",
                type="string",
                description="判定无关的简短原因，如：求内推帖、纯情绪吐槽、广告、无技术内容",
                required=False,
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        """返回特殊信号，由 MinerAgent 识别并处理"""
        reason = parameters.get("reason", "LLM判断无关")
        logger.info(f"[MarkUnrelatedTool] 标记无关: {reason}")
        return ToolResponse.success(text="__UNRELATED__", data={"reason": reason})


class FinishTool(Tool):
    """
    完成提取工具（终止工具）。
    提取到面试题后调用此工具返回结果，任务立即结束。
    """

    def __init__(self):
        super().__init__(
            name="Finish",
            description=(
                "【终止操作】提取到面试题后调用此工具返回结果。"
                "调用时机：正文或 OCR 中找到了有效面试题。"
                "answer 参数必须是 JSON 数组字符串，每项必须包含以下字段（字段名必须完全一致）："
                "question_text（问题文本）、answer_text（答案文本）、difficulty（难度）、"
                "question_type（题目类型）、topic_tags（标签数组）、company（公司）、position（岗位）。"
                "示例：[{\"question_text\":\"Redis持久化方式有哪些？\",\"answer_text\":\"RDB和AOF\","
                "\"difficulty\":\"medium\",\"question_type\":\"基础类\",\"topic_tags\":[\"Redis\",\"持久化\"],"
                "\"company\":\"字节跳动\",\"position\":\"后端开发\"}]"
                "调用后任务立即结束，无需再调用其他工具。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="answer",
                type="string",
                description="JSON 数组字符串，包含所有提取到的面试题。",
                required=True,
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        """返回提取结果"""
        answer = parameters.get("answer", "")
        logger.debug(f"[FinishTool] 提取完成，结果长度: {len(answer)}")
        return ToolResponse.success(text=answer, data={"answer": answer})
