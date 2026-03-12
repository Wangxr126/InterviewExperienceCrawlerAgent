#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试脚本：验证 TraceLogger 修复（已归档）
测试多轮对话是否正常工作
运行方式：在项目根目录执行 python archive/scripts/test_chat_fix.py
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

async def test_chat():
    """测试多轮对话"""
    import httpx
    
    base_url = "http://localhost:8000"
    user_id = "test_user_001"
    session_id = f"sess_{int(__import__('time').time() * 1000)}"
    
    messages = [
        "出一道 Redis 面试题",
        "给我讲解上面这道题",
        "换个问法考我",
    ]
    
    async with httpx.AsyncClient(timeout=120) as client:
        for i, msg in enumerate(messages, 1):
            print(f"\n{'='*60}")
            print(f"第 {i} 轮对话")
            print(f"{'='*60}")
            print(f"📤 发送: {msg}")
            
            try:
                # 调用流式接口
                async with client.stream(
                    "POST",
                    f"{base_url}/api/chat/stream",
                    json={
                        "user_id": user_id,
                        "message": msg,
                        "session_id": session_id,
                    }
                ) as resp:
                    if resp.status_code != 200:
                        print(f"❌ HTTP {resp.status_code}")
                        print(await resp.text())
                        continue
                    
                    print(f"✅ 连接成功 (HTTP {resp.status_code})")
                    
                    # 读取流式响应
                    reply = ""
                    thinking_count = 0
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                payload = json.loads(line[6:])
                                if payload.get("thinking"):
                                    thinking_count = len(payload["thinking"])
                                    print(f"   🧠 思考步骤: {thinking_count}")
                                elif payload.get("delta"):
                                    reply += payload["delta"]
                                elif payload.get("done"):
                                    print(f"   ⏱️  耗时: {payload.get('duration_ms', 0)}ms")
                            except json.JSONDecodeError:
                                pass
                    
                    print(f"📥 回复 ({len(reply)} 字):")
                    print(f"   {reply[:100]}...")
                    
            except Exception as e:
                print(f"❌ 错误: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("✅ 测试完成！如果所有轮次都成功，说明修复有效。")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(test_chat())
