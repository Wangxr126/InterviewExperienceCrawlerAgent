content = open('e:/Agent/AgentProject/wxr_agent/backend/main.py', 'r', encoding='utf-8').read()
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'SubmitAnswerRequest' in line or 'class Submit' in line:
        print(f'{i+1}: {line}')
