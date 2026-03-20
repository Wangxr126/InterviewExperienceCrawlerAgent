path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    content = f.read()

marker = "messages.value.splice(aiMsgIndex, 1, { ...aiMsg })\n        streamingMsg.value = messages.value[aiMsgIndex]\n      } else if (evType === 'tool' && !payload.data) {"
idx = content.find(marker)

# Make sure this is the thinking branch (preceded by stepObj.thought)
before = content[idx-120:idx]
if 'stepObj.thought' in before:
    replacement = "// \u76f4\u63a5\u4fee\u6539\u6b65\u9aa4\u5bf9\u8c61\u5b57\u6bb5\uff0c\u4e0d\u6574\u4f53\u66ff\u6362\u6d88\u606f\uff08\u907f\u514d\u601d\u8003\u5757\u95ea\u70c1\uff09\n      } else if (evType === 'tool' && !payload.data) {"
    content = content[:idx] + replacement + content[idx+len(marker):]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK: thinking branch splice removed')
else:
    print('SKIP: not in thinking branch, before=', repr(before))
