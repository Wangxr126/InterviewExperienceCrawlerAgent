"""
Interviewer 工具调用统计（运行时实时版）

来源：
- hello-agents 执行过程中的工具调用事件
- 按 agent 聚合，不读取 tools_*.jsonl 日志
"""

from __future__ import annotations

from typing import Dict, Any, Optional

from backend.services.logging.agent_tool_runtime_stats import agent_tool_runtime_stats


def get_interviewer_tool_usage(user_id: Optional[str] = None, days: int = 365) -> Dict[str, Any]:
    # days 参数保留仅用于兼容旧前端调用，实时模式不使用该参数过滤
    data = agent_tool_runtime_stats.snapshot(user_id=user_id)
    data["days"] = days
    return data

