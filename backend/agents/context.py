"""
Agent 运行时上下文（线程安全）

在 Orchestrator.chat() 中调用 set_current_user_id() / set_current_session_id()，
工具里通过 get_current_user_id() / get_current_session_id() 获取。
当前轮用户消息由 chat_stream 设置，供 submit_answer 在未传 user_answer 时使用。
"""
import os
import threading

_local = threading.local()


def _get_default_user_id() -> str:
    """与 backend.config 的 default_user_id 一致，避免工具内取到 user_001"""
    return os.getenv("DEFAULT_USER_ID", "Wangxr")


def set_current_user_id(uid: str) -> None:
    _local.user_id = uid


def get_current_user_id() -> str:
    return getattr(_local, "user_id", None) or _get_default_user_id()


def set_current_session_id(sid: str) -> None:
    _local.session_id = sid


def get_current_session_id() -> str:
    return getattr(_local, "session_id", "")


def set_current_user_message(msg: str) -> None:
    """当前轮用户输入，供 submit_answer 在未传 user_answer 时使用"""
    _local.current_user_message = msg


def get_current_user_message() -> str:
    return getattr(_local, "current_user_message", "") or ""
