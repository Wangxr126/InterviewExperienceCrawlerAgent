import re

# 在日志中找 truncated 错误上下文
with open('backend/logs/backend.log', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

keyword = "name 'truncated' is not defined"
idx = content.find(keyword)
if idx >= 0:
    print("=== 找到错误，前后 3000 字 ===")
    print(content[max(0, idx-3000):idx+500])
else:
    print("日志中未找到该错误")
    # 尝试找 NameError
    idx2 = content.find("NameError")
    if idx2 >= 0:
        print("找到 NameError:")
        print(content[max(0, idx2-1000):idx2+500])
