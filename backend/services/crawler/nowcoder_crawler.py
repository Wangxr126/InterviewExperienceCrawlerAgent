"""
牛客网面经爬虫（严格对齐 思路/爬虫工具/1、牛客网爬虫.py）
职责：列表页发现帖子 + 详情页抓取正文，解析逻辑与参考实现一致
"""
import time
import re
import json
import random
import logging
from typing import List, Dict, Tuple
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]

# 与参考实现完全一致的规则词典
RULES = {
    "company": {
        "字节": "字节跳动", "bytedance": "字节跳动", "抖音": "字节跳动", "TikTok": "字节跳动",
        "阿里": "阿里巴巴", "淘天": "阿里巴巴", "蚂蚁": "蚂蚁集团", "天猫": "阿里巴巴",
        "腾讯": "腾讯", "wxg": "腾讯(WXG)", "ieg": "腾讯(IEG)", "teg": "腾讯(TEG)", "qq": "腾讯",
        "美团": "美团", "百度": "百度", "快手": "快手", "拼多多": "拼多多", "pdd": "拼多多",
        "京东": "京东", "网易": "网易", "小红书": "小红书",
        "华为": "华为", "od": "华为OD", "德科": "华为OD",
        "米哈游": "米哈游", "滴滴": "滴滴", "蔚来": "蔚来", "理想": "理想", "小鹏": "小鹏",
        "b站": "Bilibili", "哔哩哔哩": "Bilibili",
        "去哪儿": "去哪儿", "携程": "携程",
        "中车": "中车", "虎牙": "虎牙", "银联": "中国银联", "极氪": "极氪",
        "cvte": "CVTE", "航旅纵横": "航旅纵横", "千寻": "千寻智能",
    },
    "role": [
        "后端", "前端", "算法", "测试", "测开", "客户端", "安卓", "Android", "ios",
        "大数据", "产品", "运营", "Java", "C++", "Python", "Go", "嵌入式", "硬件", "机械", "全栈",
    ],
    "business": [
        "搜索", "推荐", "广告", "电商", "支付", "游戏", "云", "基础架构", "Infra",
        "飞书", "微信", "大模型", "LLM", "智能运维", "自动驾驶", "核心", "商业化",
    ],
    "difficulty": {
        "困难": ["拷打", "深挖", "很难", "挂了", "凉", "压力", "手撕", "底层", "源码"],
        "简单": ["简单", "常规", "八股", "水面", "聊天", "基础", "oc", "意向"],
    },
    "post_type": {
        "吐槽": ["避雷", "恶心", "无语", "kpi", "渣男"],
        "面经": ["面经", "一面", "二面", "三面", "hr面", "复盘", "凉经"],
        "求助": ["求捞", "求助", "怎么办", "选哪个"],
    },
}


# ══════════════════════════════════════════════════════════════
# 详情页正文提取（来自 debug_nowcoder_feed.py 验证通过的逻辑）
# ══════════════════════════════════════════════════════════════

