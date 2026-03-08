"""
1. 注释掉"正在抓取"的日志
2. 为重试抓取添加日志
"""

with open('backend/services/scheduler.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    # 1. 注释掉"正在抓取"的日志
    if '正在抓取:' in line and 'logger.info' in line:
        # 注释掉这一行
        new_lines.append(line.replace('logger.info(', '# logger.info(') + ' # 注释掉，减少日志噪音\n' if '\n' not in line else '')
        if '\n' not in line:
            continue
    else:
        new_lines.append(line)

with open('backend/services/scheduler.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已注释掉"正在抓取"的日志')
