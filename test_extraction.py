import sys
import os
sys.path.insert(0, '思路/爬虫工具/牛客测试3月8日')

# 设置环境变量
from pathlib import Path
env_path = Path('思路/.env')
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('NOWCODER_COOKIE='):
                cookie = line.split('=', 1)[1].strip().strip('"').strip("'")
                os.environ['NOWCODER_COOKIE'] = cookie
                break

from test4 import get_detail_page_content

# 测试一个真实的牛客链接
test_url = 'https://www.nowcoder.com/feed/main/detail/0f8b5e5e5e5e5e5e'
headers = {
    'Cookie': os.environ.get('NOWCODER_COOKIE', ''),
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

print(f'测试链接: {test_url}')
print(f'Cookie长度: {len(headers["Cookie"])}')

content, images = get_detail_page_content(test_url, headers)

print(f'\n=== 提取结果 ===')
print(f'内容长度: {len(content)} 字符')
print(f'图片数量: {len(images)}')
print(f'\n=== 内容前800字 ===')
print(content[:800])
print(f'\n=== 内容是否包含关键词 ===')
print(f'包含"面试": {"面试" in content}')
print(f'包含"问了": {"问了" in content}')
print(f'包含"算法": {"算法" in content}')
