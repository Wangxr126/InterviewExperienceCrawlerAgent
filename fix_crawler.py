import re
import sys
import io

# 设置输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 新函数内容
new_func = r'''def _extract_content_from_initial_state_feed(html: str) -> Tuple[str, str]:
    """
    从 __INITIAL_STATE__ 提取完整正文内容（不截断）。
    支持两种页面：
    1. Feed页面：prefetchData.contentData.content
    2. Discuss页面：postDetail.content
    """
    m = re.search(r"__INITIAL_STATE__\s*=\s*(\{)", html)
    if not m:
        return "", ""
    start = m.start(1)
    depth, i, in_str, escape = 0, start, None, False
    while i < len(html):
        c = html[i]
        if in_str:
            escape = c == "\\" and not escape
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
                    d = json.loads(html[start : i + 1])
                except json.JSONDecodeError:
                    return "", ""
                break
        i += 1
    else:
        return "", ""

    # 策略1：Feed页面 - prefetchData.contentData
    prefetch = d.get("prefetchData")
    if isinstance(prefetch, dict):
        content_data = prefetch.get("contentData", {})
        if isinstance(content_data, dict):
            title = content_data.get("title", "")
            content = content_data.get("content", "")
            if content and len(content) > 50:
                # 清理Markdown图片标记和HTML标签
                content = re.sub(r'!\[.*?\]\([^\)]+\)', '', content)
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'\n{3,}', '\n\n', content)
                return title.strip(), content.strip()
    
    # 策略2：Discuss页面 - postDetail.content
    post_detail = d.get("postDetail")
    if isinstance(post_detail, dict):
        title = post_detail.get("title", "")
        content = post_detail.get("content", "")
        if content and len(content) > 50:
            content = re.sub(r'!\[.*?\]\([^\)]+\)', '', content)
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'\n{3,}', '\n\n', content)
            return title.strip(), content.strip()
    
    return "", ""
'''

# 找到并替换函数
start_pattern = r'def _extract_content_from_initial_state_feed\(html: str\) -> Tuple\[str, str\]:'
end_pattern = r'\n\ndef _extract_content_from_json'

match_start = re.search(start_pattern, content)
match_end = re.search(end_pattern, content)

if match_start and match_end:
    new_content = content[:match_start.start()] + new_func + content[match_end.start():]
    
    with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print('[OK] 函数已成功替换！')
    print('')
    print('修改内容：')
    print('1. 直接从 prefetchData.contentData 提取（不再经过 ssrCommonData）')
    print('2. 新增支持 discuss 页面的 postDetail.content')
    print('3. 清理 Markdown 和 HTML 标签，确保提取完整正文')
    print('')
    print('现在爬虫应该能够提取完整的正文内容，不再有字数限制！')
else:
    print('[ERROR] 未找到函数')
