import sys
sys.stdout.reconfigure(encoding='utf-8')

# 1. 修改 question_extractor.py
with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('Miner Agent', 'Miner Service')

with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 1. question_extractor.py: Miner Agent → Miner Service')

# 2. 重命名文件 miner_agent.py → miner_service.py
import os
if os.path.exists('backend/services/miner_agent.py'):
    os.rename('backend/services/miner_agent.py', 'backend/services/miner_service.py')
    print('✅ 2. 文件重命名: miner_agent.py → miner_service.py')

# 3. 查找所有导入 miner_agent 的文件并修改
import glob
py_files = glob.glob('backend/**/*.py', recursive=True)
modified_files = []

for file in py_files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'from backend.services.miner_agent import' in content or 'import miner_agent' in content:
            content = content.replace('from backend.services.miner_agent import', 'from backend.services.miner_service import')
            content = content.replace('miner_agent', 'miner_service')
            
            with open(file, 'w', encoding='utf-8') as f:
                f.write(content)
            modified_files.append(file)
    except:
        pass

if modified_files:
    print(f'✅ 3. 修改了 {len(modified_files)} 个导入文件:')
    for f in modified_files:
        print(f'   - {f}')
else:
    print('✅ 3. 没有找到需要修改的导入')

print('\n总结:')
print('  - Miner 现在是一个 Service，不是 Agent')
print('  - 系统中只有 2 个真正的 Agent:')
print('    1. KnowledgeArchitect Agent')
print('    2. Interviewer Agent')
