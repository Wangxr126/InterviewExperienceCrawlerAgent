path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 977-985 to see exact content
for i, l in enumerate(lines[976:986], start=977):
    print(i, repr(l))
