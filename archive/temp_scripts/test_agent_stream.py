#!/usr/bin/env python3
"""
直接测试 InterviewerAgent 的 arun_stream()
"""
import asyncio
import sys
sys.path.insert(0, '/e/Agent/AgentProject/wxr_agent')

async def test_agent_stream():
    from backend.agents.interviewer_agent import InterviewerAgent
    
    print("=" * 60)
    print("直接测试 InterviewerAgent.arun_stream()")
    print("=" * 60)
    
    agent = InterviewerAgent(user_id="test_user")
    
    print(f"\n配置检查：")
    print(f"  stream_enabled: {agent.config.stream_enabled}")
    print(f"  stream_include_thinking: {agent.config.stream_include_thinking}")
    print(f"  stream_buffer_size: {agent.config.stream_buffer_size}")
    
    message = "你好"
    
    event_count = 0
    thinking_count = 0
    
    try:
        print(f"\n[开始] 发送消息: {message}")
        
        async for event in agent.arun_stream(message):
            event_count += 1
            event_type = event.type.name if hasattr(event.type, 'name') else str(event.type)
            
            print(f"[事件 #{event_count}] type={event_type}")
            
            if event_type == 'THINKING':
                thinking_count += 1
                print(f"  ✓ 这是 THINKING 事件 #{thinking_count}")
                print(f"    data: {event.data}")
            
            if event_count >= 50:
                print(f"\n[限制] 已显示 50 个事件")
                break
        
        print("\n" + "=" * 60)
        print(f"流式完成！")
        print(f"总事件数: {event_count}")
        print(f"THINKING 事件数: {thinking_count}")
        print("=" * 60)
        
        if thinking_count == 0:
            print("\n❌ hello-agents 没有生成 THINKING 事件")
        else:
            print(f"\n✓ hello-agents 正在生成 THINKING 事件")
    
    except asyncio.TimeoutError:
        print(f"\n⏱️ 超时！已接收 {event_count} 个事件")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(test_agent_stream(), timeout=30))
    except asyncio.TimeoutError:
        print("\n⏱️ 总体超时（30秒）")
