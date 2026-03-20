path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
content = open(path, encoding='utf-8').read()

# Fix 1: thinking branch - remove unnecessary splice
old1 = '''        const stepObj = getOrCreateStep(aiMsg, stepNo)
        stepObj.thought = stepObj.thought ? `${stepObj.thought}\n${normalized}` : normalized
        messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
        streamingMsg.value = messages.value[aiMsgIndex]
      } else if (evType === 'tool' && !payload.data) {'''

new1 = '''        const stepObj = getOrCreateStep(aiMsg, stepNo)
        stepObj.thought = stepObj.thought ? `${stepObj.thought}\n${normalized}` : normalized
        // \u76f4\u63a5\u4fee\u6539\u6b65\u9aa4\u5bf9\u8c61\u5b57\u6bb5\uff0c\u4e0d\u6574\u4f53\u66ff\u6362\u6d88\u606f\uff08\u907f\u514d\u601d\u8003\u5757\u95ea\u70c1\uff09
      } else if (evType === 'tool' && !payload.data) {'''

if old1 in content:
    content = content.replace(old1, new1, 1)
    print('Fix 1 OK: thinking branch splice removed')
else:
    print('Fix 1 NOT FOUND')
    # Debug: find nearby
    idx = content.find("streamingMsg.value = messages.value[aiMsgIndex]\n      } else if")
    if idx >= 0:
        print('  nearby context:', repr(content[idx-100:idx+80]))

# Fix 2: message finish branch - remove unnecessary splice
old2 = '''          aiMsg.duration_ms = data.duration_ms ?? (Date.now() - (aiMsg._startTs || Date.now()))
          messages.value.splice(aiMsgIndex, 1, { ...aiMsg })
          streamingMsg.value = messages.value[aiMsgIndex]
        }
      } else if (evType === 'thinking') {'''

new2 = '''          aiMsg.duration_ms = data.duration_ms ?? (Date.now() - (aiMsg._startTs || Date.now()))
          // \u4e0d\u9700\u8981 splice\uff0c\u76f4\u63a5\u4fee\u6539\u5b57\u6bb5\u5373\u53ef
        }
      } else if (evType === 'thinking') {'''

if old2 in content:
    content = content.replace(old2, new2, 1)
    print('Fix 2 OK: message finish branch splice removed')
else:
    print('Fix 2 NOT FOUND')

# Fix 3: finally block - don't force thinkingOpen=true after stream ends (conflicts with fold-on-first-chunk)
old3 = '''        // \u5f53\u524d\u56de\u590d\u7684\u63a8\u7406\u8fc7\u7a0b\u9ed8\u8ba4\u5c55\u5f00\uff0c\u907f\u514d\u7528\u6237\u770b\u5230\u7684\u662f\u4e0a\u4e00\u8f6e\u6d88\u606f\u7684\u6b65\u9aa4\uff08\u524d\u540e\u4e00\u81f4\uff09
        if (finalMsg.thinking?.length > 0) {
          finalMsg.thinkingOpen = true
        }'''

new3 = '''        // \u6d41\u5f0f\u7ed3\u675f\u540e\u4fdd\u6301\u601d\u8003\u5757\u5f53\u524d\u5c55\u5f00\u72b6\u6001\uff08\u6d41\u5f0f\u8fc7\u7a0b\u4e2d\u5df2\u81ea\u52a8\u6298\u53e0\uff09\uff0c\u4e0d\u5f3a\u5236\u91cd\u65b0\u5c55\u5f00'''

if old3 in content:
    content = content.replace(old3, new3, 1)
    print('Fix 3 OK: finally thinkingOpen forced-true removed')
else:
    print('Fix 3 NOT FOUND')

open(path, 'w', encoding='utf-8').write(content)
print('Done.')
