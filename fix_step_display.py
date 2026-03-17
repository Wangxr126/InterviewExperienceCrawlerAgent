#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复前端 step 显示逻辑"""

file_path = 'web/src/views/ChatView.vue'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到 computeStepDisplay 函数的起始行
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'function computeStepDisplay(thinking, idx)' in line:
        start_idx = i
    if start_idx is not None and i > start_idx and line.strip() == '}':
        end_idx = i
        break

if start_idx is not None and end_idx is not None:
    # 替换函数体
    new_func = '''function computeStepDisplay(thinking, idx) {
  const step = thinking[idx]
  if (!step) return idx + 1
  // 优先使用后端的 __step 值（已验证正确）
  if (typeof step.__step === 'number' && step.__step > 0) {
    return step.__step
  }
  // 降级：按数组位置计算（兼容旧数据）
  let num = 0
  for (let i = 0; i <= idx; i++) {
    if (thinking[i].__step !== 'pending') num++
  }
  return num
}
'''
    
    # 保留前面的注释
    comment_start = start_idx - 4
    while comment_start >= 0 and (lines[comment_start].strip().startswith('*') or lines[comment_start].strip().startswith('/**')):
        comment_start -= 1
    comment_start += 1
    
    # 构建新的行列表
    new_lines = lines[:comment_start]
    new_lines.append('/**\n')
    new_lines.append(' * 计算步骤的显示序号：直接使用后端传来的 __step 值\n')
    new_lines.append(' * 后端已经保证 __step 是正确的步号，无需重新计算\n')
    new_lines.append(' * ✅ 修复：后端推送 step=1 时，前端直接显示"第 1 步"，不再错位\n')
    new_lines.append(' */\n')
    new_lines.append(new_func)
    new_lines.extend(lines[end_idx+1:])
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print('✅ computeStepDisplay 函数已修复')
else:
    print('❌ 找不到 computeStepDisplay 函数')
