"""
测试面试官 Agent 日志系统

快速验证日志记录功能是否正常
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.interviewer_logger import get_interviewer_logger

def test_logger():
    """测试日志记录器"""
    print("=" * 80)
    print("Test Interviewer Agent Logger")
    print("=" * 80)
    
    # 获取日志记录器
    logger = get_interviewer_logger()
    print(f"\nOK: Logger initialized")
    print(f"  Model: {logger.model_name}")
    print(f"  Log dir: {logger.model_dir}")
    
    # 测试记录对话
    print("\nTest: log_chat...")
    logger.log_chat(
        user_id="test_user",
        session_id="test_session_001",
        user_message="This is a test message",
        ai_response="This is AI test response",
        thinking_steps=[
            {"step": 1, "thought": "test thought", "action": "test_action", "observation": "test result"}
        ],
        metadata={"test": True}
    )
    print("OK: Chat log saved")
    
    # 测试记录推理过程
    print("\nTest: log_thinking...")
    logger.log_thinking(
        user_id="test_user",
        session_id="test_session_001",
        user_message="This is a test message",
        thinking_steps=[
            {"step": 1, "thought": "Step 1", "action": "action1", "observation": "result1"},
            {"step": 2, "thought": "Step 2", "action": "action2", "observation": "result2"}
        ]
    )
    print("OK: Thinking log saved")
    
    # 测试记录工具调用
    print("\nTest: log_tool_call...")
    logger.log_tool_call(
        user_id="test_user",
        session_id="test_session_001",
        tool_name="test_tool",
        tool_input={"param1": "value1"},
        tool_output="Tool output",
        success=True
    )
    print("OK: Tool call log saved")
    
    # 获取统计信息
    print("\nTest: get_stats...")
    stats = logger.get_stats()
    print(f"OK: Stats:")
    print(f"  Model: {stats['model']}")
    print(f"  Log dir: {stats['log_dir']}")
    for log_type, info in stats['files'].items():
        print(f"  {log_type}: {info['entries']} entries")
    
    print("\n" + "=" * 80)
    print("SUCCESS: All tests passed!")
    print("=" * 80)
    print(f"\nLog files location: {logger.model_dir}")
    print("\nView logs with:")
    print(f"  python view_interviewer_logs.py")
    print(f"  python view_interviewer_logs.py --chat")
    print(f"  python view_interviewer_logs.py --thinking")
    print(f"  python view_interviewer_logs.py --tools")

if __name__ == "__main__":
    try:
        test_logger()
    except Exception as e:
        print(f"\nERROR: Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
