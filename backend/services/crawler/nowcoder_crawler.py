"""
牛客网面经爬虫（严格对齐 思路/爬虫工具/1、牛客网爬虫.py）
职责：列表页发现帖子 + 详情页抓取正文，解析逻辑与参考实现一致
"""
from backend.utils.time_utils import now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
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
# 详情页正文提取：以 HTML 解析（DOM）为主，不依赖正则/关键词
# 策略：1) DOM 解析正文区  2) meta 兜底  3) JSON 中 HTML 用 BeautifulSoup 解析
# ══════════════════════════════════════════════════════════════

# 正文区域 DOM 选择器（按优先级，覆盖 discuss 与 feed 页面）
_CONTENT_DOM_SELECTORS = [
    ("div", {"class": lambda x: x and "nc-post-content" in str(x)}),
    ("div", {"class": lambda x: x and "post-topic-des" in str(x)}),
    ("div", {"class": lambda x: x and "feed-detail-content" in str(x)}),
    ("div", {"class": lambda x: x and "detail-content" in str(x)}),
    ("div", {"class": lambda x: x and "content-body" in str(x)}),
    ("div", {"class": lambda x: x and "tw-prose" in str(x)}),
    ("div", {"class": lambda x: x and "post-content" in str(x)}),
    ("div", {"class": lambda x: x and "article-content" in str(x)}),
]
_CONTENT_IDS = ["js-post-content", "post-content", "main-content"]

_TITLE_SELECTORS = [
    ("span", {"class": lambda x: x and "post-title" in str(x)}),
    ("h1", {}),
    ("div", {"class": lambda x: x and "title" in str(x).lower()}),
]


def _extract_content_from_dom(soup: BeautifulSoup) -> Tuple[str, str]:
    """
    从 DOM 解析正文（主策略）。通过 HTML 标签结构定位正文区域，不依赖正则。
    返回 (title, body)。
    """
    title, body = "", ""
    # 标题
    for tag, attrs in _TITLE_SELECTORS:
        el = soup.find(tag, attrs) if attrs else soup.find(tag)
        if el:
            t = el.get_text(strip=True)
            if t and len(t) < 200:
                title = t.replace("_牛客网", "").strip()
                break
    # 正文：按 class 选择器
    for tag, attrs in _CONTENT_DOM_SELECTORS:
        div = soup.find(tag, attrs)
        if div:
            for t in div(["script", "style"]):
                t.decompose()
            text = div.get_text(separator="\n", strip=True)
            if len(text) > 50:
                body = text
                break
    if not body:
        for aid in _CONTENT_IDS:
            div = soup.find(id=aid)
            if div:
                for t in div(["script", "style"]):
                    t.decompose()
                text = div.get_text(separator="\n", strip=True)
                if len(text) > 50:
                    body = text
                    break
    return title, body


def _extract_content_from_meta(soup: BeautifulSoup) -> Tuple[str, str]:
    """从 meta 标签提取（兜底，可能被截断）"""
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


