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
import time
import uuid
from datetime import datetime
from typing import List, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.services.storage.sqlite_service import sqlite_service
from backend.services.storage.neo4j_service import neo4j_service
from backend.services.crawler.question_extractor import extract_questions_from_post
from backend.services.knowledge.knowledge_manager import knowledge_manager
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
    logger.info(f"🔍 牛客发现任务开始（关键词={_keywords}, 最大页数={_max_pages}）...")
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

        logger.info(f"✅ 牛客发现任务完成：发现 {len(posts)} 条，新增队列 {added} 条")
        return added, discovered
    except Exception as e:
        logger.error(f"❌ 牛客发现任务失败: {e}", exc_info=True)
        return 0, []


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
        try:
            from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
            from backend.services.crawler.image_utils import download_images
            crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
            content, image_urls = crawler.fetch_post_content_full(url)
            if content and len(content) >= 50:
                image_paths = download_images(image_urls, task_id) if image_urls else []
                sqlite_service.update_task_status(
                    task_id, "fetched",
                    raw_content=content,
                    image_paths=image_paths,
                )
                logger.info(f"✅抓取content成功 [{title[:40]}]: 正文{len(content)}字, 图片{len(image_paths)}张")
            else:
                logger.warning(f"⚠️ 正文内容为空或太短（{len(content) if content else 0}字），跳过: {title[:40]}")
                sqlite_service.update_task_status(task_id, "error", error_msg=f"正文内容太短({len(content) if content else 0}字，需≥50字)")
        except Exception as e:
            sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200])
            logger.error(f"❌抓取详情失败 [{title[:40]}]: {e}")

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

        if not raw_content or len(raw_content) < 50:
            sqlite_service.update_task_status(task_id, "error", error_msg="raw_content 为空", raw_content=raw_content)
            logger.error(f"  ❌ 提取失败(正文为空) task_id={task_id} url={url[:60]} title={post_title[:40]}")
            continue

        image_paths_raw = row["image_paths"] or "[]"
        try:
            image_paths = json.loads(image_paths_raw) if isinstance(image_paths_raw, str) else image_paths_raw or []
        except Exception:
            image_paths = []

        logger.info(f"\n{'─' * 60}")
        logger.info(f"  📄 [{platform}] {post_title[:60]}")
        logger.info(f"  🔗 {url}")
        logger.info(f"  🆔 {task_id} | 正文={len(raw_content)}字 | 图片={len(image_paths)}张")
        logger.info(f"{'─' * 60}")

        _t0 = time.time()
        try:
            # MinerAgent（function-calling 模式）自主决定是否调用 ocr_images 工具：
            # - 正文有题目 → 直接调用 Finish 返回 JSON
            # - 正文无题目但有图片 → 自主调用 ocr_images → 再调用 Finish 返回 JSON
            questions, status, agent_used_tool = extract_questions_from_post(
                content=raw_content,
                platform=platform,
                company=row["company"] or "",
                position=row["position"] or "",
                business_line=row["business_line"] or "",
                difficulty=row["difficulty"] or "",
                source_url=url,
                post_title=row["post_title"] or "",
                extraction_source="content",
                image_paths=image_paths,
                task_id=task_id,
            )

            # 帖子与面经无关 → 标记 error 保留记录
            if status == "unrelated":
                sqlite_service.update_task_status(task_id, "error", error_msg="LLM 判断与面经无关（暂不删除）", raw_content=raw_content, agent_used_tool=agent_used_tool, extract_duration_sec=round(time.time()-_t0, 1))
                logger.warning(f"  ⚠️ LLM 判断与面经无关，已标记 error 保留记录: {post_title[:40]} | url={url[:80]}")
                continue

            # LLM 解析失败 → 标记 error
            if status == "parse_error":
                sqlite_service.update_task_status(task_id, "error", error_msg="LLM 返回无法解析为 JSON", raw_content=raw_content, agent_used_tool=agent_used_tool, extract_duration_sec=round(time.time()-_t0, 1))
                logger.error(f"  ❌ 提取失败(解析错误) task_id={task_id} url={url[:60]} title={post_title[:40]}")
                continue

            # 提取到题目 → 入库
            if questions:
                extraction_src = "image" if image_paths and not raw_content.strip() else "content"
                count = _save_questions(questions)
                _dur = round(time.time()-_t0, 1)
                sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source=extraction_src, raw_content=raw_content, agent_used_tool=agent_used_tool, extract_duration_sec=_dur)
                logger.info(f"  ✅ 提取完成 [{post_title[:40]}]: {count} 道题目入库，耗时 {_dur}s")
                processed += count
                continue

            # MinerAgent 正文+OCR 均无题目 → 标记 error 保留记录
            sqlite_service.update_task_status(task_id, "error", error_msg="正文+OCR 均无题目（暂不删除）", raw_content=raw_content, agent_used_tool=agent_used_tool, extract_duration_sec=round(time.time()-_t0, 1))
            logger.warning(f"  ⚠️ 正文+OCR 均无题目，已标记 error 保留记录: {post_title[:40]} | url={url[:80]}")

        except Exception as e:
            import traceback
            sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200], raw_content=raw_content, extract_duration_sec=round(time.time()-_t0, 1))
            logger.error(
                f"  ❌ LLM 提取失败 task_id={task_id} url={url[:60]} title={post_title[:40]}\n"
                f"      error={e}\n{traceback.format_exc()}"
            )

