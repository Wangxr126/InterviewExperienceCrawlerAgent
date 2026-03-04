#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
牛客 feed/main/detail 正文提取调试脚本
目标：从 https://www.nowcoder.com/feed/main/detail/xxx 爬取正文内容

策略：
  1. 解析 HTML 中的 __NEXT_DATA__ / __INITIAL_STATE__ 等 JSON（SPA 常见）
  2. 尝试调用牛客 feed 详情 API（若可发现）
  3. 备用：Playwright 渲染后提取（需安装 playwright）

用法：
  python debug_nowcoder_feed.py [URL]
  python debug_nowcoder_feed.py   # 使用默认测试链接

输出：
  debug_nowcoder_output.html  原始 HTML
  debug_nowcoder_content.txt  提取的正文
"""
import os
import sys
import re
import json
import time
import random
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from bs4 import BeautifulSoup

DEFAULT_URL = "https://www.nowcoder.com/feed/main/detail/1b7c03f03fbd43f897df4d96473b716e"
BASE_URL = "https://www.nowcoder.com"

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
        "Cookie": cookie,
    }
    time.sleep(random.uniform(1, 2))
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    return resp.text


def extract_json_from_script(html: str) -> list:
    """从 HTML 中提取所有可能的 JSON 数据块"""
    found = []
    # __NEXT_DATA__（Next.js 常见）
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            found.append(("__NEXT_DATA__", json.loads(m.group(1).strip())))
        except json.JSONDecodeError:
            pass
    # __INITIAL_STATE__（括号平衡匹配）
    m = re.search(r'__INITIAL_STATE__\s*=\s*(\{)', html)
    if m:
        start = m.start(1)
        depth, i, in_str = 0, start, None
        escape = False
        while i < len(html):
            c = html[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == in_str:
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
                        found.append(("__INITIAL_STATE__", json.loads(html[start:i+1])))
                    except json.JSONDecodeError:
                        pass
                    break
            i += 1
    # window.__PRELOADED_STATE__
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{[\s\S]*?\});', html)
    if m:
        try:
            found.append(("__PRELOADED_STATE__", json.loads(m.group(1).strip())))
        except json.JSONDecodeError:
            pass
    # self.__next_f.push 中的 JSON（Next.js 流式）
    for m in re.finditer(r'self\.__next_f\.push\(\[([^\]]+),"([^"]*)"\]\)', html):
        try:
            # 第二个参数可能是 JSON 字符串
            s = m.group(2).replace("\\\"", '"').replace("\\\\", "\\")
            if "content" in s or "body" in s or "title" in s:
                found.append(("next_f_push", json.loads(s)))
        except (json.JSONDecodeError, IndexError):
            pass
    # type="application/json" 的 script
    for tag in re.finditer(r'<script[^>]*type=["\']application/json["\'][^>]*>([\s\S]*?)</script>', html):
        try:
            j = json.loads(tag.group(1).strip())
            if isinstance(j, dict) and (len(str(j)) > 200):
                found.append(("application/json", j))
        except json.JSONDecodeError:
            pass
    return found


def dig_content(obj, path="", depth=0, max_depth=14) -> list:
    """递归查找 content/body/contentText/postContent 等正文字段"""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            klo = k.lower()
            if klo in ("content", "contenttext", "content_text", "body", "postcontent",
                       "post_content", "description", "text", "html", "markdown"):
                if isinstance(v, str) and len(v) > 15 and not v.startswith("http"):
                    # 去掉 HTML 标签
                    clean = re.sub(r"<[^>]+>", " ", v).strip()
                    if len(clean) > 15:
                        results.append((path + k, clean))
            results.extend(dig_content(v, path + k + ".", depth + 1, max_depth))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            results.extend(dig_content(v, path + f"[{i}].", depth + 1, max_depth))
    return results


def dig_title(obj, path="", depth=0, max_depth=10) -> list:
    """递归查找 title/subject 等标题字段"""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            klo = k.lower()
            if klo in ("title", "subject", "name", "headline"):
                if isinstance(v, str) and 2 < len(v) < 200 and not v.startswith("http"):
                    results.append((path + k, v.strip()))
            results.extend(dig_title(v, path + k + ".", depth + 1, max_depth))
    elif isinstance(obj, list) and obj:
        results.extend(dig_title(obj[0], path + "[0].", depth + 1, max_depth))
    return results


def _score_as_main_post(text: str, title: str = "") -> int:
    """正文越像主帖（面经）得分越高"""
    score = 0
    t = (text + " " + title)
    # 面经特征（强信号）
    if "一面" in t or "二面" in t or "三面" in t or "hr面" in t:
        score += 15
    if "面经" in t:
        score += 10
    if "分钟" in t or "自我介绍" in t or "八股" in t:
        score += 5
    if "面试官" in t or "反问" in t or "项目" in t:
        score += 3
    # 侧栏/推荐帖特征（扣分）
    if "大佬们" in t or "求建议" in t or "怎么选" in t or "帮我看看" in t:
        score -= 8
    return score


def extract_from_json_blocks(html: str, url: str = "") -> tuple:
    """从 JSON 块中提取正文，优先主帖（面经）"""
    title, body = "", ""
    body_candidates = []  # [(score, text), ...]
    title_candidates = []
    blocks = extract_json_from_script(html)
    for name, j in blocks:
        for path, text in dig_content(j):
            clean = re.sub(r"<[^>]+>", " ", text).strip()
            if len(clean) < 20:
                continue
            path_lo = path.lower()
            if "title" in path_lo or "subject" in path_lo:
                title_candidates.append(clean[:200])
            else:
                score = _score_as_main_post(clean)
                body_candidates.append((score, clean))
        for path, t in dig_title(j):
            title_candidates.append(t[:200])
    # 正文：按得分+长度排序
    body_candidates.sort(key=lambda x: (-x[0], -len(x[1])))
    for score, b in body_candidates:
        if len(b) > 50:
            body = b
            break
    # 标题：取最短的（主帖标题通常较短）
    if title_candidates:
        title = min(title_candidates, key=len)
    return title, body


def extract_from_meta(soup: BeautifulSoup) -> tuple:
    """从 meta 标签提取（SEO 常用，正文常在此）"""
    title, body = "", ""
    # og:description 或 description 通常含正文
    for sel in ['meta[property="og:description"]', 'meta[name="description"]']:
        el = soup.select_one(sel)
        if el and el.get("content"):
            body = el["content"].strip()
            body = re.sub(r'\s*#_牛客网.*$', '', body)  # 去掉牛客网后缀
            if len(body) > 30:
                break
    # 标题：og:title 或 title
    for sel in ['meta[property="og:title"]', 'title']:
        el = soup.select_one(sel)
        if el:
            t = el.get("content", el.get_text() if el.name == "title" else "").strip()
            if t:
                title = t.replace("_牛客网", "").strip()
                break
    return title, body


def extract_from_dom(soup: BeautifulSoup) -> tuple:
    """从 DOM 中提取正文（静态 HTML 场景）"""
    title, body = "", ""
    # 标题
    for sel in ["h1", "[class*='title']", "[class*='Title']"]:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(strip=True)
            if t and len(t) < 150:
                title = t
                break
    # 正文：优先找内容区
    for cls in ["nc-post-content", "post-topic-des", "feed-detail-content", "detail-content",
                "tw-prose", "post-content", "content-body", "article-content"]:
        div = soup.find("div", class_=lambda x: x and cls in str(x))
        if div:
            for t in div(["script", "style"]):
                t.decompose()
            body = div.get_text(separator="\n", strip=True)
            if len(body) > 50:
                return title or "无标题", body
    # 备选：id
    for aid in ["js-post-content", "post-content", "main-content"]:
        div = soup.find(id=aid)
        if div:
            for t in div(["script", "style"]):
                t.decompose()
            body = div.get_text(separator="\n", strip=True)
            if len(body) > 50:
                return title or "无标题", body
    return title, body


def try_playwright(url: str, cookie: str = "") -> tuple:
    """使用 Playwright 获取渲染后的正文（需 playwright 已安装）"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", ""
    title, body = "", ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENTS[0],
            extra_http_headers={"Cookie": cookie} if cookie else {},
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(2000)
            # 尝试多种选择器
            for sel in [
                "[class*='nc-post-content']", "[class*='post-topic-des']",
                "[class*='feed-detail'] [class*='content']",
                ".tw-prose", "#js-post-content",
            ]:
                el = page.query_selector(sel)
                if el:
                    body = el.inner_text()
                    if body and len(body) > 50:
                        break
            # 标题
            for sel in ["h1", "[class*='title']"]:
                el = page.query_selector(sel)
                if el:
                    title = el.inner_text().strip()
                    if title:
                        break
        except Exception as e:
            print(f"  Playwright 异常: {e}")
        finally:
            browser.close()
    return title, body


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    cookie = os.environ.get("NOWCODER_COOKIE", "")

    out_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(out_dir, "debug_nowcoder_output.html")
    txt_path = os.path.join(out_dir, "debug_nowcoder_content.txt")

    print(f"目标: {url}")
    print("=" * 60)

    # 1. 请求 HTML
    try:
        html = fetch_html(url, cookie)
    except Exception as e:
        print(f"请求失败: {e}")
        return

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("已保存: debug_nowcoder_output.html")

    soup = BeautifulSoup(html, "html.parser")

    # 2. 优先从 meta 提取（牛客 SEO 把正文放在 og:description，最可靠）
    title, body = extract_from_meta(soup)
    if body:
        print("✅ 从 meta 标签提取到正文")
    else:
        # 3. 从 JSON 块提取（SPA）
        title, body = extract_from_json_blocks(html)
        if body:
            print("✅ 从 JSON 块提取到正文")
        else:
            # 4. 从 DOM 提取
            t, b = extract_from_dom(soup)
            if b:
                title, body = t or title, b
                print("✅ 从 DOM 提取到正文")
            else:
                # 5. 尝试 Playwright
                print("⏳ 尝试 Playwright 渲染...")
                t, b = try_playwright(url, cookie)
                if b:
                    title, body = t or title, b
                    print("✅ 从 Playwright 提取到正文")
                else:
                    print("❌ 未提取到正文")

    # 输出
    result = f"# {title or '无标题'}\n\n{body}" if title else body
    print("\n" + "-" * 40)
    print(result[:800] + ("..." if len(result) > 800 else ""))
    print("-" * 40)

    if body:
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"\n已保存: debug_nowcoder_content.txt ({len(body)} 字)")
    else:
        print("\n请打开 debug_nowcoder_output.html 查看页面结构，或配置 NOWCODER_COOKIE 后重试")


if __name__ == "__main__":
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
