path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
content = open(path, encoding='utf-8').read()

# Find the exact context from the nearby output
idx = content.find("ht}\\n${normalized}` : normalized\n        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })\n        streamingMsg.value = messages.value[aiMsgIndex]\n      } else if (evType === 'too")
if idx >= 0:
    print('Found at idx:', idx)
    print('Context:', repr(content[idx-60:idx+160]))
else:
    print('Still not found')
    # Try to find the splice line near 'too'
    idx2 = content.find("messages.value.splice(aiMsgIndex, 1, { ...aiMsg })\n        streamingMsg.value = messages.value[aiMsgIndex]\n      } else if (evType === 'tool'")
    print('idx2:', idx2)
    if idx2 >= 0:
        print(repr(content[idx2-150:idx2+120]))
