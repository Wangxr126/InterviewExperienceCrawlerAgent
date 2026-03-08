"""
更新 .env 文件，添加 LOCAL 和 REMOTE 配置
"""

with open('.env', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0
in_llm_section = False

while i < len(lines):
    line = lines[i]
    
    # 检测到LLM配置区域的开始
    if '# 1. LLM' in line or '# 1. 全局 LLM' in line:
        in_llm_section = True
        # 添加新的注释
        new_lines.append('# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n')
        new_lines.append('# 1. LLM 配置（支持本地/远程切换）\n')
        new_lines.append('#    修改 LLM_MODE 即可切换：local（本地Ollama）或 remote（云端API）\n')
        new_lines.append('# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n')
        new_lines.append('\n')
        new_lines.append('# 使用模式：local（本地）或 remote（远程）\n')
        new_lines.append('LLM_MODE=local\n')
        new_lines.append('\n')
        new_lines.append('# ── 本地配置（Ollama）────────────────────────────────────────\n')
        new_lines.append('LLM_LOCAL_PROVIDER=ollama\n')
        new_lines.append('LLM_LOCAL_MODEL=qwen3:4b\n')
        new_lines.append('LLM_LOCAL_API_KEY=ollama\n')
        new_lines.append('LLM_LOCAL_BASE_URL=http://localhost:11434/v1\n')
        new_lines.append('LLM_LOCAL_TIMEOUT=60\n')
        new_lines.append('\n')
        new_lines.append('# ── 远程配置（云端API）───────────────────────────────────────\n')
        new_lines.append('LLM_REMOTE_PROVIDER=volcengine\n')
        new_lines.append('LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115\n')
        new_lines.append('LLM_REMOTE_API_KEY=your_api_key_here\n')
        new_lines.append('LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3\n')
        new_lines.append('LLM_REMOTE_TIMEOUT=300\n')
        new_lines.append('\n')
        new_lines.append('# ── 通用配置 ─────────────────────────────────────────────────\n')
        
        # 跳过旧的配置行，直到找到 LLM_TEMPERATURE
        i += 1
        while i < len(lines):
            if 'LLM_TEMPERATURE=' in lines[i]:
                new_lines.append(lines[i])
                i += 1
                break
            elif 'LLM_WARMUP_ENABLED' in lines[i] or 'Ollama 模型常驻显存' in lines[i]:
                new_lines.append(lines[i])
                i += 1
            elif lines[i].strip().startswith('#') or lines[i].strip() == '':
                new_lines.append(lines[i])
                i += 1
            else:
                # 跳过旧的配置行
                i += 1
        continue
    
    # 检测到下一个区域
    if in_llm_section and '# 2.' in line:
        in_llm_section = False
    
    new_lines.append(line)
    i += 1

with open('.env', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已更新 .env 文件')
print('')
print('新增配置：')
print('  LLM_MODE=local                    # 使用模式（local/remote）')
print('')
print('  # 本地配置')
print('  LLM_LOCAL_PROVIDER=ollama')
print('  LLM_LOCAL_MODEL=qwen3:4b')
print('  LLM_LOCAL_BASE_URL=http://localhost:11434/v1')
print('  LLM_LOCAL_TIMEOUT=60')
print('')
print('  # 远程配置')
print('  LLM_REMOTE_PROVIDER=volcengine')
print('  LLM_REMOTE_MODEL=doubao-1-5-pro-32k-250115')
print('  LLM_REMOTE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3')
print('  LLM_REMOTE_TIMEOUT=300')
print('')
print('使用方式：')
print('  - 修改 LLM_MODE=local  → 使用本地Ollama')
print('  - 修改 LLM_MODE=remote → 使用远程API')
