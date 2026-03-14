"""
小红书面经发现爬虫
两步走：
  1. Playwright 浏览器模拟搜索，获取帖子链接
  2. xhs-crawl 库 API 方式获取帖子详细内容

登录状态说明：
  - headless=False（首次 / 手动触发）：弹出浏览器，自动倒计时等待扫码，无需按回车
  - headless=True （定时任务）：依赖已保存的登录状态，未登录则静默跳过，不阻塞后台

登录状态持久化：
  - 第一次 headless=False 扫码后，状态保存到 XHS_USER_DATA_DIR（默认 backend/data/xhs_user_data）
  - 后续定时任务无需再次扫码，直接复用

相关 .env 配置：
  XHS_USER_DATA_DIR       浏览器数据目录（保存登录状态），默认 backend/data/xhs_user_data
  XHS_LINK_CACHE          已获取链接缓存文件，默认 ./xhs_link_cache.txt
  XHS_LOGIN_WAIT_SECONDS  headless=False 时等待扫码的最长秒数，默认 120
"""
import asyncio
import logging
import os
import random
import time
from typing import List, Dict
from urllib.parse import quote as _urlquote

logger = logging.getLogger(__name__)


def _cfg():
    """懒读配置，避免模块级循环依赖"""
    from backend.config.config import settings
    return settings


def _user_data_dir() -> str:
    return _cfg().xhs_user_data_dir


def _link_cache() -> str:
    return _cfg().xhs_link_cache_path


def _login_wait_seconds() -> int:
    try:
        return int(os.environ.get("XHS_LOGIN_WAIT_SECONDS", "120"))
    except ValueError:
        return 120


# ── 登录状态检测 ──────────────────────────────────────────────

def _is_logged_in(page) -> bool:
    """检测当前页面是否已登录小红书"""
    try:
        # 方式1：存在用户头像 / 昵称元素
        if page.locator(".user-avatar, .nickname, .user-name, [class*='userInfo']").count() > 0:
            return True
        # 方式2：URL 不在登录页
        if "login" in page.url.lower() or "signin" in page.url.lower():
            return False
        # 方式3：搜索结果卡片出现，说明已登录
        if page.locator("section.note-item, div[class*='note-item']").count() > 0:
            return True
        return False
    except Exception:
        return False


def _wait_for_login(page, wait_seconds: int = 120) -> bool:
    """
    headless=False 模式：在弹出浏览器中等待用户扫码登录。
    每 5 秒检测一次登录状态，超时后返回 False（不阻塞后台）。
    不使用 input()，完全非交互式。
    """
    logger.warning(
        f"⚠️  未检测到小红书登录状态，请在弹出的浏览器窗口中扫码登录。"
        f"将等待最多 {wait_seconds} 秒后自动继续..."
    )
    deadline = time.time() + wait_seconds
    check_interval = 5

    while time.time() < deadline:
        remaining = int(deadline - time.time())
        try:
            page.wait_for_timeout(check_interval * 1000)
            if _is_logged_in(page):
                logger.info("✅ 检测到登录成功，继续爬取...")
                return True
            logger.info(f"   等待扫码中... 剩余 {remaining} 秒")
        except Exception:
            break

    logger.warning(f"⏰ 等待 {wait_seconds} 秒后仍未登录，本次跳过 XHS 爬取。")
    return False


# ── Playwright 获取帖子链接 ─────────────────────────────────────

