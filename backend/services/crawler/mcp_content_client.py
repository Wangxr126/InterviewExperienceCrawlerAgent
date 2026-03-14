"""
MCP Content Fetcher 远程调用客户端

当 CRAWLER_SOURCE=mcp 时，CrawlerTool 通过此模块调用远程 MCP Content Fetcher 的 /fetch 端点。
端点格式：POST {MCP_CONTENT_FETCHER_URL}/fetch，body: {"url": "..."}
返回：{url, title, content, platform, fetchedAt, metadata}
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def fetch_content_via_mcp(
    base_url: str,
    url: str,
    timeout: int = 30,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    通过远程 MCP Content Fetcher 获取 URL 内容。

    Args:
        base_url: MCP 服务根 URL，如 https://mcp-content-fetcher.onrender.com
        url: 要抓取的目标 URL
        timeout: 请求超时秒数
        api_key: 可选，Smithery API Key（通过 Smithery 网关时使用）

    Returns:
        {url, title, content, platform, fetchedAt, metadata}

    Raises:
        httpx.HTTPError: 网络或 HTTP 错误
        ValueError: 响应格式异常
    """
    fetch_url = base_url.rstrip("/") + "/fetch"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info(
        "[MCP] 开始抓取 | url=%s | fetch_endpoint=%s | timeout=%ds",
        url,
        fetch_url,
        timeout,
    )
    t0 = time.perf_counter()

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(fetch_url, json={"url": url}, headers=headers)
            elapsed = time.perf_counter() - t0
            logger.info(
                "[MCP] HTTP 响应 | url=%s | status=%d | elapsed=%.2fs",
                url,
                resp.status_code,
                elapsed,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        elapsed = time.perf_counter() - t0
        logger.error(
            "[MCP] 抓取失败 HTTP | url=%s | status=%d | elapsed=%.2fs | error=%s",
            url,
            e.response.status_code,
            elapsed,
            str(e),
        )
        raise
    except httpx.RequestError as e:
        elapsed = time.perf_counter() - t0
        logger.error(
            "[MCP] 抓取失败 网络 | url=%s | elapsed=%.2fs | error=%s",
            url,
            elapsed,
            str(e),
        )
        raise

    if "error" in data and "url" not in data:
        logger.error("[MCP] 服务返回错误 | url=%s | error=%s", url, data.get("error"))
        raise ValueError(data.get("error", "Unknown error"))

    platform = data.get("platform", "generic")
    title = data.get("title", "")
    content = data.get("content", "")
    content_len = len(content)
    content_preview = (content[:200] + "..." if len(content) > 200 else content) if content else "(空)"
    logger.info(
        "[MCP] 抓取成功 | url=%s | platform=%s | title=%s | content_len=%d",
        url,
        platform,
        (title[:30] + "..." if len(title) > 30 else title) if title else "(无标题)",
        content_len,
    )
    logger.info("[MCP] 正文预览: %s", content_preview)
    return data
