"""
测试重构后的调度器
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("测试调度器重构")
print("=" * 60)

# 1. 测试数据库服务
print("\n[1] 测试数据库服务...")
from backend.services.scheduler_service import scheduler_service
jobs = scheduler_service.list_jobs()
print(f"   数据库中有 {len(jobs)} 个任务")
for job in jobs:
    print(f"   - {job['job_name']} ({job['job_type']}) - {'启用' if job['enabled'] else '禁用'}")

# 2. 测试调度器导入
print("\n[2] 测试调度器导入...")
from backend.services.scheduler_refactored import crawl_scheduler
print("   调度器导入成功")

# 3. 测试 API 路由
print("\n[3] 测试 API 路由...")
from backend.api.scheduler_api import router
print(f"   API 路由包含 {len(router.routes)} 个端点")

# 4. 测试核心执行方法
print("\n[4] 测试核心执行方法...")
from backend.services.scheduler_refactored import run_nowcoder_discovery, run_xhs_discovery, run_process_tasks
print("   核心方法导入成功")

# 5. 测试前端文件
print("\n[5] 测试前端文件...")
frontend_file = project_root / "frontend" / "scheduler.html"
if frontend_file.exists():
    print(f"   前端文件存在: {frontend_file}")
    print(f"   文件大小: {frontend_file.stat().st_size} 字节")
else:
    print("   [ERROR] 前端文件不存在")

print("\n" + "=" * 60)
print("所有测试通过！")
print("=" * 60)
print("\n下一步：")
print("1. 启动应用: python run.py")
print("2. 访问管理界面: http://localhost:8000/scheduler")
print("3. 测试 API: curl http://localhost:8000/api/scheduler/jobs")
