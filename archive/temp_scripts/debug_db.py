#!/usr/bin/env python3
"""
诊断脚本：检查数据库中的对话历史是否被正确保存
"""
import sqlite3
import json
from pathlib import Path

# 数据库路径
db_path = Path(__file__).parent / "backend" / "data" / "interview.db"

if not db_path.exists():
    print(f"❌ 数据库不存在: {db_path}")
    exit(1)

print(f"✅ 数据库路径: {db_path}")
print()

# 连接数据库
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 查询最新的 session
cursor.execute("""
    SELECT session_id, user_id, created_at, conversation_history 
    FROM interview_sessions 
    ORDER BY created_at DESC 
    LIMIT 5
""")

sessions = cursor.fetchall()

if not sessions:
    print("❌ 数据库中没有任何 session")
    exit(1)

print(f"📋 最近 5 个 session：\n")

for i, session in enumerate(sessions, 1):
    session_id = session["session_id"]
    user_id = session["user_id"]
    created_at = session["created_at"]
    history_json = session["conversation_history"]
    
    print(f"{'='*80}")
    print(f"Session #{i}")
    print(f"  ID: {session_id}")
    print(f"  User: {user_id}")
    print(f"  Created: {created_at}")
    
    try:
        history = json.loads(history_json or "[]")
        print(f"  消息数: {len(history)}")
        print()
        
        for j, msg in enumerate(history, 1):
            role = msg.get("role", "?")
            content = msg.get("content", "")[:100]
            ts = msg.get("timestamp") or msg.get("ts", "?")
            thinking = msg.get("thinking", [])
            
            print(f"    消息 #{j}: [{role}]")
            print(f"      内容: {content}{'...' if len(msg.get('content', '')) > 100 else ''}")
            print(f"      时间: {ts}")
            if thinking:
                print(f"      推理步骤: {len(thinking)} 步")
            print()
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON 解析失败: {e}")
        print()

conn.close()
print("✅ 诊断完成")
