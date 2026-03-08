#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""添加小红书定时任务到 scheduler.py"""

def add_xhs_scheduler():
    file_path = r'e:\Agent\AgentProject\wxr_agent\backend\services\scheduler.py'
    
    # 读取文件
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经有小红书定时任务
    if 'id="xhs_discovery"' in content:
        print("[OK] XHS scheduler already exists")
        return
    
    # 查找插入位置（在牛客任务之后，任务处理器之前）
    marker = '            )\n\n        # ── 任务处理器（cron 分钟从 .env 读取）────────────────'
    
    if marker not in content:
        print("[ERROR] Could not find insertion point")
        return
    
    # 要插入的代码
    xhs_code = '''            )

        # ── 小红书发现任务（每天凌晨3点）──────────────────────
        if cfg.ENABLE_XHS:
            self._scheduler.add_job(
                _run_xhs_discovery,
                CronTrigger(hour=3, minute=0),
                id="xhs_discovery",
                name="小红书面经发现",
                replace_existing=True,
                misfire_grace_time=3600,
            )

        # ── 任务处理器（cron 分钟从 .env 读取）────────────────'''
    
    # 替换
    content = content.replace(marker, xhs_code)
    
    # 写回文件
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("[OK] Successfully added XHS scheduler")

if __name__ == '__main__':
    add_xhs_scheduler()
