"""
SqliteSessionStore - hello_agents SessionStore 的 SQLite 实现

将 hello_agents 的会话持久化能力与项目现有的 interview_sessions 表对齐。
- save/load 使用 SQLite，而非 JSON 文件
- 路径格式：load("user_id:session_id")，save 时从 context 获取 user_id/session_id
- conversation_history 与 Message.to_dict/from_dict 格式兼容
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from hello_agents.core.message import Message

from backend.agents.context import get_current_user_id, get_current_session_id
from backend.services.storage.sqlite_service import sqlite_service

logger = logging.getLogger(__name__)


def _normalize_msg_for_message(msg: dict) -> dict:
    """将存储格式转为 Message.from_dict 兼容格式，保留 thinking/duration_ms 供前端展示"""
    role = msg.get("role") or "user"
    content = msg.get("content") or ""
    ts = msg.get("timestamp") or msg.get("ts")
    if isinstance(ts, str):
        try:
            ts = ts.replace("Z", "+00:00")
        except Exception:
            ts = None
    out = {"role": role, "content": content}
    if ts:
        out["timestamp"] = ts
    if msg.get("metadata"):
        out["metadata"] = msg.get("metadata")
    # 保留推理过程与耗时，供 get_chat_history 返回给前端
    if msg.get("thinking"):
        out["thinking"] = msg["thinking"]
    if msg.get("duration_ms") is not None:
        out["duration_ms"] = msg["duration_ms"]
    return out


def _message_to_storage(msg: Any) -> dict:
    """Message 转为存储格式（兼容现有 conversation_history），含 thinking/duration_ms"""
    if hasattr(msg, "to_dict"):
        d = msg.to_dict()
    else:
        d = dict(msg) if isinstance(msg, dict) else {}
    out = {
        "role": d.get("role", "user"),
        "content": d.get("content", ""),
        "timestamp": d.get("timestamp"),
        "ts": d.get("timestamp") or datetime.now().isoformat(),
    }
    # 🔧 关键修复：确保 thinking 字段被保存（即使为空列表也要保存）
    if "thinking" in d:
        out["thinking"] = d["thinking"]
    elif d.get("thinking") is not None:
        out["thinking"] = d["thinking"]
    if d.get("duration_ms") is not None:
        out["duration_ms"] = d["duration_ms"]
    return out


class SqliteSessionStore:
    """
    hello_agents SessionStore 接口的 SQLite 实现。

    与 SessionStore 兼容的接口：save, load, list_sessions, check_config_consistency,
    check_tool_schema_consistency。

    路径约定：load(filepath) 的 filepath 格式为 "user_id:session_id"
    """

    def __init__(self, session_dir: str = "sqlite", sqlite_service_instance=None):
        """
        Args:
            session_dir: 保留参数（兼容 hello_agents），实际使用 SQLite
            sqlite_service_instance: 可注入的 sqlite 服务，默认用全局 sqlite_service
        """
        self.session_dir = Path(session_dir)
        self._sqlite = sqlite_service_instance or sqlite_service

    def save(
        self,
        agent_config: Dict[str, Any],
        history: List[Any],
        tool_schema_hash: str,
        read_cache: Dict[str, Dict],
        metadata: Dict[str, Any],
        session_name: Optional[str] = None,
    ) -> str:
        """保存会话到 SQLite interview_sessions 表"""
        from backend.config.config import settings as _settings
        user_id = get_current_user_id()
        session_id = get_current_session_id() or session_name
        if not session_id:
            session_id = session_name or _settings.default_session_id

        self._sqlite.ensure_session_exists(session_id, user_id)

        # 转为 conversation_history 格式
        history_data = [_message_to_storage(m) for m in history]

        # 合并已有推理过程：save_session 会覆盖整段 history，仅对「已存在的」assistant 保留 thinking。
        # 这里必须“从尾部对齐”而不是从头对齐：history 可能被裁剪为最近 N 轮，若从头对齐会把旧前缀错配到新历史，
        # 导致最近消息上的 thinking 被覆盖丢失。
        try:
            session = self._sqlite.get_session(session_id)
            old_history = session.get("conversation_history") or []
            assistant_indices = [i for i, m in enumerate(history_data) if m.get("role") == "assistant"]
            old_assistant_indices = [i for i, m in enumerate(old_history) if (m or {}).get("role") == "assistant"]
            pair_count = min(len(assistant_indices), len(old_assistant_indices))
            for offset in range(1, pair_count + 1):
                idx = assistant_indices[-offset]
                old_idx = old_assistant_indices[-offset]
                old_msg = old_history[old_idx] if isinstance(old_history[old_idx], dict) else {}
                if old_msg.get("thinking") and not history_data[idx].get("thinking"):
                    history_data[idx]["thinking"] = old_msg["thinking"]
                if old_msg.get("duration_ms") is not None and history_data[idx].get("duration_ms") is None:
                    history_data[idx]["duration_ms"] = old_msg["duration_ms"]
        except Exception as e:
            logger.debug(f"[SqliteSessionStore] 合并 thinking 时忽略: {e}")

        # 🔧 调试日志：检查 thinking 数据是否被正确保存
        for i, msg in enumerate(history_data):
            if msg.get("role") == "assistant":
                thinking_count = len(msg.get("thinking", [])) if msg.get("thinking") else 0
                logger.info(f"[SqliteSessionStore.save] 消息 #{i} (assistant): thinking={thinking_count} 步, content_len={len(msg.get('content', ''))}")

        # session_meta：hello_agents 扩展字段
        session_meta = {
            "agent_config": agent_config,
            "tool_schema_hash": tool_schema_hash,
            "read_cache": read_cache,
            "saved_at": datetime.now().isoformat(),
        }

        with self._sqlite._get_conn() as conn:
            conn.execute(
                """
                UPDATE interview_sessions
                SET conversation_history = ?,
                    session_meta = ?
                WHERE session_id = ?
                """,
                (
                    json.dumps(history_data, ensure_ascii=False),
                    json.dumps(session_meta, ensure_ascii=False),
                    session_id,
                ),
            )
            conn.commit()

        logger.debug(f"[SqliteSessionStore] 已保存 session_id={session_id} user_id={user_id}")
        return f"{user_id}:{session_id}"

    def load(self, filepath: str) -> Dict[str, Any]:
        """从 SQLite 加载会话。filepath 格式：user_id:session_id"""
        parts = filepath.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"无效的 session 路径格式，应为 user_id:session_id: {filepath}")

        user_id, session_id = parts[0], parts[1]
        session = self._sqlite.get_session(session_id)
        if not session:
            raise FileNotFoundError(f"Session 不存在: {session_id}")
        if str(session.get("user_id", "")) != str(user_id):
            logger.warning(f"Session user_id 不匹配: 期望 {user_id}, 实际 {session.get('user_id')}")

        history_raw = session.get("conversation_history") or []
        history = [
            _normalize_msg_for_message(m) if isinstance(m, dict) else m
            for m in history_raw
        ]

        # 🔧 调试日志：检查加载的 thinking 数据
        for i, msg in enumerate(history):
            if msg.get("role") == "assistant":
                thinking_count = len(msg.get("thinking", [])) if msg.get("thinking") else 0
                logger.info(f"[SqliteSessionStore.load] 消息 #{i} (assistant): thinking={thinking_count} 步, content_len={len(msg.get('content', ''))}")

        # 从 session_meta 解析 hello_agents 元数据
        session_meta = {}
        try:
            meta_str = session.get("session_meta")
            if meta_str and isinstance(meta_str, str) and meta_str.strip().startswith("{"):
                session_meta = json.loads(meta_str)
        except Exception:
            pass

        return {
            "session_id": session_id,
            "created_at": session.get("start_time") or datetime.now().isoformat(),
            "saved_at": session_meta.get("saved_at", datetime.now().isoformat()),
            "agent_config": session_meta.get("agent_config", {}),
            "history": history,
            "tool_schema_hash": session_meta.get("tool_schema_hash", ""),
            "read_cache": session_meta.get("read_cache", {}),
            "metadata": {
                "total_tokens": session_meta.get("metadata", {}).get("total_tokens", 0),
                "total_steps": session_meta.get("metadata", {}).get("total_steps", 0),
                "duration_seconds": session_meta.get("metadata", {}).get("duration_seconds", 0),
                "created_at": session.get("start_time"),
            },
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出当前用户的会话（从 context 获取 user_id）"""
        user_id = get_current_user_id()
        with self._sqlite._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT session_id, start_time, end_time
                FROM interview_sessions
                WHERE user_id = ?
                ORDER BY start_time DESC
                LIMIT 50
                """,
                (user_id,),
            ).fetchall()

        return [
            {
                "filename": f"{r['session_id']}.json",
                "filepath": f"{user_id}:{r['session_id']}",
                "session_id": r["session_id"],
                "created_at": r["start_time"],
                "saved_at": r["start_time"],
                "metadata": {},
            }
            for r in rows
        ]

    def check_config_consistency(
        self,
        saved_config: Dict[str, Any],
        current_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """配置一致性检查（与 hello_agents SessionStore 接口一致）"""
        warnings = []
        if saved_config.get("llm_provider") != current_config.get("llm_provider"):
            warnings.append(
                f"LLM 提供商变化: {saved_config.get('llm_provider')} → {current_config.get('llm_provider')}"
            )
        if saved_config.get("llm_model") != current_config.get("llm_model"):
            warnings.append(
                f"模型变化: {saved_config.get('llm_model')} → {current_config.get('llm_model')}"
            )
        if saved_config.get("max_steps") != current_config.get("max_steps"):
            warnings.append(
                f"max_steps 变化: {saved_config.get('max_steps')} → {current_config.get('max_steps')}"
            )
        return {"consistent": len(warnings) == 0, "warnings": warnings}

    def check_tool_schema_consistency(
        self,
        saved_hash: str,
        current_hash: str,
    ) -> Dict[str, Any]:
        """工具 Schema 一致性检查"""
        changed = saved_hash != current_hash
        return {
            "changed": changed,
            "saved_hash": saved_hash,
            "current_hash": current_hash,
            "recommendation": "建议重新读取" if changed else "可安全恢复",
        }
