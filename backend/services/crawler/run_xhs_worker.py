"""
XHS 爬虫独立工作进程
由 main.py 的 trigger_crawler 端点以 subprocess.Popen 方式启动，
这样 Playwright headless=False 的浏览器窗口能正常弹出（独立进程有自己的 Windows 桌面）。

参数（通过命令行传入）：
  --keywords  逗号分隔的关键词，默认读 .env XHS_KEYWORDS
  --max-notes 每个关键词最多抓几条，默认读 .env XHS_MAX_NOTES_PER_KEYWORD
  --headless  是否无头，默认 false
  --process   发现后是否立即处理队列，默认 true

stdout 最后一行输出 JSON: {"discovered": N, "questions_added": M}
"""
import sys
import os
import argparse
import json

# ── Windows 必须在最早设置 ProactorEventLoop ──────────────────────────────
# sync_playwright() 内部用 asyncio.create_subprocess_exec 启动 Playwright 服务；
# Windows SelectorEventLoop 不支持子进程，必须用 ProactorEventLoop。
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 把项目根目录加入 sys.path（支持 `python -m` 和直接 `python run_xhs_worker.py` 两种用法）
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 加载 .env
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"), override=True)

import logging
try:
    from loguru import logger as _loguru_logger
    _loguru_logger.remove()
    _loguru_logger.add(
        sys.stdout,
        colorize=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",
        level="INFO",
    )
    class _InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = _loguru_logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            # 过滤 neo4j 冗长通知、httpx 请求详情
            if record.name in ("neo4j.notifications", "httpx"):
                return
            # xhs_crawl 内部日志降为 DEBUG
            if record.name.startswith("xhs_crawl"):
                level = "DEBUG"
            _loguru_logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    # 静默 hello-agents 工具注册 print（monkey-patch）
    try:
        import io as _io
        from hello_agents.tools.registry import ToolRegistry as _TR
        _orig_rt = _TR.register_tool
        _orig_rf = _TR.register_function
        def _silent_rt(self, tool, **kw):
            import sys as _sys; _old, _sys.stdout = _sys.stdout, _io.StringIO()
            try: return _orig_rt(self, tool, **kw)
            finally: _sys.stdout = _old
        def _silent_rf(self, func, **kw):
            import sys as _sys; _old, _sys.stdout = _sys.stdout, _io.StringIO()
            try: return _orig_rf(self, func, **kw)
            finally: _sys.stdout = _old
        _TR.register_tool = _silent_rt
        _TR.register_function = _silent_rf
    except Exception:
        pass
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        stream=sys.stdout,
    )
logger = logging.getLogger("xhs_worker")

# 子进程无需重复打印 Miner Service 配置（主进程已打印）
try:
    import backend.services.crawler.question_extractor as _qe
    _qe._miner_config_printed = True
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords",  default="")
    parser.add_argument("--max-notes", type=int, default=0)
    parser.add_argument("--headless",  default="false")
    parser.add_argument("--process",   default="true")
    args = parser.parse_args()

    keywords  = [k.strip() for k in args.keywords.split(",") if k.strip()] or None
    max_notes = args.max_notes or None
    headless  = args.headless.lower() == "true"
    do_process = args.process.lower() == "true"

    logger.info(f"[小红书立即爬取] 启动: keywords={keywords}, max_notes={max_notes}, headless={headless}")

    # LLM 已在 main.py 启动时预热，子进程无需重复预热

    from backend.services.crawler.xhs_crawler import XHSCrawler
    from backend.services.storage.sqlite_service import sqlite_service
    from backend.services.crawler.crawl_helpers import save_xhs_post

    crawler = XHSCrawler(headless=headless)
    posts = crawler.discover(keywords=keywords, max_notes_per_keyword=max_notes, crawl_source="立即爬取")

    discovered = 0
    for p in posts:
        if save_xhs_post(p, sqlite_service, download_images_flag=True):
            discovered += 1

    logger.info(f"[小红书立即爬取] 发现完成: {len(posts)} 条原始帖, {discovered} 条新入队")

    questions_added = 0
    if do_process and discovered > 0:
        from backend.services.scheduling.scheduler import _process_pending_tasks
        questions_added = _process_pending_tasks(batch_size=discovered + 5)
        logger.info(f"[小红书立即爬取] 处理完成: {questions_added} 道题入库")

    # 最后一行输出 JSON 供父进程读取结果
    result = {"discovered": discovered, "questions_added": questions_added}
    print(f"\n__RESULT__:{json.dumps(result, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    main()
