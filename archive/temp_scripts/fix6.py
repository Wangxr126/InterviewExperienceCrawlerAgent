path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# lines 980-981 (0-indexed) are the splice lines
if 'messages.value.splice' in lines[980] and 'streamingMsg.value' in lines[981]:
    lines[980] = '          // \u76f4\u63a5\u4fee\u6539\u5b57\u6bb5\uff0c\u4e0d splice \u6574\u4e2a\u5bf9\u8c61\n'
    lines[981] = ''  # remove streamingMsg line
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('OK: llm_chunk branch fixed')
else:
    print('NOT MATCHED:')
    for i in range(978, 985):
        print(i+1, repr(lines[i]))
