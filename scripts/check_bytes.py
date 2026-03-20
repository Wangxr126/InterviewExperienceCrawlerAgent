# 直接读取 main.py 指定行范围，输出原始内容
with open('backend/main.py', encoding='utf-8', errors='replace') as f:
    lines = []
    for i, line in enumerate(f, 1):
        if 660 <= i <= 670:
            lines.append((i, repr(line)))
for ln, content in lines:
    print(ln, content)
