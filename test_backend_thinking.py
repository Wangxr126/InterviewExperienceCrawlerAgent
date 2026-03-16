#!/usr/bin/env python3
"""
诊断脚本：检查后端是否真的在发送 thinking 事件（带超时）
"""
import asyncio
import json
import sys
sys.path.insert(0, '/e/Agent/AgentProject/wxr_agent')

async def test_stream():
    from backend.agents.interviewer_agent import get_orchestrator
    orchestrator = get_orchestrator()
    
    print("=" * 60)
    print("测试后端流式输出中的 thinking 事件")
    print("=" * 60)
    
    user_id = "test_user"
    message = "你好"  # 简单问候，不需要出题
    
    event_count = 0
    thinking_count = 0
    
    try:
        print(f"\n[开始] 发送消息: {message}")
        
        async for sse_line in orchestrator.chat_stream(
            user_id=user_id,
            message=message,
            session_id="test_session"
        ):
            event_count += 1
            
            # 解析 SSE 格式
            if isinstance(sse_line, str):
                lines = sse_line.split('\n')
                event_type = ''
                data_line = ''
                
                for line in lines:
                    if line.startswith('event: '):
                        event_type = line[7:]
                    elif line.startswith('data: '):
                        data_line = line[6:]
                
                print(f"[事件 #{event_count}] type={event_type}")
                
                if event_type == 'thinking':
                    thinking_count += 1
                    print(f"  ✓ 这是 thinking 事件 #{thinking_count}")
                    if data_line:
                        try:
                            data = json.loads(data_line)
                            print(f"    step: {data.get('step')}")
                            chunk = data.get('chunk', '')
                            print(f"    chunk: {chunk[:80]}...")
                        except Exception as e:
                            print(f"    解析失败: {e}")
                
                if event_count >= 50:  # 限制输出
                    print(f"\n[限制] 已显示 50 个事件，继续接收...")
                    break
        
        print("\n" + "=" * 60)
        print(f"流式完成！")
        print(f"总事件数: {event_count}")
        print(f"thinking 事件数: {thinking_count}")
        print("=" * 60)
        
        if thinking_count == 0:
            print("\n❌ 问题确认：后端没有发送任何 thinking 事件！")
            print("\n可能的原因：")
            print("1. hello_agents 的 arun_stream() 没有生成 thinking 事件")
            print("2. stream_include_thinking 配置没有生效")
            print("3. LLM 模型不支持 thinking 模式")
        else:
            print(f"\n✓ 后端正在发送 thinking 事件（共 {thinking_count} 个）")
            print("问题可能在前端处理逻辑")
    
    except asyncio.TimeoutError:
        print(f"\n⏱️ 超时！已接收 {event_count} 个事件，其中 {thinking_count} 个 thinking 事件")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(test_stream(), timeout=30))
    except asyncio.TimeoutError:
        print("\n⏱️ 总体超时（30秒）")
