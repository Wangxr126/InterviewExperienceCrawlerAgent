"""
下载一个真实页面的HTML，分析正文容器的class名称
"""
import requests
from bs4 import BeautifulSoup
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

url = 'https://www.nowcoder.com/feed/main/detail/26校招京东外卖ai产品 面经'

headers = {
    'Cookie': cookie,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

print(f'正在下载: {url}')
resp = requests.get(url, headers=headers, timeout=20)

if resp.status_code != 200:
    print(f'请求失败: {resp.status_code}')
    exit(1)

html = resp.text

# 保存HTML
with open('debug_page.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'HTML已保存到 debug_page.html ({len(html)} 字符)')

# 分析所有div的class
soup = BeautifulSoup(html, 'html.parser')

print('\n=== 查找包含大量文本的div ===')
all_divs = soup.find_all('div')
text_divs = []

for div in all_divs:
    text = div.get_text(strip=True)
    if len(text) > 200:
        classes = div.get('class', [])
        text_divs.append((len(text), classes, text[:100]))

# 按文本长度排序
text_divs.sort(reverse=True)

print(f'\n找到 {len(text_divs)} 个包含大量文本的div')
print('\n前10个（按文本长度）:')
for i, (length, classes, preview) in enumerate(text_divs[:10], 1):
    print(f'\n[{i}] 长度: {length} 字符')
    print(f'    Class: {classes}')
    print(f'    预览: {preview}...')
