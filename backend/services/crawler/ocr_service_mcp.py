"""
图片 OCR 服务 - MCP 版本

使用 MCP (Model Context Protocol) 调用图片识别服务
支持多种 OCR 提供商（通过 MCP 服务器）
"""
import logging
import json
import subprocess
from typing import List, Optional
from pathlib import Path

from backend.config.config import settings

logger = logging.getLogger(__name__)


def _call_mcp_ocr(image_path: str) -> Optional[str]:
    """
    通过 MCP 调用 OCR 服务
    
    Args:
        image_path: 图片的完整路径
        
    Returns:
        识别出的文本，失败返回 None
    """
    try:
        # 使用 MCP 客户端调用 OCR 工具
        # 这里假设你有一个 MCP OCR 服务器正在运行
        # 可以是 Claude Desktop 的 MCP 服务，或者自定义的 MCP 服务器
        
        # 方案1：使用 Claude API 的 Vision 功能（通过 MCP）
        # 方案2：使用专门的 OCR MCP 服务器（如 Tesseract MCP、PaddleOCR MCP）
        
        # 这里提供一个通用的 MCP 调用示例
        mcp_command = [
            "mcp",  # MCP 客户端命令
            "call",
            "--server", settings.mcp_ocr_server or "ocr-server",  # MCP 服务器名称
            "--tool", "ocr_image",  # OCR 工具名称
            "--args", json.dumps({"image_path": str(image_path)})
        ]
        
        result = subprocess.run(
            mcp_command,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            response = json.loads(result.stdout)
            return response.get("text", "")
        else:
            logger.warning(f"MCP OCR 调用失败: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"MCP OCR 调用异常: {e}")
        return None


def _call_claude_vision_ocr(image_path: str) -> Optional[str]:
    """
    使用 Claude Vision API 进行 OCR
    
    这是一个备选方案，直接调用 Claude API 的 Vision 功能
    """
    try:
        import anthropic
        import base64
        
        # 读取图片并转为 base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        # 判断图片类型
        suffix = Path(image_path).suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(suffix, "image/jpeg")
        
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "请识别图片中的所有文字内容，按原文输出。如果是面试题目，请完整提取题目和答案。"
                        }
                    ],
                }
            ],
        )
        
        return message.content[0].text
        
    except Exception as e:
        logger.error(f"Claude Vision OCR 失败: {e}")
        return None


def ocr_images_to_text(image_paths: List[str], task_id: str = "") -> str:
    """
    对本地图片进行 OCR，返回识别出的文本。
    
    优先使用 MCP OCR 服务，失败时回退到 Claude Vision API

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
    
    # 选择 OCR 方法
    ocr_method = getattr(settings, 'ocr_method', 'claude_vision')  # 默认使用 Claude Vision
    
    logger.info(f"使用 OCR 方法: {ocr_method}")

    for idx, rel_path in enumerate(image_paths):
        if not rel_path or ".." in rel_path:
            continue
        full_path = post_images_dir / rel_path
        if not full_path.exists():
            logger.warning(f"OCR 跳过不存在的图片: {full_path}")
            continue

        try:
            text = None
            
            # 尝试 MCP OCR
            if ocr_method == 'mcp':
                text = _call_mcp_ocr(str(full_path))
            
            # 回退到 Claude Vision
            if not text and ocr_method in ['claude_vision', 'mcp']:
                logger.info(f"使用 Claude Vision API 识别图片 {idx + 1}")
                text = _call_claude_vision_ocr(str(full_path))
            
            if text and text.strip():
                results.append(f"[图片{idx + 1} OCR结果]\n{text.strip()}")
            else:
                logger.warning(f"图片 {idx + 1} 未识别到文字")
                
        except Exception as e:
            logger.warning(f"OCR 单张失败 {rel_path}: {e}")

    if not results:
        return ""
    
    logger.info(f"OCR 完成，识别到 {len(results)} 张图片的文字")
    return "\n\n".join(results)
