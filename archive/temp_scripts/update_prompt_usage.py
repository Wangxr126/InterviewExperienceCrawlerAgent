"""
更新所有Agent使用新的Prompt管理系统
"""

print("=" * 80)
print("Prompt重构 - 更新代码")
print("=" * 80)

# 需要更新的文件列表
files_to_update = {
    "backend/services/crawler/question_extractor.py": {
        "old_import": "EXTRACT_SYSTEM_PROMPT",
        "new_import": "from backend.prompts.extractor_prompt import get_extractor_prompt, format_extractor_user_prompt",
        "old_usage": "EXTRACT_SYSTEM_PROMPT",
        "new_usage": "get_extractor_prompt()"
    },
    "backend/agents/architect_agent.py": {
        "old_import": "from backend.agents.prompts.architect_prompt import architect_prompt",
        "new_import": "from backend.prompts.architect_prompt import get_architect_prompt",
        "old_usage": "architect_prompt",
        "new_usage": "get_architect_prompt()"
    },
    "backend/agents/interviewer_agent.py": {
        "old_import": "from backend.agents.prompts.interviewer_prompt import interviewer_prompt",
        "new_import": "from backend.prompts.interviewer_prompt import get_interviewer_prompt",
        "old_usage": "interviewer_prompt",
        "new_usage": "get_interviewer_prompt()"
    }
}

print("\n需要更新的文件：")
for i, (file, changes) in enumerate(files_to_update.items(), 1):
    print(f"{i}. {file}")
    print(f"   旧导入: {changes['old_import']}")
    print(f"   新导入: {changes['new_import']}")
    print(f"   旧用法: {changes['old_usage']}")
    print(f"   新用法: {changes['new_usage']}")
    print()

print("=" * 80)
print("更新步骤：")
print("1. 更新 question_extractor.py")
print("2. 更新 architect_agent.py")
print("3. 更新 interviewer_agent.py")
print("4. 删除旧的 backend/agents/prompts/ 目录")
print("5. 测试所有Agent")
print("=" * 80)
