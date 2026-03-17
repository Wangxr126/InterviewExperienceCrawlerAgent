"""
测试牛客爬虫的内容提取
"""
import sys
sys.path.insert(0, '.')

from backend.services.crawler.nowcoder_crawler import NowcoderCrawler
from backend.config.config import settings

# 测试URL（从图片中看到的）
test_urls = [
    "https://www.nowcoder.com/feed/main/detail/26校招京东外卖ai产品 面经",
    "https://www.nowcoder.com/feed/main/detail/某团Agent面经-日常实习",
]

print('=== 测试牛客爬虫内容提取 ===\n')

# 需要Cookie
cookie = settings.nowcoder_cookie or input('请输入NOWCODER_COOKIE: ')

crawler = NowcoderCrawler(cookie=cookie)

for url in test_urls:
    print(f'\n测试URL: {url}')
    print('-' * 100)
    
    try:
        content, images = crawler.fetch_post_content_full(url)
        
        print(f'✓ 提取成功')
        print(f'  内容长度: {len(content)} 字符')
        print(f'  图片数量: {len(images)}')
        print(f'  内容预览（前500字）:')
        print(f'  {content[:500]}')
        print()
        
        if len(content) < 200:
            print('  ⚠️ 警告：内容过短，可能提取失败！')
        
    except Exception as e:
        print(f'✗ 提取失败: {e}')
        import traceback
        traceback.print_exc()

print('\n=== 测试完成 ===')
print('\n建议：')
print('1. 如果内容过短，检查DOM选择器是否正确')
print('2. 如果提取失败，检查Cookie是否有效')
print('3. 查看日志中的详细错误信息')