def get_xhs_links_with_playwright(
    keyword: str = "面经",
    max_notes: int = 20,
    headless: bool = False,   # 默认 False：弹出浏览器，允许扫码
    login_wait_seconds: int = None,
) -> List[Dict]:
    """
    使用 Playwright 在小红书搜索页发现帖子链接。

    Args:
        keyword:            搜索关键词
        max_notes:          最多获取链接数
        headless:           True=无头模式（定时任务用）；False=弹出浏览器（首次登录用）
        login_wait_seconds: 未登录时最长等待秒数，None 则从 .env XHS_LOGIN_WAIT_SECONDS 读取

    Returns:
        [{"title": str, "link": str}]
    """
    user_data = _user_data_dir()
    os.makedirs(user_data, exist_ok=True)

    # 清理 Chrome 遗留的 Profile 锁文件（进程异常退出时留下，会导致新实例立即崩溃）
    for lock_name in ("SingletonLock", "SingletonCookie", "lockfile", ".com.google.Chrome.LOCK"):
        lock_path = os.path.join(user_data, lock_name)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                logger.info(f"已清理 Chrome 锁文件: {lock_path}")
            except Exception:
                pass

    if login_wait_seconds is None:
        login_wait_seconds = _login_wait_seconds()

    # ── Windows: 强制使用 ProactorEventLoop ──────────────────────────
    # sync_playwright() 内部用 asyncio.create_subprocess_exec 启动 Playwright 服务进程，
    # Windows 的 SelectorEventLoop 不支持此调用 → NotImplementedError。
    # APScheduler / uvicorn 会在运行期间修改或关闭线程的 event loop，
    # 必须在每次调用前强制重置为 ProactorEventLoop。
    import sys as _sys
    if _sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            asyncio.get_running_loop()
            # 如果能拿到 running loop，说明当前在 async 协程里，不能改 loop
        except RuntimeError:
            # 不在 async 上下文（线程/subprocess），安全地替换为新的 ProactorEventLoop
            asyncio.set_event_loop(asyncio.ProactorEventLoop())

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright 未安装: pip install playwright && playwright install chromium")
        return []

    results: List[Dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=headless,
            viewport={"width": 1920, "height": 1080},
            # 不传 --no-sandbox：Windows headless=False 加此参数可能导致 Chrome 立即退出(exit 21)
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # keyword 必须 URL 编码，否则中文搜索词会带空格导致搜索失败
        search_url = (
            f"https://www.xiaohongshu.com/search_result"
            f"?keyword={_urlquote(keyword)}&source=web_search_result_notes"
        )
        logger.info(f"XHS 访问搜索页: {search_url}")
        try:
            # 使用 domcontentloaded 而非 networkidle，XHS 是重 JS SPA，networkidle 经常超时
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.warning(f"XHS 页面加载超时，尝试继续: {e}")
        page.wait_for_timeout(4000)  # 额外等待 JS 渲染

        # ── 登录状态处理（无 input()）────────────────────────
        logged_in = _is_logged_in(page)
        if not logged_in:
            if headless:
                # 无头模式：直接放弃，不弹窗、不阻塞
                logger.warning(
                    "XHS 未登录（headless 模式）。"
                    "请先以 headless=False 运行一次完成扫码，"
                    "登录状态将保存到 backend/data/xhs_user_data 供后续复用。"
                )
                browser.close()
                return []
            else:
                # 有头模式：等待用户扫码（倒计时，非阻塞）
                logger.info("浏览器已打开，请在浏览器中扫码登录小红书...")
                if not _wait_for_login(page, wait_seconds=login_wait_seconds):
                    browser.close()
                    return []
                # 登录后重新加载搜索页
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                page.wait_for_timeout(4000)

        # ── 等待搜索结果 ──────────────────────────────────────
        try:
            page.wait_for_selector(
                "section.note-item, div[class*='note-item'], "
                "div.note-item, a[href*='/explore/']",
                timeout=20000
            )
        except Exception:
            logger.warning("XHS 未找到搜索结果（可能登录状态已过期或页面结构变化）")
            # 不立即关闭，先尝试用 href 方式采集
            pass

        # 同时匹配多种卡片选择器，适配小红书页面结构变化
        cards = page.locator(
            "section.note-item, div[class*='note-item'], div.note-item"
        ).all()
        logger.info(f"XHS 找到 {len(cards)} 个结果卡片")

        if not cards:
            logger.warning("XHS 未找到任何卡片，检查选择器或登录状态")
            browser.close()
            return []

        processed_ids: set = set()

        for card in cards:
            if len(results) >= max_notes:
                break
            try:
                title_elem = card.locator(".title span, h3, [class*='title']").first
                title = title_elem.inner_text().strip() if title_elem.count() > 0 else "无标题"

                card.click(button="left", timeout=5000)
                try:
                    page.wait_for_url("**/explore/*", wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    page.wait_for_timeout(2000)

                current_url = page.url
                note_id = current_url.split("/")[-1].split("?")[0]

                if note_id not in processed_ids and note_id:
                    processed_ids.add(note_id)
                    results.append({"title": title, "link": current_url})
                    logger.info(f"XHS 获取链接 [{len(results)}/{max_notes}]: {title[:30]}")

                try:
                    page.go_back(wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(random.uniform(1500, 3000))

            except Exception as e:
                logger.debug(f"XHS 单卡片获取失败，跳过: {e}")
                if "explore" in page.url:
                    try:
                        page.go_back(wait_until="domcontentloaded", timeout=10000)
                        page.wait_for_timeout(2000)
                    except Exception:
                        pass

        browser.close()

    # 缓存链接（方便调试 / 断点续爬）
    if results:
        cache_file = _link_cache()
        with open(cache_file, "a", encoding="utf-8") as f:
            for r in results:
                f.write(r["link"] + "\n")

    logger.info(f"XHS keyword={keyword!r} 共获取 {len(results)} 条链接")
    return results


# ── 登录工具函数（供 API 单独调用）──────────────────────────

def xhs_do_login(wait_seconds: int = None) -> bool:
    """
    专门用于首次登录的函数：弹出浏览器，等待扫码，保存登录状态。
    后续的定时任务无需再调用，直接使用 headless=True 即可。
    返回 True 表示登录成功。
    """
    wait_seconds = wait_seconds or _login_wait_seconds()
    logger.info(f"打开小红书登录窗口，请扫码... 最多等待 {wait_seconds} 秒")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright 未安装")
        return False

    user_data = _user_data_dir()
    os.makedirs(user_data, exist_ok=True)
    for lock_name in ("SingletonLock", "SingletonCookie", "lockfile"):
        lock_path = os.path.join(user_data, lock_name)
        if os.path.exists(lock_path):
            try: os.remove(lock_path)
            except Exception: pass
    success = False

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://www.xiaohongshu.com", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)

        if _is_logged_in(page):
            logger.info("✅ 已处于登录状态，无需重复扫码")
            browser.close()
            return True

        success = _wait_for_login(page, wait_seconds=wait_seconds)
        browser.close()

    return success


# 「你访问的页面不见了」：xhs-crawl 遇 302/404 时 meta 回退得到的标题，通常为防爬/限流
# 此时用 Playwright 浏览器（带登录态）可正常获取正文
_PAGE_NOT_FOUND_TITLES = ("你访问的页面不见了", "页面不见了", "页面不存在")


def _is_page_not_found_result(title: str, content: str) -> bool:
    """判断是否为 xhs-crawl 遇防爬时返回的占位结果（标题含占位文案且正文为空或极短）"""
    if not title:
        return False
    content = (content or "").strip()
    return any(t in title for t in _PAGE_NOT_FOUND_TITLES) and len(content) < 100


async def _fetch_xhs_with_playwright(url: str, headless: bool = True) -> Dict | None:
    """
    用 Playwright 浏览器（带登录态）抓取小红书详情页，绕过 xhs-crawl 遇防爬时的 302/404。
    返回 {title, content, image_urls} 或 None。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright 未安装，无法使用浏览器兜底抓取")
        return None

    # Windows 必须使用 ProactorEventLoop 支持子进程
    if os.name == "nt":
        import sys
        if sys.platform == "win32":
            try:
                loop = asyncio.get_running_loop()
                # 如果当前 loop 不是 ProactorEventLoop，记录警告但继续
                if not isinstance(loop, asyncio.ProactorEventLoop):
                    logger.debug("当前 event loop 不是 ProactorEventLoop，Playwright 可能失败")
            except RuntimeError:
                # 没有运行中的 loop，设置策略
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    user_data = _user_data_dir()
    os.makedirs(user_data, exist_ok=True)
    for lock_name in ("SingletonLock", "SingletonCookie", "lockfile"):
        lock_path = os.path.join(user_data, lock_name)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except Exception:
                pass

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=headless,
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # 尝试从 __INITIAL_STATE__ 提取
            data = await page.evaluate("""() => {
                try {
                    const s = window.__INITIAL_STATE__ || {};
                    const noteId = (window.__INITIAL_STATE__?.note?.noteId || location.pathname.split('/').pop()?.split('?')[0]) || '';
                    const noteMap = s.note?.noteDetailMap || {};
                    const note = noteMap[noteId]?.note || Object.values(noteMap)[0]?.note;
                    if (note) {
                        const title = note.title || '';
                        const desc = note.desc || '';
                        const images = (note.imageList || []).map(i => i.urlDefault || i.url || '').filter(Boolean);
                        const ts = note.time || note.lastModifyTime || note.createTime || 0;
                        return { title, content: desc, image_urls: images, time_ms: ts };
                    }
                } catch {}
                return null;
            }""")
            if data and (data.get("content") or "").strip():
                await browser.close()
                # 将 time_ms 转为 post_time 字符串（北京时间）
                post_time = ""
                if data.get("time_ms"):
                    try:
                        from backend.utils.time_utils import timestamp_ms_to_beijing
                        post_time = timestamp_ms_to_beijing(int(data["time_ms"]))
                    except Exception:
                        pass
                data["post_time"] = post_time
                return data

            # DOM 兜底：正文区域
            desc_el = await page.query_selector(".desc, [class*='desc'], .note-content, [class*='note-content']")
            if desc_el:
                content = await desc_el.inner_text()
                title_el = await page.query_selector("h1, .title, [class*='title']")
                title = await title_el.inner_text() if title_el else ""
                img_urls = []
                for img in await page.query_selector_all(".note-content img[src], [class*='content'] img[src]"):
                    src = await img.get_attribute("src")
                    if src and "http" in src:
                        img_urls.append(src)
                await browser.close()
                return {"title": (title or "").strip(), "content": (content or "").strip(), "image_urls": img_urls, "post_time": ""}
        except Exception as e:
            logger.debug(f"Playwright 兜底抓取失败（可能是 event loop 问题）: {url[:60]}")
        await browser.close()
    return None


# ── xhs-crawl 获取帖子详情 ────────────────────────────────────

async def _async_fetch_details(links: List[str]) -> List[Dict]:
    """异步批量获取小红书帖子详情。CRAWLER_SOURCE=mcp 时优先用 MCP 抓取，失败则回退 xhs-crawl/Playwright"""
    cfg = _cfg()
    crawler_source = getattr(cfg, "crawler_source", "local")
    use_mcp = (
        crawler_source == "mcp"
        and getattr(cfg, "mcp_content_fetcher_url", "")
    )

    try:
        from xhs_crawl import XHSSpider
    except ImportError:
        XHSSpider = None
        if not use_mcp:
            logger.error("xhs_crawl 未安装: pip install xhs-crawl")
            return []

    logging.getLogger("xhs_crawl").setLevel(logging.WARNING)
    spider = XHSSpider() if XHSSpider else None  # MCP 失败时用作兜底

    posts: List[Dict] = []

    for idx, url in enumerate(links, 1):
        try:
            # MCP 优先：CRAWLER_SOURCE=mcp 时先尝试 MCP
            mcp_data = None
            if use_mcp:
                try:
                    from backend.services.crawler.mcp_content_client import fetch_content_via_mcp
                    base_url = getattr(cfg, "mcp_content_fetcher_url", "")
                    timeout = getattr(cfg, "mcp_content_fetcher_timeout", 30)
                    api_key = getattr(cfg, "smithery_api_key", "") or None
                    data = await asyncio.to_thread(
                        fetch_content_via_mcp, base_url, url, timeout, api_key
                    )
                    content = (data.get("content") or "").strip()
                    if content and len(content) >= 50:
                        mcp_data = {
                            "title": (data.get("title") or "").strip(),
                            "content": content,
                            "image_urls": data.get("image_urls") or [],
                            "post_time": "",
                        }
                        logger.info(f"XHS 获取详情 [{idx}/{len(links)}]: {mcp_data['title'][:30]} ({len(content)}字, {len(mcp_data['image_urls'])}图) | 获取来源=mcp")
                except Exception as e:
                    logger.debug(f"[MCP] 小红书抓取失败，回退本地: {url[:50]}... {e}")

            if mcp_data:
                posts.append({
                    "title": mcp_data["title"],
                    "content": mcp_data["content"],
                    "author": "",
                    "image_urls": mcp_data["image_urls"],
                    "image_count": len(mcp_data["image_urls"]),
                    "source_url": url,
                    "source_platform": "xiaohongshu",
                    "post_time": mcp_data.get("post_time", ""),
                })
                await asyncio.sleep(random.uniform(1, 3))
                continue

            # 本地：xhs-crawl 或 Playwright
            if not spider:
                logger.warning("xhs_crawl 未安装且 MCP 未返回有效内容，跳过")
                continue

            post = await spider.get_post_data(url)
            if not post:
                continue

            title = getattr(post, "title", "") or ""
            content = getattr(post, "content", "") or ""
            author = ""
            if hasattr(post, "user") and post.user:
                author = getattr(post.user, "nickname", "") or ""

            images: List[str] = []
            if hasattr(post, "images") and post.images:
                images = list(post.images)

            # 尝试从 xhs-crawl post 对象提取 post_time（帖子发表时间）
            post_time = ""
            for attr in ("time", "last_modify_time", "create_time", "lastModifyTime", "createTime"):
                val = getattr(post, attr, None)
                if val:
                    try:
                        from backend.utils.time_utils import timestamp_ms_to_beijing
                        post_time = timestamp_ms_to_beijing(int(val))
                        break
                    except Exception:
                        pass

            # 「页面不见了」类：xhs-crawl 遇防爬返回占位页，用 Playwright 兜底
            if _is_page_not_found_result(title, content):
                logger.info(f"xhs-crawl 返回「页面不见了」，尝试 Playwright 兜底: {url[:60]}...")
                pw_data = await _fetch_xhs_with_playwright(url)
                if pw_data and (pw_data.get("content") or "").strip():
                    title = pw_data.get("title") or title
                    content = pw_data.get("content") or content
                    images = pw_data.get("image_urls") or images
                    post_time = pw_data.get("post_time", "") or post_time
                    logger.info(f"Playwright 兜底成功: {title[:30]}... ({len(content)} 字)")
                else:
                    logger.warning(f"Playwright 兜底失败，保留空正文: {url[:60]}...")

            # 去掉 meta 回退时常见的「 - 小红书」后缀
            clean_title = title.strip()
            for suffix in (" - 小红书", "- 小红书"):
                if clean_title.endswith(suffix):
                    clean_title = clean_title[:-len(suffix)].strip()
                    break
            posts.append({
                "title": clean_title,
                "content": content,
                "author": author,
                "image_urls": images,
                "image_count": len(images),
                "source_url": url,
                "source_platform": "xiaohongshu",
                "post_time": post_time,
            })
            logger.info(f"XHS 获取详情 [{idx}/{len(links)}]: {clean_title[:30]} ({len(content)}字, {len(images)}图)")
            await asyncio.sleep(random.uniform(3, 6))

        except Exception as e:
            logger.error(f"XHS 获取详情异常 {url}: {e}")

    if spider:
        await spider.close()
    return posts


def fetch_xhs_details(links: List[str]) -> List[Dict]:
    """同步封装，适配 Windows asyncio"""
    if not links:
        return []
    if os.name == "nt":
        # Windows 需要使用 ProactorEventLoop 来支持子进程（Playwright 需要）
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_fetch_details(links))
    finally:
        loop.close()


# ── 一体化接口 ────────────────────────────────────────────────

class XHSCrawler:
    """
    小红书面经爬虫一体化接口。

    使用流程：
      1. 首次：crawler.login()  → 弹出浏览器扫码，状态保存
      2. 后续：crawler.discover()  → 无头运行，复用登录状态

    discover() 返回 [{source_url, title, content, source_platform, ...}]
    """

    def __init__(self, headless: bool = False):
        """
        headless=False（默认）：弹出浏览器，支持扫码登录，适合手动触发
        headless=True：无头模式，依赖已保存登录状态，适合自动定时任务
        """
        self.headless = headless

    def login(self, wait_seconds: int = None) -> bool:
        """手动触发登录（弹出浏览器扫码），登录后状态持久化"""
        return xhs_do_login(wait_seconds=wait_seconds)

    def is_logged_in(self) -> bool:
        """快速检查当前保存的 session 是否仍然有效"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return False
        result = False
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=_user_data_dir(),
                headless=True,
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            try:
                page.goto(
                    "https://www.xiaohongshu.com",
                    wait_until="networkidle", timeout=12000
                )
                page.wait_for_timeout(2000)
                result = _is_logged_in(page)
            except Exception:
                pass
            browser.close()
        return result

    def discover(
        self,
        keywords: List[str] = None,
        max_notes_per_keyword: int = None,
        crawl_source: str = "未知",
    ) -> List[Dict]:
        """
        搜索多个关键词，返回帖子（含详情内容）。
        keywords/max_notes_per_keyword 未传时从 .env 读取默认值。
        crawl_source: 爬取来源标识，用于日志区分（如 "立即爬取"、"定时爬取"）
        """
        cfg = _cfg()
        keywords = keywords or cfg.xhs_keywords
        max_notes = max_notes_per_keyword or cfg.xhs_max_notes_per_keyword

        all_posts: List[Dict] = []
        seen_urls: set = set()

        for kw in keywords:
            logger.info(f"[小红书{crawl_source}] 开始搜索关键词: {kw!r}")
            link_list = get_xhs_links_with_playwright(
                keyword=kw,
                max_notes=max_notes,
                headless=self.headless,
            )
            new_links = [item["link"] for item in link_list if item["link"] not in seen_urls]
            seen_urls.update(new_links)

            if not new_links:
                continue

            posts = fetch_xhs_details(new_links)
            for p in posts:
                p["post_type"] = (
                    "面经"
                    if any(k in (p.get("title", "") + p.get("content", ""))
                           for k in ["面经", "面试"])
                    else "其他"
                )
                p["discover_keyword"] = kw
                all_posts.append(p)

        logger.info(f"[小红书{crawl_source}] 共获取 {len(all_posts)} 条帖子详情")
        return all_posts
