#!/usr/bin/env python3
"""
诊断脚本：测试流式输出中是否正确发送 thinking 事件
"""
import asyncio
import json
import aiohttp
import sys

async def test_stream():
    """测试流式对话，检查 thinking 事件"""
    url = "http://localhost:8000/api/chat/stream"
    payload = {
        "user_id": "test_user",
        "message": "出一道 Python 面试题",
        "session_id": "test_session"
    }
    
    print("=" * 60)
    print("🧪 测试流式输出中的 thinking 事件")
    print("=" * 60)
    print(f"请求 URL: {url}")
    print(f"请求体: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    print("=" * 60)
    
    thinking_count = 0
    llm_chunk_count = 0
    tool_call_count = 0
    event_count = 0
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    print(f"❌ HTTP {resp.status}: {await resp.text()}")
                    return
                
                print(f"✅ 连接成功，开始接收流式数据...")
                print("=" * 60)
                
                buffer = ""
                async for chunk in resp.content.iter_any():
                    if not chunk:
                        continue
                    
                    buffer += chunk.decode('utf-8', errors='replace')
                    
                    # 按 \n\n 分割 SSE 事件
                    lines = buffer.split('\n\n')
                    buffer = lines.pop() or ""
                    
                    for event_block in lines:
                        if not event_block.strip():
                            continue
                        
                        event_count += 1
                        event_type = ""
                        data_line = ""
                        
                        for line in event_block.split('\n'):
                            if line.startswith('event: '):
                                event_type = line[7:]
                            elif line.startswith('data: '):
                                data_line = line[6:]
                        
                        if not data_line:
                            continue
                        
                        try:
                            payload_data = json.loads(data_line)
                            
                            if event_type == "thinking":
                                thinking_count += 1
                                chunk_text = payload_data.get("chunk", "")[:100]
                                print(f"🧠 [{thinking_count}] THINKING 事件: step={payload_data.get('step')}, chunk='{chunk_text}...'")
                            
                            elif event_type == "llm_chunk":
                                llm_chunk_count += 1
                                chunk_text = payload_data.get("chunk", "")[:50]
                                if llm_chunk_count % 10 == 0:
                                    print(f"📝 [{llm_chunk_count}] LLM_CHUNK 事件: '{chunk_text}...'")
                            
                            elif event_type == "tool_call_start":
                                tool_call_count += 1
                                tool_name = payload_data.get("tool_name", "")
                                print(f"🔧 [{tool_call_count}] TOOL_CALL_START: {tool_name}")
                            
                            elif event_type == "agent_finish":
                                print(f"✅ AGENT_FINISH: 完成")
                            
                            else:
                                print(f"📨 [{event_count}] {event_type.upper()}: {list(payload_data.keys())}")
                        
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON 解析失败: {e}")
                            print(f"   data_line: {data_line[:100]}")
                
                print("=" * 60)
                print(f"📊 统计结果:")
                print(f"   总事件数: {event_count}")
                print(f"   🧠 thinking 事件: {thinking_count}")
                print(f"   📝 llm_chunk 事件: {llm_chunk_count}")
                print(f"   🔧 tool_call 事件: {tool_call_count}")
                print("=" * 60)
                
                if thinking_count == 0:
                    print("⚠️  警告：没有收到任何 thinking 事件！")
                    print("   这可能意味着：")
                    print("   1. 后端没有发送 thinking 事件")
                    print("   2. hello_agents 框架没有产生 thinking 类型的事件")
                    print("   3. 检查后端日志中是否有 '[chat_stream] 🧠' 的日志")
                else:
                    print(f"✅ 成功接收 {thinking_count} 个 thinking 事件！")
    
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_stream())
