"""
立即爬取脚本 —— 用于快速填充题库

用法：
    python crawl_now.py                      # 爬牛客 20 条（默认）
    python crawl_now.py --count 50           # 爬 50 条
    python crawl_now.py --platform xhs       # 爬小红书（需已登录）
    python crawl_now.py --keywords "Go面经,Python面经"

爬取流程：
  1. 搜索发现帖子 URL（列表页）
  2. 对每条 URL 先查数据库去重，已爬过的跳过
  3. 爬取帖子详情页（正文）
  4. LLM 提取结构化 Q&A（最多 6000 字符）
  5. 写入 SQLite + Neo4j（Neo4j 不可用时只写 SQLite）

注意：
  - 牛客需要 Cookie，在 .env 填入 NOWCODER_COOKIE 可获取更完整结果
  - 小红书需先登录：python crawl_now.py --xhs-login
"""
import sys, os, argparse, logging, time, json

# ── 确保在项目根目录运行，并加载正确 conda 环境 ──────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

CONDA_PYTHON = r"C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe"
if os.path.abspath(sys.executable).lower() != os.path.abspath(CONDA_PYTHON).lower():
    if os.path.exists(CONDA_PYTHON):
        import subprocess
        subprocess.run([CONDA_PYTHON, __file__] + sys.argv[1:])
        sys.exit(0)

# ── 加载 .env ─────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"), override=True)

# ── 日志设置 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("crawl_now")

