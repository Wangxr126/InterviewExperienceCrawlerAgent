"""
图片 OCR 服务

支持三种 OCR 方式，通过 .env 的 OCR_METHOD 配置切换：

  qwen_vl       — 阿里云百炼 Qwen-VL（推荐，已有 EMBED_API_KEY 即可用）
  claude_vision — Anthropic Claude Vision API（需要 ANTHROPIC_API_KEY）
  mcp           — 本地 mcp-image-extractor（本地 Node.js 服务，无需 API Key）

.env 示例：
    OCR_METHOD=qwen_vl          # 切换到 Qwen-VL
    OCR_MODEL=qwen-vl-plus      # 可选，留空则自动选默认模型
    OCR_API_KEY=sk-xxx          # 可选，留空则复用 EMBED_API_KEY
"""
import logging
import json
import base64
import subprocess
import sys
from typing import Optional, List
from pathlib import Path

from backend.config.config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 方式一：Qwen-VL（阿里云百炼 / dashscope）
# ──────────────────────────────────────────────────────────────

def _call_qwen_vl_ocr(image_path: str) -> Optional[str]:
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

        # 读取图片转 base64
        suffix = Path(image_path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/jpeg")

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text",
                     "text": "请识别图片中的所有文字内容，按原文输出。如果是面试题目，请完整提取题目和答案。"}
                ]
            }],
            max_tokens=2048,
        )
        return resp.choices[0].message.content

    except Exception as e:
        logger.error(f"[OCR-QwenVL] 识别失败: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 方式二：Claude Vision（Anthropic）
# ──────────────────────────────────────────────────────────────

def _call_claude_vision_ocr(image_path: str) -> Optional[str]:
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
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": mime, "data": b64}},
                    {"type": "text",
                     "text": "请识别图片中的所有文字内容，按原文输出。如果是面试题目，请完整提取题目和答案。"}
                ]
            }],
        )
        return message.content[0].text

    except Exception as e:
        logger.error(f"[OCR-Claude] 识别失败: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# 方式三：本地 mcp-image-extractor（Node.js MCP server）
# ──────────────────────────────────────────────────────────────

def _call_mcp_ocr(image_path: str) -> Optional[str]:
    """
    通过本地 mcp-image-extractor MCP server 提取图片 base64，
    再调用当前配置的视觉模型（qwen_vl / claude_vision）做 OCR。

    mcp-image-extractor 负责：图片读取 + 压缩缩放到 512x512
    视觉模型负责：实际文字识别
    """
    index_js = settings.mcp_image_extractor_path
    if not Path(index_js).exists():
        logger.error(f"[OCR-MCP] mcp-image-extractor 不存在: {index_js}")
        logger.error("请先在 mcp/mcp-image-extractor 目录执行: npm run build")
        return None

    # MCP 会话：initialize → tools/call extract_image_from_file
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "ocr-client", "version": "1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "extract_image_from_file",
                    "arguments": {"file_path": str(Path(image_path).resolve())}}},
    ]
    stdin_data = "\n".join(json.dumps(m) for m in messages) + "\n"

    try:
        result = subprocess.run(
            ["node", index_js],
            input=stdin_data, capture_output=True,
            text=True, timeout=30, encoding="utf-8"
        )
    except subprocess.TimeoutExpired:
        logger.error("[OCR-MCP] mcp-image-extractor 超时")
        return None
    except Exception as e:
        logger.error(f"[OCR-MCP] 启动失败: {e}")
        return None

    # 解析 MCP 响应，找 id=2 的结果
    meta = None
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            resp = json.loads(line)
            if resp.get("id") == 2:
                content = resp.get("result", {}).get("content", [])
                if content:
                    meta_text = content[0].get("text", "")
                    try:
                        meta = json.loads(meta_text)
                    except Exception:
                        meta = {"raw": meta_text}
                break
        except json.JSONDecodeError:
            continue

    if not meta:
        logger.warning("[OCR-MCP] 未获取到图片信息")
        return None

    logger.info(f"[OCR-MCP] 图片元数据: {meta}")

    # mcp-image-extractor 将图片缩放后存为临时文件或只返回元数据
    # 2.0.0 版本返回元数据，实际图片仍在原路径，直接用原图调用视觉模型
    # 回退到 qwen_vl 或 claude_vision 做识别
    logger.info("[OCR-MCP] 调用视觉模型识别...")
    text = _call_qwen_vl_ocr(image_path)
    if not text:
        text = _call_claude_vision_ocr(image_path)
    return text


# ──────────────────────────────────────────────────────────────
# 统一入口
# ──────────────────────────────────────────────────────────────

def ocr_images_to_text(image_paths: List[str], task_id: str = "") -> str:
    """
    批量 OCR 本地图片，返回拼接后的文本。

    OCR 方式由 .env 的 OCR_METHOD 控制：
      qwen_vl       — 阿里云百炼 Qwen-VL（推荐）
      claude_vision — Claude Vision API
      mcp           — 本地 mcp-image-extractor + 视觉模型

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
    logger.info(f"[OCR] 方式={method}, 图片数={len(image_paths)}, task={task_id}")

    # 预检 API Key
    if method == "qwen_vl" and not settings.ocr_api_key:
        logger.warning("[OCR] qwen_vl 模式但未配置 API Key，请设置 OCR_API_KEY 或 EMBED_API_KEY")
        return ""
    if method == "claude_vision" and not settings.anthropic_api_key:
        logger.warning("[OCR] claude_vision 模式但 ANTHROPIC_API_KEY 未配置")
        return ""

    results = []
    for idx, rel_path in enumerate(image_paths):
        if not rel_path or ".." in rel_path:
            continue
        full_path = post_images_dir / rel_path
        if not full_path.exists():
            logger.warning(f"[OCR] 跳过不存在的图片: {full_path}")
            continue

        try:
            text = None
            if method == "qwen_vl":
                text = _call_qwen_vl_ocr(str(full_path))
            elif method == "claude_vision":
                text = _call_claude_vision_ocr(str(full_path))
            elif method == "mcp":
                text = _call_mcp_ocr(str(full_path))
            else:
                logger.warning(f"[OCR] 未知方式: {method}，回退到 qwen_vl")
                text = _call_qwen_vl_ocr(str(full_path))

            # 失败时依次回退
            if not text and method != "qwen_vl":
                logger.info(f"[OCR] {method} 失败，回退到 qwen_vl")
                text = _call_qwen_vl_ocr(str(full_path))
            if not text and method != "claude_vision":
                logger.info(f"[OCR] 回退到 claude_vision")
                text = _call_claude_vision_ocr(str(full_path))

            if text and text.strip():
                results.append(f"[图片{idx + 1} OCR结果]\n{text.strip()}")
            else:
                logger.warning(f"[OCR] 图片 {idx + 1} 未识别到文字: {rel_path}")

        except Exception as e:
            logger.warning(f"[OCR] 单张失败 {rel_path}: {e}")

    if not results:
        return ""

    logger.info(f"[OCR] 完成，成功识别 {len(results)}/{len(image_paths)} 张")
    return "\n\n".join(results)
