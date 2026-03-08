"""
验证重构后的调度器
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("调度器重构验证测试")
print("=" * 60)

# 1. 验证导入
print("\n[1/5] 验证导入...")
try:
    from backend.services.scheduler_refactored import crawl_scheduler
    from backend.services.scheduler_service import scheduler_service
    from backend.api.scheduler_api import router
    print("   [OK] 所有模块导入成功")
except Exception as e:
    print(f"   [ERROR] 导入失败: {e}")
    sys.exit(1)

# 2. 验证数据库
print("\n[2/5] 验证数据库...")
try:
    jobs = scheduler_service.list_jobs()
    print(f"   [OK] 数据库连接成功，共有 {len(jobs)} 个任务")
    for job in jobs:
        status = '启用' if job['enabled'] else '禁用'
        print(f"      - {job['job_name']} ({job['job_type']}) - {status}")
except Exception as e:
    print(f"   [ERROR] 数据库验证失败: {e}")
    sys.exit(1)

# 3. 验证兼容方法
print("\n[3/5] 验证向后兼容方法...")
methods = ['trigger_nowcoder_discovery', 'trigger_xhs_discovery', 'trigger_process_tasks', 'get_stats']
for method in methods:
    if hasattr(crawl_scheduler, method):
        print(f"   [OK] {method} 存在")
    else:
        print(f"   [ERROR] {method} 不存在")
        sys.exit(1)

# 4. 验证 API 路由
print("\n[4/5] 验证 API 路由...")
try:
    routes = [route.path for route in router.routes]
    print(f"   [OK] API 路由注册成功，共 {len(routes)} 个端点")
    for route in routes:
        print(f"      - {route}")
except Exception as e:
    print(f"   [ERROR] API 路由验证失败: {e}")
    sys.exit(1)

# 5. 验证前端文件
print("\n[5/5] 验证前端文件...")
frontend_file = Path("frontend/scheduler.html")
if frontend_file.exists():
    print(f"   [OK] 前端文件存在: {frontend_file}")
else:
    print(f"   [ERROR] 前端文件不存在: {frontend_file}")
    sys.exit(1)

print("\n" + "=" * 60)
print("[SUCCESS] 所有验证通过！")
print("=" * 60)
print("\n下一步：")
print("  1. 启动应用: python run.py")
print("  2. 访问管理界面: http://localhost:8000/scheduler")
print("  3. 测试 API: http://localhost:8000/docs")
print("\n")
