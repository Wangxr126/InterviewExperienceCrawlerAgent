import sys

file_path = 'backend/services/finetune_service.py'

# 读取原始字节
with open(file_path, 'rb') as f:
    raw_bytes = f.read()

print(f"原始文件大小: {len(raw_bytes)} 字节")

# 尝试用 GBK 解码（Windows 中文环境常见编码）
try:
    content = raw_bytes.decode('gbk')
    print("✅ 成功用 GBK 解码")
except:
    try:
        content = raw_bytes.decode('gb2312')
        print("✅ 成功用 GB2312 解码")
    except:
        content = raw_bytes.decode('latin1')
        print("⚠️ 使用 latin1 解码（可能有问题）")

# 保存为 UTF-8
with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)

print(f"✅ 文件已转换为 UTF-8 编码并保存")

# 验证
with open(file_path, 'r', encoding='utf-8') as f:
    test = f.read()
print(f"✅ UTF-8 验证成功，文件大小: {len(test)} 字符")
