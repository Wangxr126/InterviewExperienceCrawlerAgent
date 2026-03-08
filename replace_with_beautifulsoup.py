import re
from typing import Tuple

def _extract_content_from_dom(html: str) -> Tuple[str, str]:
    """
    从HTML DOM中提取完整正文内容（使用BeautifulSoup，参考text3.py）
    这是最可靠的方法，直接从渲染的HTML中提取，不依赖可能被截断的JSON
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("需要安装 beautifulsoup4: pip install beautifulsoup4")
        return "", ""
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # 提取标题
    title = ""
    title_tag = soup.find('h1') or soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
    
    # 精准定位正文容器（参考text3.py的策略）
    possible_classes = [
        'nc-post-content', 'post-topic-des', 'article-content',
        'feed-detail-content', 'post-detail', 'detail-content',
        'feed-content', 'post-detail-content-box', 'nc-post-topic-des'
    ]
    
    content_container = None
    for cls in possible_classes:
        # 模糊匹配 class 名称（因为牛客用随机哈希）
        container = soup.find('div', class_=lambda c: c and cls in c)
        if container:
            content_container = container
            break
    
    if not content_container:
        # 如果找不到特定容器，尝试查找包含大量文本的div
        all_divs = soup.find_all('div')
        for div in all_divs:
            text = div.get_text(strip=True)
            if len(text) > 200:  # 正文通常很长
                content_container = div
                break
    
    if not content_container:
        return title, ""
    
    # 提取完整的纯文本正文（保留换行符）
    clean_text = content_container.get_text(separator='\n', strip=True)
    
    # 清理多余的空行
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
    
    return title.strip(), clean_text.strip()


# 测试代码
if __name__ == "__main__":
    # 读取生产代码中的HTML
    with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找并替换函数
    old_func_start = 'def _extract_content_from_initial_state_feed(html: str) -> Tuple[str, str]:'
    old_func_end = '    return "", ""'
    
    # 找到函数的结束位置（下一个def或文件末尾）
    start_idx = content.find(old_func_start)
    if start_idx == -1:
        print('[ERROR] 未找到目标函数')
        exit(1)
    
    # 找到下一个函数定义
    next_def = content.find('\ndef ', start_idx + 1)
    if next_def == -1:
        next_def = len(content)
    
    old_function = content[start_idx:next_def]
    
    new_function = '''def _extract_content_from_initial_state_feed(html: str) -> Tuple[str, str]:
    """
    从HTML DOM中提取完整正文内容（使用BeautifulSoup，参考text3.py）
    这是最可靠的方法，直接从渲染的HTML中提取，不依赖可能被截断的JSON
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("需要安装 beautifulsoup4: pip install beautifulsoup4")
        return "", ""
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # 提取标题
    title = ""
    title_tag = soup.find('h1') or soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        # 移除"_牛客网"等后缀
        for suffix in ["_牛客网", " - 牛客网", "_牛客在手,offer到手"]:
            if suffix in title:
                title = title.split(suffix)[0].strip()
    
    # 精准定位正文容器（参考text3.py的策略）
    possible_classes = [
        'nc-post-content', 'post-topic-des', 'article-content',
        'feed-detail-content', 'post-detail', 'detail-content',
        'feed-content', 'post-detail-content-box', 'nc-post-topic-des'
    ]
    
    content_container = None
    for cls in possible_classes:
        # 模糊匹配 class 名称（因为牛客用随机哈希）
        container = soup.find('div', class_=lambda c: c and cls in c)
        if container:
            content_container = container
            break
    
    if not content_container:
        # 如果找不到特定容器，尝试查找包含大量文本的div
        all_divs = soup.find_all('div')
        for div in all_divs:
            text = div.get_text(strip=True)
            if len(text) > 200:  # 正文通常很长
                content_container = div
                break
    
    if not content_container:
        return title, ""
    
    # 提取完整的纯文本正文（保留换行符）
    clean_text = content_container.get_text(separator='\\n', strip=True)
    
    # 清理多余的空行
    clean_text = re.sub(r'\\n{3,}', '\\n\\n', clean_text)
    
    return title.strip(), clean_text.strip()

'''
    
    new_content = content.replace(old_function, new_function)
    
    with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print('[OK] 已替换为BeautifulSoup DOM提取方法！')
    print('')
    print('关键改进：')
    print('1. 不再依赖JSON中可能被截断的content字段')
    print('2. 直接从HTML DOM中提取完整正文')
    print('3. 使用text3.py的策略：模糊匹配class名称')
    print('4. 支持多种正文容器class')
    print('5. 自动清理标题后缀')
