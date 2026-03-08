"""
添加 anthropic 到 requirements.txt
"""

with open('requirements.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 在 easyocr 后面添加 anthropic
new_lines = []
for line in lines:
    new_lines.append(line)
    if 'easyocr' in line.lower():
        new_lines.append('anthropic>=0.39.0         # Anthropic Claude API（用于 Claude Vision OCR）\n')

with open('requirements.txt', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已添加 anthropic 到 requirements.txt')
print('')
print('请运行以下命令安装：')
print('  pip install anthropic')
print('')
print('或者重新安装所有依赖：')
print('  pip install -r requirements.txt')
