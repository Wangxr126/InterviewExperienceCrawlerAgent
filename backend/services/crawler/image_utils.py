"""
帖子图片下载工具
将远程图片下载到本地，返回相对路径（供 crawl_tasks.image_paths 入库）
相对路径格式：post_images/{task_id}/0.jpg
"""
import os
import re
import logging
import requests
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from backend.config.config import settings

logger = logging.getLogger(__name__)

_POST_IMAGES_BASE = settings.post_images_dir


def _guess_ext(url: str, content_type: str = "") -> str:
    """根据 URL 或 Content-Type 推断扩展名"""
    path = urlparse(url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
        if ext in path or path.endswith(ext[1:]):
            return ext[1:]
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg"
    if "png" in content_type:
        return "png"
    if "gif" in content_type:
        return "gif"
    if "webp" in content_type:
        return "webp"
    return "jpg"


def download_images(
    image_urls: List[str],
    task_id: str,
    timeout: int = 15,
) -> List[str]:
    """
    下载图片到 backend/data/post_images/{task_id}/，返回相对路径列表。
    相对路径格式：post_images/{task_id}/0.jpg（便于前端 /post-images/ 静态服务访问）

    Args:
        image_urls: 图片 URL 列表
        task_id: 任务 ID（如 TASK_XXX）
        timeout: 单张图片下载超时秒数

    Returns:
        成功保存的图片相对路径列表，如 ["TASK_XXX/0.jpg", ...]，前端拼接 /post-images/ 即可
    """
    if not image_urls:
        return []

    out_dir = _POST_IMAGES_BASE / task_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # 相对路径：TASK_XXX/0.jpg，前端通过 /post-images/TASK_XXX/0.jpg 访问
    rel_prefix = task_id
    saved: List[str] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://www.xiaohongshu.com/",
    }

    failed = 0
    for idx, url in enumerate(image_urls):
        if not url or not url.startswith("http"):
            continue
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            ext = _guess_ext(url, resp.headers.get("Content-Type", ""))
            fname = f"{idx}.{ext}"
            out_path = out_dir / fname
            with open(out_path, "wb") as f:
                f.write(resp.content)
            rel = f"{rel_prefix}/{fname}"
            saved.append(rel)
        except Exception as e:
            failed += 1
            logger.warning(f"图片下载失败 {url[:60]}: {e}")

    if image_urls:
        logger.info(f"图片下载完成: {task_id} | 共{len(image_urls)}张, 成功{len(saved)}张" + (f", 失败{failed}张" if failed else ""))
    return saved
