path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Replace lines 1164-1179 (0-indexed 1163-1178)
new_lines = [
    '            eventCount++\n',
    '            \n',
    '            // \u5904\u7406\u4e8b\u4ef6\n',
    '            handleEvent(payload)\n',
    '            \n',
    '            // \u8282\u6d41\u6eda\u52a8\uff1a\u6bcf 150ms \u6700\u591a\u89e6\u53d1\u4e00\u6b21\uff0c\u907f\u514d\u6bcf\u4e2a chunk \u90fd\u91cd\u6392\n',
    '            const now = Date.now()\n',
    '            if (now - lastUpdateTime > 150) {\n',
    '              lastUpdateTime = now\n',
    '              scrollToBottom()\n',
    '            }\n',
]

lines[1163:1179] = new_lines

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('OK: SSE loop throttled, rAF and console.log removed')
