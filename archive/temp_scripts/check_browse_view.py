with open('web/src/views/BrowseView.vue', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    
for i, line in enumerate(lines, 1):
    if 'onActivated' in line or 'onMounted' in line or 'loadQuestions' in line:
        print(f'{i:4d}: {line.rstrip()}')
