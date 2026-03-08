"""
面经爬取调度器
职责：
  1. 定时发现新帖子（牛客 / 小红书）→ 写入 crawl_tasks 队列
  2. 定时处理待爬取任务 → 爬全文 → LLM 提取题目 → 写入 SQLite + Neo4j
  3. 提供手动触发接口

定时策略（可在 CrawlerConfig 中调整）：
  - 牛客发现任务：每天 02:00 / 14:00
  - XHS 发现任务：每天 03:00（需浏览器，建议手动触发）
  - 任务处理器：每小时整点（最多处理 10 条）

使用：
  scheduler = CrawlScheduler()
  scheduler.start()          # 后台启动
  scheduler.trigger_nowcoder_discovery()  # 手动触发
  scheduler.stop()           # 停止
"""
from backend.utils.time_utils import now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
import logging
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.services.sqlite_service import sqlite_service
from backend.services.neo4j_service import neo4j_service
from backend.services.crawler.question_extractor import extract_questions_from_post
from backend.services.knowledge_manager import knowledge_manager
from backend.config.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 配置（全部从 .env 读取，通过 settings 代理）
# ══════════════════════════════════════════════════════════════

class _CrawlerConfig:
    """从 settings（即 .env）懒加载爬虫配置，运行时每次访问都读最新值"""

    @property
    def NOWCODER_COOKIE(self) -> str:
        return settings.nowcoder_cookie

    @property
    def NOWCODER_KEYWORDS(self) -> List[str]:
        return settings.nowcoder_keywords

    @property
    def NOWCODER_MAX_PAGES(self) -> int:
        return settings.nowcoder_max_pages

    @property
    def XHS_KEYWORDS(self) -> List[str]:
        return settings.xhs_keywords

    @property
    def XHS_MAX_NOTES_PER_KEYWORD(self) -> int:
        return settings.xhs_max_notes_per_keyword

    @property
    def PROCESS_BATCH_SIZE(self) -> int:
        return settings.crawler_process_batch_size

    @property
    def ENABLE_NOWCODER(self) -> bool:
        return settings.scheduler_enable_nowcoder

    @property
    def ENABLE_XHS(self) -> bool:
        return settings.scheduler_enable_xhs


cfg = _CrawlerConfig()


# ══════════════════════════════════════════════════════════════
# 核心处理函数（供 Scheduler Job 调用）
# ══════════════════════════════════════════════════════════════

def _run_nowcoder_discovery(keywords: List[str] = None, max_pages: int = None) -> tuple:
    """牛客面经发现任务（keywords/max_pages 不传时从 .env 读取）。返回 (新增数, 发现列表)"""
    _keywords = keywords or cfg.NOWCODER_KEYWORDS
    _max_pages = max_pages if max_pages is not None else cfg.NOWCODER_MAX_PAGES
    logger.info(f"[牛客定时爬取] 开始（关键词={_keywords}, 最大页数={_max_pages}）...")
    try:
        from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
        crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
        posts = crawler.discover(
            keywords=_keywords,
            max_pages=_max_pages,
            crawl_source="定时爬取"
        )

        added = 0
        discovered = []
        for p in posts:
            task_id = sqlite_service.add_crawl_task(
                source_url=p["source_url"],
                source_platform="nowcoder",
                post_title=p.get("title", ""),
                company=p.get("company", ""),
                position=p.get("position", ""),
                business_line=p.get("business_line", ""),
                difficulty=p.get("difficulty", ""),
                post_type=p.get("post_type", ""),
                discover_keyword=p.get("discover_keyword", ""),
            )
            if task_id:
                added += 1
            discovered.append({"title": p.get("title", "")[:50], "url": p.get("source_url", "")})

        logger.info(f"[牛客定时爬取] 发现完成：发现 {len(posts)} 条，新增队列 {added} 条")
        return added, discovered
    except Exception as e:
        logger.error(f"[牛客定时爬取] 失败: {e}", exc_info=True)
        return 0, []


