"""修复 question_extractor.py 中缺少 q_id 的问题"""
import re

file_path = r"e:\Agent\AgentProject\wxr_agent\backend\services\crawler\question_extractor.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 查找并替换
old_code = '''        item_difficulty = str(item.get("difficulty", "")).strip()
        difficulty_val = _normalize_difficulty(item_difficulty) if item_difficulty else ""
        # q_id 由数据库自动生成（INTEGER PRIMARY KEY AUTOINCREMENT）
        questions.append({
            "question_text": q_text,'''

new_code = '''        item_difficulty = str(item.get("difficulty", "")).strip()
        difficulty_val = _normalize_difficulty(item_difficulty) if item_difficulty else ""
        
        # 生成唯一的 q_id（UUID）
        import uuid
        q_id = str(uuid.uuid4())
        
        questions.append({
            "q_id": q_id,  # 添加 q_id 字段
            "question_text": q_text,'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] 已修复 q_id 缺失问题")
else:
    print("[FAIL] 未找到目标代码，可能已经修复或代码结构已变化")
