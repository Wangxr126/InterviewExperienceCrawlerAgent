with open('backend/services/finetune_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到问题行并修复
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    # 在 "if not p.exists():" 后面添加return语句
    if i > 0 and 'if not p.exists():' in lines[i-1] and line.strip() == '':
        # 检查下一行是否是 imported = 
        if i+1 < len(lines) and 'imported = skipped = failed = 0' in lines[i+1]:
            # 在空行位置插入return语句
            new_lines[-1] = '        return {"imported": 0, "skipped": 0, "failed": 0, "error": "文件不存在"}\n'
            new_lines.append('\n')

with open('backend/services/finetune_service.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已修复 finetune_service.py 的语法错误')
print('修复：在 if not p.exists(): 后添加了 return 语句')
