"""
完全按照test3.py重写_fetch_post_content_full_impl函数
使用BeautifulSoup模糊匹配class名称
"""

with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到_fetch_post_content_full_impl函数并替换
import re

# 新的实现（完全按照test3.py）
new_impl = '''def _fetch_post_content_full_impl(
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
            logger.info(f"找到正文容器: class包含'{cls}'")
            break

    if not content_container:
        logger.warning(f"未能定位到正文内容: {url[:80]}")
        return "", "", []

    # 1. 提取完整的纯文本正文 (保留换行符)
    body = content_container.get_text(separator='\\n', strip=True)
    
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
    
    return title, body, image_urls'''

# 使用正则替换整个函数
pattern = r'def _fetch_post_content_full_impl\([^)]+\)[^:]+:.*?(?=\n(?:def |# |_BASE_URL))'
match = re.search(pattern, content, re.DOTALL)

if match:
    content = content.replace(match.group(0), new_impl)
    
    with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已按照test3.py重写_fetch_post_content_full_impl！')
    print('')
    print('关键改进：')
    print('1. 使用BeautifulSoup模糊匹配class名称')
    print('2. 支持带随机哈希的class (如 feed-content_1a2b3)')
    print('3. 完全按照test3.py的逻辑实现')
    print('4. 移除了四级提取策略，直接用DOM提取')
else:
    print('[ERROR] 未找到目标函数')
