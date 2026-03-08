#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 scheduler.py 导入问题"""

import sys

def fix_scheduler():
    file_path = r'e:\Agent\AgentProject\wxr_agent\backend\services\scheduler.py'
    
    # 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经有 scheduler 别名
    if 'scheduler = crawl_scheduler' in content:
        print("[OK] scheduler alias already exists")
        return
    
    # 替换
    old_text = 'crawl_scheduler = CrawlScheduler()'
    new_text = '''crawl_scheduler = CrawlScheduler()
# 为了兼容性，提供别名
scheduler = crawl_scheduler'''
    
    if old_text in content:
        content = content.replace(old_text, new_text)
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("[OK] Successfully added scheduler alias")
    else:
        print("[ERROR] Could not find 'crawl_scheduler = CrawlScheduler()' line")
        sys.exit(1)

if __name__ == '__main__':
    fix_scheduler()