def _html_to_text(html_str: str) -> str:
    """将 HTML 片段解析为纯文本，使用 BeautifulSoup 而非正则"""
    if not html_str or not isinstance(html_str, str):
        return ""
    try:
        soup = BeautifulSoup(html_str, "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return ""


def _extract_json_scripts(html: str) -> list:
    """提取页面中的 JSON 数据块（__NEXT_DATA__、__INITIAL_STATE__、__PRELOADED_STATE__ 等）"""
    found = []
    m = re.search(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
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
    m = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{)', html)
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
    """递归查找正文字段，返回 [(text, is_html), ...]，用 BeautifulSoup 解析 HTML"""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("content", "contenttext", "content_text", "body",
                             "postcontent", "post_content", "description", "text", "html"):
                if isinstance(v, str) and len(v) > 20 and not v.startswith("http"):
                    # 用 BeautifulSoup 解析 HTML，不用正则 strip
                    clean = _html_to_text(v)
                    if len(clean) > 20:
                        results.append(clean)
            results.extend(_dig_content_fields(v, depth + 1, max_depth))
    elif isinstance(obj, list):
        for v in obj:
            results.extend(_dig_content_fields(v, depth + 1, max_depth))
    return results


def _extract_content_from_initial_state_feed(html: str) -> Tuple[str, str]:
    """
    从 window.__INITIAL_STATE__ JSON中提取完整正文内容
    严格按照test4.py的逻辑实现
    """
    # 使用正则表达式提取JSON（与test4.py完全一致）
    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if not match:
        return "", ""
    
    try:
        data = json.loads(match.group(1))
        
        # 策略1：Feed页面 - prefetchData.contentData
        if 'prefetchData' in data and data['prefetchData']:
            content_data = data['prefetchData'].get('contentData', {})
            title = content_data.get('title', '')
            content = content_data.get('content', '')
            
            if content:
                # 清理Markdown和HTML标签（与test4.py一致）
                content = re.sub(r'!\[.*?\]\([^\)]+\)', '', content)  # 移除图片标记
                content = re.sub(r'<[^>]+>', '', content)  # 移除HTML标签
                content = re.sub(r'\n{3,}', '\n\n', content)  # 压缩多余换行
                
                return title.strip(), content.strip()
        
        # 策略2：Discuss页面 - postDetail
        if 'postDetail' in data and data['postDetail']:
            title = data['postDetail'].get('title', '')
            content = data['postDetail'].get('content', '')
            
            if content:
                content = re.sub(r'!\[.*?\]\([^\)]+\)', '', content)
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'\n{3,}', '\n\n', content)
                
                return title.strip(), content.strip()
    
    except Exception as e:
        logger.warning(f"解析__INITIAL_STATE__失败: {e}")
    
    return "", ""

def _extract_content_from_json(html: str) -> str:
    """从 JSON 块中提取正文（SPA 兜底）。用 HTML 解析取文本，不依赖关键词打分。"""
    blocks = _extract_json_scripts(html)
    candidates = []
    for j in blocks:
        for text in _dig_content_fields(j):
            if len(text) > 50:
                candidates.append(text)
    # 取最长的正文块（主帖通常最长），不用关键词打分
    if candidates:
        return max(candidates, key=len)
    return ""


def _resolve_feed_to_discuss(soup: BeautifulSoup, url: str) -> str:
    """
    feed 页面尝试解析出 discuss 链接，discuss 页面通常有完整服务端渲染正文。
    优先使用 canonical，避免误取侧栏推荐链接。
    """
    if "/feed/main/detail/" not in url:
        return url
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        h = canonical["href"].strip()
        if "/discuss/" in h:
            return h if h.startswith("http") else urljoin("https://www.nowcoder.com", h)
    return url


def _fetch_post_content_full_impl(
    html: str, soup: BeautifulSoup, url: str = ""
) -> Tuple[str, str, List[str]]:
    """
    按照test3.py的方式提取内容：使用BeautifulSoup模糊匹配class名称
    """
    title, body = "", ""
    
    # === 🎯 史诗级增强：精准定位正文容器（完全按照test3.py） ===
    # 牛客网的前端经常用带随机哈希的 class 名 (如 feed-content_1a2b3)
    # 我们用模糊匹配，只要 class 包含下面这些关键词，就把它抓出来！
    possible_classes = [
        'nc-post-content', 'post-topic-des', 'article-content',
        'feed-detail-content', 'post-detail', 'detail-content',
        'feed-content', 'post-detail-content-box'
    ]

    content_container = None
    for cls in possible_classes:
        # 模糊匹配 class 名称
        container = soup.find('div', class_=lambda c: c and cls in c)
        if container:
            content_container = container
            logger.debug(f"找到正文容器: class包含'{cls}'")
            break

    if not content_container:
        logger.warning(f"未能定位到正文内容: {url[:80]}")
        return "", "", []

    # 1. 提取完整的纯文本正文 (保留换行符)
    body = content_container.get_text(separator='\n', strip=True)
    
    # 2. 提取标题（从soup中查找）
    for tag, attrs in _TITLE_SELECTORS:
        el = soup.find(tag, attrs) if attrs else soup.find(tag)
        if el:
            t = el.get_text(strip=True)
            if t and len(t) < 200:
                title = t.replace("_牛客网", "").strip()
                break
    
    # 3. 提取图片
    image_urls = _collect_image_urls(soup, html) if body else []
    
    return title, body, image_urls
# 图片提取：与 test_nowcoder_fetch.py 完全一致（DOM + JSON/imgMoment）
_BASE_URL = "https://www.nowcoder.com"
_CONTENT_CLASSES_FOR_IMG = [
    "nc-post-content", "post-topic-des", "feed-detail-content",
    "detail-content", "content-body", "post-content", "feed-content-text", "feed-img",
]


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
    """判断是否为正文中的用户上传图片（排除表情、头像、UI 图标）"""
    if not src or not src.startswith("http") or src.startswith("data:"):
        return False
    if "static.nowcoder.com" in src:
        return False
    if img_tag and (img_tag.get("data-card-emoji") or img_tag.get("data-card-nowcoder")):
        return False
    style = (img_tag.get("style") or "").lower() if img_tag else ""
    if "18px" in style or "14px" in style or "12px" in style:
        if "width" in style or "height" in style:
            return False
    if "uploadfiles.nowcoder.com/images/20220815/" in src and "318889480" in src:
        return False
    return True


def _collect_content_blocks(obj, depth=0, max_depth=14) -> list:
    """收集 content 块及其父对象，返回 [(html, parent_obj), ...]。主帖图片在 imgMoment/contentImageUrls。"""
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


def _extract_images_from_html(html: str) -> List[str]:
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


def _extract_from_img_moment(parent: dict) -> List[str]:
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


def _dig_image_urls_from_main_post_only(obj, depth=0, max_depth=14) -> List[str]:
    """仅从主帖提取图片。主帖 = content 最长的块。图片来源：content HTML + imgMoment/contentImageUrls"""
    blocks = _collect_content_blocks(obj, depth, max_depth)
    if not blocks:
        return []
    main_block = max(blocks, key=lambda x: len(x[0]))
    html, parent = main_block[0], main_block[1]
    urls = _extract_images_from_html(html)
    urls.extend(_extract_from_img_moment(parent))
    return list(dict.fromkeys(urls))


def _collect_image_urls_from_dom(soup: BeautifulSoup) -> List[str]:
    """从 DOM 正文区域收集图片 URL，仅保留用户上传图（排除表情、UI）"""
    urls = []
    for cls in _CONTENT_CLASSES_FOR_IMG:
        div = soup.find("div", class_=lambda x: x and cls in str(x))
        if div:
            for img in div.find_all("img", src=True):
                src = img.get("src", "").strip()
                if src and not src.startswith("data:"):
                    u = src if src.startswith("http") else (
                        "https:" + src if src.startswith("//") else urljoin(_BASE_URL, src)
                    )
                    if _is_user_content_image(img, u) and u not in urls:
                        urls.append(u)
            if urls:
                return urls
    return urls


def _collect_image_urls_from_json(html: str) -> List[str]:
    """
    从 __INITIAL_STATE__ 中提取图片URL
    关键发现：用户上传的图片存储在 imgMoment 数组中，不在 content 文本里！
    """
    images = []
    
    # 查找 __INITIAL_STATE__ 的JSON数据（使用手动解析，避免正则匹配问题）
    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{)', html)
    if not match:
        return images
    
    # 手动解析JSON（处理未闭合的字符串）
    start = match.start(1)
    depth = 0
    i = start
    in_str = None
    escape = False
    
    while i < len(html) and i < start + 200000:  # 限制搜索范围
        c = html[i]
        
        if in_str:
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == in_str:
                in_str = None
            i += 1
            continue
        
        if c in ('"', "'"):
            in_str = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                json_str = html[start:i + 1]
                try:
                    data = json.loads(json_str)
                    
                    # feed页面：prefetchData.X.ssrCommonData.contentData.imgMoment
                    prefetch = data.get('prefetchData')
                    if prefetch:
                        # 如果是字典，转为列表
                        if isinstance(prefetch, dict):
                            prefetch = list(prefetch.values())
                        
                        # 遍历查找 contentData
                        if isinstance(prefetch, list):
                            for item in prefetch:
                                if not isinstance(item, dict):
                                    continue
                                
                                # 查找 ssrCommonData.contentData
                                ssr = item.get('ssrCommonData') or item.get('ssrData')
                                if isinstance(ssr, dict):
                                    content_data = ssr.get('contentData')
                                    if isinstance(content_data, dict):
                                        # 关键：从 imgMoment 数组提取图片
                                        img_moment = content_data.get('imgMoment', [])
                                        if isinstance(img_moment, list):
                                            for img_item in img_moment:
                                                if isinstance(img_item, dict):
                                                    src = img_item.get('src', '')
                                                    if src and _is_user_content_image_url(src):
                                                        images.append(src)
                                                elif isinstance(img_item, str) and _is_user_content_image_url(img_item):
                                                    images.append(img_item)
                    
                    # discuss页面：postDetail.imgMoment
                    if 'postDetail' in data and data['postDetail']:
                        post_detail = data['postDetail']
                        img_moment = post_detail.get('imgMoment', [])
                        if isinstance(img_moment, list):
                            for img_item in img_moment:
                                if isinstance(img_item, dict):
                                    src = img_item.get('src', '')
                                    if src and _is_user_content_image_url(src):
                                        images.append(src)
                                elif isinstance(img_item, str) and _is_user_content_image_url(img_item):
                                    images.append(img_item)
                
                except Exception as e:
                    logger.warning(f"解析__INITIAL_STATE__图片失败: {e}")
                break
        i += 1
    
    # 去重并过滤表情包
    unique_images = []
    seen = set()
    for img in images:
        if img not in seen and 'emoticon' not in img and img.startswith('http'):
            seen.add(img)
            unique_images.append(img)
    
    return unique_images


def _collect_image_urls(soup: BeautifulSoup, html: str) -> List[str]:
    """
    收集图片URL（整合DOM和JSON两种方式）
    优先使用JSON方式（test4.py验证可用），DOM方式作为兜底
    """
    # 优先使用JSON方式提取图片（test4.py中验证可用）
    images = _collect_image_urls_from_json(html)
    
    # 如果JSON方式没有提取到图片，尝试DOM方式
    if not images:
        images = _collect_image_urls_from_dom(soup)
    
    return images


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
        以 HTML 解析（DOM）为主，不依赖正则/关键词。
        feed 链接若 DOM 无正文，会尝试解析 discuss 链接并重新抓取。
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
            title, body, image_urls = _fetch_post_content_full_impl(html, soup, post_url)

            # feed 页面仍无正文时，尝试跳转到 discuss 获取完整服务端渲染内容
            if not body and "/feed/main/detail/" in post_url:
                discuss_url = _resolve_feed_to_discuss(soup, post_url)
                if discuss_url != post_url:
                    logger.info(f"feed 页面无正文，尝试 discuss 链接: {discuss_url[:60]}")
                    time.sleep(random.uniform(1, 2))
                    resp2 = self.session.get(discuss_url, timeout=20)
                    if resp2.status_code == 200:
                        html2 = resp2.text
                        soup2 = BeautifulSoup(html2, "html.parser")
                        title, body, image_urls = _fetch_post_content_full_impl(html2, soup2, discuss_url)

            if body:
                logger.info(f"牛客 详情页解析成功: {title[:30] or '(无标题)'}... ({len(body)}字, {len(image_urls)}图)")
            else:
                logger.warning(f"未识别到正文结构 [nowcoder]: {post_url[:80]}")

            return body, image_urls

        except Exception as e:
            logger.error(f"详情页解析异常 {post_url}: {e}")
            return "", []

    # ── 列表页发现（严格按参考 parse_list_page）──────────────────────────────

    def discover_page(self, keyword: str, page: int) -> List[Dict]:
        """
        爬取一页搜索结果，返回帖子元数据列表
        修复：统一使用POST API接口（参考test4.py的正确实现）
        """
        try:
            logger.debug(f"牛客 请求列表页: keyword={keyword!r}, page={page}")
            time.sleep(random.uniform(2, 4))
            self._update_headers()
            
            # 统一使用POST API接口（test4.py验证可用）
            return self._discover_page_ajax(keyword, page)
                
        except Exception as e:
            logger.error(f"列表页爬取失败 keyword={keyword!r} page={page}: {e}")
            return []
    

    def _discover_page_ajax(self, keyword: str, page: int) -> List[Dict]:
        """调用AJAX接口（使用POST请求，参考test4.py）"""
        from urllib.parse import quote
        current_timestamp = int(time.time() * 1000)
        api_url = f"https://gw-c.nowcoder.com/api/sparta/pc/search?_={current_timestamp}"
        
        payload = {
            "type": "all",
            "query": keyword,
            "page": page,
            "tag": [],
            "order": "",
            "gioParams": {
                "logid_var": "208c8a30-1a3b-11f1-9ba9-5947654d7ac0",
                "sessionID_var": "100_1772897667667_9590",
                "searchFrom_var": "历史搜索",
                "searchEnter_var": "主站"
            }
        }
        
        # 添加必要的headers（Referer中的中文需要URL编码）
        safe_keyword = quote(keyword)
        headers = self.session.headers.copy()
        headers.update({
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.nowcoder.com/search/all?query={safe_keyword}&type=all",
            "Origin": "https://www.nowcoder.com",
            "Accept": "application/json, text/plain, */*",
        })
        
        resp = self.session.post(api_url, json=payload, headers=headers, timeout=20)
        if resp.status_code != 200:
            logger.warning(f"AJAX接口请求失败 {resp.status_code} page={page}")
            return []
        
        try:
            data = resp.json()
            records = data.get("data", {}).get("records", [])
            
            if not records:
                logger.warning(f"第 {page} 页未找到数据")
                return []
            
            logger.debug(f"牛客 [{page}/20] 列表页发现: 本页 {len(records)} 条")
            
            return self._parse_records_from_json(records, keyword)
            
        except Exception as e:
            logger.error(f"解析AJAX响应失败: {e}")
            return []
    
    def _parse_records_from_json(self, records: List[Dict], keyword: str) -> List[Dict]:
        """解析JSON格式的帖子记录"""
        results = []
        
        for idx, rec in enumerate(records, 1):
            try:
                data = rec.get("data", {})
                moment = data.get("momentData", {})
                
                # 提取关键信息
                content_id = moment.get("id") or data.get("contentId")
                uuid = moment.get("uuid", "")
                title = moment.get("title", "")
                content = moment.get("content", "")
                
                if not content_id or not uuid:
                    continue
                
                # 构造详情页URL
                post_url = f"{self.BASE_URL}/feed/main/detail/{uuid}"
                
                # 提取用户信息
                user_brief = data.get("userBrief", {})
                author = user_brief.get("nickname", "匿名")
                
                # 提取时间（使用北京时间 UTC+8）
                created_at = moment.get("createdAt", 0)
                pub_time = timestamp_ms_to_beijing(created_at) if created_at else ""
                
                # 元数据分析
                full_text = f"{title} {content}"
                analysis = _extract_meta_info(title, full_text)
                
                results.append({
                    "title": title,
                    "source_url": post_url,
                    "source_platform": "nowcoder",
                    "company": analysis["company"],
                    "position": analysis["role"],
                    "business_line": analysis["business"],
                    "difficulty": analysis["difficulty"],
                    "post_type": analysis["post_type"],
                    "discover_keyword": keyword,
                })
                
                logger.debug(f"牛客 [{idx}/{len(records)}] 列表页发现: {title[:30]}... | {post_url}")
                
            except Exception as e:
                logger.warning(f"解析单条记录失败: {e}")
                continue
        
        logger.debug(f"牛客 keyword={keyword!r} 发现 {len(results)} 条")
        return results
    
    def _discover_page_dom_fallback(self, html: str, keyword: str, page: int) -> List[Dict]:
        """DOM解析兜底方案（当JSON解析失败时）"""
        soup = BeautifulSoup(html, "html.parser")
        
        # 定位帖子卡片（与参考一致：tw-bg-white + tw-mt-3 + tw-rounded-xl）
        post_cards = soup.find_all(
            "div",
            class_=lambda x: x and "tw-bg-white" in x and "tw-mt-3" in x and "tw-rounded-xl" in x,
        )
        if not post_cards:
            logger.info(f"第 {page} 页未找到数据（检查 Cookie 或是否末页）")
            return []

        results = []
        total = len(post_cards)
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

                # 核心：从整个卡片文本解析（与参考一致）
                full_card_text = card.get_text(separator=" ", strip=True)
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
                    "discover_keyword": keyword,
                })
                logger.info(
                    f"牛客 [{idx}/{total}] 列表页发现: {title[:30]}... | {post_url[:60]}"
                )
            except Exception as e:
                logger.warning(f"牛客 列表页解析单条出错 [{idx}/{total}]: {e}")
                continue

        logger.debug(f"牛客 keyword={keyword} page={page} 发现 {len(results)} 条")
        return results

    def discover(
        self,
        keywords: List[str] = None,
        max_pages: int = 3,
        check_db_dedup: bool = True,
        crawl_source: str = "未知",
    ) -> List[Dict]:
        """
        批量发现面经帖子。
        check_db_dedup=True 时对已爬取链接去重。
        crawl_source: 爬取来源标识，用于日志区分（如 "立即爬取"、"定时爬取"）
        """
        keywords = keywords or ["面经"]
        all_posts: List[Dict] = []
        seen_urls: set = set()
        skipped_db = 0

        db_check = None
        if check_db_dedup:
            try:
                from backend.services.storage.sqlite_service import sqlite_service
                db_check = sqlite_service.is_url_crawled
            except Exception:
                pass

        for kw in keywords:
            for page in range(1, max_pages + 1):
                posts = self.discover_page(kw, page)
                if not posts:
                    break
                new_in_page = 0
                for p in posts:
                    url = p["source_url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    new_in_page += 1
                    if db_check and db_check(url):
                        skipped_db += 1
                        continue
                    all_posts.append(p)
                if new_in_page == 0:
                    logger.info(f"[牛客{crawl_source}] keyword={kw!r} page={page} 无新链接（全部重复），提前终止翻页")
                    break
            time.sleep(random.uniform(1, 2))

        if skipped_db:
            logger.info(f"[牛客{crawl_source}] 去重：数据库已有 {skipped_db} 条，本次新增 {len(all_posts)} 条")
        return all_posts
