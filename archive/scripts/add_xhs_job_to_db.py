#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在数据库中添加小红书定时任务"""

import sys
sys.path.insert(0, r'e:\Agent\AgentProject\wxr_agent')

from backend.services.scheduler_service import scheduler_service

def add_xhs_job():
    """添加小红书定时任务到数据库"""
    
    # 检查是否已存在小红书任务
    jobs = scheduler_service.list_jobs()
    for job in jobs:
        if job['job_type'] == 'xhs_discovery':
            print(f"[INFO] XHS job already exists: {job['job_name']} (ID: {job['job_id']})")
            return
    
    # 创建小红书任务配置
    xhs_job_config = {
        "job_name": "小红书面经发现",
        "job_type": "xhs_discovery",
        "schedule_type": "cron",
        "schedule_config": {
            "hour": "3",
            "minute": "0"
        },
        "job_params": {
            "xhs_keywords": ["agent面经"],
            "xhs_max_notes": 5,
            "xhs_headless": True
        },
        "enabled": True,
        "description": "每天凌晨3点从小红书搜索并发现新的面经帖子"
    }
    
    # 添加到数据库
    job_id = scheduler_service.add_job(xhs_job_config)
    print(f"[OK] Successfully added XHS job: {job_id}")
    print(f"     Name: {xhs_job_config['job_name']}")
    print(f"     Schedule: Every day at 3:00 AM")
    print(f"     Keywords: {xhs_job_config['job_params']['xhs_keywords']}")

if __name__ == '__main__':
    add_xhs_job()
