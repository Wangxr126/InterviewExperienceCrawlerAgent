"""
将历史会话清洗并迁移到 .env 默认 user/session。

目标：
1) 把历史消息统一到 DEFAULT_USER_ID + DEFAULT_SESSION_ID
2) 清洗为当前前端可展示的兼容格式
3) 保留尽量多的有效历史（包含 thinking）

用法：
  conda activate NewCoderAgent
  python -m backend.scripts.migrate_chat_history_to_default_session --dry-run
  python -m backend.scripts.migrate_chat_history_to_default_session --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config.config import settings


def _parse_iso(v: Any) -> Optional[datetime]:
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is not None:
            d = d.astimezone().replace(tzinfo=None)
        return d
    except Exception:
        return None


def _extract_user_content(content: str) -> str:
    if not content:
        return ""
    if "[用户消息]" in content:
        idx = content.find("[用户消息]")
        content = content[idx + len("[用户消息]") :]
    content = content.lstrip("\n\r")
    content = re.sub(r"【q_id:[^】]*】", "", content).strip()
    if content.startswith("[系统]"):
        lines = content.splitlines()
        content = "\n".join(
            l for l in lines if not l.startswith("[系统]") and not l.startswith("[Task]") and not l.startswith("[Output]")
        ).strip()
    return content


def _normalize_thinking(thinking_raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(thinking_raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for i, step in enumerate(thinking_raw):
        if not isinstance(step, dict):
            continue
        tools: List[Dict[str, Any]] = []
        raw_tools = step.get("tools") if isinstance(step.get("tools"), list) else []
        for t in raw_tools:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name") or "").replace("🔧", "").strip() or "（占位）工具"
            obs = t.get("result") or t.get("observation") or ""
            obs_str = str(obs) if obs else ""
            tools.append(
                {
                    "name": name,
                    "args": t.get("args") if isinstance(t.get("args"), dict) else {},
                    "result": obs_str,
                    "observation": obs_str,
                    "observationIsJson": obs_str.strip().startswith("{") or obs_str.strip().startswith("["),
                }
            )
        # 旧格式 action/toolArgs
        if not tools and step.get("action"):
            obs = step.get("observation") or step.get("result") or ""
            obs_str = str(obs) if obs else ""
            tools.append(
                {
                    "name": str(step.get("action") or "").replace("🔧", "").strip() or "（占位）工具",
                    "args": step.get("toolArgs") if isinstance(step.get("toolArgs"), dict) else {},
                    "result": obs_str,
                    "observation": obs_str,
                    "observationIsJson": obs_str.strip().startswith("{") or obs_str.strip().startswith("["),
                }
            )
        # 只有 observation 的情况，补占位工具
        if not tools:
            obs = step.get("observation") or step.get("result") or ""
            obs_str = str(obs) if obs else ""
            if obs_str.strip():
                tools.append(
                    {
                        "name": "（占位）工具",
                        "args": {},
                        "result": obs_str,
                        "observation": obs_str,
                        "observationIsJson": obs_str.strip().startswith("{") or obs_str.strip().startswith("["),
                    }
                )
        out.append({"__step": step.get("__step", i + 1), "thought": step.get("thought", ""), "tools": tools})
    return out


def _clean_one_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    role = str(msg.get("role") or "").strip() or "user"
    content = str(msg.get("content") or "")
    timestamp = msg.get("timestamp") or msg.get("ts")

    # 清除 legacy token
    if "\x00THINKING\x00" in content:
        content = content.replace("\x00THINKING\x00", "")

    if role == "user":
        content = _extract_user_content(content)
        if not content:
            return None
    elif role == "assistant":
        if not content.strip():
            return None
        # 跳过 DSML/工具调用原始串/生成中占位
        if content.lstrip().startswith("<|"):
            return None
        if content.strip().startswith('[{"name'):
            return None
        if content.strip() in ("（生成中...）", "(生成中...)"):
            return None
    else:
        if not content.strip():
            return None

    out: Dict[str, Any] = {"role": role, "content": content}
    if timestamp:
        out["timestamp"] = timestamp
        out["ts"] = timestamp
    if role == "assistant":
        thinking = _normalize_thinking(msg.get("thinking"))
        if thinking:
            out["thinking"] = thinking
        if msg.get("duration_ms") is not None:
            out["duration_ms"] = msg.get("duration_ms")
    return out


def _dedup_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    prev_sig: Optional[Tuple[str, str, str]] = None
    for m in messages:
        sig = (m.get("role", ""), m.get("content", ""), str(m.get("timestamp") or m.get("ts") or ""))
        if prev_sig == sig:
            continue
        deduped.append(m)
        prev_sig = sig
    return deduped


def migrate(apply: bool) -> int:
    db_path = settings.sqlite_db_path
    default_user = settings.default_user_id
    default_session = settings.default_session_id

    if not os.path.isfile(db_path):
        print(f"数据库不存在: {db_path}")
        return 1

    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT session_id, user_id, conversation_history, session_meta, start_time
            FROM interview_sessions
            ORDER BY start_time ASC
            """
        ).fetchall()
        if not rows:
            print("无会话数据可迁移。")
            return 0

        merged: List[Dict[str, Any]] = []
        session_count = 0
        raw_count = 0
        clean_count = 0
        for r in rows:
            raw = r["conversation_history"] or "[]"
            try:
                hist = json.loads(raw)
            except Exception:
                hist = []
            if not isinstance(hist, list):
                continue
            session_count += 1
            for msg in hist:
                if not isinstance(msg, dict):
                    continue
                raw_count += 1
                cleaned = _clean_one_message(msg)
                if cleaned:
                    merged.append(cleaned)
                    clean_count += 1

        # 按消息时间排序（无时间的放后面）
        merged.sort(
            key=lambda m: (
                _parse_iso(m.get("timestamp") or m.get("ts") or "") is None,
                _parse_iso(m.get("timestamp") or m.get("ts") or "") or datetime.max,
            )
        )
        merged = _dedup_messages(merged)

        # 为无时间戳消息补时间
        base = datetime.now()
        for i, m in enumerate(merged):
            if not (m.get("timestamp") or m.get("ts")):
                ts = (base).isoformat()
                m["timestamp"] = ts
                m["ts"] = ts
                base = base

        print(f"default_user={default_user}, default_session={default_session}")
        print(f"sessions_scanned={session_count}, raw_messages={raw_count}, cleaned_messages={clean_count}, final_messages={len(merged)}")

        if not apply:
            print("dry-run 完成（未写入）")
            return 0

        backup = Path(settings.backend_data_dir) / f"chat_history_migration_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

        # 统一 user_id/session_id
        conn.execute(
            "INSERT OR IGNORE INTO interview_sessions (session_id, user_id, session_type) VALUES (?, ?, 'practice')",
            (default_session, default_user),
        )
        conn.execute(
            """
            UPDATE interview_sessions
            SET conversation_history = ?, user_id = ?
            WHERE session_id = ?
            """,
            (json.dumps(merged, ensure_ascii=False), default_user, default_session),
        )
        # 其它 session 统一删除，避免读取混乱
        conn.execute("DELETE FROM interview_sessions WHERE session_id != ?", (default_session,))
        # 关联表统一 user/session
        conn.execute("UPDATE study_records SET user_id = ?, session_id = ?", (default_user, default_session))
        conn.execute("UPDATE episodic_log SET user_id = ?, session_id = ?", (default_user, default_session))
        conn.commit()

        print(f"apply 完成，备份文件: {backup}")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="清洗并迁移 chat 历史到默认 user/session")
    parser.add_argument("--apply", action="store_true", help="执行写入")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    args = parser.parse_args()

    do_apply = bool(args.apply and not args.dry_run)
    return migrate(do_apply)


if __name__ == "__main__":
    raise SystemExit(main())

