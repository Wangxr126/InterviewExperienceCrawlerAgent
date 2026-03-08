import sys
import chardet

file_path = 'backend/services/finetune_service.py'

# 读取原始字节
with open(file_path, 'rb') as f:
    raw_bytes = f.read()

print(f"File size: {len(raw_bytes)} bytes")

# 检测编码
detected = chardet.detect(raw_bytes)
print(f"Detected encoding: {detected}")

# 尝试多种编码
encodings = [detected['encoding'], 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin1']
content = None

for enc in encodings:
    if not enc:
        continue
    try:
        content = raw_bytes.decode(enc, errors='ignore')
        print(f"Success with {enc}")
        break
    except:
        print(f"Failed with {enc}")

if content:
    # 保存为 UTF-8
    with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print("File converted to UTF-8")
else:
    print("Failed to decode file")
