"""
更新 .env 文件，为所有Agent添加LOCAL和REMOTE配置
"""

with open('.env', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
skip_until_next_section = False

while i < len(lines):
    line = lines[i]
    
    # 检测到Agent配置区域
    if '# 2.' in line and 'Agent' in line:
        # 添加新的Agent配置区域
        new_lines.append('# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n')
        new_lines.append('# 2. 各 Agent 差异化配置（留空则使用全局配置）\n')
        new_lines.append('# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n')
        new_lines.append('\n')
        
        # Architect Agent
        new_lines.append('# ── Architect Agent（知识架构师）─────────────────────────────\n')
        new_lines.append('ARCHITECT_MODE=                      # 使用模式（留空使用全局LLM_MODE）\n')
        new_lines.append('# 本地配置（留空使用全局LOCAL配置）\n')
        new_lines.append('ARCHITECT_LOCAL_PROVIDER=\n')
        new_lines.append('ARCHITECT_LOCAL_MODEL=\n')
        new_lines.append('ARCHITECT_LOCAL_BASE_URL=\n')
        new_lines.append('ARCHITECT_LOCAL_TIMEOUT=\n')
        new_lines.append('# 远程配置（留空使用全局REMOTE配置）\n')
        new_lines.append('ARCHITECT_REMOTE_PROVIDER=\n')
        new_lines.append('ARCHITECT_REMOTE_MODEL=\n')
        new_lines.append('ARCHITECT_REMOTE_BASE_URL=\n')
        new_lines.append('ARCHITECT_REMOTE_TIMEOUT=\n')
        new_lines.append('# 通用配置\n')
        new_lines.append('ARCHITECT_TEMPERATURE=0.2\n')
        new_lines.append('\n')
        
        # Interviewer Agent
        new_lines.append('# ── Interviewer Agent（面试官）───────────────────────────────\n')
        new_lines.append('INTERVIEWER_MODE=                    # 使用模式（留空使用全局LLM_MODE）\n')
        new_lines.append('# 本地配置（留空使用全局LOCAL配置）\n')
        new_lines.append('INTERVIEWER_LOCAL_PROVIDER=\n')
        new_lines.append('INTERVIEWER_LOCAL_MODEL=\n')
        new_lines.append('INTERVIEWER_LOCAL_BASE_URL=\n')
        new_lines.append('INTERVIEWER_LOCAL_TIMEOUT=\n')
        new_lines.append('# 远程配置（留空使用全局REMOTE配置）\n')
        new_lines.append('INTERVIEWER_REMOTE_PROVIDER=\n')
        new_lines.append('INTERVIEWER_REMOTE_MODEL=\n')
        new_lines.append('INTERVIEWER_REMOTE_BASE_URL=\n')
        new_lines.append('INTERVIEWER_REMOTE_TIMEOUT=\n')
        new_lines.append('# 通用配置\n')
        new_lines.append('INTERVIEWER_TEMPERATURE=0.5\n')
        new_lines.append('INTERVIEWER_MAX_STEPS=8\n')
        new_lines.append('\n')
        
        # Extractor
        new_lines.append('# ── Extractor（题目提取器）───────────────────────────────────\n')
        new_lines.append('# 使用全局LLM配置，只需配置temperature\n')
        new_lines.append('EXTRACTOR_TEMPERATURE=0.2\n')
        new_lines.append('EXTRACTOR_MAX_RETRIES=3\n')
        new_lines.append('\n')
        
        # 跳过旧的Agent配置，直到找到下一个区域
        skip_until_next_section = True
        i += 1
        continue
    
    # 检测到下一个区域（Embedding或其他）
    if skip_until_next_section and '# 3.' in line:
        skip_until_next_section = False
    
    # 如果在跳过模式，跳过这一行
    if skip_until_next_section:
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

with open('.env', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已更新 .env 文件')
print('')
print('为每个Agent添加了完整配置：')
print('')
print('Architect Agent:')
print('  - ARCHITECT_MODE')
print('  - ARCHITECT_LOCAL_* (4项)')
print('  - ARCHITECT_REMOTE_* (4项)')
print('  - ARCHITECT_TEMPERATURE')
print('')
print('Interviewer Agent:')
print('  - INTERVIEWER_MODE')
print('  - INTERVIEWER_LOCAL_* (4项)')
print('  - INTERVIEWER_REMOTE_* (4项)')
print('  - INTERVIEWER_TEMPERATURE')
print('  - INTERVIEWER_MAX_STEPS')
print('')
print('Extractor:')
print('  - EXTRACTOR_TEMPERATURE (使用全局LLM配置)')
print('  - EXTRACTOR_MAX_RETRIES')
print('')
print('说明：')
print('  - 每个Agent的MODE留空，则使用全局LLM_MODE')
print('  - 每个Agent的LOCAL/REMOTE配置留空，则使用全局配置')
print('  - EXTRACTOR不是独立Agent，直接使用全局LLM配置')
