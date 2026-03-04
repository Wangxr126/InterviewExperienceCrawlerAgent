"""
资源猎人工具箱 (Hunter Tools)
整合了 牛客网爬虫 和 小红书爬虫，统一对外提供抓取能力。
"""

import json
import logging
import re
import os
import asyncio
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from typing import List, Dict, Any

# ✅ 引入 Tool 和 ToolParameter
from hello_agents.tools import Tool, ToolParameter

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. 核心工具：全网爬取器 (CrawlerTool)
# ==============================================================================

class CrawlerTool(Tool):
    """
    抓取网页内容。支持自动识别牛客网(nowcoder)和小红书(xiaohongshu)链接。
    """

    def __init__(self):
        super().__init__(
            name="web_crawler",
            description="抓取指定URL的网页内容。支持牛客网帖子和小红书笔记。"
        )

    # ✅ 必须实现的方法：定义参数结构
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="url",
                type="string",
                description="需要抓取的网页链接 (URL)",
                required=True
            )
        ]

    # ✅ 必须实现的方法：执行逻辑 (接收字典)
    def run(self, parameters: Dict[str, Any]) -> str:
        url = parameters.get("url")
        if not url:
            return "❌ 参数错误：缺少 url"

        domain = urlparse(url).netloc

        try:
            if "nowcoder.com" in domain:
                return self._crawl_nowcoder(url)
            elif "xiaohongshu.com" in domain:
                return self._crawl_xhs(url)
            else:
                return f"❌ 暂不支持该域名抓取: {domain}。目前仅支持 nowcoder.com 和 xiaohongshu.com"
        except Exception as e:
            logger.error(f"抓取失败 {url}: {e}")
            return f"❌ 抓取发生异常: {str(e)}"

    # -------------------------------------------------------
    # A. 牛客网爬取逻辑
    # -------------------------------------------------------
    def _crawl_nowcoder(self, url: str) -> str:
        logger.info(f"🕸️ [牛客网] 开始抓取: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': 'https://www.nowcoder.com',
        }

        try:
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=15)

            if response.status_code != 200:
                return f"请求失败，状态码: {response.status_code}"

            soup = BeautifulSoup(response.text, 'html.parser')

            # 查找正文
            content_div = soup.find('div', class_=lambda x: x and ('nc-post-content' in x or 'post-topic-des' in x))
            if not content_div:
                content_div = soup.find(id="js-post-content")

            # 查找标题
            title_tag = soup.find('span', class_='post-title') or soup.find('div', class_='title')
            title = title_tag.get_text(strip=True) if title_tag else "无标题"

            if content_div:
                for script in content_div(["script", "style"]):
                    script.decompose()

                content = content_div.get_text(separator='\n', strip=True)

                return f"【来源】牛客网\n【标题】{title}\n【链接】{url}\n【正文】\n{content}"
            else:
                return "❌ 未识别到正文结构 (可能需要更新 Cookie 或 页面结构变更)"

        except Exception as e:
            return f"牛客网解析异常: {str(e)}"

    # -------------------------------------------------------
    # B. 小红书爬取逻辑
    # -------------------------------------------------------
    def _crawl_xhs(self, url: str) -> str:
        logger.info(f"📕 [小红书] 开始抓取: {url}")

        try:
            from xhs_crawl import XHSSpider
        except ImportError:
            return "❌ 缺少依赖 `xhs-crawl`，请先 pip install xhs-crawl"

        async def async_fetch():
            spider = XHSSpider()
            try:
                post = await spider.get_post_data(url)
                if not post:
                    return "❌ 数据为空或帖子不存在"

                title = getattr(post, "title", "无标题")
                content = getattr(post, "content", "无内容")

                image_urls = []
                if hasattr(post, "images") and post.images:
                    image_urls = post.images

                result_text = f"【来源】小红书\n【标题】{title}\n【链接】{url}\n【正文】\n{content}"

                if image_urls:
                    result_text += f"\n【检测到图片】共 {len(image_urls)} 张"
                    for img in image_urls:
                        result_text += f"\n[IMAGE_URL]: {img}"

                return result_text

            except Exception as e:
                return f"❌ 小红书抓取异常: {str(e)}"
            finally:
                await spider.close()

        try:
            if os.name == "nt":
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            return asyncio.run(async_fetch())
        except Exception as e:
            return f"异步执行出错: {str(e)}"


