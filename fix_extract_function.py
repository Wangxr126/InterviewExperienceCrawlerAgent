"""
严格按照test4.py的逻辑重写_extract_content_from_initial_state_feed函数
"""

with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 新的函数实现（完全按照test4.py）
new_function = '''def _extract_content_from_initial_state_feed(html: str) -> Tuple[str, str]:
    """
    从 window.__INITIAL_STATE__ JSON中提取完整正文内容
    严格按照test4.py的逻辑实现
    """
    # 使用正则表达式提取JSON（与test4.py完全一致）
    match = re.search(r'window\\.__INITIAL_STATE__\\s*=\\s*(\\{.*?\\});', html, re.DOTALL)
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
                content = re.sub(r'!\\[.*?\\]\\([^\\)]+\\)', '', content)  # 移除图片标记
                content = re.sub(r'<[^>]+>', '', content)  # 移除HTML标签
                content = re.sub(r'\\n{3,}', '\\n\\n', content)  # 压缩多余换行
                
                return title.strip(), content.strip()
        
        # 策略2：Discuss页面 - postDetail
        if 'postDetail' in data and data['postDetail']:
            title = data['postDetail'].get('title', '')
            content = data['postDetail'].get('content', '')
            
            if content:
                content = re.sub(r'!\\[.*?\\]\\([^\\)]+\\)', '', content)
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'\\n{3,}', '\\n\\n', content)
                
                return title.strip(), content.strip()
    
    except Exception as e:
        logger.warning(f"解析__INITIAL_STATE__失败: {e}")
    
    return "", ""'''

# 找到函数并替换
import re

# 匹配整个函数（从def到下一个def或文件末尾）
pattern = r'def _extract_content_from_initial_state_feed\(html: str\) -> Tuple\[str, str\]:.*?(?=\ndef )'
match = re.search(pattern, content, re.DOTALL)

if match:
    old_function = match.group(0)
    content = content.replace(old_function, new_function + '\n')
    
    with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print('[OK] 已按照test4.py重写_extract_content_from_initial_state_feed函数！')
    print('')
    print('关键改进：')
    print('1. 使用正则表达式直接提取JSON（与test4.py一致）')
    print('2. 简化了JSON解析逻辑')
    print('3. 移除了手动字符串解析的复杂代码')
    print('4. 完全对齐test4.py的成功实现')
else:
    print('[ERROR] 未找到目标函数')
