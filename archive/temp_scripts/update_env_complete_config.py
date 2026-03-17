"""
更新 .env 文件，添加完整的Agent配置项
"""

with open('.env', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # 1. 在 ARCHITECT_MODEL 前添加 ARCHITECT_PROVIDER
    if 'ARCHITECT_MODEL=' in line and i > 0 and 'ARCHITECT_PROVIDER' not in lines[i-1]:
        new_lines.append('ARCHITECT_PROVIDER=                  # 留空使用 LLM_PROVIDER\n')
        new_lines.append(line)
        i += 1
        continue
    
    # 2. 在 ARCHITECT_TEMPERATURE 后添加 ARCHITECT_TIMEOUT
    if 'ARCHITECT_TEMPERATURE=' in line:
        new_lines.append(line)
        # 检查下一行是否已经有 ARCHITECT_TIMEOUT
        if i + 1 < len(lines) and 'ARCHITECT_TIMEOUT' not in lines[i+1]:
            new_lines.append('ARCHITECT_TIMEOUT=                   # 留空使用 LLM_TIMEOUT\n')
        i += 1
        continue
    
    # 3. 在 INTERVIEWER_MODEL 前添加 INTERVIEWER_PROVIDER
    if 'INTERVIEWER_MODEL=' in line and i > 0 and 'INTERVIEWER_PROVIDER' not in lines[i-1]:
        new_lines.append('INTERVIEWER_PROVIDER=                # 留空使用 LLM_PROVIDER\n')
        new_lines.append(line)
        i += 1
        continue
    
    # 4. 在 INTERVIEWER_TEMPERATURE 后添加 INTERVIEWER_TIMEOUT
    if 'INTERVIEWER_TEMPERATURE=' in line:
        new_lines.append(line)
        # 检查下一行是否已经有 INTERVIEWER_TIMEOUT
        if i + 1 < len(lines) and 'INTERVIEWER_TIMEOUT' not in lines[i+1]:
            new_lines.append('INTERVIEWER_TIMEOUT=                 # 留空使用 LLM_TIMEOUT\n')
        i += 1
        continue
    
    # 5. 在 FINETUNE_LLM_MODEL 前添加 FINETUNE_LLM_PROVIDER
    if 'FINETUNE_LLM_MODEL=' in line and i > 0 and 'FINETUNE_LLM_PROVIDER' not in lines[i-1]:
        new_lines.append('FINETUNE_LLM_PROVIDER=volcengine\n')
        new_lines.append(line)
        i += 1
        continue
    
    # 6. 在 FINETUNE_LLM_TEMPERATURE 后添加 FINETUNE_LLM_TIMEOUT
    if 'FINETUNE_LLM_TEMPERATURE=' in line:
        new_lines.append(line)
        # 检查下一行是否已经有 FINETUNE_LLM_TIMEOUT
        if i + 1 < len(lines) and 'FINETUNE_LLM_TIMEOUT' not in lines[i+1]:
            new_lines.append('FINETUNE_LLM_TIMEOUT=180\n')
        i += 1
        continue
    
    # 删除旧的注释行（如 "# gemma3:4b"）
    if line.strip() == '# gemma3:4b':
        i += 1
        continue
    
    new_lines.append(line)
    i += 1

with open('.env', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已更新 .env 文件')
print('')
print('添加的配置项：')
print('  1. ARCHITECT_PROVIDER')
print('  2. ARCHITECT_TIMEOUT')
print('  3. INTERVIEWER_PROVIDER')
print('  4. INTERVIEWER_TIMEOUT')
print('  5. FINETUNE_LLM_PROVIDER')
print('  6. FINETUNE_LLM_TIMEOUT')
print('')
print('现在每个Agent都有完整的配置项：')
print('  - PROVIDER (提供商)')
print('  - MODEL (模型)')
print('  - API_KEY (密钥)')
print('  - BASE_URL (地址)')
print('  - TIMEOUT (超时)')
print('  - TEMPERATURE (温度)')
