"""
修复牛客图片提取函数
将 _collect_image_urls_from_json 函数替换为正确的实现
"""
import re

# 读取文件
with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到函数开始和结束位置
start_line = None
end_line = None
in_function = False
indent_level = None

for i, line in enumerate(lines):
    if 'def _collect_image_urls_from_json(html: str) -> List[str]:' in line:
        start_line = i
        in_function = True
        indent_level = len(line) - len(line.lstrip())
        continue
    
    if in_function and line.strip() and not line.strip().startswith('#'):
        current_indent = len(line) - len(line.lstrip())
        # 如果遇到同级或更低级别的def，说明函数结束
        if current_indent == indent_level and line.strip().startswith('def '):
            end_line = i
            break

if start_line is None:
    print("❌ 未找到函数")
    exit(1)

if end_line is None:
    print("❌ 未找到函数结束位置")
    exit(1)

print(f"找到函数: 第 {start_line + 1} 行到第 {end_line} 行")

# 新的函数实现
new_function_lines = '''def _collect_image_urls_from_json(html: str) -> List[str]:
    """
    从 __INITIAL_STATE__ 中提取图片URL
    关键发现：用户上传的图片存储在 imgMoment 数组中，不在 content 文本里！
    """
    images = []
    
    # 查找 __INITIAL_STATE__ 的JSON数据（使用手动解析，避免正则匹配问题）
    match = re.search(r'window\\.__INITIAL_STATE__\\s*=\\s*(\\{)', html)
    if not match:
        return images
    
    # 手动解析JSON（处理未闭合的字符串）
    start = match.start(1)
    depth = 0
    i = start
    in_str = None
    escape = False
    
    while i < len(html) and i < start + 200000:  # 限制搜索范围
        c = html[i]
        
        if in_str:
            if escape:
                escape = False
            elif c == '\\\\':
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
                    
                    # feed页面：prefetchData.X.ssrCommonData.contentData.imgMoment
                    prefetch = data.get('prefetchData')
                    if prefetch:
                        # 如果是字典，转为列表
                        if isinstance(prefetch, dict):
                            prefetch = list(prefetch.values())
                        
                        # 遍历查找 contentData
                        if isinstance(prefetch, list):
                            for item in prefetch:
                                if not isinstance(item, dict):
                                    continue
                                
                                # 查找 ssrCommonData.contentData
                                ssr = item.get('ssrCommonData') or item.get('ssrData')
                                if isinstance(ssr, dict):
                                    content_data = ssr.get('contentData')
                                    if isinstance(content_data, dict):
                                        # 关键：从 imgMoment 数组提取图片
                                        img_moment = content_data.get('imgMoment', [])
                                        if isinstance(img_moment, list):
                                            for img_item in img_moment:
                                                if isinstance(img_item, dict):
                                                    src = img_item.get('src', '')
                                                    if src and _is_user_content_image_url(src):
                                                        images.append(src)
                                                elif isinstance(img_item, str) and _is_user_content_image_url(img_item):
                                                    images.append(img_item)
                    
                    # discuss页面：postDetail.imgMoment
                    if 'postDetail' in data and data['postDetail']:
                        post_detail = data['postDetail']
                        img_moment = post_detail.get('imgMoment', [])
                        if isinstance(img_moment, list):
                            for img_item in img_moment:
                                if isinstance(img_item, dict):
                                    src = img_item.get('src', '')
                                    if src and _is_user_content_image_url(src):
                                        images.append(src)
                                elif isinstance(img_item, str) and _is_user_content_image_url(img_item):
                                    images.append(img_item)
                
                except Exception as e:
                    logger.warning(f"解析__INITIAL_STATE__图片失败: {e}")
                break
        i += 1
    
    # 去重并过滤表情包
    unique_images = []
    seen = set()
    for img in images:
        if img not in seen and 'emoticon' not in img and img.startswith('http'):
            seen.add(img)
            unique_images.append(img)
    
    return unique_images

'''.split('\n')

# 替换函数
new_lines = lines[:start_line] + [line + '\n' for line in new_function_lines] + lines[end_line:]

# 写回文件
with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("✅ 函数替换成功！")
print(f"删除了 {end_line - start_line} 行旧代码")
print(f"添加了 {len(new_function_lines)} 行新代码")
