path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    content = f.read()

# Locate the splice after stepObj.thought assignment in the thinking branch
marker = 'messages.value.splice(aiMsgIndex, 1, { ...aiMsg })\n        streamingMsg.value = messages.value[aiMsgIndex]\n      } else if (evType === \'tool\' && !payload.data) {'
idx = content.find(marker)
print('marker idx:', idx)
if idx >= 0:
    print('before:', repr(content[idx-120:idx]))
    print('after:', repr(content[idx:idx+len(marker)+10]))
