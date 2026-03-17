content = open('e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue', 'r', encoding='utf-8').read()
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'submit_answer' in line or 'submitAnswer' in line or 'submit-answer' in line:
        print(f'{i+1}: {line}')
