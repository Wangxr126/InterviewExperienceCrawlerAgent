"""
修复config.py中重复的@property装饰器
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到并修复重复的@property
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)
    
    # 检查是否是@property后面紧跟着注释再跟着@property
    if i + 2 < len(lines):
        if '@property' in line and '# ──' in lines[i+1] and '@property' in lines[i+2]:
            # 跳过第一个@property，保留注释和第二个@property
            new_lines.pop()  # 移除刚添加的@property
            i += 1
            continue
    
    i += 1

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已修复 config.py 中重复的 @property 装饰器')
print('问题：post_images_dir 后面有两个 @property')
print('修复：移除多余的 @property')