def _run_xhs_discovery(keywords: List[str] = None, max_notes: int = None, headless: bool = True):
    """小红书面经发现任务（定时任务默认 headless=True，依赖已保存的登录状态）"""
    _keywords = keywords or cfg.XHS_KEYWORDS
    _max_notes = max_notes if max_notes is not None else cfg.XHS_MAX_NOTES_PER_KEYWORD
    logger.info(f"[小红书定时爬取] 开始（关键词={_keywords}, 最大帖子数={_max_notes}）...")
    try:
        from backend.services.crawler.xhs_crawler import XHSCrawler
        from backend.services.crawler.crawl_helpers import save_xhs_post
        
        crawler = XHSCrawler(headless=headless)
        posts = crawler.discover(
            keywords=_keywords,
            max_notes_per_keyword=_max_notes,
            crawl_source="定时爬取"
        )

        discovered = 0
        for p in posts:
            if save_xhs_post(p, sqlite_service, download_images_flag=True):
                discovered += 1

        logger.info(f"[小红书定时爬取] 发现完成: {len(posts)} 条原始帖, {discovered} 条新入队")
        
        # 立即处理新发现的任务
        questions_added = 0
        if discovered > 0:
            questions_added = _process_pending_tasks(batch_size=discovered + 5)
            logger.info(f"[小红书定时爬取] 处理完成: {questions_added} 道题入库")
        
        return discovered
    except Exception as e:
        logger.error(f"[小红书定时爬取] 失败: {e}", exc_info=True)
        return 0


