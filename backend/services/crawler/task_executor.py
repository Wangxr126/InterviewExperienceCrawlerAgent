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
    "extract_pending",
    "retry_errors",
    "re_extract_all",
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
) -> Dict[str, Any]:
    """
    统一执行入口。所有按钮、定时任务均通过此方法调用。

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

    if action == "extract_pending":
        return _execute_extract_pending(_batch, source_info)

    if action == "retry_errors":
        return _execute_retry_errors(_batch, source_info)

    if action == "re_extract_all":
        return _execute_re_extract_all(_batch, source_info)

    if action == "clean_data":
        return _execute_clean_data(_batch, source_info)

    return {
        "status": "error",
        "message": f"未知 action: {action}",
        "source_info": source_info,
    }


def prepare_extract_pending() -> tuple[int, Dict[str, int]]:
    """查询待提取数量及按平台分布，供 API 异步启动前使用。返回 (pending_count, initial_by_platform)"""
    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT COUNT(*) as c FROM crawl_tasks WHERE status='fetched'").fetchone()
        pending = row["c"] if row else 0
        if pending == 0:
            return 0, {}
        rows = conn.execute(
            "SELECT source_platform, COUNT(*) as cnt FROM crawl_tasks WHERE status='fetched' GROUP BY source_platform"
        ).fetchall()
        initial = {r["source_platform"]: r["cnt"] for r in rows}
    return pending, initial


def _execute_extract_pending(batch_size: int, source_info: Dict[str, str]) -> Dict[str, Any]:
    """仅提取 fetched 状态帖子（无 DB 变更，直接触发 process_tasks）"""
    pending, _ = prepare_extract_pending()
    if pending == 0:
        return {
            "status": "ok",
            "message": "没有待提取的帖子（状态为 fetched 的记录为 0）",
            "pending": 0,
            "source_info": source_info,
        }
    from backend.services.scheduling.scheduler import crawl_scheduler
    cnt = crawl_scheduler.trigger_process_tasks(batch_size=batch_size)
    return {
        "status": "ok",
        "message": f"提取完成，入库 {cnt} 道题目",
        "pending": pending,
        "questions_added": cnt,
        "source_info": source_info,
    }


def prepare_retry_errors() -> tuple[int, int, int, Dict[str, int]]:
    """
    重试失败项：执行 DB 重置，返回 (to_extract, to_fetch, total, initial_by_platform)。
    供 API 异步启动前使用；若 total>0，再调用 execute("process_tasks")。
    """
    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.execute("""
            UPDATE crawl_tasks SET status='unrelated', error_msg='LLM 判断与面经无关'
            WHERE status='error' AND (
              error_msg LIKE '%正文无有效面试题%'
              OR error_msg LIKE '%正文无面试题%'
              OR error_msg LIKE '%LLM 判断与面经无关%'
            )
        """)
        r1 = conn.execute("""
            UPDATE crawl_tasks SET status='fetched', error_msg=NULL
            WHERE status='error' AND (
              raw_content IS NOT NULL
              OR (image_paths IS NOT NULL AND image_paths != '[]')
            )
        """)
        to_extract = r1.rowcount
        r2 = conn.execute("""
            UPDATE crawl_tasks SET status='pending', error_msg=NULL
            WHERE status='error'
            AND (raw_content IS NULL OR trim(raw_content) = '')
            AND (image_paths IS NULL OR image_paths = '[]')
        """)
        to_fetch = r2.rowcount
        conn.commit()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT source_platform, COUNT(*) as cnt FROM crawl_tasks WHERE status='fetched' GROUP BY source_platform"
        ).fetchall()
        initial = {r["source_platform"]: r["cnt"] for r in rows} if rows else {}
    return to_extract, to_fetch, to_extract + to_fetch, initial


def _execute_retry_errors(batch_size: int, source_info: Dict[str, str]) -> Dict[str, Any]:
    """重试失败项：重置 error→fetched/pending，再触发 process_tasks"""
    to_extract, to_fetch, total, _ = prepare_retry_errors()
    if total == 0:
        return {
            "status": "ok",
            "message": "没有可重试的帖子（error 记录为 0）",
            "reset": 0,
            "source_info": source_info,
        }
    from backend.services.scheduling.scheduler import crawl_scheduler
    cnt = crawl_scheduler.trigger_process_tasks(batch_size=batch_size)
    stats = sqlite_service.get_crawl_stats()
    msg_parts = []
    if to_fetch:
        msg_parts.append(f"{to_fetch} 条待重新抓取")
    if to_extract:
        msg_parts.append(f"{to_extract} 条待重新提取")
    return {
        "status": "ok",
        "message": "已重置 " + "、".join(msg_parts) + f"，入库 {cnt} 道题目",
        "reset": total,
        "questions_added": cnt,
        "queue_stats": stats,
        "source_info": source_info,
    }


def prepare_re_extract_all() -> tuple[int, int, Dict[str, int]]:
    """
    重新提取所有：删除旧题目、将 done/error 重置为 fetched，返回 (reset_count, deleted_questions, initial_by_platform)。
    供 API 异步启动前使用；若 reset>0，再调用 execute("process_tasks")。
    """
    _re_extract_cond = "status IN ('done','error') AND raw_content IS NOT NULL"
    with sqlite3.connect(sqlite_service.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT task_id, source_url FROM crawl_tasks WHERE {_re_extract_cond}"
        ).fetchall()
    if not rows:
        return 0, 0, {}
    urls = [r["source_url"] for r in rows]
    deleted_questions = 0
    try:
        from backend.services.storage.neo4j_service import neo4j_service
        for url in urls:
            neo4j_service.delete_questions_by_source_url(url)
    except Exception as e:
        logger.warning("Neo4j 删除题目失败（SQLite 将照常删除）: %s", e)
    with sqlite3.connect(sqlite_service.db_path) as conn:
        for url in urls:
            cur = conn.execute("DELETE FROM questions WHERE source_url=?", (url,))
            deleted_questions += cur.rowcount
        conn.execute(
            f"""UPDATE crawl_tasks SET status='fetched', questions_count=0, error_msg=NULL,
                extraction_source=NULL, extract_duration_min=NULL
            WHERE {_re_extract_cond} AND source_url IN (""" + ",".join("?" * len(urls)) + ")",
            urls,
        )
        conn.commit()
        conn.row_factory = sqlite3.Row
        rows2 = conn.execute(
            "SELECT source_platform, COUNT(*) as cnt FROM crawl_tasks WHERE status='fetched' GROUP BY source_platform"
        ).fetchall()
        initial = {r["source_platform"]: r["cnt"] for r in rows2} if rows2 else {}
    return len(rows), deleted_questions, initial


def _execute_re_extract_all(batch_size: int, source_info: Dict[str, str]) -> Dict[str, Any]:
    """重新提取所有：删除旧题目、将 done/error 重置为 fetched，再触发 process_tasks"""
    reset_count, deleted_questions, _ = prepare_re_extract_all()
    if reset_count == 0:
        return {
            "status": "ok",
            "message": "没有可重新提取的帖子",
            "reset": 0,
            "source_info": source_info,
        }
    from backend.services.scheduling.scheduler import crawl_scheduler
    cnt = crawl_scheduler.trigger_process_tasks(batch_size=batch_size)
    stats = sqlite_service.get_crawl_stats()
    return {
        "status": "ok",
        "message": f"已重置 {reset_count} 条（删除 {deleted_questions} 道旧题），重新提取完成，入库 {cnt} 道题目",
        "reset": reset_count,
        "questions_deleted": deleted_questions,
        "questions_added": cnt,
        "queue_stats": stats,
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
