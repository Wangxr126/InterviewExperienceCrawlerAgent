"""
配置迁移脚本：将 .env 中的调度器配置迁移到数据库
运行：python -m backend.scripts.migrate_scheduler_config
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.config.config import settings
from backend.services.scheduler_service import scheduler_service


def migrate_config():
    """迁移 .env 配置到数据库"""
    print("[INFO] 开始迁移调度器配置...")
    
    migrated_count = 0
    
    # ========== 1. 迁移牛客定时任务 ==========
    if settings.scheduler_enable_nowcoder:
        print("\n[INFO] 迁移牛客定时任务...")
        
        job_config = {
            "job_name": "牛客面经定时爬取",
            "job_type": "nowcoder_discovery",
            "schedule_type": "cron",
            "schedule_config": {
                "hour": settings.scheduler_nowcoder_hours,
                "minute": "0"
            },
            "job_params": {
                "keywords": settings.nowcoder_keywords,
                "max_pages": settings.nowcoder_max_pages
            },
            "enabled": True,
            "description": f"从 .env 迁移：每天 {settings.scheduler_nowcoder_hours.replace(',', '/')} 点爬取牛客面经"
        }
        
        job_id = scheduler_service.add_job(job_config)
        print(f"   [OK] 已创建任务：{job_config['job_name']} (ID: {job_id})")
        migrated_count += 1
    else:
        print("\n[SKIP] 跳过牛客任务（SCHEDULER_ENABLE_NOWCODER=false）")
    
    # ========== 2. 迁移小红书定时任务 ==========
    if settings.scheduler_enable_xhs:
        print("\n[INFO] 迁移小红书定时任务...")
        
        job_config = {
            "job_name": "小红书面经定时爬取",
            "job_type": "xhs_discovery",
            "schedule_type": "cron",
            "schedule_config": {
                "hour": "3",
                "minute": "0"
            },
            "job_params": {
                "keywords": settings.xhs_keywords,
                "max_notes_per_keyword": settings.xhs_max_notes_per_keyword,
                "headless": True
            },
            "enabled": True,
            "description": "从 .env 迁移：每天 3 点爬取小红书面经（需已登录）"
        }
        
        job_id = scheduler_service.add_job(job_config)
        print(f"   [OK] 已创建任务：{job_config['job_name']} (ID: {job_id})")
        migrated_count += 1
    else:
        print("\n[SKIP] 跳过小红书任务（SCHEDULER_ENABLE_XHS=false）")
    
    # ========== 3. 迁移任务处理器 ==========
    print("\n[INFO] 迁移任务处理器...")
    
    job_config = {
        "job_name": "面经题目提取处理器",
        "job_type": "process_tasks",
        "schedule_type": "cron",
        "schedule_config": {
            "minute": str(settings.scheduler_process_minute)
        },
        "job_params": {
            "batch_size": settings.crawler_process_batch_size
        },
        "enabled": True,
        "description": f"从 .env 迁移：每小时第 {settings.scheduler_process_minute} 分钟处理任务队列"
    }
    
    job_id = scheduler_service.add_job(job_config)
    print(f"   [OK] 已创建任务：{job_config['job_name']} (ID: {job_id})")
    migrated_count += 1
    
    # ========== 完成 ==========
    print(f"\n[SUCCESS] 迁移完成！共创建 {migrated_count} 个定时任务")
    print("\n[INFO] 后续步骤：")
    print("   1. 重启应用：python run.py")
    print("   2. 访问前端查看定时任务：http://localhost:8000/scheduler")
    print("   3. 可选：在 .env 中禁用旧的调度器配置（保留配置值，仅作为默认值）")


if __name__ == "__main__":
    try:
        migrate_config()
    except Exception as e:
        print(f"\n[ERROR] 迁移失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
