#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""添加缺失的 _collect_image_urls 函数"""

import sys
import io

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 读取文件
with open('backend/services/crawler/nowcoder_crawler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 _collect_image_urls_from_json 函数的结束位置
# 在它之后添加 _collect_image_urls 函数

insert_marker = '''    return unique_images


# ══════════════════════════════════════════════════════════════
# 元数据提取（规则匹配）
# ══════════════════════════════════════════════════════════════'''

new_function = '''    return unique_images


def _collect_image_urls(soup: BeautifulSoup, html: str) -> List[str]:
    """
    收集图片URL（整合DOM和JSON两种方式）
    优先使用JSON方式（test4.py验证可用），DOM方式作为兜底
    """
    # 优先使用JSON方式提取图片（test4.py中验证可用）
    images = _collect_image_urls_from_json(html)
    
    # 如果JSON方式没有提取到图片，尝试DOM方式
    if not images:
        images = _collect_image_urls_from_dom(soup)
    
    return images


# ══════════════════════════════════════════════════════════════
# 元数据提取（规则匹配）
# ══════════════════════════════════════════════════════════════'''

if insert_marker in content:
    content = content.replace(insert_marker, new_function)
    print("[OK] 成功添加 _collect_image_urls 函数")
else:
    print("[ERROR] 未找到插入位置")
    print("尝试查找其他标记...")

# 写回文件
with open('backend/services/crawler/nowcoder_crawler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("\n[OK] 修复完成！")
print("添加了 _collect_image_urls 函数，整合DOM和JSON两种图片提取方式")