def _process_pending_tasks(batch_size: int = None):
    """
    处理 crawl_tasks 队列：
      pending  → 抓取详情页 → fetched
      fetched  → LLM 提取题目 → done / error
    """
    batch_size = batch_size or cfg.PROCESS_BATCH_SIZE
    logger.info(f"[定时任务] ⚙️  开始处理任务队列（最多 {batch_size} 条）...")

    processed = 0

    # ── Step 1: pending → 抓取详情（仅牛客）──────────────────
    pending = sqlite_service.get_pending_tasks(platform="nowcoder", limit=batch_size)
    if pending:
        logger.info(f"[定时任务] 📥 开始抓取详情，本批 {len(pending)} 条 pending 任务")
    for task in pending:
        task_id = task["task_id"]
        url = task["source_url"]
        title = (task.get("post_title") or "").strip() or "(无标题)"
        try:
            from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
            from backend.services.crawler.image_utils import download_images
            crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
            content, image_urls = crawler.fetch_post_content_full(url)
            if content and len(content) > 100:
                image_paths = download_images(image_urls, task_id) if image_urls else []
                sqlite_service.update_task_status(
                    task_id, "fetched",
                    raw_content=content,
                    image_paths=image_paths,
                )
                logger.info(f"[定时任务] ✅抓取content成功 [{title[:40]}]: 正文{len(content)}字, 图片{len(image_paths)}张")
            else:
                sqlite_service.update_task_status(task_id, "error", error_msg="正文内容为空或太短")
        except Exception as e:
            sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200])
            logger.error(f"[定时任务] ❌抓取详情失败 [{title[:40]}]: {e}")

    # ── Step 2: fetched → LLM 提取 → 写库 ────────────────────
    # 同时处理牛客和小红书（XHS 在 discover 时就已经 fetched）
    with sqlite_service._get_conn() as conn:
        fetched_rows = conn.execute(
            "SELECT * FROM crawl_tasks WHERE status='fetched' LIMIT ?",
            (batch_size,)
        ).fetchall()

    if fetched_rows:
        logger.info(f"[定时任务] 📋 开始 LLM 提取，本批 {len(fetched_rows)} 条 fetched 帖子")

    for row in fetched_rows:
        task_id = row["task_id"]
        raw_content = row["raw_content"] or ""
        url = row["source_url"]
        platform = row["source_platform"]
        post_title = (row["post_title"] or "").strip() or "(无标题)"

        logger.debug(f"  📄 正在处理帖子: {post_title[:60]}...")

        if not raw_content or len(raw_content) < 50:
            sqlite_service.update_task_status(task_id, "error", error_msg="raw_content 为空", raw_content=raw_content)
            logger.error(f"  ❌ 提取失败(正文为空) task_id={task_id} url={url[:60]} title={post_title[:40]}")
            continue

        image_paths_raw = row["image_paths"] or "[]"
        try:
            image_paths = json.loads(image_paths_raw) if isinstance(image_paths_raw, str) else image_paths_raw or []
        except Exception:
            image_paths = []

        try:
            questions, status = extract_questions_from_post(
                content=raw_content,
                platform=platform,
                company=row["company"] or "",
                position=row["position"] or "",
                business_line=row["business_line"] or "",
                difficulty=row["difficulty"] or "",
                source_url=url,
                post_title=row["post_title"] or "",
                extraction_source="content",
            )

            # 帖子与面经无关 → 暂不删除（LLM 判断不准确），仅标记为 error 保留记录
            if status == "unrelated":
                # cnt = sqlite_service.delete_by_source_url(url)
                # logger.warning(f"  🗑️ 内容与面经无关，已删除记录: {post_title[:40]} | url={url[:80]} | 删除 {cnt} 题")
                sqlite_service.update_task_status(task_id, "error", error_msg="LLM 判断与面经无关（暂不删除）", raw_content=raw_content)
                logger.warning(f"  ⚠️ LLM 判断与面经无关，已标记 error 保留记录: {post_title[:40]} | url={url[:80]}")
                continue

            # LLM 解析失败 → 标记 error 并打印后台
            if status == "parse_error":
                sqlite_service.update_task_status(task_id, "error", error_msg="LLM 返回无法解析为 JSON", raw_content=raw_content)
                logger.error(f"  ❌ 提取失败(解析错误) task_id={task_id} url={url[:60]} title={post_title[:40]}")
                continue

            # 正文提取到题目 → 入库（必须传 raw_content 保留原文，否则会被覆盖为空）
            if questions:
                count = _save_questions(questions)
                sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source="content", raw_content=raw_content)
                logger.debug(f"  ✅ 提取完成(正文) [{post_title[:40]}]: {count} 道题目入库")
                processed += count
                continue

            # 正文无题目，有图片 → 尝试 OCR 后再提取
            if image_paths:
                from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
                logger.warning(f"  📷 正文无题目，尝试 OCR {len(image_paths)} 张图片...")
                ocr_text = ocr_images_to_text(image_paths, task_id)
                if ocr_text:
                    content_with_ocr = raw_content + "\n\n【图片 OCR 识别补充】\n" + ocr_text
                    questions2, status2 = extract_questions_from_post(
                        content=content_with_ocr,
                        platform=platform,
                        company=row["company"] or "",
                        position=row["position"] or "",
                        business_line=row["business_line"] or "",
                        difficulty=row["difficulty"] or "",
                        source_url=url,
                        post_title=row["post_title"] or "",
                        extraction_source="image",
                    )
                    if questions2:
                        count = _save_questions(questions2)
                        sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source="image", raw_content=raw_content)
                        logger.debug(f"  ✅ 提取完成(图片) [{post_title[:40]}]: {count} 道题目入库")
                        processed += count
                        continue

            # 正文无题目，OCR 也无 → 暂不删除（LLM 判断不准确），仅标记为 error 保留记录
            # cnt = sqlite_service.delete_by_source_url(url)
            # logger.warning(f"  🗑️ 正文+OCR 均无题目（与面经无关），已删除记录: {post_title[:40]} | url={url[:80]} | 删除 {cnt} 题")
            sqlite_service.update_task_status(task_id, "error", error_msg="正文+OCR 均无题目（暂不删除）", raw_content=raw_content)
            logger.warning(f"  ⚠️ 正文+OCR 均无题目，已标记 error 保留记录: {post_title[:40]} | url={url[:80]}")

        except Exception as e:
            import traceback
            sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200], raw_content=raw_content)
            logger.error(
                f"  ❌ LLM 提取失败 task_id={task_id} url={url[:60]} title={post_title[:40]}\n"
                f"      error={e}\n{traceback.format_exc()}"
            )

