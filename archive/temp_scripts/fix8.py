path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

changes = 0

# Find and print all lines with 'streamingMsg.value = messages.value[aiMsgIndex]'
for i, l in enumerate(lines):
    if 'streamingMsg.value = messages.value[aiMsgIndex]' in l:
        print(i+1, repr(l))

print('---')
# Also check for 'chatStore.syncMessages' calls in handleEvent
for i, l in enumerate(lines):
    if 'chatStore.syncMessages' in l:
        print(i+1, repr(l))
