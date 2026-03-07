#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛客网正文提取 + 图片下载 - 独立可执行脚本

用法：
  python test_nowcoder_fetch.py [URL]
  python test_nowcoder_fetch.py                    # 使用默认测试链接
  python test_nowcoder_fetch.py "https://www.nowcoder.com/discuss/xxx"

依赖：pip install requests beautifulsoup4

输出目录：backend/data/nowcoder_output/
  - xxx_content.txt 提取的正文
  - xxx_images/      下载的图片
（不保存 HTML）
"""
import os
import re
import json
import time
import random
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
# 可选：从 .env 读取 Cookie（若需登录态）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://www.nowcoder.com"


def _get_out_dir() -> Path:
    """输出目录：backend/data/nowcoder_output，所有后端数据统一在 backend 下"""
    try:
        from backend.config.config import settings
        return settings.nowcoder_output_dir
    except ImportError:
        return Path(__file__).resolve().parent / "backend" / "data" / "nowcoder_output"
# DEFAULT_URL = "https://www.nowcoder.com/discuss/795353285103276032"
# DEFAULT_URL = "https://www.nowcoder.com/feed/main/detail/21b0cbea3bac4eb4876a71900b0543ed?sourceSSR=search"
DEFAULT_URL="https://www.nowcoder.com/feed/main/detail/78d6c8c30f1741e6b0a1a02d7b4bbfab"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


def fetch_html(url: str, cookie: str = "") -> str:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": BASE_URL,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cookie": cookie or "",
    }
    time.sleep(random.uniform(1, 2))
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text


# ========== DOM 正文提取 ==========
CONTENT_CLASSES = [
    "nc-post-content", "post-topic-des", "feed-detail-content",
    "detail-content", "content-body", "tw-prose", "post-content", "article-content",
]
CONTENT_IDS = ["js-post-content", "post-content", "main-content"]


def extract_from_dom(soup: BeautifulSoup) -> tuple:
    """从 DOM 解析正文，返回 (title, body)"""
    title, body = "", ""
    # 标题
    for sel in [
        ("span", lambda x: x and "post-title" in str(x)),
        ("h1", None),
        ("div", lambda x: x and "title" in str(x).lower()),
    ]:
        tag, attrs = sel[0], sel[1]
        el = soup.find(tag, class_=attrs) if attrs else soup.find(tag)
        if el:
            t = el.get_text(strip=True)
            if t and len(t) < 200:
                title = t.replace("_牛客网", "").strip()
                break
    # 正文
    for cls in CONTENT_CLASSES:
        div = soup.find("div", class_=lambda x: x and cls in str(x))
        if div:
            for t in div(["script", "style"]):
                t.decompose()
            text = div.get_text(separator="\n", strip=True)
            if len(text) > 50:
                body = text
                break
    if not body:
        for aid in CONTENT_IDS:
            div = soup.find(id=aid)
            if div:
                for t in div(["script", "style"]):
                    t.decompose()
                text = div.get_text(separator="\n", strip=True)
                if len(text) > 50:
                    body = text
                    break
    return title, body


def extract_from_meta(soup: BeautifulSoup) -> tuple:
    """从 meta 标签提取（兜底）"""
    title, body = "", ""
    for sel in ['meta[property="og:description"]', 'meta[name="description"]']:
        el = soup.select_one(sel)
        if el and el.get("content"):
            body = el["content"].strip()
            body = re.sub(r'\s*#_牛客网.*$', '', body)
            if len(body) > 30:
                break
    for sel in ['meta[property="og:title"]', 'title']:
        el = soup.select_one(sel)
        if el:
            t = el.get("content", el.get_text() if el.name == "title" else "").strip()
            if t:
                title = t.replace("_牛客网", "").strip()
                break
    return title, body


def html_to_text(html_str: str) -> str:
    """HTML 片段解析为纯文本"""
    if not html_str or not isinstance(html_str, str):
        return ""
    try:
        s = BeautifulSoup(html_str, "html.parser")
        for t in s(["script", "style"]):
            t.decompose()
        return s.get_text(separator="\n", strip=True)
    except Exception:
        return ""


def extract_json_blocks(html: str) -> list:
    """提取 __NEXT_DATA__、__INITIAL_STATE__、__PRELOADED_STATE__"""
    found = []
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            found.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass
    for pattern in [r'__INITIAL_STATE__\s*=\s*(\{)', r'window\.__PRELOADED_STATE__\s*=\s*(\{)']:
        m = re.search(pattern, html)
        if m:
            start = m.start(1)
            depth, i, in_str, escape = 0, start, None, False
            while i < len(html):
                c = html[i]
                if in_str:
                    escape = (c == "\\" and not escape)
                    if not escape and c == in_str:
                        in_str = None
                    i += 1
                    continue
                if c in ('"', "'"):
                    in_str = c
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            found.append(json.loads(html[start:i + 1]))
                        except json.JSONDecodeError:
                            pass
                        break
                i += 1
    return found


def dig_content(obj, depth=0, max_depth=14) -> list:
    """递归查找正文字段"""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("content", "contenttext", "body", "postcontent",
                             "description", "text", "html"):
                if isinstance(v, str) and len(v) > 20 and not v.startswith("http"):
                    clean = html_to_text(v)
                    if len(clean) > 20:
                        results.append(clean)
            results.extend(dig_content(v, depth + 1, max_depth))
    elif isinstance(obj, list):
        for v in obj:
            results.extend(dig_content(v, depth + 1, max_depth))
    return results


def extract_from_initial_state_feed(html: str) -> tuple:
    """
    牛客 feed 页面：从 __INITIAL_STATE__ 的 prefetchData.ssrCommonData.contentData 提取主帖正文。
    meta/og:description 会被截断，完整内容在 prefetchData 中。
    返回 (title, body)，未找到则 ("", "")。
    """
    m = re.search(r"__INITIAL_STATE__\s*=\s*(\{)", html)
    if not m:
        return "", ""
    start = m.start(1)
    depth, i, in_str, escape = 0, start, None, False
    while i < len(html):
        c = html[i]
        if in_str:
            escape = c == "\\" and not escape
            if not escape and c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'"):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    d = json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return "", ""
                break
        i += 1
    else:
        return "", ""

    prefetch = d.get("prefetchData") or d.get("prefetch")
    if isinstance(prefetch, dict):
        prefetch = list(prefetch.values())
    if not isinstance(prefetch, list):
        return "", ""

    title, body = "", ""
    for item in prefetch:
        if not isinstance(item, dict):
            continue
        ssr = item.get("ssrCommonData") or item.get("ssrData")
        if not isinstance(ssr, dict):
            continue
        # 主帖在 contentData，排除 similarRecommend（推荐帖）
        content_data = ssr.get("contentData")
        if isinstance(content_data, dict):
            c = content_data.get("content") or content_data.get("text") or ""
            if isinstance(c, str) and len(c) > 100:
                # 可能是 HTML，用 BeautifulSoup 转纯文本
                if "<" in c and ">" in c:
                    c = html_to_text(c)
                body = c.strip()
                title = (content_data.get("title") or content_data.get("subject") or "").strip()
                break
    return title, body


def extract_from_json(html: str) -> str:
    """从 JSON 块提取正文（SPA 兜底）。feed 页优先用 extract_from_initial_state_feed。"""
    blocks = extract_json_blocks(html)
    candidates = []
    for j in blocks:
        for text in dig_content(j):
            if len(text) > 50:
                candidates.append(text)
    return max(candidates, key=len) if candidates else ""


def collect_image_urls_from_dom(soup: BeautifulSoup) -> list:
    """从 DOM 正文区域收集图片 URL，仅保留用户上传图（排除表情、UI）"""
    urls = []
    for cls in CONTENT_CLASSES[:5] + ["post-content", "feed-content-text", "feed-img"]:
        div = soup.find("div", class_=lambda x: x and cls in str(x))
        if div:
            for img in div.find_all("img", src=True):
                src = img.get("src", "").strip()
                if src and not src.startswith("data:"):
                    u = src if src.startswith("http") else ("https:" + src if src.startswith("//") else urljoin(BASE_URL, src))
                    if _is_user_content_image(img, u) and u not in urls:
                        urls.append(u)
            if urls:
                return urls
    return urls


def _looks_like_image_url(s: str) -> bool:
    """判断字符串是否像图片 URL"""
    if not s or not isinstance(s, str) or not s.startswith("http"):
        return False
    slo = s.lower()
    return any(x in slo for x in [".jpg", ".jpeg", ".png", ".webp", ".gif", "image", "img", "static", "cdn"])


def dig_image_urls(obj, depth=0, max_depth=14) -> list:
    """递归从 JSON 中查找图片 URL（feed 页面图片常在 JSON 里）"""
    if depth > max_depth:
        return []
    urls = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            klo = k.lower()
            if klo in ("url", "src", "imageurl", "image_url", "picurl", "pic_url", "cover", "thumbnail", "picture"):
                if isinstance(v, str) and _looks_like_image_url(v):
                    urls.append(v)
            urls.extend(dig_image_urls(v, depth + 1, max_depth))
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, str) and _looks_like_image_url(v):
                urls.append(v)
            else:
                urls.extend(dig_image_urls(v, depth + 1, max_depth))
    return urls


def _is_user_content_image_url(url: str) -> bool:
    """仅根据 URL 判断是否像用户上传图（无 img 标签时用）"""
    if not url or not url.startswith("http") or url.startswith("data:"):
        return False
    if "static.nowcoder.com" in url:
        return False
    if "uploadfiles.nowcoder.com/images/20220815/" in url and "318889480" in url:
        return False
    if "avatar" in url.lower() or "logo" in url.lower() or "favicon" in url.lower():
        return False
    return True


def _is_user_content_image(img_tag, src: str) -> bool:
    """
    判断是否为正文中的用户上传图片（排除表情、头像、UI 图标）。
    规律：表情有 data-card-emoji、18x18；static 为 UI；用户上传多为 uploadfiles 非 emoji 路径。
    """
    if not src or not src.startswith("http") or src.startswith("data:"):
        return False
    # 排除 static 静态资源
    if "static.nowcoder.com" in src:
        return False
    # 排除表情：data-card-emoji 或 URL 含 emoji 路径 /images/20220815/318889480_
    if img_tag and (img_tag.get("data-card-emoji") or img_tag.get("data-card-nowcoder")):
        return False
    style = (img_tag.get("style") or "").lower() if img_tag else ""
    if "18px" in style or "14px" in style or "12px" in style:
        if "width" in style or "height" in style:
            return False  # 小图标/表情
    # 排除牛客表情图路径（固定格式）
    if "uploadfiles.nowcoder.com/images/20220815/" in src and "318889480" in src:
        return False
    return True


def _collect_content_blocks(obj, depth=0, max_depth=14) -> list:
    """收集 content 块及其父对象，返回 [(html, parent_obj), ...]。主帖图片在 imgMoment/contentImageUrls，不在 content HTML。"""
    if depth > max_depth:
        return []
    blocks = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("content", "html", "body", "text", "description"):
                if isinstance(v, str) and len(v) > 50:
                    blocks.append((v, obj))
            blocks.extend(_collect_content_blocks(v, depth + 1, max_depth))
    elif isinstance(obj, list):
        for v in obj:
            blocks.extend(_collect_content_blocks(v, depth + 1, max_depth))
    return blocks


def _extract_images_from_html(html: str) -> list:
    """从单个 HTML 字符串中提取用户上传图"""
    urls = []
    try:
        s = BeautifulSoup(html, "html.parser")
        for img in s.find_all("img", src=True):
            src = img.get("src", "").strip()
            if _is_user_content_image(img, src):
                urls.append(src)
    except Exception:
        pass
    return urls


def _extract_from_img_moment(parent: dict) -> list:
    """从主帖的 imgMoment 或 contentImageUrls 提取图片 URL（用户上传图在此，不在 content HTML）"""
    urls = []
    for key in ("imgMoment", "contentImageUrls"):
        arr = parent.get(key)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if isinstance(item, dict) and "src" in item:
                src = item.get("src", "").strip()
                if src and _is_user_content_image_url(src):
                    urls.append(src)
            elif isinstance(item, str) and _is_user_content_image_url(item):
                urls.append(item)
    return urls


def dig_image_urls_from_main_post_only(obj, depth=0, max_depth=14) -> list:
    """
    仅从主帖提取图片。主帖 = content 最长的块。
    图片来源：1) content HTML 中的 img  2) 主帖的 imgMoment/contentImageUrls（用户上传图多在此）
    """
    blocks = _collect_content_blocks(obj, depth, max_depth)
    if not blocks:
        return []
    main_block = max(blocks, key=lambda x: len(x[0]))
    html, parent = main_block[0], main_block[1]
    urls = _extract_images_from_html(html)
    urls.extend(_extract_from_img_moment(parent))
    return list(dict.fromkeys(urls))


def collect_image_urls_from_html(html: str) -> list:
    """
    从 JSON 收集用户上传图。仅从主帖 content（最长的块）提取，排除相关推荐等。
    """
    urls = []
    for block in extract_json_blocks(html):
        # 只从主帖最长 content 提取，不混入推荐帖
        for u in dig_image_urls_from_main_post_only(block):
            if u not in urls:
                urls.append(u)
    return urls


def collect_image_urls(soup: BeautifulSoup, html: str = "") -> list:
    """从 DOM 和 JSON 收集图片 URL（feed 页面图片多在 JSON 中）"""
    urls = collect_image_urls_from_dom(soup)
    if not urls and html:
        urls = collect_image_urls_from_html(html)
    return urls


def download_images(urls: list, out_dir: Path) -> list:
    """下载图片到 out_dir，返回保存的文件路径列表"""
    if not urls:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENTS[0], "Referer": BASE_URL}
    saved = []
    for i, url in enumerate(urls):
        if not url or not url.startswith("http"):
            continue
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            ext = "jpg"
            ct = resp.headers.get("Content-Type", "").lower()
            if "png" in ct:
                ext = "png"
            elif "gif" in ct:
                ext = "gif"
            elif "webp" in ct:
                ext = "webp"
            fpath = out_dir / f"{i}.{ext}"
            with open(fpath, "wb") as f:
                f.write(resp.content)
            saved.append(str(fpath))
        except Exception as e:
            print(f"  [!] 图片下载失败 {url[:50]}...: {e}")
    return saved


def url_to_safe_slug(url: str) -> str:
    """将 URL 转为 Windows 安全文件名（去除 ?# 等非法字符）"""
    parsed = urlparse(url)
    path = (parsed.netloc or "") + (parsed.path or "")
    slug = path.replace("/", "_")
    for c in r'\/:*?"<>|':
        slug = slug.replace(c, "_")
    slug = re.sub(r'[?\#]', "_", slug).strip("_") or "page"
    return slug[:120]  # 避免路径过长


