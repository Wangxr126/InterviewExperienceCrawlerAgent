"""修复 question_extractor.py 中缺少 q_id 的问题 - 精确匹配版本"""

file_path = r"e:\Agent\AgentProject\wxr_agent\backend\services\crawler\question_extractor.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到包含 "# q_id 由数据库自动生成" 的行
modified = False
for i, line in enumerate(lines):
    if "# q_id 由数据库自动生成" in line:
        # 替换这一行和下一行
        lines[i] = "        \n"
        lines[i] += "        # 生成唯一的 q_id（UUID）\n"
        lines[i] += "        import uuid\n"
        lines[i] += "        q_id = str(uuid.uuid4())\n"
        lines[i] += "        \n"
        
        # 在 questions.append({ 后面插入 q_id
        if i+1 < len(lines) and "questions.append({" in lines[i+1]:
            # 找到 "question_text" 那一行
            for j in range(i+2, min(i+10, len(lines))):
                if '"question_text":' in lines[j]:
                    # 在这一行前面插入 q_id
                    indent = len(lines[j]) - len(lines[j].lstrip())
                    lines[j] = ' ' * indent + '"q_id": q_id,  # 添加 q_id 字段\n' + lines[j]
                    modified = True
                    break
        break

if modified:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("[OK] 已修复 q_id 缺失问题")
else:
    print("[FAIL] 未找到目标代码")
