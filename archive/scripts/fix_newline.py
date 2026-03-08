"""修复换行符问题"""

file_path = "backend/services/crawler/question_extractor.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 修复错误的换行符
content = content.replace('newline="\n"', 'newline="\\n"')
content = content.replace('+ "\n"', '+ "\\n"')

# 确保第194行附近的代码正确
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'with open(ft_path, "a", encoding="utf-8"' in line:
        # 确保这一行是正确的
        if 'newline=' in line and not 'newline="\\n"' in line:
            lines[i] = '        with open(ft_path, "a", encoding="utf-8", newline="\\n") as f:'
            print(f"修复第 {i+1} 行: {lines[i]}")
    if 'f.write(json.dumps(ft_record' in line:
        if '+ "\\n"' not in line:
            lines[i] = '            f.write(json.dumps(ft_record, ensure_ascii=False) + "\\n")'
            print(f"修复第 {i+1} 行: {lines[i]}")

content = '\n'.join(lines)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("✓ 文件已修复")
