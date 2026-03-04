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

def _run_nowcoder_discovery(keywords: List[str] = None, max_pages: int = None):
    """牛客面经发现任务（keywords/max_pages 不传时从 .env 读取）"""
    _keywords = keywords or cfg.NOWCODER_KEYWORDS
    _max_pages = max_pages if max_pages is not None else cfg.NOWCODER_MAX_PAGES
    logger.info(f"🔍 牛客发现任务开始（关键词={_keywords}, 最大页数={_max_pages}）...")
    try:
        from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
        crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
        posts = crawler.discover(keywords=_keywords, max_pages=_max_pages)

        added = 0
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
            )
            if task_id:
                added += 1

        logger.info(f"✅ 牛客发现任务完成：发现 {len(posts)} 条，新增队列 {added} 条")
        return added
    except Exception as e:
        logger.error(f"❌ 牛客发现任务失败: {e}", exc_info=True)
        return 0


def _run_xhs_discovery(headless: bool = True):
    """小红书面经发现任务（定时任务默认 headless=True，依赖已保存的登录状态）"""
    logger.info("🔍 小红书发现任务开始...")
    try:
        from backend.services.crawler.xhs_crawler import XHSCrawler
        crawler = XHSCrawler(headless=headless)
        posts = crawler.discover(
            keywords=cfg.XHS_KEYWORDS,
            max_notes_per_keyword=cfg.XHS_MAX_NOTES_PER_KEYWORD,
        )

        from backend.services.crawler.crawl_helpers import save_xhs_post
        added = 0
        for p in posts:
            if save_xhs_post(p, sqlite_service, download_images_flag=True):
                added += 1

        logger.info(f"✅ XHS 发现任务完成：发现 {len(posts)} 条，新增队列 {added} 条")
        return added
    except Exception as e:
        logger.error(f"❌ XHS 发现任务失败: {e}", exc_info=True)
        return 0


def _process_pending_tasks(batch_size: int = None):
    """
    处理 crawl_tasks 队列：
      pending  → 抓取详情页 → fetched
      fetched  → LLM 提取题目 → done / error
    """
    batch_size = batch_size or cfg.PROCESS_BATCH_SIZE
    logger.info(f"⚙️  开始处理任务队列（最多 {batch_size} 条）...")

    processed = 0

    # ── Step 1: pending → 抓取详情（仅牛客）──────────────────
    pending = sqlite_service.get_pending_tasks(platform="nowcoder", limit=batch_size)
    if pending:
        logger.info(f"📥 开始抓取详情，本批 {len(pending)} 条 pending 任务")
    for task in pending:
        task_id = task["task_id"]
        url = task["source_url"]
        title = (task.get("post_title") or "").strip() or "(无标题)"
        logger.info(f"  📄 正在抓取: {title[:50]}... | {url[:50]}")
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
                logger.info(f"  ✅ 抓取详情成功 [{title[:40]}]: 正文{len(content)}字, 图片{len(image_paths)}张")
            else:
                sqlite_service.update_task_status(task_id, "error", error_msg="正文内容为空或太短")
        except Exception as e:
            sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200])
            logger.error(f"  ❌ 抓取详情失败 [{title[:40]}]: {e}")

    # ── Step 2: fetched → LLM 提取 → 写库 ────────────────────
    # 同时处理牛客和小红书（XHS 在 discover 时就已经 fetched）
    with sqlite_service._get_conn() as conn:
        fetched_rows = conn.execute(
            "SELECT * FROM crawl_tasks WHERE status='fetched' LIMIT ?",
            (batch_size,)
        ).fetchall()

    if fetched_rows:
        logger.info(f"📋 开始 LLM 提取，本批 {len(fetched_rows)} 条 fetched 帖子")

    for row in fetched_rows:
        task_id = row["task_id"]
        raw_content = row["raw_content"] or ""
        url = row["source_url"]
        platform = row["source_platform"]
        post_title = (row["post_title"] or "").strip() or "(无标题)"

        logger.info(f"  📄 正在处理帖子: {post_title[:60]}... | URL: {url[:60]}")

        if not raw_content or len(raw_content) < 50:
            sqlite_service.update_task_status(task_id, "error", error_msg="raw_content 为空", raw_content=raw_content)
            continue

        try:
            questions = extract_questions_from_post(
                content=raw_content,
                platform=platform,
                company=row["company"] or "",
                position=row["position"] or "",
                business_line=row["business_line"] or "",
                difficulty=row["difficulty"] or "",
                source_url=url,
                post_title=row["post_title"] or "",
            )

            if not questions:
                sqlite_service.update_task_status(task_id, "error", error_msg="LLM 未提取到题目", raw_content=raw_content)
                continue

            count = _save_questions(questions)
            sqlite_service.update_task_status(task_id, "done", questions_count=count)
            logger.info(f"  ✅ 提取完成 [{post_title[:40]}]: {count} 道题目入库")
            processed += count

        except Exception as e:
            sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200], raw_content=raw_content)
            logger.error(f"  ❌ LLM 提取失败 [{post_title[:40]}]: {e}")

    logger.info(f"⚙️  本轮处理完成，入库题目 {processed} 道")
    return processed


