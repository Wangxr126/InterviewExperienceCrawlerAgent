path = 'e:/Agent/AgentProject/wxr_agent/web/src/views/ChatView.vue'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Remove the redundant streamingMsg.value line (0-indexed 1111)
# and add a unified streamingMsg update before chatStore.syncMessages
if 'streamingMsg.value = messages.value[aiMsgIndex]' in lines[1111]:
    lines[1111] = ''  # remove per-branch streamingMsg update
    # Insert unified streamingMsg sync before chatStore.syncMessages (line 1113, 0-indexed)
    lines[1113] = '      // \u7edf\u4e00\u5728\u672b\u5c3e\u540c\u6b65 streamingMsg \u5f15\u7528\uff08splice \u540e\u9700\u8981\u91cd\u65b0\u6307\u5411\u65b0\u5bf9\u8c61\uff09\n      streamingMsg.value = messages.value[aiMsgIndex] ?? null\n      chatStore.syncMessages(messages.value)\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('OK: unified streamingMsg sync at end of handleEvent')
else:
    print('NOT MATCHED:', repr(lines[1111]))
