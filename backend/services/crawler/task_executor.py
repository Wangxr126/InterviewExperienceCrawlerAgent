"""
统一任务执行层：所有爬虫/提取/清洗操作均通过此模块执行。

设计目标：
  1. 按钮、定时任务统一走 execute()
  2. 每次执行返回 source_info，明确标注本地 vs MCP
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Literal, Optional

from backend.config.config import settings
from backend.services.storage import sqlite_service

logger = logging.getLogger(__name__)

ActionType = Literal[
    "nowcoder_discovery",
    "xhs_discovery",
    "process_tasks",
    "clean_data",
]
TriggerSource = Literal["button", "scheduled"]


def _get_source_info(trigger_source: TriggerSource = "button") -> Dict[str, str]:
    """从配置读取当前正文抓取、图片 OCR 方式，供前端/日志区分本地 vs MCP"""
    crawler_source = getattr(settings, "crawler_source", "local")
    ocr_method = getattr(settings, "ocr_method", "ollama_vl")
    return {
        "crawler_source": crawler_source,  # local | mcp（正文抓取）
        "ocr_method": ocr_method,          # ollama_vl | qwen_vl | claude_vision | mcp（图片 OCR）
        "trigger_source": trigger_source,   # button | scheduled
    }


def execute(
    action: ActionType,
    trigger_source: TriggerSource = "button",
    *,
    keywords: Optional[List[str]] = None,
    max_pages: Optional[int] = None,
    max_notes: Optional[int] = None,
    headless: bool = True,
    batch_size: Optional[int] = None,
    process: bool = False,
    force_inline_process_tasks: bool = False,
) -> Dict[str, Any]:
    """
    统一执行入口。所有按钮、定时任务均通过此方法调用。

    force_inline_process_tasks:
        为 True 时强制在当前进程执行队列处理（process_tasks 子进程 worker 入口必须传 True，避免递归拉起子进程）。

    Returns:
        dict 含 status, message, source_info，以及各 action 特有字段
    """
    source_info = _get_source_info(trigger_source)
    _batch = batch_size if batch_size is not None else getattr(settings, "crawler_process_batch_size", 10)

    if action == "nowcoder_discovery":
        from backend.services.scheduling.scheduler import _run_nowcoder_discovery
        added, discovered = _run_nowcoder_discovery(keywords=keywords, max_pages=max_pages)
        return {
            "status": "ok",
            "platform": "nowcoder",
            "discovered": added,
            "discovered_links": discovered or [],
            "questions_added": -1,
            "message": f"发现 {added} 条新帖子",
            "source_info": source_info,
        }

    if action == "xhs_discovery":
        from backend.services.scheduling.scheduler import _run_xhs_discovery
        added = _run_xhs_discovery(headless=headless)
        return {
            "status": "ok",
            "platform": "xiaohongshu",
            "discovered": added,
            "message": f"发现 {added} 条新帖子",
            "source_info": source_info,
        }

    if action == "process_tasks":
        _run_mode = getattr(settings, "crawler_background_run_mode", "process").lower()
        if not force_inline_process_tasks and _run_mode == "process":
            from backend.services.scheduling.process_tasks_spawn import spawn_process_tasks_worker

            _reason = (
                "scheduled-cron"
                if trigger_source == "scheduled"
                else f"task-execute-{trigger_source}"
            )
            spawn_process_tasks_worker(batch_size=_batch, reason=_reason)
            stats = sqlite_service.get_crawl_stats()
            return {
                "status": "ok",
                "questions_added": -1,
                "queue_stats": stats,
                "message": (
                    f"已提交子进程处理队列（batch_size={_batch}），"
                    f"详见 SUBPROCESS_LOG_DIR/process_tasks/ 下按时间戳命名的 .log"
                ),
                "source_info": source_info,
            }
        from backend.services.scheduling.scheduler import crawl_scheduler
        cnt = crawl_scheduler.trigger_process_tasks(batch_size=_batch)
        stats = sqlite_service.get_crawl_stats()
        return {
            "status": "ok",
            "questions_added": cnt,
            "queue_stats": stats,
            "message": f"处理完成，入库 {cnt} 道题目",
            "source_info": source_info,
        }

    if action == "clean_data":
        return _execute_clean_data(_batch, source_info)

    return {
        "status": "error",
        "message": f"未知 action: {action}",
        "source_info": source_info,
    }


def _execute_clean_data(batch_size: int, source_info: Dict[str, str]) -> Dict[str, Any]:
    """清洗无关帖：删除 unrelated，对 done 二次 LLM 判断"""
    from backend.services.crawler.question_extractor import check_contents_related_batch

    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        unrelated_rows = conn.execute(
            "SELECT task_id, source_url, post_title FROM crawl_tasks WHERE status='unrelated'"
        ).fetchall()
    deleted_total = 0
    for r in unrelated_rows:
        cnt = sqlite_service.delete_by_source_url(r["source_url"])
        deleted_total += cnt

    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT task_id, source_url, raw_content, post_title
               FROM crawl_tasks WHERE status='done' AND raw_content IS NOT NULL
               LIMIT ?""",
            (batch_size,),
        ).fetchall()
    tasks = [dict(r) for r in rows]
    contents = [t["raw_content"] or "" for t in tasks]
    BATCH = 5
    for i in range(0, len(contents), BATCH):
        chunk = contents[i : i + BATCH]
        chunk_tasks = tasks[i : i + BATCH]
        results = check_contents_related_batch(chunk)
        for j, related in enumerate(results):
            if not related:
                cnt = sqlite_service.delete_by_source_url(chunk_tasks[j]["source_url"])
                deleted_total += cnt

    stats = sqlite_service.get_crawl_stats()
    total_checked = len(unrelated_rows) + len(tasks)
    msg = (
        f"已检查 {total_checked} 条，删除 {deleted_total} 道无关题目"
        if deleted_total
        else f"已检查 {total_checked} 条，均与面经相关"
    )
    return {
        "status": "ok",
        "message": msg,
        "checked": total_checked,
        "deleted": deleted_total,
        "queue_stats": stats,
        "source_info": source_info,
    }


# 供外部获取当前配置（不执行任务）
def get_source_info() -> Dict[str, str]:
    """返回当前 crawler_source、ocr_method，供 /api/config 等使用"""
    return _get_source_info("button")
