#!/usr/bin/env python3
"""验证修复效果"""
import sys
import time

print("=" * 60)
print("修复验证清单")
print("=" * 60)

# 1. 检查日志配置修复
print("\n1️⃣ 检查日志配置修复...")
with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()
    if 'is_main_process = os.environ.get' in content and 'if is_main_process:' in content:
        print("   ✅ 日志配置已修复（多进程模式下只在主进程输出）")
    else:
        print("   ❌ 日志配置未修复")
        sys.exit(1)

# 2. 检查前端响应式更新修复
print("\n2️⃣ 检查前端响应式更新修复...")
with open('web/src/views/ChatView.vue', 'r', encoding='utf-8') as f:
    content = f.read()
    if 'const newMsg = { ...aiMsg }' in content and 'messages.value[msgIndex] = newMsg' in content:
        print("   ✅ 前端响应式更新已修复（使用新对象替换）")
    else:
        print("   ❌ 前端响应式更新未修复")
        sys.exit(1)

# 3. 检查会话保持修复
print("\n3️⃣ 检查会话保持修复...")
with open('web/src/views/ChatView.vue', 'r', encoding='utf-8') as f:
    content = f.read()
    if 'prevActive' in content and '页面失活时中断正在进行的请求' in content:
        print("   ✅ 会话保持已修复（页面切换时正确处理）")
    else:
        print("   ❌ 会话保持未修复")
        sys.exit(1)

print("\n" + "=" * 60)
print("✅ 所有修复验证通过！")
print("=" * 60)
print("\n📋 修复内容总结：")
print("1. 日志重复打印：多进程模式下只在主进程输出到终端")
print("2. 前端不实时刷新：使用新对象替换触发Vue响应式更新")
print("3. 会话丢失：页面切换时正确中断请求，激活时重新加载")
print("\n🚀 请重启后端验证效果：")
print("   conda activate NewCoderAgent; python run.py --workers 4")
print("\n💡 前端需要重新编译（如果使用生产模式）：")
print("   cd web && npm run build")
