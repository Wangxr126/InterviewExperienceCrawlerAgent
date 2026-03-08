"""
调试牛客网图片提取 - 分析HTML结构找出图片位置
"""
import requests
import json
import re
from bs4 import BeautifulSoup
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_page_structure(url: str):
    """分析页面结构，找出图片在哪里"""
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.nowcoder.com/"
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    
    print("=" * 80)
    print(f"分析页面: {url}")
    print("=" * 80)
    
    # 1. 查找所有img标签
    print("\n【1. 页面中的所有 <img> 标签】")
    all_imgs = soup.find_all('img')
    print(f"找到 {len(all_imgs)} 个 <img> 标签")
    
    for idx, img in enumerate(all_imgs[:10], 1):  # 只显示前10个
        src = img.get('src', '')
        alt = img.get('alt', '')
        class_name = img.get('class', [])
        print(f"\n  {idx}. src: {src[:100]}")
        print(f"     alt: {alt}")
        print(f"     class: {class_name}")
    
    # 2. 查找 __INITIAL_STATE__
    print("\n\n【2. 查找 __INITIAL_STATE__ JSON数据】")
    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{)', html)
    if match:
        print("[OK] 找到 __INITIAL_STATE__")
        
        # 尝试提取完整JSON
        start = match.start(1)
        depth = 0
        i = start
        in_str = None
        escape = False
        
        while i < len(html) and i < start + 100000:  # 限制搜索范围
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
                        print(f"[OK] 成功解析JSON，大小: {len(json_str)} 字符")
                        
                        # 查找图片相关字段
                        print("\n【3. JSON中的图片相关字段】")
                        find_image_fields(data, path="root")
                        
                    except json.JSONDecodeError as e:
                        print(f"[ERROR] JSON解析失败: {e}")
                    break
            i += 1
    else:
        print("[ERROR] 未找到 __INITIAL_STATE__")
    
    # 3. 查找正文容器
    print("\n\n【4. 查找正文容器】")
    content_classes = [
        'nc-post-content', 'post-topic-des', 'feed-detail-content',
        'detail-content', 'feed-content', 'post-detail-content-box'
    ]
    
    for cls in content_classes:
        container = soup.find('div', class_=lambda c: c and cls in c)
        if container:
            print(f"[OK] 找到容器: class包含'{cls}'")
            
            # 查找容器内的图片
            imgs_in_container = container.find_all('img')
            print(f"   容器内有 {len(imgs_in_container)} 个 <img> 标签")
            
            for idx, img in enumerate(imgs_in_container[:5], 1):
                src = img.get('src', '')
                print(f"   {idx}. {src[:80]}")
            break

def find_image_fields(obj, path="", depth=0, max_depth=10):
    """递归查找JSON中的图片字段"""
    if depth > max_depth:
        return
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{path}.{key}" if path else key
            
            # 检查是否是图片相关字段
            if any(keyword in key.lower() for keyword in ['img', 'image', 'pic', 'photo', 'url']):
                if isinstance(value, str) and ('http' in value or 'uploadfiles' in value):
                    print(f"  [IMG] {current_path}: {value[:100]}")
                elif isinstance(value, list) and value:
                    print(f"  [IMG] {current_path}: [数组，{len(value)}项]")
                    if isinstance(value[0], str):
                        print(f"     示例: {value[0][:100]}")
            
            # 递归搜索
            find_image_fields(value, current_path, depth + 1, max_depth)
    
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            current_path = f"{path}[{idx}]"
            find_image_fields(item, current_path, depth + 1, max_depth)

if __name__ == "__main__":
    # 测试URL - 使用一个已知包含图片的帖子
    test_urls = [
        "https://www.nowcoder.com/feed/main/detail/0c5e0c0e8e8e4b0a9b0a0b0a0b0a0b0a",  # 示例URL
        "https://www.nowcoder.com/discuss/658285588870144000",  # discuss页面示例
    ]
    
    print("请输入要分析的牛客帖子URL（或直接回车使用默认URL）:")
    user_input = input().strip()
    
    if user_input:
        analyze_page_structure(user_input)
    else:
        print("使用默认URL进行测试...")
        # 先搜索一个真实的帖子
        from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
        crawler = NowcoderCrawler()
        
        posts = crawler.discover_page("面经", 1)
        if posts:
            test_url = posts[0]["source_url"]
            print(f"使用第一个搜索结果: {test_url}\n")
            analyze_page_structure(test_url)
        else:
            print("未找到测试帖子")
