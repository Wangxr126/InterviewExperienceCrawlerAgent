import time
import random
import csv
import os
import asyncio
import re  # 用于清洗文件名
import requests  # 用于下载图片
from playwright.sync_api import sync_playwright
from xhs_crawl import XHSSpider  # xhs-crawl核心库

# ================= 基础配置 =================
# 注意：KEYWORD 变量已移动到 main 函数中
MAX_NOTES = 2  # 爬取帖子数量上限
CSV_FILENAME = f"小红书面经_无互动数据_{int(time.time())}.csv"  # 结果保存文件名
USER_DATA_DIR = "./xhs_user_data"  # 浏览器数据目录（保存登录状态）
LINK_FILE = "小红书面经链接列表.txt"  # 帖子链接保存文件
DOWNLOAD_IMG_DIR = "./xhs_downloads"  # 图片下载目录
DELAY_RANGE = (5, 10)  # 每次请求延迟范围（秒）


# ============================================================

def init_env():
    """初始化运行环境"""
    # 创建必要目录
    for dir_path in [USER_DATA_DIR, DOWNLOAD_IMG_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"📁 创建目录: {dir_path}")

    # 检查依赖（简化版）
    try:
        import playwright
        from xhs_crawl import XHSSpider
        import requests
    except ImportError:
        print("⚠️ 缺少依赖，正在自动安装...")
        os.system("pip install playwright xhs-crawl requests")
        os.system("playwright install chromium")
        print("✅ 依赖安装完成，请重新运行程序")
        exit(0)


def clean_filename(text):
    """清洗文件名，去除非法字符"""
    # 替换 Windows/Linux 文件名中的非法字符
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]', '_', text)
    return cleaned.strip()[:50]  # 限制长度，防止文件名过长


