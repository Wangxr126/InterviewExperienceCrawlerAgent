"""
修复：恢复_extract_content_from_initial_state_feed为JSON提取
并确保_extract_content_from_dom使用text3.py的选择器
"""

# 正确的_extract_content_from_initial_state_feed（从JSON提取）
correct_json_function = '''def _extract_content_from_initial_state_feed(html: str) -> Tuple[str, str]:
    """
    从 window.__INITIAL_STATE__ JSON中提取完整正文内容
    """
    m = re.search(r"window\\.__INITIAL_STATE__\\s*=\\s*(\\{)", html)
    if not m:
        return "", ""
    start = m.start(1)
    depth, i, in_str, escape = 0, start, None, False
    while i < len(html):
        c = html[i]
        if in_str:
            escape = c == "\\\\" and not escape
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
                content = re.sub(r'!\\[.*?\\]\\([^\\)]+\\)', '', content)
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'\\n{3,}', '\\n\\n', content)
                return title.strip(), content.strip()

    # 策略2：Discuss页面 - postDetail
    post_detail = d.get("postDetail")
    if isinstance(post_detail, dict):
        title = post_detail.get("title", "")
        content = post_detail.get("content", "")
        if content and len(content) > 50:
            content = re.sub(r'!\\[.*?\\]\\([^\\)]+\\)', '', content)
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'\\n{3,}', '\\n\\n', content)
            return title.strip(), content.strip()

    return "", ""
'''

# 读取文件
with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到并替换_extract_content_from_initial_state_feed函数
import re as regex

# 找到函数开始
pattern = r'def _extract_content_from_initial_state_feed\(html: str\) -> Tuple\[str, str\]:.*?(?=\ndef )'
match = regex.search(pattern, content, regex.DOTALL)

if match:
    old_function = match.group(0)
    content = content.replace(old_function, correct_json_function + '\n')
    
    with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已恢复_extract_content_from_initial_state_feed为JSON提取！')
    print('')
    print('关键修复：')
    print('1. 恢复从window.__INITIAL_STATE__ JSON提取')
    print('2. 支持prefetchData.contentData（Feed页面）')
    print('3. 支持postDetail（Discuss页面）')
    print('4. _extract_content_from_dom保持不变（已有正确的选择器）')
else:
    print('[ERROR] 未找到目标函数')