# 递归重试逻辑（添加到scheduler.py的_process_pending_tasks函数末尾）

    logger.info(f"[定时任务] ⚙️  本轮处理完成，入库题目 {processed} 道")

    # ── Step 3: 递归重试失败的任务（直到全部成功或达到最大次数）──────────────────────────────
    from backend.config.config import settings
    max_recursive_retries = settings.crawler_recursive_retry_max
    
    retry_round = 0
    while retry_round < max_recursive_retries:
        # 检查是否还有error状态的任务
        error_tasks = sqlite_service.get_tasks_by_status("error", limit=batch_size)
        if not error_tasks:
            logger.info(f"[定时任务] ✅ 所有任务处理完成，无需重试")
            break
        
        retry_round += 1
        logger.info(f"[定时任务] 🔄 第 {retry_round}/{max_recursive_retries} 轮递归重试，发现 {len(error_tasks)} 个失败任务...")
        
        # 重试这些失败任务
        retry_success = 0
        for task in error_tasks:
            task_id = task["task_id"]
            url = task["source_url"]
            title = task["post_title"] or "无标题"
            
            try:
                # 重新抓取详情页
                from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
                from backend.services.crawler.image_utils import download_images
                crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
                
                logger.debug(f"  🔄 重试抓取: {title[:40]}... | {url[:60]}")
                content, image_urls = crawler.fetch_post_content_full(url)
                
                if not content or len(content) < 100:
                    logger.warning(f"    ⚠️ 重试失败：内容为空或过短")
                    continue
                
                # 下载图片
                image_paths = download_images(image_urls, task_id) if image_urls else []
                
                # 更新为fetched状态
                sqlite_service.update_task_status(
                    task_id, "fetched",
                    raw_content=content,
                    image_paths=image_paths,
                )
                
                # 立即尝试提取
                questions, status = extract_questions_from_post(
                    content=content,
                    platform=task["source_platform"],
                    company=task["company"] or "",
                    position=task["position"] or "",
                    business_line=task["business_line"] or "",
                    difficulty=task["difficulty"] or "",
                    source_url=url,
                    post_title=title,
                    extraction_source="content",
                )
                
                if questions:
                    count = _save_questions(questions)
                    sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source="content", raw_content=content)
                    logger.info(f"    ✅ 重试成功: {title[:40]} | 提取 {count} 道题目")
                    retry_success += 1
                    processed += count
                else:
                    # 尝试OCR
                    if image_paths:
                        from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
                        logger.debug(f"    📷 尝试 OCR {len(image_paths)} 张图片...")
                        ocr_text = ocr_images_to_text(image_paths, task_id)
                        if ocr_text:
                            content_with_ocr = content + "\n\n【图片 OCR 识别补充】\n" + ocr_text
                            questions2, status2 = extract_questions_from_post(
                                content=content_with_ocr,
                                platform=task["source_platform"],
                                company=task["company"] or "",
                                position=task["position"] or "",
                                business_line=task["business_line"] or "",
                                difficulty=task["difficulty"] or "",
                                source_url=url,
                                post_title=title,
                                extraction_source="image",
                            )
                            if questions2:
                                count = _save_questions(questions2)
                                sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source="image", raw_content=content)
                                logger.info(f"    ✅ 重试成功(OCR): {title[:40]} | 提取 {count} 道题目")
                                retry_success += 1
                                processed += count
                                continue
                    
                    # 仍然失败，保持error状态
                    sqlite_service.update_task_status(task_id, "error", error_msg=f"第{retry_round}轮重试仍无法提取题目", raw_content=content)
                    logger.warning(f"    ⚠️ 重试失败: {title[:40]} | 仍无法提取题目")
                    
            except Exception as e:
                logger.error(f"    ❌ 重试异常: {title[:40]} | {e}")
                sqlite_service.update_task_status(task_id, "error", error_msg=f"第{retry_round}轮重试异常: {str(e)[:150]}")
        
        logger.info(f"[定时任务] 🔄 第 {retry_round} 轮重试完成：成功 {retry_success}/{len(error_tasks)} 个任务")
        
        # 如果本轮没有任何成功，提前退出
        if retry_success == 0:
            logger.warning(f"[定时任务] ⚠️ 第 {retry_round} 轮重试无任何成功，停止递归重试")
            break
    
    # 最终统计
    final_error_count = len(sqlite_service.get_tasks_by_status("error", limit=1000))
    if final_error_count > 0:
        logger.warning(f"[定时任务] ⚠️ 递归重试结束，仍有 {final_error_count} 个任务失败")
    else:
        logger.info(f"[定时任务] ✅ 所有任务处理完成！")

    return processed



def _get_embedding(text: str) -> Optional[List[float]]:
    """获取文本向量（调用 DashScope Embedding API），失败时返回 None"""
    try:
        from backend.tools.knowledge_manager_tools import generate_embedding
        vec = generate_embedding(text)
        return vec if vec else None
    except Exception as e:
        logger.debug(f"生成 embedding 失败（Neo4j 写入将跳过）: {e}")
        return None


