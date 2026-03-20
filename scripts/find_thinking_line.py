with open('backend/main.py', encoding='utf-8') as f:
    lines = f.readlines()

# 找到 'THINKING' in content 那行
for i, line in enumerate(lines):
    if "'THINKING' in content" in line and 670 < i < 685:
        print(f'Found at line {i+1}: {repr(line)}')
        target_idx = i
        break
else:
    print('Not found!')
    for i in range(673, 690):
        print(i+1, repr(lines[i]))
    exit(1)

# 打印要替换的范围
print('Lines to replace:')
for i in range(target_idx-1, target_idx+8):
    print(i+1, repr(lines[i]))
