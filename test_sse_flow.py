#!/usr/bin/env python3
"""
完整 SSE 流式测试：后端 → 前端
验证每一步的数据格式和传输
"""
import asyncio
import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def test_orchestrator_stream():
    """测试 orchestrator.chat_stream() 的输出"""
    print("\n" + "="*60)
    print("🔍 测试 1: orchestrator.chat_stream() 输出")
    print("="*60)
    
    from backend.agents.orchestrator import get_orchestrator
    
    orchestrator = get_orchestrator()
    
    print("\n📤 发送消息: '出一道 Python 面试题'")
    print("⏳ 等待流式响应...\n")
    
    event_count = 0
    chunk_count = 0
    
    async for sse_line in orchestrator.chat_stream(
        user_id="test_user",
        message="出一道 Python 面试题",
        session_id="test_session_001"
    ):
        event_count += 1
        
        # 打印原始 SSE 行
        print(f"\n[事件 #{event_count}]")
        print(f"  原始行: {repr(sse_line[:100])}")
        
        # 解析 SSE 格式
        if isinstance(sse_line, bytes):
            sse_line = sse_line.decode('utf-8')
        
        lines = sse_line.strip().split('\n')
        event_type = None
        data_line = None
        
        for line in lines:
            if line.startswith('event: '):
                event_type = line[7:]
            elif line.startswith('data: '):
                data_line = line[6:]
        
        if data_line:
            try:
                payload = json.loads(data_line)
                print(f"  事件类型: {payload.get('type', event_type)}")
                
                if payload.get('type') == 'llm_chunk':
                    chunk = payload.get('data', {}).get('chunk', '')
                    if chunk:
                        chunk_count += 1
                        print(f"  📝 Chunk #{chunk_count}: {repr(chunk[:50])}")
                elif payload.get('type') == 'agent_finish':
                    result = payload.get('data', {}).get('result', '')
                    print(f"  ✅ 完成: {repr(result[:100])}")
                else:
                    print(f"  数据: {str(payload.get('data', {}))[:100]}")
            except json.JSONDecodeError as e:
                print(f"  ❌ JSON 解析失败: {e}")
                print(f"  原始数据: {repr(data_line[:100])}")
        
        if event_count >= 20:  # 限制输出
            print(f"\n... (已显示前 20 个事件，继续接收中...)")
            break
    
    print(f"\n✅ 流式完成！共接收 {event_count} 个事件，{chunk_count} 个 chunk")


async def test_http_stream():
    """测试 HTTP 流式接口"""
    print("\n" + "="*60)
    print("🔍 测试 2: HTTP /api/chat/stream 接口")
    print("="*60)
    
    import aiohttp
    
    payload = {
        "user_id": "test_user",
        "message": "出一道 Python 面试题",
        "session_id": "test_session_002"
    }
    
    print(f"\n📤 POST http://localhost:8000/api/chat/stream")
    print(f"   payload: {json.dumps(payload, ensure_ascii=False)}")
    print("⏳ 等待流式响应...\n")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'http://localhost:8000/api/chat/stream',
                json=payload,
                headers={'Accept': 'text/event-stream'}
            ) as resp:
                print(f"📊 HTTP 状态: {resp.status}")
                print(f"📋 响应头:")
                for k, v in resp.headers.items():
                    if k.lower() in ['content-type', 'cache-control', 'connection', 'x-accel-buffering']:
                        print(f"   {k}: {v}")
                
                event_count = 0
                chunk_count = 0
                buffer = ''
                
                async for chunk in resp.content.iter_any():
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode('utf-8')
                    
                    buffer += chunk
                    
                    # 按 \n\n 分割事件
                    while '\n\n' in buffer:
                        event_block, buffer = buffer.split('\n\n', 1)
                        
                        if not event_block.strip():
                            continue
                        
                        event_count += 1
                        print(f"\n[事件 #{event_count}]")
                        print(f"  原始块: {repr(event_block[:80])}")
                        
                        # 解析
                        event_type = None
                        data_line = None
                        
                        for line in event_block.split('\n'):
                            if line.startswith('event: '):
                                event_type = line[7:]
                            elif line.startswith('data: '):
                                data_line = line[6:]
                        
                        if data_line:
                            try:
                                payload_obj = json.loads(data_line)
                                print(f"  事件类型: {payload_obj.get('type', event_type)}")
                                
                                if payload_obj.get('type') == 'llm_chunk':
                                    chunk_text = payload_obj.get('data', {}).get('chunk', '')
                                    if chunk_text:
                                        chunk_count += 1
                                        print(f"  📝 Chunk #{chunk_count}: {repr(chunk_text[:50])}")
                                elif payload_obj.get('type') == 'agent_finish':
                                    result = payload_obj.get('data', {}).get('result', '')
                                    print(f"  ✅ 完成: {repr(result[:100])}")
                            except json.JSONDecodeError as e:
                                print(f"  ❌ JSON 解析失败: {e}")
                        
                        if event_count >= 20:
                            print(f"\n... (已显示前 20 个事件)")
                            return
                
                print(f"\n✅ HTTP 流式完成！共接收 {event_count} 个事件，{chunk_count} 个 chunk")
    
    except Exception as e:
        print(f"❌ HTTP 请求失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("\n" + "="*60)
    print("🚀 SSE 流式完整诊断")
    print("="*60)
    
    # 测试 1: orchestrator 直接输出
    try:
        await test_orchestrator_stream()
    except Exception as e:
        print(f"\n❌ 测试 1 失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试 2: HTTP 接口
    try:
        await test_http_stream()
    except Exception as e:
        print(f"\n❌ 测试 2 失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
