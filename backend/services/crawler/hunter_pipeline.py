"""
兼容 HunterPipeline 入口。

历史代码通过 run_hunter_pipeline(url, source_platform) 调用采集流程，
当前仓库已迁移到 crawler + scheduler 体系，原模块缺失会导致导入失败。
本文件提供最小兼容实现：抓取单条 URL、写入 crawl_tasks，并触发单任务提取。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict

from backend.config.config import settings
from backend.services.crawler.crawl_helpers import save_xhs_post
from backend.services.crawler.mcp_content_client import fetch_content_via_mcp
from backend.services.crawler.xhs_crawler import _async_fetch_details, fetch_xhs_details
from backend.services.scheduling.scheduler import process_single_task
from backend.services.storage.sqlite_service import sqlite_service

logger = logging.getLogger(__name__)


@dataclass
class HunterPipelineResult:
    success: bool
    text: str = ""
    skip_reason: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    ocr_triggered: bool = False


def _normalize_xhs_link(url: str) -> str:
    s = (url or "").strip()
    if not s:
        return ""
    # xhslink 短链在后续抓取中可直接使用；保留原链接，避免过度处理。
    return s


async def _fetch_single_post(source_url: str, source_platform: str = "") -> Dict[str, Any] | None:
    """
    统一抓取入口：优先按 .env 配置走 MCP，失败后回退本地抓取。
    """
    _platform = (source_platform or "xiaohongshu").strip() or "xiaohongshu"
    crawler_source = getattr(settings, "crawler_source", "local")
    if crawler_source == "mcp" and getattr(settings, "mcp_content_fetcher_url", ""):
        try:
            data = await asyncio.to_thread(
                fetch_content_via_mcp,
                settings.mcp_content_fetcher_url,
                source_url,
                int(getattr(settings, "mcp_content_fetcher_timeout", 30) or 30),
                (getattr(settings, "smithery_api_key", "") or None),
            )
            content = (data.get("content") or "").strip()
            if content:
                metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                image_urls = data.get("image_urls") or (metadata.get("image_urls") if isinstance(metadata, dict) else []) or []
                return {
                    "source_url": source_url,
                    "source_platform": data.get("platform") or _platform,
                    "title": (data.get("title") or "").strip(),
                    "content": content,
                    "image_urls": image_urls if isinstance(image_urls, list) else [],
                    "post_time": "",
                }
            logger.warning("[HunterPipelineCompat] MCP 抓取为空，回退本地抓取: %s", source_url[:100])
        except Exception as e:
            logger.warning("[HunterPipelineCompat] MCP 抓取失败，回退本地抓取: %s", e)

    # 本地抓取兜底（包含 xhs-crawl / Playwright / 内部回退）
    try:
        posts = await _async_fetch_details([source_url])
    except Exception:
        posts = fetch_xhs_details([source_url])
    if not posts:
        return None
    post = posts[0] or {}
    post.setdefault("source_url", source_url)
    post.setdefault("source_platform", _platform)
    post.setdefault("title", "")
    post.setdefault("content", "")
    post.setdefault("image_urls", [])
    post.setdefault("post_time", "")
    return post


async def run_hunter_pipeline(url: str, source_platform: str = "") -> HunterPipelineResult:
    """兼容旧版接口：处理单条 URL 并返回统一结果。"""
    source_url = _normalize_xhs_link(url)
    if not source_url:
        return HunterPipelineResult(success=False, skip_reason="空链接")

    post = await _fetch_single_post(source_url, source_platform=source_platform)
    if not post:
        return HunterPipelineResult(success=False, skip_reason="抓取失败或内容为空")

    task_id = save_xhs_post(post, sqlite_service, download_images_flag=True)
    if not task_id:
        # 可能已存在该 URL：尝试复用旧任务。
        with sqlite_service._get_conn() as conn:
            row = conn.execute(
                "SELECT task_id FROM crawl_tasks WHERE source_url=? ORDER BY discovered_at DESC LIMIT 1",
                (source_url,),
            ).fetchone()
        if not row:
            return HunterPipelineResult(success=False, skip_reason="写入任务失败")
        task_id = row["task_id"]

    single = process_single_task(task_id)
    if single.get("status") != "ok":
        return HunterPipelineResult(
            success=False,
            skip_reason=single.get("message", "提取失败"),
            meta={"task_id": task_id},
        )

    questions = sqlite_service.get_questions_by_source_url(source_url)
    question_lines = []
    for idx, q in enumerate(questions[:20], start=1):
        qt = (q.get("question_text") or "").strip()
        at = (q.get("answer_text") or "").strip()
        if not qt:
            continue
        if at:
            question_lines.append(f"{idx}. Q: {qt}\nA: {at}")
        else:
            question_lines.append(f"{idx}. Q: {qt}")

    content = (post.get("content") or "").strip()
    merged_text = content
    if question_lines:
        merged_text = f"{content}\n\n提取题目：\n" + "\n\n".join(question_lines)

    logger.info("[HunterPipelineCompat] 完成 task_id=%s, questions=%s", task_id, len(questions))
    return HunterPipelineResult(
        success=True,
        text=merged_text[:12000],
        skip_reason="",
        meta={
            "task_id": task_id,
            "questions_added": int(single.get("questions_added") or 0),
            "source_platform": post.get("source_platform", "xiaohongshu"),
            "source_url": source_url,
        },
        ocr_triggered=bool(single.get("ocr_called")),
    )
