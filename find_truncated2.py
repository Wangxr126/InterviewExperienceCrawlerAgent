import re

with open('backend/logs/backend.log', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

keyword = "name 'truncated' is not defined"
idx = content.find(keyword)
if idx >= 0:
    # 打印完整的 traceback（从 Traceback 往前找）
    segment = content[max(0, idx-500):idx+2000]
    print(segment)
else:
    print('not found')
