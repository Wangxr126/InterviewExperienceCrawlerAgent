"""
优化Agent配置
1. 从config.py中删除未使用的Hunter配置
2. 优化.env文件的注释和结构
"""

print("=" * 60)
print("Agent 配置优化")
print("=" * 60)

# 1. 删除config.py中的Hunter配置
print("\n[1/2] 检查 config.py 中的 Hunter 配置...")

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到Hunter配置的起始和结束行
hunter_start = -1
hunter_end = -1
for i, line in enumerate(lines):
    if '# ── 2. Hunter Agent' in line:
        hunter_start = i
    if hunter_start != -1 and '# ── 3. Architect Agent' in line:
        hunter_end = i
        break

if hunter_start != -1 and hunter_end != -1:
    print(f"   找到 Hunter 配置：第 {hunter_start + 1} 行到第 {hunter_end} 行")
    print(f"   共 {hunter_end - hunter_start} 行")
    
    # 删除Hunter配置
    new_lines = lines[:hunter_start] + lines[hunter_end:]
    
    with open('backend/config/config.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("   ✅ 已删除 Hunter 配置")
else:
    print("   ⚠️ 未找到 Hunter 配置（可能已删除）")

# 2. 优化.env文件
print("\n[2/2] 优化 .env 文件...")

with open('.env', 'r', encoding='utf-8') as f:
    env_content = f.read()

# 检查是否有Hunter配置
if 'HUNTER_' in env_content:
    print("   ⚠️ .env 中存在 HUNTER_ 配置，需要手动删除")
else:
    print("   ✅ .env 中没有 HUNTER_ 配置")

# 添加配置说明注释
if '# Agent 配置说明' not in env_content:
    print("   添加配置说明...")
    
    # 在第2节后添加说明
    explanation = """
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 配置说明：
#   - 留空则使用全局 LLM 配置
#   - Architect: 知识架构师，结构化任务，temperature 建议 0.0-0.2
#   - Interviewer: 面试官，对话任务，temperature 建议 0.5-0.7
#   - Extractor: 题目提取器，使用全局 LLM，temperature 建议 0.0-0.2
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    # 在 "2. 各 Agent 差异化 LLM" 后添加
    env_content = env_content.replace(
        '# 2. 各 Agent 差异化 LLM（留空则回退使用全局 LLM）\n# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n',
        '# 2. 各 Agent 差异化 LLM（留空则回退使用全局 LLM）\n# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n' + explanation
    )
    
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("   ✅ 已添加配置说明")

print("\n" + "=" * 60)
print("优化完成！")
print("=" * 60)
print("\n总结：")
print("1. ✅ 删除了 config.py 中未使用的 Hunter 配置")
print("2. ✅ 优化了 .env 文件的注释")
print("\n现在所有 Agent 配置都清晰明了：")
print("  - Interviewer Agent: 面试对话")
print("  - Architect Agent: 知识架构")
print("  - Extractor: 题目提取（使用全局LLM）")
print("  - Finetune: 微调辅助")
print("\n配置优先级：Agent专属配置 > 全局配置")