def _get_embedding(text: str) -> Optional[List[float]]:
    """获取文本向量（调用 DashScope Embedding API），失败时返回 None"""
    try:
        from backend.tools.architect_tools import generate_embedding
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
            with sqlite_service._get_conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO questions
                        (q_id, question_text, answer_text, difficulty, question_type,
                         source_platform, source_url, company, position, business_line,
                         topic_tags, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    q["q_id"], q["question_text"], q.get("answer_text", ""),
                    q.get("difficulty", "medium"), q.get("question_type", "技术题"),
                    q.get("source_platform", ""), q.get("source_url", ""),
                    q.get("company", ""), q.get("position", ""), q.get("business_line", ""),
                    json.dumps(tags, ensure_ascii=False),
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
        logger.info("✅ 面经爬取调度器已启动")
        logger.info(f"   - 牛客发现：{'每天 ' + nowcoder_hours.replace(',', '/') + ':00' if cfg.ENABLE_NOWCODER else '已关闭（SCHEDULER_ENABLE_NOWCODER=false）'}")
        logger.info(f"   - XHS 发现：{'已开启（每天 03:00）' if cfg.ENABLE_XHS else '手动触发（SCHEDULER_ENABLE_XHS=false）'}")
        logger.info(f"   - 任务处理：每小时第 {process_minute} 分钟")

    def stop(self):
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("调度器已停止")

    # ── 手动触发接口（供 API 调用）───────────────────────────

    def trigger_nowcoder_discovery(self, keywords: List[str] = None, max_pages: int = 2) -> int:
        """手动触发牛客发现（立即执行，返回新增任务数）"""
        logger.info("手动触发牛客发现任务...")
        return _run_nowcoder_discovery(keywords=keywords, max_pages=max_pages)

    def trigger_xhs_discovery(self, keywords: List[str] = None, headless: bool = True) -> int:
        """
        手动触发小红书发现任务。
        headless=True：无头运行（需已登录），适合 API 触发
        headless=False：弹出浏览器（自动等待扫码），适合首次运行
        """
        logger.info(f"手动触发 XHS 发现任务 headless={headless}...")
        return _run_xhs_discovery(headless=headless)

    def trigger_process_tasks(self, batch_size: int = 10) -> int:
        """手动触发任务处理（立即提取题目）"""
        logger.info(f"手动触发任务处理 batch_size={batch_size}...")
        return _process_pending_tasks(batch_size=batch_size)

    def get_stats(self) -> Dict:
        """获取调度器统计信息"""
        crawl_stats = sqlite_service.get_crawl_stats()
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
        }


# ── 全局单例 ─────────────────────────────────────────────────
crawl_scheduler = CrawlScheduler()