# ==============================================================================
# 2. 辅助工具：视觉提取器 (VisualExtractor)
# ==============================================================================

class VisualExtractor(Tool):
    """
    处理包含 [IMAGE_URL] 标记的文本，模拟 OCR 识别。
    """
    def __init__(self):
        super().__init__(
            name="extract_image_text",
            description="从文本中提取 [IMAGE_URL] 链接，并使用 OCR 识别图片中的文字。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="text_with_urls",
                type="string",
                description="包含图片链接的原始文本",
                required=True
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        text_with_urls = parameters.get("text_with_urls", "")

        image_urls = re.findall(r'\[IMAGE_URL\]:\s*(https?://[^\s]+)', text_with_urls)

        if not image_urls:
            return "未发现图片链接，无需 OCR 处理。"

        logger.info(f"👁️ [视觉提取] 发现 {len(image_urls)} 张图片，开始 OCR...")

        ocr_results = []
        for idx, img_url in enumerate(image_urls, 1):
            # 模拟 OCR 结果 (实际可对接大模型 Vision API)
            ocr_text = f"[图片{idx} OCR结果] (此处为模拟识别内容...)"
            ocr_results.append(ocr_text)

        return text_with_urls + "\n\n【OCR 识别补充】\n" + "\n".join(ocr_results)


# ==============================================================================
# 3. 辅助工具：文本清洗器 (TextSanitizer)
# ==============================================================================

class TextSanitizer(Tool):
    """
    清洗文本，去除 HTML 标签、广告干扰。
    """
    def __init__(self):
        super().__init__(
            name="sanitize_text",
            description="清洗文本，去除 HTML 标签、广告干扰和无意义字符。"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="raw_text",
                type="string",
                description="需要清洗的脏文本",
                required=True
            )
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        raw_text = parameters.get("raw_text", "")
        if not raw_text:
            return ""

        # 简单清洗逻辑
        clean_text = re.sub(r'\[IMAGE_URL\]:.*', '', raw_text)
        clean_text = re.sub(r'<[^>]+>', '', clean_text)
        clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)

        noise_patterns = [r"登录后查看更多", r"点击链接查看详情", r"著作权归作者所有"]
        for pattern in noise_patterns:
            clean_text = re.sub(pattern, '', clean_text)

        logger.info("🧹 [清洗完成] 文本去噪完毕")
        return clean_text.strip()


# ==============================================================================
# 4. 内容质量校验器 (ContentValidator)
# 判断：爬取的文本是否和面经相关？是否需要识别图片中的内容？
# ==============================================================================

# 面经相关关键词（命中 >= 2 个才算相关）
_INTERVIEW_KEYWORDS = [
    "面试", "面经", "题目", "问答", "考察", "问了", "岗位", "公司",
    "技术栈", "算法题", "系统设计", "后端", "前端", "校招", "社招",
    "实习", "手撕", "拷打", "笔试", "HR", "offer", "机会",
    "redis", "mysql", "java", "python", "go语言", "spring", "kafka",
    "分布式", "微服务", "docker", "k8s", "数据库", "并发", "锁",
]

# 问题特征词（出现 >= 3 个说明文本里已有足够的题目内容）
_QUESTION_PATTERNS = [
    "？", "如何", "为什么", "什么是", "区别", "原理", "怎么", "介绍",
    "讲一下", "说说", "谈谈", "实现", "设计", "比较", "说明",
]


