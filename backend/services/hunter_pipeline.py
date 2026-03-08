"""
HunterPipeline —— 纯代码驱动的内容采集管道

替换原来由 HunterAgent（ReAct LLM）控制的流程。
原则：所有"是否做某事"的判断都是确定性规则，不依赖 LLM 编排。
LLM 仅在 MetaExtractor 对规则无法覆盖的情况下作为兜底使用。

管道步骤（代码固定顺序）：
  Step 1  爬取   CrawlerTool
  Step 2  清洗   TextSanitizer
  Step 3  校验   ContentValidator（规则判断：是否相关、是否需要 OCR）
  Step 4  OCR    VisualExtractor（仅在 Step 3 返回 needs_ocr=True 时执行）
  Step 5  元信息  MetaExtractor（规则优先，LLM 兜底）
  ─────────────────────────────────────────────
  Step 6  结构化  由 ArchitectAgent 负责（仍保留 LLM，因为需要语义理解）
"""

import json
import logging
from typing import Optional, Dict, Any

from backend.tools.hunter_tools import CrawlerTool, TextSanitizer, ContentValidator, VisualExtractor
from backend.tools.knowledge_manager_tools import MetaExtractor

logger = logging.getLogger(__name__)

# 懒加载单例，避免每次 pipeline 运行都重新实例化工具
_crawler = None
_sanitizer = None
_validator = None
_ocr = None
_meta_extractor = None


def _get_tools():
    global _crawler, _sanitizer, _validator, _ocr, _meta_extractor
    if _crawler is None:
        _crawler = CrawlerTool()
        _sanitizer = TextSanitizer()
        _validator = ContentValidator()
        _ocr = VisualExtractor()
        _meta_extractor = MetaExtractor()
    return _crawler, _sanitizer, _validator, _ocr, _meta_extractor


class HunterPipelineResult:
    """管道最终产物，传给 ArchitectAgent 做结构化"""

    def __init__(self):
        self.success: bool = False
        self.skip_reason: Optional[str] = None   # 跳过原因（不相关/爬取失败）
        self.text: str = ""                       # 最终清洗（+可能含 OCR 补充）后的文本
        self.meta: Dict[str, Any] = {}            # 元信息（company/position/difficulty...）
        self.ocr_triggered: bool = False          # 是否触发了 OCR
        self.image_count: int = 0

    def __repr__(self):
        return (f"HunterPipelineResult(success={self.success}, "
                f"ocr={self.ocr_triggered}, images={self.image_count}, "
                f"text_len={len(self.text)}, meta={self.meta})")


async def run_hunter_pipeline(url: str,
                               source_platform: str = "") -> HunterPipelineResult:
    """
    执行完整的内容采集管道。
    这是一个纯确定性函数：每步是否执行由代码规则决定，不通过 LLM 编排。

    Args:
        url:             目标页面 URL
        source_platform: 可选，平台提示（nowcoder/xiaohongshu），影响相关性阈值

    Returns:
        HunterPipelineResult
    """
    result = HunterPipelineResult()
    crawler, sanitizer, validator, ocr, meta_ext = _get_tools()

    # ── Step 1：爬取 ─────────────────────────────────────────────
    logger.info(f"📡 [Step 1] 开始爬取: {url}")
    raw_text = crawler.run({"url": url})

    if not raw_text or len(raw_text.strip()) < 20 or "失败" in raw_text[:50]:
        result.skip_reason = f"爬取失败或内容为空: {raw_text[:80]}"
        logger.warning(f"⚠️ {result.skip_reason}")
        return result

    # ── Step 2：清洗 ─────────────────────────────────────────────
    logger.info(f"🧹 [Step 2] 清洗文本 (原始长度 {len(raw_text)})")
    clean_text = sanitizer.run({"raw_text": raw_text})

    # ── Step 3：内容校验（规则判断，无 LLM 参与）────────────────
    logger.info(f"🔍 [Step 3] 内容校验")
    validation_raw = validator.run({
        "scraped_text": clean_text,
        "source_platform": source_platform
    })

    try:
        validation = json.loads(validation_raw)
    except Exception:
        logger.warning("ContentValidator 返回非 JSON，按相关处理")
        validation = {"relevant": True, "needs_ocr": False, "image_count": 0}

    result.image_count = validation.get("image_count", 0)

    if not validation.get("relevant", True):
        result.skip_reason = f"非面经内容（{validation.get('reason', '')}）"
        logger.info(f"🚫 [Step 3] 跳过：{result.skip_reason}")
        return result

    # ── Step 4：OCR（仅当 needs_ocr=True 时执行）──────────────
    if validation.get("needs_ocr", False) and result.image_count > 0:
        logger.info(f"📷 [Step 4] 触发 OCR（{result.image_count} 张图片）")
        ocr_result = ocr.run({"raw_text_with_image_urls": clean_text})
        if ocr_result and "失败" not in ocr_result[:20]:
            clean_text = ocr_result  # OCR 工具返回的是合并后的完整文本
        result.ocr_triggered = True
    else:
        quality = validation.get("content_quality", "")
        logger.info(f"⏭️  [Step 4] 跳过 OCR（content_quality={quality}）")

    # ── Step 5：元信息提取（规则优先，LLM 兜底）─────────────────
    logger.info(f"🏷️  [Step 5] 提取元信息")
    meta_raw = meta_ext.run({
        "raw_text": clean_text[:3000],
        "source_platform": source_platform
    })

    try:
        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
    except Exception:
        meta = {}

    # 填充完整
    result.success = True
    result.text = clean_text
    result.meta = meta or {}
    logger.info(f"✅ HunterPipeline 完成: {result}")
    return result
