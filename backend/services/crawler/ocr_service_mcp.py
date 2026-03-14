"""
图片 OCR 服务

支持三种 OCR 方式，通过 .env 的 OCR_METHOD 配置切换：

  ollama_vl     — 本地 Ollama 视觉模型（推荐，无需 API Key）
  qwen_vl       — 阿里云百炼 Qwen-VL（已有 EMBED_API_KEY 即可用）
  claude_vision — Anthropic Claude Vision API（需要 ANTHROPIC_API_KEY）

.env 示例：
    OCR_METHOD=ollama_vl        # 切换到本地 Ollama
    OCR_TIMEOUT=120             # 单张超时秒数
    OCR_RETRIES=3               # 失败/乱码重试次数
    OCR_MODEL=qwen3-vl:2b       # 可选，留空则自动选默认模型
"""
import logging
import base64
import re
import time
from typing import Optional, List
from pathlib import Path

from backend.config.config import settings

logger = logging.getLogger(__name__)


def _is_ocr_garbled(text: str) -> bool:
    """检测 OCR 结果是否可能为乱码（非中文/英文面经内容）"""
    if not text or not text.strip():
        return False
    t = text.strip()
    if len(t) < 5:
        return False  # 太短不判定
    chinese = len(re.findall(r"[\u4e00-\u9fff]", t))
    total = len(t)
    # 面经应为中文为主，若中文占比 < 15% 且总长 > 20，可能乱码（如阿拉伯文等）
    if total > 20 and chinese / total < 0.15:
        return True
    return False


# ──────────────────────────────────────────────────────────────
# 方式一：Ollama VL（本地视觉模型）
# ──────────────────────────────────────────────────────────────

