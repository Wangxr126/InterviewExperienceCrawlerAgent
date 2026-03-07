"""
图片 OCR 服务

当正文提取不到题目时，尝试从帖子图片中识别文字，供 LLM 再次提取。
使用 EasyOCR 本地识别，不依赖 LLM Vision API。
"""
import logging
from typing import List

from backend.config.config import settings

logger = logging.getLogger(__name__)

_reader = None


def _get_reader():
    """懒加载 EasyOCR Reader（首次调用时下载模型，约 100MB）"""
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
        except Exception as e:
            logger.error(f"EasyOCR 初始化失败: {e}，请确保已安装: pip install easyocr")
            raise
    return _reader


def ocr_images_to_text(image_paths: List[str], task_id: str = "") -> str:
    """
    对本地图片进行 OCR，返回识别出的文本。

    Args:
        image_paths: 相对路径列表，如 ["TASK_XXX/0.jpg", "TASK_XXX/1.png"]
        task_id: 任务 ID，用于日志

    Returns:
        拼接后的 OCR 文本，失败时返回空字符串
    """
    if not image_paths:
        return ""

    post_images_dir = settings.post_images_dir
    results = []

    try:
        reader = _get_reader()
    except Exception:
        return ""

    for idx, rel_path in enumerate(image_paths):
        if not rel_path or ".." in rel_path:
            continue
        full_path = post_images_dir / rel_path
        if not full_path.exists():
            logger.warning(f"OCR 跳过不存在的图片: {full_path}")
            continue

        try:
            detections = reader.readtext(str(full_path))
            # detections: [(bbox, text, confidence), ...]
            lines = [item[1] for item in detections if item[1].strip()]
            text = "\n".join(lines).strip()
            if text:
                results.append(f"[图片{idx + 1} OCR结果]\n{text}")
        except Exception as e:
            logger.warning(f"OCR 单张失败 {rel_path}: {e}")

    if not results:
        return ""
    return "\n\n".join(results)
