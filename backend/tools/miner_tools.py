"""
Miner Agent 工具箱
提供图片 OCR 识别工具，供 MinerAgent 在正文无题目时按需调用
"""
import logging
from typing import List, Dict, Any

from hello_agents.tools import Tool, ToolParameter

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
                "当正文内容太笼统（如只有寥寥数语）、无面试题可提取时，调用此工具获取图片中的文字内容，"
                "再从中提取面试题目。"
                "返回所有图片识别出的文字拼接结果。无图片时返回空字符串。"
            ),
        )
        self._image_paths = image_paths or []
        self._task_id = task_id

    def get_parameters(self) -> List[ToolParameter]:
        return []  # 图片路径由 Agent 初始化时注入，无需 LLM 传参

    def run(self, parameters: Dict[str, Any]) -> str:
        """执行 OCR，返回识别文字字符串（失败或无图片时返回空字符串）。"""
        if not self._image_paths:
            logger.info("[OcrTool] 无图片可识别")
            return ""

        logger.info(f"[OcrTool] 开始 OCR，共 {len(self._image_paths)} 张图片")
        try:
            from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
            result = ocr_images_to_text(self._image_paths, self._task_id)
            if result:
                logger.info(f"[OcrTool] OCR 成功，识别字符数: {len(result)}")
            else:
                logger.warning("[OcrTool] OCR 未识别到文字")
            return result or ""
        except Exception as e:
            logger.error(f"[OcrTool] OCR 失败: {e}")
            return ""
