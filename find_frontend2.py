import os

files = [
    'e:/Agent/AgentProject/wxr_agent/web/src/components/QuestionDialog.vue',
    'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue',
]

for fpath in files:
    if not os.path.exists(fpath):
        print(f'NOT FOUND: {fpath}')
        continue
    content = open(fpath, 'r', encoding='utf-8').read()
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if any(p in line for p in ['submit_answer', 'submitAnswer', '/api/submit', 'last_score', 'score', 'fetch(']):
            print(f'{os.path.basename(fpath)}:{i+1}: {line}')
