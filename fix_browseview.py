with open('web/src/views/BrowseView.vue', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    # 在onMounted(loadQuestions)后添加onActivated
    if line.strip() == 'onMounted(loadQuestions)':
        new_lines.append('\n')
        new_lines.append('// 页面激活时重新加载数据（解决删除后切换页面数据不刷新的问题）\n')
        new_lines.append('onActivated(loadQuestions)\n')

with open('web/src/views/BrowseView.vue', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] BrowseView.vue 已添加 onActivated')
