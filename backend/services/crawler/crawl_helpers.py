"""
爬虫入库统一逻辑
供 scheduler 定时任务 与 run_xhs_worker 立即爬取 共用，保证思路和实现一致。
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def save_xhs_post(
    post: Dict[str, Any],
    sqlite_service,
    download_images_flag: bool = True,
) -> Optional[str]:
    """
    将小红书帖子入库：链接、标题、正文、图片（相对路径）。

    Args:
        post: 含 source_url, title, content, image_urls, post_type 等
        sqlite_service: SQLite 服务实例
        download_images_flag: 是否下载图片到本地并保存相对路径

    Returns:
        task_id 若新增成功，否则 None（URL 已存在）
    """
    task_id = sqlite_service.add_crawl_task(
        source_url=post.get("source_url", ""),
        source_platform="xiaohongshu",
        post_title=post.get("title", ""),
        post_type=post.get("post_type", ""),
    )
    if not task_id:
        return None

    raw_content = post.get("content", "") or ""
    image_paths: list = []

    if download_images_flag:
        image_urls = post.get("image_urls") or post.get("images") or []
        if image_urls:
            from backend.services.crawler.image_utils import download_images
            image_paths = download_images(image_urls, task_id)

    sqlite_service.update_task_status(
        task_id=task_id,
        status="fetched",
        raw_content=raw_content,
        image_paths=image_paths,
    )
    return task_id