# 关闭不必要的第三方库日志
for noisy in ("httpx", "httpcore", "openai", "urllib3", "neo4j"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


# ══════════════════════════════════════════════════════════════
# 核心爬取逻辑
# ══════════════════════════════════════════════════════════════

def crawl_nowcoder(target_count: int = 20, keywords: list = None, max_pages: int = 3):
    """爬取牛客面经，返回入库题目数"""
    from backend.config.config import settings
    from backend.services.sqlite_service import sqlite_service
    from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
    from backend.services.crawler.question_extractor import extract_questions_from_post
    from backend.services.scheduler import _save_questions

    cookie = settings.nowcoder_cookie
    if not cookie:
        logger.warning("⚠️  NOWCODER_COOKIE 未配置，搜索结果可能不完整")
        logger.warning("   → 在 .env 中填入 NOWCODER_COOKIE 可获取更完整数据")

    keywords = keywords or settings.nowcoder_keywords
    logger.info(f"🚀 牛客爬取开始 | 目标 {target_count} 条 | 关键词: {keywords[:3]}...")

    crawler = NowcoderCrawler(cookie=cookie)

    # ── Step 1：发现帖子 URL（含数据库去重）─────────────────
    logger.info("📡 Step 1: 发现帖子 URL（自动跳过已爬取）...")
    posts = crawler.discover(
        keywords=keywords,
        max_pages=max_pages,
        check_db_dedup=True,       # 链接发现后立即查 DB，跳过已爬
    )
    if not posts:
        logger.warning("未发现新帖子（所有结果已爬取或 Cookie 失效）")
        return 0

    logger.info(f"✅ 发现 {len(posts)} 条新帖子，开始爬取前 {target_count} 条")
    posts = posts[:target_count]

    total_questions = 0
    for i, post in enumerate(posts, 1):
        url = post["source_url"]
        title = post.get("title", "")[:30]
        logger.info(f"\n[{i}/{len(posts)}] {title}...")
        logger.info(f"  URL: {url}")

        # ── Step 2：入队（UNIQUE 约束二次去重）──────────────
        task_id = sqlite_service.add_crawl_task(
            source_url=url,
            source_platform="nowcoder",
            post_title=post.get("title", ""),
            company=post.get("company", ""),
            position=post.get("position", ""),
            business_line=post.get("business_line", ""),
            difficulty=post.get("difficulty", ""),
            post_type=post.get("post_type", ""),
        )
        if not task_id:
            logger.info("  ⏩ 已在队列中，跳过")
            continue

        # ── Step 3：爬取详情页 ────────────────────────────
        logger.info("  📥 Step 3: 爬取详情页...")
        content = crawler.fetch_post_content(url)
        if not content or len(content) < 80:
            sqlite_service.update_task_status(task_id, "error", error_msg="正文为空")
            logger.warning(f"  ⚠️  正文为空，跳过")
            continue

        logger.info(f"  ✅ 获取正文 {len(content)} 字")
        sqlite_service.update_task_status(task_id, "fetched", raw_content=content)

        # ── Step 4：LLM 提取 Q&A ──────────────────────────
        logger.info("  🤖 Step 4: LLM 提取题目...")
        questions = extract_questions_from_post(
            content=content,
            platform="nowcoder",
            company=post.get("company", ""),
            position=post.get("position", ""),
            business_line=post.get("business_line", ""),
            difficulty=post.get("difficulty", ""),
            source_url=url,
            post_title=post.get("title", ""),
        )
        if not questions:
            sqlite_service.update_task_status(task_id, "error", error_msg="LLM 未提取到题目")
            logger.warning("  ⚠️  LLM 未提取到题目")
            continue

        # ── Step 5：写入数据库 ────────────────────────────
        count = _save_questions(questions)
        sqlite_service.update_task_status(task_id, "done", questions_count=count)
        total_questions += count
        logger.info(f"  💾 入库 {count} 道题目（累计 {total_questions}）")

    logger.info(f"\n🎉 牛客爬取完成：处理 {len(posts)} 篇，入库 {total_questions} 道题目")
    return total_questions


def xhs_login_only():
    """小红书扫码登录（只登录，不爬取）"""
    from backend.services.crawler.xhs_crawler import xhs_do_login
    logger.info("打开浏览器，请在 120 秒内完成小红书扫码登录...")
    ok = xhs_do_login(wait_seconds=120)
    if ok:
        logger.info("✅ 登录成功，后续可以用 --platform xhs 爬取")
    else:
        logger.warning("❌ 未检测到登录，请重试")


def crawl_xhs(target_count: int = 20, keywords: list = None):
    """爬取小红书面经（需已登录）"""
    from backend.config.config import settings
    from backend.services.sqlite_service import sqlite_service
    from backend.services.crawler.xhs_crawler import XHSCrawler
    from backend.services.crawler.question_extractor import extract_questions_from_post
    from backend.services.scheduler import _save_questions

    keywords = keywords or settings.xhs_keywords
    logger.info(f"🚀 小红书爬取开始 | 目标 {target_count} 条 | 关键词: {keywords}...")

    crawler = XHSCrawler(headless=True)  # 依赖已保存的登录状态

    posts = crawler.discover(
        keywords=keywords,
        max_notes_per_keyword=max(5, target_count // len(keywords) + 1),
    )
    if not posts:
        logger.warning("未获取到帖子（可能未登录，运行 python crawl_now.py --xhs-login）")
        return 0

    total_questions = 0
    for i, post in enumerate(posts[:target_count], 1):
        url = post["source_url"]
        content = post.get("content", "")
        title = post.get("title", "")[:30]
        logger.info(f"[{i}/{min(len(posts), target_count)}] {title}...")

        if not content or len(content) < 80:
            logger.warning("  正文为空，跳过")
            continue

        task_id = sqlite_service.add_crawl_task(
            source_url=url,
            source_platform="xiaohongshu",
            post_title=post.get("title", ""),
            post_type=post.get("post_type", ""),
        )
        if not task_id:
            logger.info("  ⏩ 已爬取，跳过")
            continue

        sqlite_service.update_task_status(task_id, "fetched", raw_content=content)

        logger.info("  🤖 LLM 提取题目...")
        questions = extract_questions_from_post(
            content=content,
            platform="xiaohongshu",
            source_url=url,
            post_title=post.get("title", ""),
        )
        if not questions:
            sqlite_service.update_task_status(task_id, "error", error_msg="LLM 未提取到题目")
            continue

        count = _save_questions(questions)
        sqlite_service.update_task_status(task_id, "done", questions_count=count)
        total_questions += count
        logger.info(f"  💾 入库 {count} 道题目（累计 {total_questions}）")

    logger.info(f"\n🎉 小红书爬取完成：入库 {total_questions} 道题目")
    return total_questions


# ══════════════════════════════════════════════════════════════
# 命令行入口
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="面经立即爬取工具")
    parser.add_argument("--platform", choices=["nowcoder", "xhs"], default="nowcoder",
                        help="爬取平台（默认 nowcoder）")
    parser.add_argument("--count", type=int, default=20,
                        help="目标爬取帖子数（默认 20）")
    parser.add_argument("--keywords", type=str, default="",
                        help="搜索关键词，逗号分隔，如 'Java面经,Go面经'")
    parser.add_argument("--pages", type=int, default=3,
                        help="牛客每个关键词最多抓几页（默认 3）")
    parser.add_argument("--xhs-login", action="store_true",
                        help="仅执行小红书扫码登录（不爬取）")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] or None

    if args.xhs_login:
        xhs_login_only()
        return

    t0 = time.time()
    if args.platform == "nowcoder":
        crawl_nowcoder(target_count=args.count, keywords=keywords, max_pages=args.pages)
    else:
        crawl_xhs(target_count=args.count, keywords=keywords)

    elapsed = time.time() - t0
    logger.info(f"\n⏱  总耗时: {elapsed:.1f}s")

    # 显示最终题库统计
    try:
        from backend.services.sqlite_service import sqlite_service
        import sqlite3
        with sqlite3.connect(sqlite_service.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            stats = sqlite_service.get_crawl_stats()
        logger.info(f"📊 当前题库: {total} 道题目")
        logger.info(f"📋 爬取任务: {stats}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
