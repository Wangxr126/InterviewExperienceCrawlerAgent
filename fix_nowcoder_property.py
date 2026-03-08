"""
为nowcoder_output_dir添加@property装饰器
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到nowcoder_output_dir并添加@property
new_lines = []
for i, line in enumerate(lines):
    # 在nowcoder_output_dir定义前添加@property
    if 'def nowcoder_output_dir' in line and i > 0:
        # 检查上一行是否已经有@property
        if '@property' not in lines[i-1]:
            new_lines.append('    @property\n')
    
    new_lines.append(line)

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已为 nowcoder_output_dir 添加 @property 装饰器')
