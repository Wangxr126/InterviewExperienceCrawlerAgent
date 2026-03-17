import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('backend/services/scheduler.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 在第288行后添加重试调用
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    
    # 在"本轮处理完成"这一行后添加重试逻辑
    if i == 287 and '本轮处理完成' in line:  # 第288行（索引287）
        new_lines.append('\n')
        new_lines.append('    # ── Step 3: 重试失败的任务 ──────────────────────────────\n')
        new_lines.append('    retry_count = _retry_failed_tasks()\n')
        new_lines.append('    if retry_count > 0:\n')
        new_lines.append('        logger.info(f"🔄 重试成功 {retry_count} 个任务")\n')
        new_lines.append('\n')

with open('backend/services/scheduler.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已在_process_pending_tasks函数中添加重试调用')
print('位置：第288行后')
print('现在处理任务时会自动重试失败的任务！')