# 递归重试逻辑（添加到scheduler.py的_process_pending_tasks函数末尾）

    logger.info(f"⚙️  本轮处理完成，入库题目 {processed} 道")

    # 最终统计
    final_error_count = len(sqlite_service.get_tasks_by_status("error", limit=1000))
    if final_error_count > 0:
        logger.warning(f"⚠️ 本轮处理结束，仍有 {final_error_count} 个任务处于 error 状态")
    else:
        logger.info(f"✅ 所有任务处理完成！")

    return processed



def process_single_task(task_id: str) -> Dict:
    """
    对单个 task_id 重新执行完整的 OCR + MinerAgent 提取流程。
    适用于：
      - fetched/error 状态的任务（有正文）
      - 需要重新跑 OCR 的含图片任务

    返回 dict：
      status: ok / error
      questions_added: 提取到的题目数
      ocr_called: MinerAgent 是否调用了 OCR
      message: 人类可读描述
    """
    with sqlite_service._get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM crawl_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()

    if not row:
        return {"status": "error", "message": f"task_id 不存在: {task_id}", "questions_added": 0, "ocr_called": False}

    task = dict(row)
    raw_content = task.get("raw_content") or ""
    url = task.get("source_url", "")
    platform = task.get("source_platform", "")
    post_title = (task.get("post_title") or "").strip() or "(无标题)"

    if not raw_content or len(raw_content.strip()) < 50:
        return {
            "status": "error",
            "message": f"任务正文为空或过短（{len(raw_content)}字），需先抓取正文",
            "questions_added": 0,
            "ocr_called": False,
        }

    image_paths_raw = task.get("image_paths") or "[]"
    try:
        image_paths = json.loads(image_paths_raw) if isinstance(image_paths_raw, str) else image_paths_raw or []
    except Exception:
        image_paths = []

    logger.info(f"[SingleTask] 开始处理 task_id={task_id}, 图片数={len(image_paths)}, 正文={len(raw_content)}字")

    # 先删除该任务已有的旧题目，再重新提取（避免重复）
    with sqlite_service._get_conn() as conn:
        old_count = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE source_url=?", (url,)
        ).fetchone()[0]
        if old_count > 0:
            conn.execute("DELETE FROM questions WHERE source_url=?", (url,))
            conn.commit()
            logger.info(f"[SingleTask] 已删除旧题目 {old_count} 道")

    # 重置状态为 fetched，确保后续写库逻辑正确
    sqlite_service.update_task_status(task_id, "fetched", raw_content=raw_content, image_paths=image_paths)

    try:
        questions, status, agent_used_tool = extract_questions_from_post(
            content=raw_content,
            platform=platform,
            company=task.get("company") or "",
            position=task.get("position") or "",
            business_line=task.get("business_line") or "",
            difficulty=task.get("difficulty") or "",
            source_url=url,
            post_title=post_title,
            extraction_source="content",
            image_paths=image_paths,
            task_id=task_id,
        )
    except Exception as e:
        import traceback
        sqlite_service.update_task_status(task_id, "error", error_msg=str(e)[:200], raw_content=raw_content)
        logger.error(f"[SingleTask] 提取异常 task_id={task_id}: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": str(e)[:300], "questions_added": 0, "ocr_called": False}

    if status == "unrelated":
        sqlite_service.update_task_status(task_id, "error", error_msg="LLM 判断与面经无关", raw_content=raw_content, agent_used_tool=agent_used_tool)
        return {"status": "ok", "message": "LLM 判断内容与面经无关", "questions_added": 0, "ocr_called": agent_used_tool}

    if status == "parse_error":
        sqlite_service.update_task_status(task_id, "error", error_msg="LLM 返回无法解析为 JSON", raw_content=raw_content, agent_used_tool=agent_used_tool)
        return {"status": "error", "message": "LLM 返回格式错误，无法解析", "questions_added": 0, "ocr_called": agent_used_tool}

    if questions:
        extraction_src = "image" if image_paths and not raw_content.strip() else "content"
        count = _save_questions(questions)
        sqlite_service.update_task_status(task_id, "done", questions_count=count, extraction_source=extraction_src, raw_content=raw_content, agent_used_tool=agent_used_tool)
        logger.info(f"[SingleTask] 完成 task_id={task_id}: {count} 道题目入库, ocr_called={agent_used_tool}")
        return {
            "status": "ok",
            "message": f"提取完成，{count} 道题目入库" + ("（含 OCR 识别图片）" if agent_used_tool else ""),
            "questions_added": count,
            "ocr_called": agent_used_tool,
        }

    sqlite_service.update_task_status(task_id, "error", error_msg="正文+OCR 均无题目", raw_content=raw_content, agent_used_tool=agent_used_tool)
    return {"status": "ok", "message": "未提取到题目（正文和图片均无面试题内容）", "questions_added": 0, "ocr_called": agent_used_tool}


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
                logger.debug(f"✅ 已更新 {len(url_company_map)} 个URL的公司信息")
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

        # 从数据库加载所有启用的任务（替代硬编码 cron）
        from backend.services.scheduling.scheduler_service import scheduler_service
        jobs = scheduler_service.list_jobs(enabled_only=True)
        for job_config in jobs:
            self._add_scheduler_job(job_config)

        self._scheduler.start()
        self._running = True
        logger.info(f"[定时任务] ✅ 调度器已启动，从数据库加载 {len(jobs)} 个任务")

    def _add_scheduler_job(self, job_config: dict):
        """将数据库任务配置添加到 APScheduler"""
        from backend.services.scheduling.scheduler_service import scheduler_service
        job_id = job_config["job_id"]
        schedule_type = job_config["schedule_type"]
        schedule_config = job_config["schedule_config"]
        job_params = job_config.get("job_params", {})
        job_type = job_config["job_type"]

        # 构建触发器
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
            import pytz
            from datetime import timedelta
            _hours = schedule_config.get("interval_hours") or schedule_config.get("hours", 0)
            _minutes = schedule_config.get("interval_minutes") or schedule_config.get("minutes", 0)
            _seconds = schedule_config.get("interval_seconds") or schedule_config.get("seconds", 0)
            _tz = pytz.timezone("Asia/Shanghai")
            _start_date = None
            _raw_start = schedule_config.get("start_time")
            if _raw_start:
                try:
                    _h, _m = [int(x) for x in _raw_start.split(":")]
                    _now = datetime.now(_tz)
                    _candidate = _now.replace(hour=_h, minute=_m, second=0, microsecond=0)
                    if _candidate <= _now:
                        _candidate += timedelta(days=1)
                    _start_date = _candidate
                    logger.info(f"[定时任务] interval 首次执行: {_start_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                except Exception as _e:
                    logger.warning(f"[定时任务] start_time 解析失败（{_raw_start}），立即开始: {_e}")
            trigger = IntervalTrigger(
                hours=int(_hours),
                minutes=int(_minutes),
                seconds=int(_seconds),
                start_date=_start_date,
                timezone="Asia/Shanghai"
            )
        else:
            logger.error(f"[定时任务] 未知调度类型: {schedule_type}")
            return

        # 任务执行函数
        def _make_job_fn(jid, jtype, jparams):
            def job_fn():
                try:
                    if jtype == "nowcoder_discovery":
                        _run_nowcoder_discovery(
                            keywords=jparams.get("nowcoder_keywords"),
                            max_pages=jparams.get("nowcoder_max_pages")
                        )
                    elif jtype == "xhs_discovery":
                        _run_xhs_discovery(
                            headless=jparams.get("xhs_headless", True)
                        )
                    elif jtype == "process_tasks":
                        _process_pending_tasks(
                            batch_size=jparams.get("process_batch_size")
                        )
                    else:
                        logger.error(f"[定时任务] 未知任务类型: {jtype}")
                except Exception as e:
                    logger.error(f"[定时任务] 任务执行异常 {jtype}: {e}", exc_info=True)
            return job_fn

        apscheduler_id = f"db_{job_id}"
        self._scheduler.add_job(
            _make_job_fn(job_id, job_type, job_params),
            trigger=trigger,
            id=apscheduler_id,
            name=job_config["job_name"],
            replace_existing=True,
            misfire_grace_time=3600,
        )
        if not hasattr(self, '_job_registry'):
            self._job_registry = {}
        self._job_registry[job_id] = apscheduler_id
        logger.info(f"[定时任务] ✅ 已添加任务: {job_config['job_name']} ({schedule_type})")

    def reload_jobs(self):
        """重新从数据库加载所有任务"""
        if not self._running:
            return
        from backend.services.scheduling.scheduler_service import scheduler_service
        if not hasattr(self, '_job_registry'):
            self._job_registry = {}
        for job_id, apscheduler_id in list(self._job_registry.items()):
            try:
                self._scheduler.remove_job(apscheduler_id)
            except Exception:
                pass
        self._job_registry.clear()
        jobs = scheduler_service.list_jobs(enabled_only=True)
        for job_config in jobs:
            self._add_scheduler_job(job_config)
        logger.info(f"[定时任务] ✅ 已重新加载 {len(jobs)} 个任务")

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

    def trigger_xhs_discovery(self, keywords: List[str] = None, headless: bool = True) -> int:
        """
        手动触发小红书发现任务。
        headless=True：无头运行（需已登录），适合 API 触发
        headless=False：弹出浏览器（自动等待扫码），适合首次运行
        """
        logger.info(f"手动触发 XHS 发现任务 headless={headless}...")
        return _run_xhs_discovery(headless=headless)

    def trigger_process_tasks(self, batch_size: int = None) -> int:
        """手动触发任务处理（立即提取题目），batch_size 不传时从 env CRAWLER_PROCESS_BATCH_SIZE 读取"""
        _batch = batch_size if batch_size is not None else cfg.PROCESS_BATCH_SIZE
        logger.info(f"手动触发任务处理 batch_size={_batch}...")
        return _process_pending_tasks(batch_size=_batch)

    def reload_jobs(self):
        """重新加载调度任务（任务配置更新后调用）"""
        if not self._running:
            logger.warning("调度器未运行，无需 reload")
            return
        for job in self._scheduler.get_jobs():
            job.reschedule(job.trigger)
        logger.info("✅ 调度任务已重新加载")

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


# ── 全局单例 ─────────────────────────────────────────────────
crawl_scheduler = CrawlScheduler()



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
    
    logger.info(f"🔄 开始重试失败任务（最大重试{_max_retries}次，间隔{_retry_delay}秒）...")
    
    # 只重试牛客任务：XHS 失败通常是因为未登录，重试无意义
    failed_tasks = sqlite_service.get_tasks_by_status("error", platform="nowcoder", limit=50)
    
    if not failed_tasks:
        logger.info("   ✅ 没有牛客 error 状态的任务")
        return 0
    
    logger.info(f"   📋 发现 {len(failed_tasks)} 个牛客 error 任务，开始重试...")
    from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
    crawler = NowcoderCrawler(cookie=cfg.NOWCODER_COOKIE)
    
    success_count = 0
    
    for task in failed_tasks:
        task_id = task["task_id"]
        url = task["source_url"]
        title = task["post_title"] or "无标题"
        error_msg_prev = task.get("error_msg") or ""

        # 跳过 LLM 判断类错误（重新爬取也没用，内容已经够了）
        if any(kw in error_msg_prev for kw in ("LLM 判断", "均无题目", "LLM 返回")):
            logger.debug(f"  ⏭️ 跳过（LLM类错误，重爬无意义）: {title[:40]}")
            continue
        
        logger.info(f"  🔄 重试任务: {title[:40]}... | {url[:60]}")
        
        # 重试循环
        for attempt in range(1, _max_retries + 1):
            try:
                content, image_urls = crawler.fetch_post_content_full(url)
                
                if not content or len(content) < 50:
                    logger.warning(f"    ⚠️ 第{attempt}次重试失败：内容为空或过短（{len(content) if content else 0}字）")
                    if attempt < _max_retries:
                        time.sleep(_retry_delay)
                        continue
                    else:
                        sqlite_service.update_task_status(
                            task_id, "error",
                            error_msg=f"重试{_max_retries}次后仍无法提取内容"
                        )
                        break
                
                # 下载图片
                image_paths = []
                if image_urls:
                    from backend.services.crawler.image_utils import download_images
                    image_paths = download_images(image_urls, task_id)
                
                # 更新为 fetched 状态，让下次 _process_pending_tasks 的 Step 2 继续处理
                sqlite_service.update_task_status(
                    task_id=task_id,
                    status="fetched",
                    raw_content=content,
                    image_paths=image_paths,
                )
                
                success_count += 1
                logger.info(f"    ✅ 第{attempt}次重试成功: {len(content)}字, {len(image_paths)}图")
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
    
    logger.info(f"✅ 重试完成：成功 {success_count}/{len(failed_tasks)} 个任务")
    return success_count