def resolve_feed_to_discuss(soup: BeautifulSoup, url: str) -> str:
    """feed 页面尝试解析 discuss 链接（discuss 有完整服务端渲染正文）"""
    if "/feed/main/detail/" not in url:
        return url
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        h = canonical["href"].strip()
        if "/discuss/" in h:
            return h if h.startswith("http") else urljoin(BASE_URL, h)
    return url


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    cookie = os.environ.get("NOWCODER_COOKIE", "")

    out_dir = _get_out_dir()
    slug = url_to_safe_slug(url)
    txt_path = out_dir / f"{slug}_content.txt"
    img_dir = out_dir / f"{slug}_images"

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"目标: {url}")
    print("=" * 60)

    # 1. 请求（不保存 HTML）
    try:
        html = fetch_html(url, cookie)
    except Exception as e:
        print(f"请求失败: {e}")
        return 1

    soup = BeautifulSoup(html, "html.parser")

    # 2. 提取正文（feed 页优先从 __INITIAL_STATE__ 取完整内容，meta 会截断）
    title, body = "", ""
    if "/feed/main/detail/" in url:
        title, body = extract_from_initial_state_feed(html)
    if not body:
        title, body = extract_from_dom(soup)
    if not body:
        title, body = extract_from_meta(soup)
    if not body:
        body = extract_from_json(html)

    # feed 页面无正文时，尝试跳转到 discuss 获取完整内容
    if not body and "/feed/main/detail/" in url:
        discuss_url = resolve_feed_to_discuss(soup, url)
        if discuss_url != url:
            print(f"feed 页面无正文，尝试 discuss 链接: {discuss_url[:60]}...")
            try:
                html = fetch_html(discuss_url, cookie)
                soup = BeautifulSoup(html, "html.parser")
                title, body = extract_from_dom(soup)
                if not body:
                    title, body = extract_from_meta(soup)
                if not body:
                    body = extract_from_json(html)
                if body:
                    url = discuss_url
                    slug = url_to_safe_slug(url)
                    txt_path = out_dir / f"{slug}_content.txt"
                    img_dir = out_dir / f"{slug}_images"
            except Exception as e:
                print(f"  discuss 请求失败: {e}")

    if not body:
        print("未提取到正文")
        return 1

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"# {title or '无标题'}\n\n{body}")
    print(f"已保存正文: {txt_path} ({len(body)} 字)")
    print("-" * 40)
    print(body[:500] + ("..." if len(body) > 500 else ""))
    print("-" * 40)

    # 3. 收集并下载图片到 backend/data/nowcoder_output（DOM + JSON）
    img_urls = collect_image_urls(soup, html)
    if img_urls:
        print(f"发现 {len(img_urls)} 张图片，正在下载...")
        saved = download_images(img_urls, img_dir)
        print(f"已保存 {len(saved)} 张到: {img_dir}")
    else:
        print("未发现正文内图片")

    print("\n完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
