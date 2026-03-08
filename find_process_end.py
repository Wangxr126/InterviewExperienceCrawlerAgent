import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('backend/services/scheduler.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到_process_pending_tasks函数的结尾
in_function = False
for i, line in enumerate(lines, 1):
    if 'def _process_pending_tasks' in line:
        in_function = True
        start = i
    
    if in_function and line.strip().startswith('def ') and i > start:
        # 找到下一个函数，说明当前函数结束了
        print(f'_process_pending_tasks 函数结束于第 {i-1} 行')
        print(f'最后几行:')
        for j in range(max(0, i-10), i):
            print(f'{j+1:4d}: {lines[j].rstrip()}')
        
        # 检查是否有return语句
        print(f'\n检查return语句:')
        for j in range(max(0, i-20), i):
            if 'return' in lines[j]:
                print(f'{j+1:4d}: {lines[j].rstrip()}')
        break
