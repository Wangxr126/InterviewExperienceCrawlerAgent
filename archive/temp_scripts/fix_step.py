#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""修复 tool_call_finish 中的 step 推送错误"""

import re

with open('backend/agents/interviewer_agent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换逻辑：在 tool_call_finish 处理中，添加 target_step_no 变量来正确追踪步号
old_code = '''                        ev_step_no = int(event.data.get("step") or 0)
                        if ev_step_no == 0:
                            # step 字段缺失：首次工具调用时初始化为1，后续保持不变
                            if _current_step_no == 0:
                                _current_step_no = 1
                        elif ev_step_no != _current_step_no:
                            # step 编号变化：提交旧步，开启新步
                            if _current_step_no > 0 and (current_step.get("thought") or current_step.get("tools")):
                                current_step["__step"] = _current_step_no
                                thinking_steps.append({k: v for k, v in current_step.items() if v})
                            current_step = {"tools": []}
                            _current_step_no = ev_step_no
                        if "tools" not in current_step:
                            current_step["tools"] = []
                        current_step["tools"].append({
                            "name": f"🔧 {tool_name}",
                            "args": tool_args if isinstance(tool_args, dict) else {},
                            "observation": obs_str,
                            "observationIsJson": _is_obs_json(obs_str),
                        })'''

new_code = '''                        ev_step_no = int(event.data.get("step") or 0)
                        target_step_no = _current_step_no  # 默认归属当前步
                        if ev_step_no == 0:
                            # step 字段缺失：首次工具调用时初始化为1，后续保持不变
                            if _current_step_no == 0:
                                _current_step_no = 1
                            target_step_no = _current_step_no
                        elif ev_step_no != _current_step_no:
                            # step 编号变化：提交旧步，开启新步
                            if _current_step_no > 0 and (current_step.get("thought") or current_step.get("tools")):
                                current_step["__step"] = _current_step_no
                                thinking_steps.append({k: v for k, v in current_step.items() if v})
                            current_step = {"tools": []}
                            _current_step_no = ev_step_no
                            target_step_no = ev_step_no  # ✅ 工具归属新步
                        if "tools" not in current_step:
                            current_step["tools"] = []
                        current_step["tools"].append({
                            "name": f"🔧 {tool_name}",
                            "args": tool_args if isinstance(tool_args, dict) else {},
                            "observation": obs_str,
                            "observationIsJson": _is_obs_json(obs_str),
                            "step": target_step_no,  # ✅ 显式记录工具所属的步号
                        })'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('backend/agents/interviewer_agent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('✅ 修复完成！已更新 tool_call_finish 中的 step 推送逻辑')
else:
    print('❌ 未找到目标代码，可能已修复或代码结构不同')
    print('尝试查找关键字符串...')
    if 'ev_step_no = int(event.data.get("step") or 0)' in content:
        print('✓ 找到 ev_step_no 初始化')
    if 'current_step["tools"].append({' in content:
        print('✓ 找到 tools.append')
