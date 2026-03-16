#!/usr/bin/env python3
"""
快速测试脚本：验证修复是否生效
运行方式：python test_fix.py
"""
import subprocess
import time
import sqlite3
import json
from pathlib import Path

def check_backend_running():
    """检查后端是否运行"""
    try:
        import requests
        resp = requests.get("http://localhost:8000/api/config", timeout=2)
        return resp.status_code == 200
    except:
        return False

def get_latest_session():
    """获取最新的 session"""
    db_path = Path(__file__).parent / "backend" / "data" / "interview.db"
    if not db_path.exists():
        return None
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT session_id, conversation_history 
        FROM interview_sessions 
        ORDER BY created_at DESC 
        LIMIT 1
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    history = json.loads(row["conversation_history"] or "[]")
    return {
        "session_id": row["session_id"],
        "messages": history
    }

def test_database_persistence():
    """测试数据库持久化"""
    print("\n" + "="*80)
    print("🧪 测试 1: 数据库持久化")
    print("="*80)
    
    session = get_latest_session()
    if not session:
        print("❌ 没有找到任何 session")
        return False
    
    print(f"✅ 找到 session: {session['session_id']}")
    print(f"   消息数: {len(session['messages'])}")
    
    # 检查是否有 user 和 assistant 消息
    has_user = any(m.get("role") == "user" for m in session["messages"])
    has_assistant = any(m.get("role") == "assistant" for m in session["messages"])
    
    print(f"   User 消息: {'✅' if has_user else '❌'}")
    print(f"   Assistant 消息: {'✅' if has_assistant else '❌'}")
    
    if has_assistant:
        assistant_msg = next(m for m in session["messages"] if m.get("role") == "assistant")
        content = assistant_msg.get("content", "")
        thinking = assistant_msg.get("thinking", [])
        
        print(f"\n   Assistant 消息内容:")
        print(f"     - 文本长度: {len(content)} 字符")
        print(f"     - 推理步骤: {len(thinking)} 步")
        
        if content and content != "（生成中...）":
            print(f"     - 内容预览: {content[:100]}...")
            return True
        elif thinking:
            print(f"     - 有推理过程，但无文本内容")
            return True
        else:
            print(f"     - ❌ 内容为空且无推理过程")
            return False
    
    return False

def main():
    print("\n🚀 开始测试修复...")
    print()
    
    # 检查后端
    print("📡 检查后端状态...")
    if not check_backend_running():
        print("❌ 后端未运行，请先启动: python run.py")
        return False
    print("✅ 后端运行中")
    
    # 测试数据库
    success = test_database_persistence()
    
    print("\n" + "="*80)
    if success:
        print("✅ 修复验证成功！")
        print("\n📝 下一步：")
        print("  1. 打开浏览器访问 http://localhost:5173")
        print("  2. 发送一条测试消息")
        print("  3. 等待流式完成")
        print("  4. 刷新页面 (Ctrl+R)")
        print("  5. 检查内容是否保留")
    else:
        print("❌ 修复验证失败")
        print("\n💡 排查步骤：")
        print("  1. 检查后端日志: tail -f backend.log")
        print("  2. 运行诊断脚本: python debug_db.py")
        print("  3. 清空数据库重试: rm backend/data/interview.db")
    print("="*80 + "\n")
    
    return success

if __name__ == "__main__":
    main()
