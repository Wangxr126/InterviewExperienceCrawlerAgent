#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复流式推送中的三个问题：
1. step和工具不对应
2. 答案被推送到工具调用位置
3. final_answer保存错误
"""

import re

def fix_issue_2_and_3():
    """修复问题2和3：分离result和thinking_steps"""
    with open('backend/agents/interviewer_agent.py', 'r', encoding='utf-8') as f:
        content = f.read()

    old_code = """                            # ✅ 兜底：result 为空时，从 full_content 或 thinking_steps 最后一步的 thought 提取
                            # 原因：DeepSeek 等模型有时把最终答案写在 reasoning_content（thinking）而非 content，
                            # 导致 agent_finish.result 为空，前端显示空白。
                            if not d.get('result') and not full_content.strip():
                                fallback = ''
                                # 优先取最后一步的 thought（DeepSeek 把答案写在思考里的场景）
                                if thinking_steps:
                                    last_thought = thinking_steps[-1].get('thought', '')
                                    if last_thought and last_thought.strip():
                                        fallback = last_thought.strip()
                                if fallback:
                                    d['result'] = fallback
                                    full_content = fallback
                                    logger.info(f'[chat_stream] agent_finish.result 为空，已从 thinking 兜底 ({len(fallback)}字)')
                            elif not d.get('result') and full_content.strip():
                                d['result'] = full_content.strip()"""

    new_code = """                            # ✅ 修复：result 优先使用 full_content（llm_chunk 累积的最终答案）
                            # 不从 thinking_steps 提取，避免把推理内容当成最终答案
                            if not d.get('result'):
                                if full_content.strip():
                                    d['result'] = full_content.strip()
                                else:
                                    # 仅当 full_content 完全为空时，才用占位符
                                    d['result'] = "（无文本回答，仅有推理过程）"
                                    logger.warning(f'[chat_stream] agent_finish.result 为空，使用占位符')"""

    if old_code in content:
        content = content.replace(old_code, new_code)
        with open('backend/agents/interviewer_agent.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ 修复成功：问题2和3 - 分离result和thinking_steps")
        return True
    else:
        print("❌ 未找到要替换的代码（问题2和3）")
        return False

def fix_issue_1():
    """修复问题1：重构step编号追踪逻辑"""
    with open('backend/agents/interviewer_agent.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 修复tool_call_finish中的step检测逻辑
    old_step_logic = """                        # 检测步骤切换（兜底，step_start 未触发时）：
                        # ev_step_no=0 表示 step 字段缺失，不触发步骤切换，所有工具归属当前步。
                        # ev_step_no 变化时才切换，但要先把 current_step 并入已有对应步（避免并发工具丢失）。
                        ev_step_no = int(event.data.get("step") or 0)
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
                            target_step_no = ev_step_no  # ✅ 工具归属新步"""

    new_step_logic = """                        # ✅ 修复：严格的step编号同步
                        # 从event.data获取step编号，确保与后端一致
                        ev_step_no = int(event.data.get("step") or _current_step_no or 1)
                        
                        # 检测步骤切换
                        if ev_step_no != _current_step_no:
                            # 步编号变化：提交旧步，开启新步
                            if _current_step_no > 0 and (current_step.get("thought") or current_step.get("tools")):
                                current_step["__step"] = _current_step_no
                                thinking_steps.append({k: v for k, v in current_step.items() if v})
                            current_step = {"tools": []}
                            _current_step_no = ev_step_no
                        
                        target_step_no = _current_step_no"""

    if old_step_logic in content:
        content = content.replace(old_step_logic, new_step_logic)
        with open('backend/agents/interviewer_agent.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ 修复成功：问题1 - 重构step编号追踪逻辑")
        return True
    else:
        print("⚠️  问题1的代码块可能已修改，跳过")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("开始修复流式推送问题...")
    print("=" * 60)
    
    success = True
    success = fix_issue_2_and_3() and success
    success = fix_issue_1() and success
    
    if success:
        print("\n" + "=" * 60)
        print("✅ 所有修复完成！")
        print("=" * 60)
    else:
        print("\n⚠️  部分修复失败，请手动检查")