def _save_questions(questions: List[Dict]) -> int:
    """
    将提取的题目写入 SQLite（主存储）+ Neo4j（知识图谱，可选）。
    Neo4j 不可用时静默跳过，不影响 SQLite 入库。
    返回成功入库数量。
    """
    saved = 0
    for q in questions:
        if not isinstance(q, dict):
            logger.warning("跳过非字典题目项")
            continue
        try:
            tags = (
                json.loads(q.get("topic_tags", "[]"))
                if isinstance(q.get("topic_tags"), str)
                else q.get("topic_tags", [])
            )

            # ── SQLite（主存储，必须成功）───────────────────
            extraction_source = q.get("extraction_source", "content")
            with sqlite_service._get_conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO questions
                        (q_id, question_text, answer_text, difficulty, question_type,
                         source_platform, source_url, company, position, business_line,
                         topic_tags, extraction_source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    q["q_id"], q["question_text"], q.get("answer_text", ""),
                    q.get("difficulty", "medium"), q.get("question_type", "技术题"),
                    q.get("source_platform", ""), q.get("source_url", ""),
                    q.get("company", ""), q.get("position", ""), q.get("business_line", ""),
                    json.dumps(tags, ensure_ascii=False),
                    extraction_source,
                ))
                conn.commit()

            # ── Neo4j（知识图谱 + 向量索引，可选）─────────
            if neo4j_service.available:
                embedding = _get_embedding(q["question_text"])
                if embedding:
                    neo4j_service.add_question(
                        q_id=q["q_id"],
                        text=q["question_text"],
                        answer=q.get("answer_text", ""),
                        tags=tags,
                        embedding=embedding,
                        metadata={
                            "difficulty": q.get("difficulty", "medium"),
                            "question_type": q.get("question_type", "技术题"),
                            "company": q.get("company", ""),
                            "position": q.get("position", ""),
                            "source_platform": q.get("source_platform", ""),
                            "source": q.get("source_url", ""),
                        }
                    )
                else:
                    logger.debug(f"跳过 Neo4j 写入（无法生成 embedding）: {q['q_id']}")

            saved += 1
        except Exception as e:
            logger.error(f"保存题目失败 {q.get('q_id', '?')}: {e}")
    
    # ── 更新crawl_tasks表中的公司信息（如果LLM提取到了）─────────
    if saved > 0 and questions:
        # 收集所有URL对应的公司信息
        url_company_map = {}
        for q in questions:
            if isinstance(q, dict):
                url = q.get("source_url", "")
                company = q.get("company", "").strip()
                # 只有当LLM提取到了公司信息，且不是"未知"时才更新
                if url and company and company != "未知":
                    url_company_map[url] = company
        
        # 批量更新crawl_tasks表
        if url_company_map:
            try:
                with sqlite_service._get_conn() as conn:
                    for url, company in url_company_map.items():
                        # 只更新company字段为空或"未知"的记录
                        conn.execute("""
                            UPDATE crawl_tasks 
                            SET company = ? 
                            WHERE source_url = ? 
                            AND (company IS NULL OR company = '' OR company = '未知')
                        """, (company, url))
                    conn.commit()
                logger.debug(f"[定时任务] ✅ 已更新 {len(url_company_map)} 个URL的公司信息")
            except Exception as e:
                logger.warning(f"更新crawl_tasks公司信息失败: {e}")
    
    return saved



# ══════════════════════════════════════════════════════════════
# APScheduler 调度器
# ══════════════════════════════════════════════════════════════