def _call_ollama_vl_ocr(image_path: str, timeout: int = 120) -> Optional[str]:
    """
    使用本地 Ollama 视觉模型识别图片文字。
    默认使用 qwen3-vl:2b，无需 API Key。
    """
    model = settings.ocr_model or "qwen3-vl:2b"
    base_url = "http://localhost:11434/v1"

    try:
        from openai import OpenAI

        suffix = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        client = OpenAI(api_key="ollama", base_url=base_url, timeout=timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text",
                     "text": "请识别图片中的**所有**文字内容，按原文完整输出，**不要遗漏任何内容**。\n\n要求：\n1. 逐字逐句识别，包括题目编号、问题、答案、注释等所有文本\n2. 保持原文格式和换行\n3. 如果内容很长，也要完整输出，不要省略\n4. 特别注意：面试题目通常较长，请确保识别完整，不要中途截断"}
                ]
            }],
            max_tokens=8192,
        )
        return resp.choices[0].message.content

    except Exception as e:
        logger.error(f"[OCR-OllamaVL] 识别失败: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 方式二：Qwen-VL（阿里云百炼 / dashscope）
# ──────────────────────────────────────────────────────────────

def _call_qwen_vl_ocr(image_path: str, timeout: int = 120) -> Optional[str]:
    """
    使用阿里云百炼 Qwen-VL 系列模型识别图片文字。
    复用 EMBED_API_KEY（dashscope），无需额外配置。
    """
    api_key = settings.ocr_api_key
    if not api_key:
        logger.warning("[OCR-QwenVL] 未配置 API Key（OCR_API_KEY 或 EMBED_API_KEY）")
        return None

    model = settings.ocr_model or "qwen-vl-plus"
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    try:
        from openai import OpenAI

        suffix = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text",
                     "text": "请识别图片中的**所有**文字内容，按原文完整输出，**不要遗漏任何内容**。\n\n要求：\n1. 逐字逐句识别，包括题目编号、问题、答案、注释等所有文本\n2. 保持原文格式和换行\n3. 如果内容很长，也要完整输出，不要省略\n4. 特别注意：面试题目通常较长，请确保识别完整，不要中途截断"}
                ]
            }],
            max_tokens=8192,
        )
        return resp.choices[0].message.content

    except Exception as e:
        logger.error(f"[OCR-QwenVL] 识别失败: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 方式三：Claude Vision（Anthropic）
# ──────────────────────────────────────────────────────────────

def _call_claude_vision_ocr(image_path: str, timeout: int = 120) -> Optional[str]:
    """使用 Claude Vision API 识别图片文字。"""
    api_key = settings.anthropic_api_key
    if not api_key or api_key in ("your_anthropic_api_key_here", ""):
        logger.warning("[OCR-Claude] ANTHROPIC_API_KEY 未配置，跳过")
        return None

    try:
        import anthropic

        suffix = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        model = settings.ocr_model or "claude-3-5-sonnet-20241022"
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text",
                     "text": "请识别图片中的**所有**文字内容，按原文完整输出，**不要遗漏任何内容**。\n\n要求：\n1. 逐字逐句识别，包括题目编号、问题、答案、注释等所有文本\n2. 保持原文格式和换行\n3. 如果内容很长，也要完整输出，不要省略\n4. 特别注意：面试题目通常较长，请确保识别完整，不要中途截断"}
                ]
            }],
        )
        return message.content[0].text

    except Exception as e:
        logger.error(f"[OCR-Claude] 识别失败: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 统一入口
# ──────────────────────────────────────────────────────────────

def ocr_images_to_text(image_paths: List[str], task_id: str = "") -> str:
    """
    批量 OCR 本地图片，返回拼接后的文本。

    OCR 方式由 .env 的 OCR_METHOD 控制：
      ollama_vl     — 本地 Ollama 视觉模型（推荐）
      qwen_vl       — 阿里云百炼 Qwen-VL
      claude_vision — Claude Vision API

    Args:
        image_paths: 相对路径列表，如 ["TASK_XXX/0.jpg"]
        task_id: 任务 ID，仅用于日志

    Returns:
        拼接后的 OCR 文本，全部失败时返回空字符串
    """
    if not image_paths:
        return ""

    method = settings.ocr_method
    post_images_dir = settings.post_images_dir
    timeout = settings.ocr_timeout
    max_retries = settings.ocr_retries
    logger.info(f"[OCR] 方式={method}, 图片数={len(image_paths)}, timeout={timeout}s, retries={max_retries}, task={task_id}")

    # 预检 API Key（ollama_vl 不需要）
    if method == "qwen_vl" and not settings.ocr_api_key:
        logger.warning("[OCR] qwen_vl 模式但未配置 API Key，请设置 OCR_API_KEY 或 EMBED_API_KEY")
        return ""
    if method == "claude_vision" and not settings.anthropic_api_key:
        logger.warning("[OCR] claude_vision 模式但 ANTHROPIC_API_KEY 未配置")
        return ""

    def _do_ocr(path: str) -> Optional[str]:
        t = None
        if method == "ollama_vl":
            t = _call_ollama_vl_ocr(path, timeout)
        elif method == "claude_vision":
            t = _call_claude_vision_ocr(path, timeout)
        elif method == "qwen_vl":
            t = _call_qwen_vl_ocr(path, timeout)
        else:
            t = _call_ollama_vl_ocr(path, timeout)
        if not t and method == "claude_vision":
            t = _call_qwen_vl_ocr(path, timeout)
        elif not t and method == "qwen_vl":
            t = _call_claude_vision_ocr(path, timeout)
        return t

    results = []
    for idx, rel_path in enumerate(image_paths):
        if not rel_path or ".." in rel_path:
            continue
        full_path = post_images_dir / rel_path
        if not full_path.exists():
            logger.warning(f"[OCR] 跳过不存在的图片: {full_path}")
            continue

        text = None
        for attempt in range(max_retries + 1):
            try:
                text = _do_ocr(str(full_path))
                if text and text.strip():
                    if _is_ocr_garbled(text):
                        logger.warning(f"[OCR] 图片 {idx + 1} 疑似乱码（第 {attempt + 1}/{max_retries + 1} 次）: {text[:50]}...")
                        text = None
                        if attempt < max_retries:
                            time.sleep(1)
                        continue
                    break
                else:
                    if attempt < max_retries:
                        logger.warning(f"[OCR] 图片 {idx + 1} 未识别到文字，第 {attempt + 1}/{max_retries + 1} 次重试: {rel_path}")
                        time.sleep(1)
            except Exception as e:
                logger.warning(f"[OCR] 图片 {idx + 1} 第 {attempt + 1} 次失败: {e}")
                if attempt < max_retries:
                    time.sleep(1)

        if text and text.strip():
            results.append(f"[图片{idx + 1} OCR结果]\n{text.strip()}")
        else:
            logger.warning(f"[OCR] 图片 {idx + 1} 重试 {max_retries} 次后仍未识别到有效文字: {rel_path}")

    if not results:
        return ""

    logger.info(f"[OCR] 完成，成功识别 {len(results)}/{len(image_paths)} 张")
    return "\n\n".join(results)
