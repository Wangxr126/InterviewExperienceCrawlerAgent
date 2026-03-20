content = open('e:/Agent/AgentProject/wxr_agent/web/src/api.js', 'r', encoding='utf-8').read()
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'submitAnswer' in line or 'submit_answer' in line:
        print(f'{i+1}: {line}')