class CrawlScheduler:
    """面经爬取定时调度器（后台线程，不阻塞 FastAPI）"""

    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._running = False

    def start(self):
        if self._running:
            return

        nowcoder_hours = settings.scheduler_nowcoder_hours    # 如 "2,14"
        process_minute = settings.scheduler_process_minute    # 如 "0"

        # ── 牛客发现任务（cron 时间从 .env 读取）──────────────
        if cfg.ENABLE_NOWCODER:
            self._scheduler.add_job(
                _run_nowcoder_discovery,
                CronTrigger(hour=nowcoder_hours, minute=0),
                id="nowcoder_discovery",
                name="牛客面经发现",
                replace_existing=True,
                misfire_grace_time=3600,
            )

        # ── 小红书发现任务（每天凌晨3点）──────────────────────
        if cfg.ENABLE_XHS:
            self._scheduler.add_job(
                _run_xhs_discovery,
                CronTrigger(hour=3, minute=0),
                id="xhs_discovery",
                name="小红书面经发现",
                replace_existing=True,
                misfire_grace_time=3600,
            )

        # ── 任务处理器（cron 分钟从 .env 读取）────────────────
        self._scheduler.add_job(
            _process_pending_tasks,
            CronTrigger(minute=process_minute),
            id="task_processor",
            name="面经题目提取处理器",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self._scheduler.start()
        self._running = True
        
        # 从数据库加载动态配置的任务
        from backend.services.scheduler_service import scheduler_service
        db_jobs = scheduler_service.list_jobs(enabled_only=True)
        
        # 加载数据库任务
        for job in db_jobs:
            try:
                job_id = f"db_{job['job_id']}"
                job_type = job['job_type']
                schedule_type = job['schedule_type']
                schedule_config = job['schedule_config']
                job_params = job['job_params']
                
                # 构建触发器
                if schedule_type == "cron":
                    trigger = CronTrigger(
                        hour=schedule_config.get('hour'),
                        minute=schedule_config.get('minute'),
                        day=schedule_config.get('day'),
                        month=schedule_config.get('month'),
                        day_of_week=schedule_config.get('day_of_week'),
                        timezone="Asia/Shanghai"
                    )
                elif schedule_type == "interval":
                    # 确保至少有一个间隔参数不为 None
                    interval_kwargs = {}
                    if schedule_config.get('interval_seconds'):
                        interval_kwargs['seconds'] = schedule_config.get('interval_seconds')
                    if schedule_config.get('interval_minutes'):
                        interval_kwargs['minutes'] = schedule_config.get('interval_minutes')
                    if schedule_config.get('interval_hours'):
                        interval_kwargs['hours'] = schedule_config.get('interval_hours')
                    
                    if not interval_kwargs:
                        logger.warning(f"任务 {job['job_name']} 的间隔配置为空，跳过")
                        continue
                    
                    trigger = IntervalTrigger(
                        **interval_kwargs,
                        timezone="Asia/Shanghai"
                    )
                else:
                    continue
                
                # 根据任务类型选择执行函数
                if job_type == "nowcoder_discovery":
                    func = lambda jp=job_params: _run_nowcoder_discovery(
                        keywords=jp.get('nowcoder_keywords'),
                        max_pages=jp.get('nowcoder_max_pages')
                    )
                elif job_type == "xhs_discovery":
                    func = lambda jp=job_params: _run_xhs_discovery(
                        keywords=jp.get('xhs_keywords'),
                        max_notes=jp.get('xhs_max_notes'),
                        headless=jp.get('xhs_headless', True)
                    )
                elif job_type == "process_tasks":
                    func = lambda jp=job_params: _process_pending_tasks(
                        batch_size=jp.get('process_batch_size')
                    )
                else:
                    continue
                
                # 添加任务到调度器
                self._scheduler.add_job(
                    func,
                    trigger,
                    id=job_id,
                    name=job['job_name'],
                    replace_existing=True,
                    misfire_grace_time=3600
                )
            except Exception as e:
                logger.error(f"加载数据库任务失败 {job.get('job_name', '?')}: {e}")
        
        # 显示实际加载的任务信息
        logger.info("✅ 面经爬取调度器已启动")
        all_jobs = self._scheduler.get_jobs()
        
        # 按类型分组显示
        nowcoder_jobs = [j for j in all_jobs if 'nowcoder' in j.id.lower()]
        xhs_jobs = [j for j in all_jobs if 'xhs' in j.id.lower()]
        process_jobs = [j for j in all_jobs if 'process' in j.id.lower() or 'task' in j.id.lower()]
        
        if nowcoder_jobs:
            for job in nowcoder_jobs:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "N/A"
                logger.info(f"   - {job.name}：下次运行 {next_run}")
        else:
            logger.info(f"   - 牛客发现：未配置")
        
        if xhs_jobs:
            for job in xhs_jobs:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "N/A"
                logger.info(f"   - {job.name}：下次运行 {next_run}")
        else:
            logger.info(f"   - XHS 发现：未配置")
        
        if process_jobs:
            for job in process_jobs:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "N/A"
                logger.info(f"   - {job.name}：下次运行 {next_run}")
        else:
            logger.info(f"   - 任务处理：未配置")

    def stop(self):
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("调度器已停止")

    # ── 手动触发接口（供 API 调用）───────────────────────────

    def trigger_nowcoder_discovery(self, keywords: List[str] = None, max_pages: int = 2) -> tuple:
        """手动触发牛客发现（立即执行，返回 (新增任务数, 发现列表)）"""
        logger.info("手动触发牛客发现任务...")
        return _run_nowcoder_discovery(keywords=keywords, max_pages=max_pages)

    def trigger_xhs_discovery(self, keywords: List[str] = None, max_notes: int = None, headless: bool = True) -> int:
        """
        手动触发小红书发现任务。
        headless=True：无头运行（需已登录），适合 API 触发
        headless=False：弹出浏览器（自动等待扫码），适合首次运行
        """
        logger.info(f"手动触发 XHS 发现任务 headless={headless}...")
        return _run_xhs_discovery(keywords=keywords, max_notes=max_notes, headless=headless)

    def trigger_process_tasks(self, batch_size: int = None) -> int:
        """手动触发任务处理（立即提取题目），batch_size 不传时从 env CRAWLER_PROCESS_BATCH_SIZE 读取"""
        _batch = batch_size if batch_size is not None else cfg.PROCESS_BATCH_SIZE
        logger.info(f"手动触发任务处理 batch_size={_batch}...")
        return _process_pending_tasks(batch_size=_batch)

    def get_stats(self) -> Dict:
        """获取调度器统计信息（含 keywords 用于筛选下拉）"""
        crawl_stats = sqlite_service.get_crawl_stats()
        keywords = sqlite_service.get_crawl_keywords()
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if next_run else "N/A",
            })
        return {
            "running": self._running,
            "scheduled_jobs": jobs,
            "crawl_stats": crawl_stats,
            "keywords": keywords,
        }



    def reload_jobs(self):
        """从数据库重新加载定时任务配置"""
        from backend.services.scheduler_service import scheduler_service
        
        if not self._running:
            logger.warning("调度器未运行，无法重新加载任务")
            return
        
        logger.info("开始重新加载定时任务...")
        
        # 移除所有现有的数据库任务（保留代码中定义的默认任务）
        for job in self._scheduler.get_jobs():
            if job.id.startswith("db_"):  # 数据库任务的 ID 前缀
                self._scheduler.remove_job(job.id)
        
        # 从数据库加载启用的任务
        jobs = scheduler_service.list_jobs(enabled_only=True)
        
        for job in jobs:
            try:
                job_id = f"db_{job['job_id']}"
                job_type = job['job_type']
                schedule_type = job['schedule_type']
                schedule_config = job['schedule_config']
                job_params = job['job_params']
                
                # 构建触发器
                if schedule_type == "cron":
                    trigger = CronTrigger(
                        hour=schedule_config.get('hour'),
                        minute=schedule_config.get('minute'),
                        day=schedule_config.get('day'),
                        month=schedule_config.get('month'),
                        day_of_week=schedule_config.get('day_of_week'),
                        timezone="Asia/Shanghai"
                    )
                elif schedule_type == "interval":
                    # 确保至少有一个间隔参数不为 None
                    interval_kwargs = {}
                    if schedule_config.get('interval_seconds'):
                        interval_kwargs['seconds'] = schedule_config.get('interval_seconds')
                    if schedule_config.get('interval_minutes'):
                        interval_kwargs['minutes'] = schedule_config.get('interval_minutes')
                    if schedule_config.get('interval_hours'):
                        interval_kwargs['hours'] = schedule_config.get('interval_hours')
                    
                    if not interval_kwargs:
                        logger.warning(f"任务 {job['job_name']} 的间隔配置为空，跳过")
                        continue
                    
                    trigger = IntervalTrigger(
                        **interval_kwargs,
                        timezone="Asia/Shanghai"
                    )
                else:
                    logger.warning(f"未知的调度类型: {schedule_type}")
                    continue
                
                # 根据任务类型选择执行函数
                if job_type == "nowcoder_discovery":
                    func = lambda jp=job_params: _run_nowcoder_discovery(
                        keywords=jp.get('nowcoder_keywords'),
                        max_pages=jp.get('nowcoder_max_pages')
                    )
                elif job_type == "xhs_discovery":
                    func = lambda jp=job_params: _run_xhs_discovery(
                        keywords=jp.get('xhs_keywords'),
                        max_notes=jp.get('xhs_max_notes'),
                        headless=jp.get('xhs_headless', True)
                    )
                elif job_type == "process_tasks":
                    func = lambda jp=job_params: _process_pending_tasks(
                        batch_size=jp.get('process_batch_size')
                    )
                else:
                    logger.warning(f"未知的任务类型: {job_type}")
                    continue
                
                # 添加任务到调度器
                self._scheduler.add_job(
                    func,
                    trigger,
                    id=job_id,
                    name=job['job_name'],
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                
                logger.info(f"✅ 已加载任务: {job['job_name']} ({job_type})")
                
            except Exception as e:
                logger.error(f"加载任务失败 {job.get('job_name', '?')}: {e}", exc_info=True)
        
        logger.info(f"定时任务重新加载完成，当前共 {len(self._scheduler.get_jobs())} 个任务")


# ── 全局单例 ─────────────────────────────────────────────────
crawl_scheduler = CrawlScheduler()
# 为了兼容性，提供别名
scheduler = crawl_scheduler



def _retry_failed_tasks(max_retries: int = None, retry_delay: int = None) -> int:
    """
    重试爬取失败的任务
    
    Args:
        max_retries: 最大重试次数（不传时从配置读取）
        retry_delay: 重试间隔秒数（不传时从配置读取）
    
    Returns:
        成功重试的任务数
    """
    from backend.config.config import settings
    import time
    
    _max_retries = max_retries if max_retries is not None else settings.crawler_fetch_max_retries
    _retry_delay = retry_delay if retry_delay is not None else settings.crawler_retry_delay
    
    logger.info(f"[定时任务] 🔄 开始重试失败任务（最大重试{_max_retries}次，间隔{_retry_delay}秒）...")
    
    # 查询需要重试的任务（状态为error的）
    failed_tasks = sqlite_service.get_tasks_by_status("error", limit=50)
    
    if not failed_tasks:
        logger.info("   ✅ 没有error状态的任务")
        return 0
    
    logger.info(f"   📋 发现 {len(failed_tasks)} 个error状态的任务，开始重试...")
    from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
    crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
    
    success_count = 0
    
    for task in failed_tasks:
        task_id = task["task_id"]
        url = task["source_url"]
        title = task["post_title"] or "无标题"
        
        logger.info(f"  🔄 重试任务: {title[:40]}... | {url[:60]}")
        
        # 重试循环
        for attempt in range(1, _max_retries + 1):
            try:
                # 爬取详情页
                html = crawler._fetch_detail_html(url)
                
                if not html:
                    logger.warning(f"    ⚠️ 第{attempt}次重试失败：未获取到HTML")
                    if attempt < _max_retries:
                        time.sleep(_retry_delay)
                        continue
                    else:
                        sqlite_service.update_task_status(
                            task_id, "error", 
                            error_msg=f"重试{_max_retries}次后仍无法获取HTML"
                        )
                        break
                
                # 提取内容
                title_extracted, content = crawler._extract_content_from_initial_state_feed(html)
                
                if not content or len(content) < 50:
                    logger.warning(f"    ⚠️ 第{attempt}次重试失败：内容为空或过短")
                    if attempt < _max_retries:
                        time.sleep(_retry_delay)
                        continue
                    else:
                        sqlite_service.update_task_status(
                            task_id, "error", 
                            error_msg=f"重试{_max_retries}次后仍无法提取内容"
                        )
                        break
                
                # 提取图片
                images = crawler._extract_images_from_html(html)
                
                # 下载图片
                image_paths = []
                if images:
                    from backend.services.crawler.image_utils import download_images
                    image_paths = download_images(images, task_id)
                
                # 更新任务状态
                sqlite_service.update_task_status(
                    task_id=task_id,
                    status="fetched",
                    raw_content=content,
                    image_paths=image_paths,
                )
                
                success_count += 1
                logger.info(f"    ✅ 第{attempt}次重试成功: {len(content)}字符, {len(image_paths)}张图片")
                break
                
            except Exception as e:
                logger.error(f"    ❌ 第{attempt}次重试异常: {e}")
                if attempt < _max_retries:
                    time.sleep(_retry_delay)
                else:
                    sqlite_service.update_task_status(
                        task_id, "error", 
                        error_msg=f"重试{_max_retries}次后仍失败: {str(e)[:200]}"
                    )
        
        # 每个任务之间稍微延迟
        time.sleep(2)
    
    logger.info(f"[定时任务] ✅ 重试完成：成功 {success_count}/{len(failed_tasks)} 个任务")
    return success_count




