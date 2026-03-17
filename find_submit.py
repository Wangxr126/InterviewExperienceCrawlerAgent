content = open('e:/Agent/AgentProject/wxr_agent/backend/main.py', 'r', encoding='utf-8').read()
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'submit_answer' in line or 'no_eval' in line or '无评估' in line:
        print(f'{i+1}: {line}')
