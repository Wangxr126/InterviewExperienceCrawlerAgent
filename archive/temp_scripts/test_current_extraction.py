"""
测试当前的提取逻辑是否能正确提取完整内容
"""
import sys
sys.path.insert(0, 'backend')

from services.crawler.nowcoder_crawler import NowcoderCrawler
from pathlib import Path

# 读取Cookie
cookie = ""
env_path = Path('.env')
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('NOWCODER_COOKIE='):
                cookie = line.split('=', 1)[1].strip().strip('"').strip("'")
                break

if not cookie:
    print('[ERROR] 未找到NOWCODER_COOKIE')
    exit(1)

print(f'[OK] Cookie长度: {len(cookie)}')

# 测试几个真实的帖子
test_urls = [
    'https://www.nowcoder.com/feed/main/detail/26校招京东外卖ai产品 面经',
    'https://www.nowcoder.com/feed/main/detail/阿里巴巴大模型Agent校招面经',
]

crawler = NowcoderCrawler(cookie=cookie)

for url in test_urls:
    print(f'\n{"="*80}')
    print(f'测试URL: {url}')
    print(f'{"="*80}')
    
    try:
        content, images = crawler.fetch_post_content_full(url)
        
        print(f'\n提取结果:')
        print(f'- 内容长度: {len(content)} 字符')
        print(f'- 图片数量: {len(images)}')
        print(f'\n内容前500字:')
        print(content[:500])
        print(f'\n内容是否完整:')
        print(f'- 包含"面试": {"面试" in content}')
        print(f'- 包含"问了": {"问了" in content}')
        print(f'- 长度>500: {len(content) > 500}')
        
        if len(content) < 200:
            print(f'\n⚠️ 警告：内容过短，可能提取失败！')
        elif len(content) == 167:
            print(f'\n❌ 错误：内容正好167字符，说明被截断了！')
        else:
            print(f'\n✅ 内容长度正常')
            
    except Exception as e:
        print(f'\n❌ 提取失败: {e}')
        import traceback
        traceback.print_exc()
