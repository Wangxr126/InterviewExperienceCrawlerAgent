import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('backend/services/scheduler.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修复：将查询pending改为查询error
content = content.replace(
    '# 查询需要重试的任务（状态为pending且raw_content为空的）\n    failed_tasks = sqlite_service.get_tasks_by_status("pending", limit=50)',
    '# 查询需要重试的任务（状态为error的）\n    failed_tasks = sqlite_service.get_tasks_by_status("error", limit=50)'
)

with open('backend/services/scheduler.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 已修复重试逻辑')
print('修改：查询状态从 pending 改为 error')
print('现在会正确重试失败的任务！')