def _extract_content_from_meta(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    从 meta 标签提取正文（最可靠策略）。
    牛客 feed 页面会把帖子正文放入 og:description 和 description。
    """
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


def _extract_content_from_dom(soup: BeautifulSoup) -> str:
    """从 DOM 提取正文（备用策略）"""
    for cls in ["nc-post-content", "post-topic-des", "feed-detail-content",
                "tw-prose", "post-content", "article-content"]:
        div = soup.find("div", class_=lambda x: x and cls in str(x))
        if div:
            for t in div(["script", "style"]):
                t.decompose()
            text = div.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return text
    for aid in ["js-post-content", "post-content", "main-content"]:
        div = soup.find(id=aid)
        if div:
            for t in div(["script", "style"]):
                t.decompose()
            text = div.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return text
    return ""


def _extract_json_scripts(html: str) -> list:
    """提取页面中的 JSON 数据块"""
    found = []
    m = re.search(r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            found.append(json.loads(m.group(1).strip()))
        except json.JSONDecodeError:
            pass
    m = re.search(r'__INITIAL_STATE__\s*=\s*(\{)', html)
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


def _dig_content_fields(obj, depth=0, max_depth=14) -> list:
    """递归查找正文字段"""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("content", "contenttext", "content_text", "body",
                             "postcontent", "post_content", "description", "text"):
                if isinstance(v, str) and len(v) > 20 and not v.startswith("http"):
                    clean = re.sub(r"<[^>]+>", " ", v).strip()
                    if len(clean) > 20:
                        results.append(clean)
            results.extend(_dig_content_fields(v, depth + 1, max_depth))
    elif isinstance(obj, list):
        for v in obj:
            results.extend(_dig_content_fields(v, depth + 1, max_depth))
    return results


def _extract_content_from_json(html: str) -> str:
    """从 JSON 块中提取正文（兜底策略）"""
    blocks = _extract_json_scripts(html)
    candidates = []
    for j in blocks:
        for text in _dig_content_fields(j):
            # 面经特征打分
            score = 0
            if "一面" in text or "二面" in text or "三面" in text or "hr面" in text:
                score += 15
            if "面经" in text:
                score += 10
            if "分钟" in text or "自我介绍" in text or "八股" in text or "反问" in text:
                score += 5
            candidates.append((score, len(text), text))
    candidates.sort(key=lambda x: (-x[0], -x[1]))
    for _, length, text in candidates:
        if length > 50:
            return text
    return ""


def _fetch_post_content_full_impl(
    html: str, soup: BeautifulSoup
) -> Tuple[str, str, List[str]]:
    """
    三级提取策略，返回 (title, body, image_urls)
      1. meta 标签（最可靠）
      2. DOM 类名选择器
      3. JSON 块递归搜索
    """
    # 1. meta
    title, body = _extract_content_from_meta(soup)
    if body:
        # meta 中无图片，需从 DOM 中补充图片 URL
        image_urls = _collect_image_urls(soup, html)
        return title, body, image_urls

    # 2. DOM
    body = _extract_content_from_dom(soup)
    if body:
        image_urls = _collect_image_urls(soup, html)
        return title, body, image_urls

    # 3. JSON
    body = _extract_content_from_json(html)
    image_urls = _collect_image_urls(soup, html) if body else []
    return title, body, image_urls


def _collect_image_urls(soup: BeautifulSoup, html: str = "") -> List[str]:
    """从页面中收集图片 URL（优先从正文区域）"""
    BASE = "https://www.nowcoder.com"
    urls = []
    for cls in ["nc-post-content", "post-topic-des", "post-content"]:
        div = soup.find("div", class_=lambda x: x and cls in str(x))
        if div:
            for img in div.find_all("img", src=True):
                src = img.get("src", "").strip()
                if src and not src.startswith("data:"):
                    urls.append(src if src.startswith("http") else
                                ("https:" + src if src.startswith("//") else urljoin(BASE, src)))
            if urls:
                return urls
    return urls


# ══════════════════════════════════════════════════════════════
# 元数据提取（规则匹配）
# ══════════════════════════════════════════════════════════════

def _extract_meta_info(title: str, content_preview: str) -> Dict[str, str]:
    """
    从标题和内容中提取结构化元数据（与参考 extract_meta_info 完全一致）
    """
    text_scan = f"{title} {content_preview}".lower()
    result = {
        "company": "未知",
        "role": "未知",
        "business": "未知",
        "difficulty": "适中",
        "post_type": "其他",
    }
    # 1. 公司
    for key, name in RULES["company"].items():
        if key.lower() in text_scan:
            result["company"] = name
            break
    # 2. 岗位
    for role in RULES["role"]:
        if role.lower() in text_scan:
            result["role"] = role
            break
    # 3. 业务线
    for bus in RULES["business"]:
        if bus.lower() in text_scan:
            result["business"] = bus
            break
    # 4. 难度
    diff_score = 0
    if any(k in text_scan for k in RULES["difficulty"]["困难"]):
        diff_score += 1
    if any(k in text_scan for k in RULES["difficulty"]["简单"]):
        diff_score -= 1
    if diff_score > 0:
        result["difficulty"] = "困难/拷打"
    elif diff_score < 0:
        result["difficulty"] = "简单/常规"
    # 5. 帖子类型
    for p_type, keywords in RULES["post_type"].items():
        if any(k in text_scan for k in keywords):
            result["post_type"] = p_type
            break
    return result


class NowcoderCrawler:
    """
    牛客面经爬虫，严格对齐 思路/爬虫工具/1、牛客网爬虫.py
    """

    BASE_URL = "https://www.nowcoder.com"

    def __init__(self, cookie: str = ""):
        self.cookie = cookie
        self.session = requests.Session()
        self._update_headers()

    def _update_headers(self):
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Referer": self.BASE_URL,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": self.cookie,
        })

    # ── 详情页爬取（严格按参考 parse_detail_page）────────────────────────────

    def fetch_post_content(self, post_url: str) -> str:
        """爬取帖子详情页，返回纯文本正文（兼容旧接口）"""
        text, _ = self.fetch_post_content_full(post_url)
        return text

    def fetch_post_content_full(self, post_url: str) -> Tuple[str, List[str]]:
        """
        爬取帖子详情页，返回 (正文纯文本, 图片URL列表)。
        提取优先级：meta 标签 → DOM 类名选择器 → JSON 块
        """
        if not post_url.startswith("http"):
            return "", []
        try:
            time.sleep(random.uniform(1, 2))
            self._update_headers()
            resp = self.session.get(post_url, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"详情页请求失败 {resp.status_code}: {post_url}")
                return "", []

            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            title, body, image_urls = _fetch_post_content_full_impl(html, soup)

            if body:
                logger.debug(f"详情页提取成功: {post_url[:60]} ({len(body)} 字, {len(image_urls)} 图)")
            else:
                logger.warning(f"未识别到正文结构: {post_url}")

            return body, image_urls

        except Exception as e:
            logger.error(f"详情页解析异常 {post_url}: {e}")
            return "", []

    # ── 列表页发现（严格按参考 parse_list_page）──────────────────────────────

    def discover_page(self, keyword: str, page: int) -> List[Dict]:
        """爬取一页搜索结果，返回帖子元数据列表"""
        list_url = f"{self.BASE_URL}/search/all?query={keyword}&type=all&searchType=历史搜索&page={page}"
        try:
            time.sleep(random.uniform(2, 4))
            self._update_headers()
            resp = self.session.get(list_url, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"列表页请求失败 {resp.status_code} page={page}")
                return []

            soup = BeautifulSoup(resp.text, "html.parser")

            # 定位帖子卡片（与参考一致：tw-bg-white + tw-mt-3 + tw-rounded-xl）
            post_cards = soup.find_all(
                "div",
                class_=lambda x: x and "tw-bg-white" in x and "tw-mt-3" in x and "tw-rounded-xl" in x,
            )
            if not post_cards:
                logger.info(f"第 {page} 页未找到数据（检查 Cookie 或是否末页）")
                return []

            results = []
            for idx, card in enumerate(post_cards, 1):
                try:
                    # 标题
                    title_tag = card.find(
                        "div",
                        class_=lambda x: x and "tw-font-bold" in x and "tw-text-lg" in x,
                    )
                    if not title_tag:
                        continue
                    title = title_tag.get_text(strip=True) or "无标题"

                    # 链接
                    link_tag = title_tag.find("a")
                    if not link_tag:
                        continue
                    href = link_tag.get("href", "")
                    post_url = urljoin(self.BASE_URL, href.split("?")[0]) if href else ""

                    # 发布时间
                    time_tag = card.find("div", class_=lambda x: x and "show-time" in x)
                    pub_time = time_tag.get_text(strip=True) if time_tag else ""

                    # 作者
                    author_tag = card.find("div", class_="user-nickname")
                    author = author_tag.get_text(strip=True) if author_tag else "匿名"

                    # 核心：从整个卡片文本解析（与参考一致）
                    full_card_text = card.get_text(separator=" ", strip=True)
                    preview_div = card.find("div", class_="placeholder-text")
                    preview_content = preview_div.get_text(strip=True) if preview_div else ""

                    analysis = _extract_meta_info(title, full_card_text)

                    results.append({
                        "title": title,
                        "source_url": post_url,
                        "source_platform": "nowcoder",
                        "company": analysis["company"],
                        "position": analysis["role"],
                        "business_line": analysis["business"],
                        "difficulty": analysis["difficulty"],
                        "post_type": analysis["post_type"],
                    })
                    logger.debug(
                        f"  [{analysis['company']}-{analysis['role']}] {title[:20]}... ({analysis['difficulty']})"
                    )
                except Exception as e:
                    logger.debug(f"解析单条出错: {e}")
                    continue

            logger.info(f"牛客 keyword={keyword} page={page} 发现 {len(results)} 条")
            return results

        except Exception as e:
            logger.error(f"列表页异常 {list_url}: {e}")
            return []

    def discover(
        self,
        keywords: List[str] = None,
        max_pages: int = 3,
        check_db_dedup: bool = True,
    ) -> List[Dict]:
        """
        批量发现面经帖子。
        check_db_dedup=True 时对已爬取链接去重。
        """
        keywords = keywords or ["面经"]
        all_posts: List[Dict] = []
        seen_urls: set = set()
        skipped_db = 0

        db_check = None
        if check_db_dedup:
            try:
                from backend.services.sqlite_service import sqlite_service
                db_check = sqlite_service.is_url_crawled
            except Exception:
                pass

        for kw in keywords:
            for page in range(1, max_pages + 1):
                posts = self.discover_page(kw, page)
                if not posts:
                    break
                for p in posts:
                    url = p["source_url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    if db_check and db_check(url):
                        skipped_db += 1
                        continue
                    all_posts.append(p)
            time.sleep(random.uniform(1, 2))

        if skipped_db:
            logger.info(f"牛客去重：数据库已有 {skipped_db} 条，本次新增 {len(all_posts)} 条")
        return all_posts
