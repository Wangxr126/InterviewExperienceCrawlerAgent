#!/usr/bin/env python3
"""
MCP Content Extractor - 牛客/小红书 URL 内容+图片提取

从牛客网(nowcoder)和小红书(xiaohongshu) URL 提取正文和图片。
复用 backend 的完整爬虫逻辑，支持：
- 牛客：DOM + __INITIAL_STATE__ 解析，含图片
- 小红书：xhs-crawl + Playwright 兜底（需登录态时）

运行方式（在项目根目录）：
  uv run python mcp/mcp-content-extractor/server.py
  或：conda activate NewCoderAgent && python mcp/mcp-content-extractor/server.py

Cursor 配置：在 .cursor/mcp.json 中添加此服务器。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 确保项目根在 path 中，以便 import backend
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 加载 .env（项目根目录）
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

from fastmcp import FastMCP

mcp = FastMCP(
    "content-extractor",
    instructions="从牛客网(nowcoder)和小红书(xiaohongshu) URL 提取正文和图片，供 Cursor/Agent 使用"
)


def _extract_nowcoder(url: str) -> dict:
    """调用 backend 牛客爬虫，返回 {title, content, image_urls}"""
    from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
    from backend.config.config import settings

    cookie = getattr(settings, "nowcoder_cookie", "") or os.environ.get("NOWCODER_COOKIE", "")
    crawler = NowcoderCrawler(cookie=cookie)
    title, content, image_urls = crawler.fetch_post_content_full_with_title(url)
    return {
        "platform": "nowcoder",
        "url": url,
        "title": title,
        "content": content,
        "image_urls": image_urls,
    }


def _extract_xhs(url: str) -> dict:
    """调用 backend 小红书爬虫，返回 {title, content, image_urls}"""
    from backend.services.crawler.xhs_crawler import fetch_xhs_details

    posts = fetch_xhs_details([url])
    if not posts:
        return {
            "platform": "xiaohongshu",
            "url": url,
            "title": "",
            "content": "",
            "image_urls": [],
            "error": "未能获取到帖子内容。小红书可能需要登录，请先在后端完成扫码登录（POST /api/crawler/xhs/login），或检查 xhs-crawl 是否安装。",
        }

    p = posts[0]
    return {
        "platform": "xiaohongshu",
        "url": url,
        "title": p.get("title", ""),
        "content": p.get("content", ""),
        "image_urls": p.get("image_urls", []),
    }


@mcp.tool()
def extract_nowcoder_content(url: str) -> str:
    """从牛客网(nowcoder.com)帖子 URL 提取标题、正文和图片 URL 列表。

    支持 feed 和 discuss 页面，自动解析 __INITIAL_STATE__ 和 DOM。
    牛客一般无需登录即可获取公开帖子内容。

    Args:
        url: 牛客帖子链接，如 https://www.nowcoder.com/feed/main/detail/xxx 或 /discuss/xxx

    Returns:
        JSON 字符串，包含 title, content, image_urls
    """
    if "nowcoder.com" not in url:
        return '{"error": "URL 必须是牛客网链接 (nowcoder.com)"}'
    try:
        result = _extract_nowcoder(url)
        import json
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        import json
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


@mcp.tool()
def extract_xhs_content(url: str) -> str:
    """从小红书(xiaohongshu.com)笔记 URL 提取标题、正文和图片 URL 列表。

    优先使用 xhs-crawl 库；遇防爬（页面不见了）时自动用 Playwright 兜底。
    小红书需要登录态：首次使用请在后端调用 POST /api/crawler/xhs/login 完成扫码，
    登录状态保存在 backend/data/xhs_user_data，MCP 会复用该目录（需配置 XHS_USER_DATA_DIR 与后端一致）。

    Args:
        url: 小红书笔记链接，如 https://www.xiaohongshu.com/explore/xxx

    Returns:
        JSON 字符串，包含 title, content, image_urls
    """
    if "xiaohongshu.com" not in url and "xhs.com" not in url:
        return '{"error": "URL 必须是小红书链接 (xiaohongshu.com 或 xhs.com)"}'
    try:
        result = _extract_xhs(url)
        import json
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        import json
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


@mcp.tool()
def extract_content(url: str) -> str:
    """根据 URL 自动识别平台，提取牛客或小红书帖子的标题、正文和图片。

    自动识别 nowcoder.com / xiaohongshu.com / xhs.com，并调用对应解析逻辑。

    Args:
        url: 帖子链接（牛客或小红书）

    Returns:
        JSON 字符串，包含 platform, title, content, image_urls
    """
    if "nowcoder.com" in url:
        return extract_nowcoder_content(url)
    if "xiaohongshu.com" in url or "xhs.com" in url:
        return extract_xhs_content(url)
    import json
    return json.dumps({
        "error": "暂仅支持牛客(nowcoder.com)和小红书(xiaohongshu.com)链接",
        "url": url,
    }, ensure_ascii=False)


if __name__ == "__main__":
    # 支持两种模式：
    # - stdio：本地 Cursor 子进程（默认）
    # - streamable-http：云端部署（Smithery 等），监听 PORT
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        port = int(os.environ.get("PORT", "8081"))
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=port,
            path="/mcp",
        )
    else:
        mcp.run()