class ContentValidator(Tool):
    """
    内容质量校验器。
    爬取帖子后，在决定是否 OCR 图片之前调用此工具：
    1. 判断帖子是否与面经/技术面试相关（不相关则直接跳过）
    2. 判断正文是否已包含足够的面试题目内容
    3. 如果正文不足 + 有图片 → 建议触发 OCR
    4. 如果正文已足够 → 跳过 OCR，节省资源

    返回 JSON：{relevant, needs_ocr, reason, content_quality, image_count}
    """

    def __init__(self):
        super().__init__(
            name="validate_content",
            description=(
                "校验爬取的文本内容：判断是否为面经相关内容，以及是否需要对图片进行OCR识别。"
                "在 CrawlerTool 之后、VisualExtractor 之前调用。"
            )
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="scraped_text",
                type="string",
                description="CrawlerTool 爬取并经 TextSanitizer 清洗后的文本",
                required=True
            ),
            ToolParameter(
                name="source_platform",
                type="string",
                description="来源平台: nowcoder / xiaohongshu",
                required=False
            ),
        ]

    def run(self, parameters: Dict[str, Any]) -> str:
        text = parameters.get("scraped_text", "")
        source_platform = parameters.get("source_platform", "")

        if not text or len(text.strip()) < 20:
            result = {
                "relevant": False,
                "needs_ocr": False,
                "reason": "正文为空或过短，无法判断",
                "content_quality": "empty",
                "image_count": 0
            }
            return _fmt_result(result)

        text_lower = text.lower()

        # ── Step 1：统计图片数量 ──
        image_count = len(re.findall(r'\[IMAGE_URL\]', text))

        # ── Step 2：相关性判断（关键词命中数 >= 2）──
        keyword_hits = [kw for kw in _INTERVIEW_KEYWORDS if kw in text_lower]
        is_relevant = len(keyword_hits) >= 2

        # 对小红书/牛客网降低门槛（本身就是面经平台）
        if source_platform in ("nowcoder", "xiaohongshu") and len(keyword_hits) >= 1:
            is_relevant = True

        if not is_relevant:
            result = {
                "relevant": False,
                "needs_ocr": False,
                "reason": f"内容与面试/技术无关（命中关键词：{keyword_hits[:3]}）",
                "content_quality": "irrelevant",
                "image_count": image_count
            }
            logger.info(f"🚫 [ContentValidator] 非相关内容，跳过处理")
            return _fmt_result(result)

        # ── Step 3：正文完整性判断 ──
        # 问题特征词命中数
        question_hits = sum(text.count(p) for p in _QUESTION_PATTERNS)
        # 有效文字长度（去除空白和图片标记后）
        clean_len = len(re.sub(r'\[IMAGE_URL\][^\n]*', '', text).replace('\n', '').replace(' ', ''))

        # 判断逻辑：
        # - 有效文字 >= 400 字 且问题特征词 >= 4 → 正文已足够，无需 OCR
        # - 有效文字 < 200 字 或 问题特征词 < 3 → 正文不足，若有图片则需 OCR
        if clean_len >= 400 and question_hits >= 4:
            content_quality = "sufficient"
            needs_ocr = False
            reason = (f"正文内容充足（{clean_len}字，{question_hits}个问题特征）"
                      f"，无需识别图片")
        elif clean_len < 200 or question_hits < 3:
            content_quality = "insufficient"
            needs_ocr = image_count > 0
            reason = (f"正文较少（{clean_len}字，{question_hits}个问题特征）"
                      f"，{'发现 ' + str(image_count) + ' 张图片需 OCR' if needs_ocr else '但无图片'}")
        else:
            # 中间情况：正文有一些内容，但可能图片里还有补充题目
            content_quality = "partial"
            # 如果图片比较多（>=2张）说明帖子依赖图片
            needs_ocr = image_count >= 2
            reason = (f"正文部分充足（{clean_len}字，{question_hits}个问题特征）"
                      f"，{'图片较多建议 OCR' if needs_ocr else '图片少可跳过 OCR'}")

        result = {
            "relevant": True,
            "needs_ocr": needs_ocr,
            "reason": reason,
            "content_quality": content_quality,
            "image_count": image_count,
            "keyword_hits": keyword_hits[:5],
            "question_pattern_count": question_hits
        }
        logger.info(f"✅ [ContentValidator] relevant=True, needs_ocr={needs_ocr}, "
                    f"quality={content_quality}, images={image_count}")
        return _fmt_result(result)


def _fmt_result(result: dict) -> str:
    """将校验结果格式化为 JSON 字符串，供 Agent 解析"""
    return json.dumps(result, ensure_ascii=False)