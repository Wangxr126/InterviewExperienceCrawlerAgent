"""
重构后的调度器（支持数据库配置）
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
from backend.services.scheduler_service import scheduler_service
from backend.services.neo4j_service import neo4j_service
from backend.services.crawler.question_extractor import extract_questions_from_post
from backend.services.knowledge_manager import knowledge_manager
from backend.config.config import settings

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# 配置（从 .env 读取默认值）
# ══════════════════════════════════════════════════════════════

class _CrawlerConfig:
    """从 settings（即 .env）懒加载爬虫配置，作为默认值"""

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


cfg = _CrawlerConfig()


# ══════════════════════════════════════════════════════════════
# 核心执行方法（被定时任务和手动触发共用）
# ══════════════════════════════════════════════════════════════

async def run_nowcoder_discovery(keywords: List[str] = None, max_pages: int = None) -> dict:
    """
    牛客发现任务 - 核心逻辑
    
    Returns:
        {
            "status": "success" / "error",
            "added": int,
            "discovered": List[dict],
            "error": str (可选)
        }
    """
    _keywords = keywords or cfg.NOWCODER_KEYWORDS
    _max_pages = max_pages if max_pages is not None else cfg.NOWCODER_MAX_PAGES
    
    logger.info(f"[定时任务] 🔍 牛客发现任务开始（关键词={_keywords}, 最大页数={_max_pages}）...")
    
    try:
        from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
        crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
        posts = crawler.discover(keywords=_keywords, max_pages=_max_pages)

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

        logger.info(f"[定时任务] ✅ 牛客发现任务完成：发现 {len(posts)} 条，新增队列 {added} 条")
        
        return {
            "status": "success",
            "added": added,
            "discovered": discovered,
            "total": len(posts)
        }
        
    except Exception as e:
        logger.error(f"[定时任务] ❌ 牛客发现任务失败: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "added": 0,
            "discovered": []
        }


async def run_xhs_discovery(keywords: List[str] = None, max_notes: int = None, headless: bool = True) -> dict:
    """
    小红书发现任务 - 核心逻辑
    
    Returns:
        {
            "status": "success" / "error",
            "added": int,
            "error": str (可选)
        }
    """
    _keywords = keywords or cfg.XHS_KEYWORDS
    _max_notes = max_notes if max_notes is not None else cfg.XHS_MAX_NOTES_PER_KEYWORD
    
    logger.info(f"[定时任务] 🔍 小红书发现任务开始（headless={headless}）...")
    
    try:
        from backend.services.crawler.xhs_crawler import XHSCrawler
        crawler = XHSCrawler(headless=headless)
        posts = crawler.discover(keywords=_keywords, max_notes_per_keyword=_max_notes)

        from backend.services.crawler.crawl_helpers import save_xhs_post
        added = 0
        for p in posts:
            if save_xhs_post(p, sqlite_service, download_images_flag=True):
                added += 1

        logger.info(f"[定时任务] ✅ XHS 发现任务完成：发现 {len(posts)} 条，新增队列 {added} 条")
        
        return {
            "status": "success",
            "added": added,
            "total": len(posts)
        }
        
    except Exception as e:
        logger.error(f"[定时任务] ❌ XHS 发现任务失败: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "added": 0
        }


async def run_process_tasks(batch_size: int = None) -> dict:
    """
    处理任务队列 - 核心逻辑
    
    Returns:
        {
            "status": "success" / "error",
            "processed": int,
            "error": str (可选)
        }
    """
    batch_size = batch_size or cfg.PROCESS_BATCH_SIZE
    logger.info(f"[定时任务] ⚙️  开始处理任务队列（最多 {batch_size} 条）...")

    try:
        processed = 0

        # Step 1: pending → 抓取详情（仅牛客）
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

        # Step 2: fetched → LLM 提取
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

            if not raw_content or len(raw_content) < 50:
                sqlite_service.update_task_status(task_id, "error", error_msg="raw_content 为空", raw_content=raw_content)
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

                if status == "unrelated":
                    sqlite_service.update_task_status(task_id, "error", error_msg="LLM 判断与面经无关", raw_content=raw_content)
                    continue

                if status == "parse_error":
                    sqlite_service.update_task_status(task_id, "error", error_msg="LLM 返回无法解析", raw_content=raw_content)
                    continue

                if questions:
                    count = _save_questions(questions)
                    sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source="content", raw_content=raw_content)
                    processed += count
                    continue

                # 尝试 OCR
                if image_paths:
                    from backend.services.crawler.ocr_service_mcp import ocr_images_to_text
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
                            processed += count
                            continue

                sqlite_service.update_task_status(task_id, "error", error_msg="正文+OCR 均无题目", raw_content=raw_content)

            except Exception as e:
                sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200], raw_content=raw_content)
                logger.error(f"[定时任务] ❌ LLM 提取失败: {e}")

        logger.info(f"[定时任务] ⚙️  本轮处理完成，入库题目 {processed} 道")
        
        return {
            "status": "success",
            "processed": processed
        }
        
    except Exception as e:
        logger.error(f"[定时任务] ❌ 任务处理失败: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "processed": 0
        }


def _get_embedding(text: str) -> Optional[List[float]]:
    """获取文本向量"""
    try:
        from backend.tools.knowledge_manager_tools import generate_embedding
        vec = generate_embedding(text)
        return vec if vec else None
    except Exception as e:
        logger.debug(f"生成 embedding 失败: {e}")
        return None


def _save_questions(questions: List[Dict]) -> int:
    """保存题目到 SQLite + Neo4j"""
    saved = 0
    for q in questions:
        if not isinstance(q, dict):
            continue
        try:
            tags = (
                json.loads(q.get("topic_tags", "[]"))
                if isinstance(q.get("topic_tags"), str)
                else q.get("topic_tags", [])
            )

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

            saved += 1
        except Exception as e:
            logger.error(f"保存题目失败 {q.get('q_id', '?')}: {e}")
    
    return saved


# ══════════════════════════════════════════════════════════════
# 重构后的调度器类
# ══════════════════════════════════════════════════════════════

class CrawlScheduler:
    """面经爬取调度器（支持数据库配置）"""

    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._running = False
        self._job_registry = {}  # job_id -> APScheduler job_id 映射

    def start(self):
        """启动调度器，从数据库加载所有启用的任务"""
        if self._running:
            return

        # 从数据库加载启用的任务
        jobs = scheduler_service.list_jobs(enabled_only=True)
        
        for job_config in jobs:
            self._add_scheduler_job(job_config)

        self._scheduler.start()
        self._running = True
        
        logger.info(f"[定时任务] ✅ 调度器已启动，加载 {len(jobs)} 个任务")

    def stop(self):
        """停止调度器"""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("[定时任务] 调度器已停止")

    def reload_jobs(self):
        """重新加载数据库中的任务配置"""
        if not self._running:
            return
        
        # 移除所有现有任务
        for job_id in list(self._job_registry.keys()):
            apscheduler_job_id = self._job_registry[job_id]
            try:
                self._scheduler.remove_job(apscheduler_job_id)
            except:
                pass
        self._job_registry.clear()
        
        # 重新加载
        jobs = scheduler_service.list_jobs(enabled_only=True)
        for job_config in jobs:
            self._add_scheduler_job(job_config)
        
        logger.info(f"[定时任务] ✅ 已重新加载 {len(jobs)} 个任务")

    def _add_scheduler_job(self, job_config: dict):
        """将数据库任务添加到 APScheduler"""
        job_id = job_config["job_id"]
        job_type = job_config["job_type"]
        schedule_type = job_config["schedule_type"]
        schedule_config = job_config["schedule_config"]
        job_params = job_config["job_params"]
        
        # 创建触发器
        if schedule_type == "cron":
            trigger = CronTrigger(
                hour=schedule_config.get("hour", "*"),
                minute=schedule_config.get("minute", "*"),
                day=schedule_config.get("day", "*"),
                month=schedule_config.get("month", "*"),
                day_of_week=schedule_config.get("day_of_week", "*"),
                timezone="Asia/Shanghai"
            )
        elif schedule_type == "interval":
            trigger = IntervalTrigger(
                hours=schedule_config.get("hours", 0),
                minutes=schedule_config.get("minutes", 0),
                seconds=schedule_config.get("seconds", 0),
                timezone="Asia/Shanghai"
            )
        else:
            logger.error(f"未知的调度类型: {schedule_type}")
            return
        
        # 创建任务函数（同步包装器，避免协程警告）
        def job_wrapper():
            import asyncio
            try:
                # 在新的事件循环中运行异步任务
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self._execute_job(job_id, job_type, job_params))
                finally:
                    loop.close()
                
                # 更新运行信息
                next_run = self._scheduler.get_job(f"db_job_{job_id}").next_run_time
                scheduler_service.update_job_run_info(
                    job_id=job_id,
                    status=result["status"],
                    result=result,
                    next_run_at=next_run
                )
            except Exception as e:
                logger.error(f"[定时任务] 任务执行异常: {e}", exc_info=True)
        
        # 添加到 APScheduler
        apscheduler_job_id = f"db_job_{job_id}"
        self._scheduler.add_job(
            job_wrapper,
            trigger=trigger,
            id=apscheduler_job_id,
            name=job_config["job_name"],
            replace_existing=True,
            misfire_grace_time=3600
        )
        
        self._job_registry[job_id] = apscheduler_job_id
        logger.info(f"[定时任务] ✅ 已添加任务: {job_config['job_name']}")

    async def _execute_job(self, job_id: str, job_type: str, job_params: dict) -> dict:
        """执行任务"""
        logger.info(f"[定时任务] 🚀 执行任务: {job_type} (ID: {job_id})")
        
        try:
            if job_type == "nowcoder_discovery":
                return await run_nowcoder_discovery(
                    keywords=job_params.get("keywords"),
                    max_pages=job_params.get("max_pages")
                )
            elif job_type == "xhs_discovery":
                return await run_xhs_discovery(
                    keywords=job_params.get("keywords"),
                    max_notes=job_params.get("max_notes_per_keyword"),
                    headless=job_params.get("headless", True)
                )
            elif job_type == "process_tasks":
                return await run_process_tasks(
                    batch_size=job_params.get("batch_size")
                )
            else:
                return {"status": "error", "error": f"未知的任务类型: {job_type}"}
        except Exception as e:
            logger.error(f"[定时任务] ❌ 任务执行失败: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    # ========== 任务管理接口 ==========

    def add_job(self, job_config: dict) -> str:
        """添加新任务"""
        job_id = scheduler_service.add_job(job_config)
        
        if self._running and job_config.get("enabled", True):
            job_config["job_id"] = job_id
            self._add_scheduler_job(job_config)
        
        return job_id

    def update_job(self, job_id: str, job_config: dict):
        """更新任务"""
        scheduler_service.update_job(job_id, job_config)
        
        if self._running:
            # 移除旧任务
            if job_id in self._job_registry:
                apscheduler_job_id = self._job_registry[job_id]
                try:
                    self._scheduler.remove_job(apscheduler_job_id)
                except:
                    pass
                del self._job_registry[job_id]
            
            # 添加新任务（如果启用）
            if job_config.get("enabled", True):
                job_config["job_id"] = job_id
                self._add_scheduler_job(job_config)

    def delete_job(self, job_id: str):
        """删除任务"""
        if self._running and job_id in self._job_registry:
            apscheduler_job_id = self._job_registry[job_id]
            try:
                self._scheduler.remove_job(apscheduler_job_id)
            except:
                pass
            del self._job_registry[job_id]
        
        scheduler_service.delete_job(job_id)

    def enable_job(self, job_id: str):
        """启用任务"""
        scheduler_service.enable_job(job_id)
        
        if self._running:
            job_config = scheduler_service.get_job(job_id)
            if job_config:
                self._add_scheduler_job(job_config)

    def disable_job(self, job_id: str):
        """禁用任务"""
        scheduler_service.disable_job(job_id)
        
        if self._running and job_id in self._job_registry:
            apscheduler_job_id = self._job_registry[job_id]
            try:
                self._scheduler.remove_job(apscheduler_job_id)
            except:
                pass
            del self._job_registry[job_id]

    async def trigger_job(self, job_id: str) -> dict:
        """手动触发任务"""
        job_config = scheduler_service.get_job(job_id)
        if not job_config:
            return {"status": "error", "error": "任务不存在"}
        
        result = await self._execute_job(
            job_id=job_id,
            job_type=job_config["job_type"],
            job_params=job_config["job_params"]
        )
        
        # 更新运行信息
        next_run = None
        if job_id in self._job_registry:
            apscheduler_job_id = self._job_registry[job_id]
            job = self._scheduler.get_job(apscheduler_job_id)
            if job:
                next_run = job.next_run_time
        
        scheduler_service.update_job_run_info(
            job_id=job_id,
            status=result["status"],
            result=result,
            next_run_at=next_run
        )
        
        return result

    def get_stats(self) -> Dict:
        """获取调度器统计信息"""
        jobs = scheduler_service.list_jobs()
        crawl_stats = sqlite_service.get_crawl_stats()
        keywords = sqlite_service.get_crawl_keywords()
        
        return {
            "running": self._running,
            "total_jobs": len(jobs),
            "enabled_jobs": sum(1 for j in jobs if j["enabled"]),
            "disabled_jobs": sum(1 for j in jobs if not j["enabled"]),
            "jobs": jobs,
            "crawl_stats": crawl_stats,
            "keywords": keywords
        }

    # ========== 向后兼容方法（供旧代码调用）==========

    def trigger_nowcoder_discovery(self, keywords: List[str] = None, max_pages: int = 2) -> tuple:
        """手动触发牛客发现（兼容旧接口，返回 (新增数, 发现列表)）"""
        import asyncio
        result = asyncio.run(run_nowcoder_discovery(keywords=keywords, max_pages=max_pages))
        return result.get("added", 0), result.get("discovered", [])

    def trigger_xhs_discovery(self, keywords: List[str] = None, headless: bool = True) -> int:
        """手动触发小红书发现（兼容旧接口，返回新增数）"""
        import asyncio
        result = asyncio.run(run_xhs_discovery(keywords=keywords, headless=headless))
        return result.get("added", 0)

    def trigger_process_tasks(self, batch_size: int = None) -> int:
        """手动触发任务处理（兼容旧接口，返回处理数）"""
        import asyncio
        result = asyncio.run(run_process_tasks(batch_size=batch_size))
        return result.get("processed", 0)


# 全局单例
crawl_scheduler = CrawlScheduler()
