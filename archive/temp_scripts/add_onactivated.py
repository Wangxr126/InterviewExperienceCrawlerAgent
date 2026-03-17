import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 1. CollectView.vue
with open('web/src/views/CollectView.vue', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    # 在onUnmounted前添加onActivated
    if 'onUnmounted(() => { stopExtractPolling(); stopCrawlPolling() })' in line:
        # 在这一行前插入onActivated
        indent = len(line) - len(line.lstrip())
        new_lines.insert(-1, '\n')
        new_lines.insert(-1, ' ' * indent + '// 页面激活时重新加载数据（解决删除后切换页面数据不刷新的问题）\n')
        new_lines.insert(-1, ' ' * indent + 'onActivated(async () => {\n')
        new_lines.insert(-1, ' ' * indent + '  await loadStats()\n')
        new_lines.insert(-1, ' ' * indent + '  await loadTasks()\n')
        new_lines.insert(-1, ' ' * indent + '})\n')
        new_lines.insert(-1, '\n')

with open('web/src/views/CollectView.vue', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] CollectView.vue 已添加 onActivated')

# 2. BrowseView.vue
with open('web/src/views/BrowseView.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加onActivated到import
if 'onActivated' not in content:
    content = content.replace(
        "import { ref, reactive, computed, onMounted",
        "import { ref, reactive, computed, onMounted, onActivated"
    )

# 找到onMounted并在后面添加onActivated
if 'onActivated' not in content or content.count('onActivated') == 1:  # 只在import中有
    # 找到onMounted的位置
    import re
    pattern = r'(onMounted\(async \(\) => \{[^}]+\}\))'
    match = re.search(pattern, content)
    if match:
        onmounted_block = match.group(0)
        # 在onMounted后添加onActivated
        new_block = onmounted_block + '\n\n// 页面激活时重新加载数据\nonActivated(async () => {\n  await loadQuestions()\n})\n'
        content = content.replace(onmounted_block, new_block)

with open('web/src/views/BrowseView.vue', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] BrowseView.vue 已添加 onActivated')

# 3. FinetuneView.vue
with open('web/src/views/FinetuneView.vue', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加onActivated到import
if 'onActivated' not in content:
    content = content.replace(
        "import { ref, reactive, computed, watch, onMounted",
        "import { ref, reactive, computed, watch, onMounted, onActivated"
    )

# 找到onMounted并在后面添加onActivated
if 'onActivated' not in content or content.count('onActivated') == 1:
    pattern = r'(onMounted\(async \(\) => \{[^}]+\}\))'
    match = re.search(pattern, content)
    if match:
        onmounted_block = match.group(0)
        new_block = onmounted_block + '\n\n// 页面激活时重新加载数据\nonActivated(async () => {\n  await loadSamples()\n  await loadStats()\n})\n'
        content = content.replace(onmounted_block, new_block)

with open('web/src/views/FinetuneView.vue', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] FinetuneView.vue 已添加 onActivated')

print('\n✅ 所有页面已添加 onActivated 钩子')
print('现在切换页面时会自动重新加载数据！')