def get_jingyan_links(keyword):
    """
    第一步：模拟真人点击帖子，获取带完整鉴权参数的链接
    """
    print(f"\n===== 【第一步】获取帖子链接 (关键词: {keyword}) =====")
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            viewport={'width': 1920, 'height': 1080},
            args=['--start-maximized', '--disable-blink-features=AutomationControlled']
        )
        page = browser.pages[0]

        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
        print(f"🌐 访问搜索页: {search_url}")
        page.goto(search_url, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # 智能登录检查
        if page.locator(".user-avatar, .nickname, .user-name").count() > 0:
            print("✅ 检测到本地登录状态，自动跳过扫码步骤...")
        else:
            print("\n" + "=" * 60)
            print("⚠️ 未检测到登录状态！")
            print("👉 请在弹出的浏览器中完成扫码登录，登录后按回车继续...")
            print("=" * 60)
            input(">> 登录完成后按回车键：")
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(3000)

        notes_list = []
        processed_note_ids = set()

        print("🔍 定位搜索页帖子卡片...")
        try:
            page.wait_for_selector("section.note-item, div[class*='note-item']", timeout=10000)
        except:
            print("⚠️ 页面加载超时或无搜索结果")
            browser.close()
            return []

        cards = page.locator("section.note-item, div[class*='note-item']").all()

        for card_idx, card in enumerate(cards):
            if len(notes_list) >= MAX_NOTES:
                break

            try:
                title_elem = card.locator(".title span, h3, [class*='title']").first
                title = title_elem.inner_text().strip() if title_elem.count() > 0 else "无标题"

                print(f"\n🖱️ [{len(notes_list) + 1}/{MAX_NOTES}] 尝试点击: {title[:15]}...")

                card.click(button="left", timeout=5000)
                page.wait_for_url("**/explore/*", wait_until="networkidle", timeout=8000)

                current_url = page.url
                note_id = current_url.split("/")[-1].split("?")[0]

                if note_id not in processed_note_ids:
                    processed_note_ids.add(note_id)
                    notes_list.append({"title": title, "link": current_url})
                    print(f"✅ 获取链接成功")
                else:
                    print("⚠️ 已存在，跳过")

                page.go_back(wait_until="networkidle")
                page.wait_for_timeout(random.uniform(1.5, 3) * 1000)

            except Exception as e:
                print(f"⏭️ 获取失败，自动跳过此条 (原因: {str(e)[:50]})")
                if page.url.startswith("https://www.xiaohongshu.com/explore/"):
                    try:
                        page.go_back(wait_until="networkidle")
                    except:
                        pass
                continue

        with open(LINK_FILE, "w", encoding="utf-8") as f:
            for note in notes_list:
                f.write(note["link"] + "\n")

        browser.close()
        return [note["link"] for note in notes_list]


def crawl_post_details(links):
    """
    第二步：爬取详情（自定义图片下载逻辑）
    """
    print("\n===== 【第二步】爬取帖子详细内容 =====")

    async def async_crawl():
        spider = XHSSpider()
        all_posts = []

        for idx, url in enumerate(links, 1):
            try:
                print(f"\n🔍 正在爬取 [{idx}/{len(links)}]")

                post = await spider.get_post_data(url)
                if not post:
                    print("⏭️ 数据为空，自动跳过")
                    continue

                post_info = {
                    "标题": getattr(post, "title", "无标题") or "无标题",
                    "作者": getattr(post.user, "nickname", "未知作者") if hasattr(post, "user") else "未知作者",
                    "内容": getattr(post, "content", "无内容") or "无内容",
                    "图片数量": len(post.images) if hasattr(post, "images") and post.images else 0,
                    "帖子链接": url
                }
                all_posts.append(post_info)

                print(f"✅ 成功: {post_info['标题'][:15]}... (内容:{len(post_info['内容'])}字)")

                # ==========================================
                # 🔥 修改部分：自定义图片下载 (Title + 序号)
                # ==========================================
                if post_info["图片数量"] > 0:
                    print(f"   📥 正在下载 {post_info['图片数量']} 张图片...")

                    # 1. 清洗标题作为文件名前缀
                    safe_title = clean_filename(post_info["标题"])
                    if not safe_title:
                        safe_title = f"无标题_{int(time.time())}"

                    # 2. 遍历下载
                    for i, img_url in enumerate(post.images, 1):
                        try:
                            # 构造文件名: 标题_1.jpg, 标题_2.jpg
                            file_name = f"{safe_title}_{i}.jpg"
                            save_path = os.path.join(DOWNLOAD_IMG_DIR, file_name)

                            # 发送请求下载
                            resp = requests.get(img_url, timeout=15)
                            if resp.status_code == 200:
                                with open(save_path, "wb") as f:
                                    f.write(resp.content)
                            # print(f"      已保存: {file_name}")
                        except Exception as img_e:
                            print(f"      ⚠️ 图片 {i} 下载失败: {img_e}")
                # ==========================================

                time.sleep(random.uniform(*DELAY_RANGE))

            except Exception as e:
                print(f"⏭️ 爬取异常，跳过此条: {str(e)[:50]}")
                time.sleep(random.uniform(*DELAY_RANGE))
                continue

        await spider.close()
        return all_posts

    # Windows 异步兼容处理
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(async_crawl())
    finally:
        loop.close()

    return result


def save_to_csv(posts):
    """第三步：保存结果"""
    print("\n===== 【第三步】保存爬取结果 =====")
    if not posts:
        print("⚠️ 无数据")
        return

    fieldnames = ["标题", "作者", "内容", "图片数量", "帖子链接"]

    with open(CSV_FILENAME, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(posts)

    print(f"✅ 保存成功: {CSV_FILENAME} (共 {len(posts)} 条)")


def main():
    """主函数"""
    search_keyword = "面经"  # 修改搜索关键词

    init_env()

    links = get_jingyan_links(search_keyword)
    if not links:
        print("❌ 未获取到链接")
        return

    posts = crawl_post_details(links)

    save_to_csv(posts)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 程序终止")
    except Exception as e:
        print(f"\n❌ 错误: {e}")