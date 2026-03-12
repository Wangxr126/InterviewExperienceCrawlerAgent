"""
Agent 运行时上下文（线程安全）

在 Orchestrator.chat() 中调用 set_current_user_id() / set_current_session_id()，
工具里通过 get_current_user_id() / get_current_session_id() 获取。
"""
import threading

_local = threading.local()
_default_user_id = "user_001"


def set_current_user_id(uid: str) -> None:
    _local.user_id = uid


def get_current_user_id() -> str:
    return getattr(_local, "user_id", _default_user_id)


def set_current_session_id(sid: str) -> None:
    _local.session_id = sid


def get_current_session_id() -> str:
    return getattr(_local, "session_id", "")
