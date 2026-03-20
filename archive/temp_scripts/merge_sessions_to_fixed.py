#!/usr/bin/env python
"""
将同一用户的历史会话合并到当前固定 session_id 中。

使用场景：
  - 之前系统为每次对话生成随机 session_id（或多种规则混用）
  - 现在前端/后端统一使用固定 session_id（如 sess_Wangxr）
  - 结果是数据库里老会话还在，但前端只看得到固定 session_id 的那一条

本脚本会做三件事：
  1. 读取指定 user_id 在 interview_sessions 表中的所有 session
  2. 将除 target_session_id 以外的所有会话的 conversation_history
     依时间顺序合并到 target_session_id 的 conversation_history 里
     - 每条消息会在 metadata.original_session_id / metadata.original_index 中保留溯源信息
  3. 将 study_records / episodic_log 中老 session_id 统一改为 target_session_id

注意：
  - 默认从 backend.config.config.settings 读取：
      * sqlite_db_path
      * default_user_id （作为 user_id 默认值）
      * default_session_id （作为 target_session_id 默认值）
  - 支持通过命令行参数覆盖：
      --user-id
      --target-session-id
      --dry-run   只打印计划，不写入数据库

运行示例（在已激活的项目环境中）：
  python merge_sessions_to_fixed.py --user-id Wangxr --target-session-id sess_Wangxr
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from typing import List, Dict, Any, Tuple

from backend.config.config import settings
from backend.services.storage.sqlite_service import sqlite_service


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.sqlite_db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def list_sessions_for_user(user_id: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT session_id, user_id, session_type, start_time, end_time,
                   conversation_history
            FROM interview_sessions
            WHERE user_id = ?
            ORDER BY start_time ASC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def ensure_target_session(user_id: str, target_session_id: str) -> Dict[str, Any]:
    """
    确保目标 session 存在；不存在则使用现有逻辑创建一条空会话。
    """
    # 复用项目内的工具，保持行为一致
    sqlite_service.ensure_session_exists(target_session_id, user_id)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT session_id, user_id, session_type, start_time, end_time,
                   conversation_history
            FROM interview_sessions
            WHERE session_id = ?
            """,
            (target_session_id,),
        ).fetchone()
    return dict(row) if row else {}


def parse_history(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            return json.loads(raw)
        except Exception:
            return []
    return []


def merge_histories(
    target_history: List[Dict[str, Any]],
    other_sessions: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    将 other_sessions 中的历史按 start_time 顺序合并到 target_history 之后。
    为避免重复执行脚本导致重复合并，采用简单去重策略：
      - 若消息中已存在 metadata.original_session_id，则认为已经是合并后的记录，跳过。
    """
    merged = list(target_history)
    added = 0

    for sess in other_sessions:
        sid = sess["session_id"]
        history = parse_history(sess.get("conversation_history"))
        if not history:
            continue

        for idx, msg in enumerate(history):
            if not isinstance(msg, dict):
                continue

            meta = msg.get("metadata") or {}
            # 如果已经带有 original_session_id，说明之前被合并过，跳过
            if meta.get("original_session_id"):
                continue

            meta = dict(meta)  # 拷贝一份
            meta.setdefault("original_session_id", sid)
            meta.setdefault("original_index", idx)

            new_msg = dict(msg)
            new_msg["metadata"] = meta
            merged.append(new_msg)
            added += 1

    return merged, added


def migrate_session_ids_in_tables(
    user_id: str,
    source_session_ids: List[str],
    target_session_id: str,
    dry_run: bool,
) -> Dict[str, int]:
    """
    将 study_records / episodic_log 中老 session_id 改为 target_session_id。
    返回各表受影响行数。
    """
    if not source_session_ids:
        return {"study_records": 0, "episodic_log": 0}

    placeholders = ",".join("?" * len(source_session_ids))
    params = [user_id] + source_session_ids

    stats = {"study_records": 0, "episodic_log": 0}

    with get_conn() as conn:
        # study_records
        cur = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM study_records
            WHERE user_id = ?
              AND session_id IN ({placeholders})
            """,
            params,
        )
        stats["study_records"] = cur.fetchone()["c"]

        # episodic_log
        cur = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM episodic_log
            WHERE user_id = ?
              AND session_id IN ({placeholders})
            """,
            params,
        )
        stats["episodic_log"] = cur.fetchone()["c"]

        if dry_run:
            return stats

        # 实际更新
        conn.execute(
            f"""
            UPDATE study_records
            SET session_id = ?
            WHERE user_id = ?
              AND session_id IN ({placeholders})
            """,
            [target_session_id, user_id] + source_session_ids,
        )
        conn.execute(
            f"""
            UPDATE episodic_log
            SET session_id = ?
            WHERE user_id = ?
              AND session_id IN ({placeholders})
            """,
            [target_session_id, user_id] + source_session_ids,
        )
        conn.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="合并老会话到固定 session_id")
    parser.add_argument(
        "--user-id",
        default=settings.default_user_id,
        help=f"目标用户 ID，默认 {settings.default_user_id!r}",
    )
    parser.add_argument(
        "--target-session-id",
        default=settings.default_session_id,
        help=f"合并后的固定 session_id，默认 {settings.default_session_id!r}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划，不写入数据库",
    )
    args = parser.parse_args()

    user_id = str(args.user_id)
    target_session_id = str(args.target_session_id)
    dry_run = bool(args.dry_run)

    print(f"SQLite DB: {settings.sqlite_db_path}")
    print(f"user_id: {user_id}")
    print(f"target_session_id: {target_session_id}")
    print(f"dry_run: {dry_run}")
    print("-" * 80)

    sessions = list_sessions_for_user(user_id)
    if not sessions:
        print(f"❌ user_id={user_id!r} 在 interview_sessions 中没有任何会话记录")
        return

    print(f"找到会话总数: {len(sessions)}")

    target_session = ensure_target_session(user_id, target_session_id)
    target_history = parse_history(target_session.get("conversation_history"))

    print(
        f"目标会话: session_id={target_session_id!r}, "
        f"现有消息数={len(target_history)}"
    )

    other_sessions = [s for s in sessions if s["session_id"] != target_session_id]
    other_ids = [s["session_id"] for s in other_sessions]

    print(f"参与合并的其他会话数量: {len(other_sessions)}")
    if other_sessions:
        print("其它会话列表（按 start_time 升序）：")
        for s in other_sessions:
            print(
                f"  - {s['session_id']} | type={s.get('session_type')} "
                f"| start={s.get('start_time')} | end={s.get('end_time')}"
            )

    # 合并 conversation_history
    merged_history, added_msgs = merge_histories(target_history, other_sessions)
    print("-" * 80)
    print(f"预计追加消息条数: {added_msgs}")
    print(f"合并后总消息数: {len(merged_history)}")

    # 统计并（可选）更新 study_records / episodic_log
    stats = migrate_session_ids_in_tables(
        user_id=user_id,
        source_session_ids=other_ids,
        target_session_id=target_session_id,
        dry_run=True,
    )
    print(
        f"预计需要迁移的 study_records 行数: {stats['study_records']}, "
        f"episodic_log 行数: {stats['episodic_log']}"
    )

    if dry_run:
        print("\nDry-run 模式，不会写入任何变更。确认结果后去掉 --dry-run 再执行一次即可。")
        return

    # 真正写入 conversation_history
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE interview_sessions
            SET conversation_history = ?
            WHERE session_id = ?
            """,
            (json.dumps(merged_history, ensure_ascii=False), target_session_id),
        )
        conn.commit()

    # 真正更新 study_records / episodic_log
    stats = migrate_session_ids_in_tables(
        user_id=user_id,
        source_session_ids=other_ids,
        target_session_id=target_session_id,
        dry_run=False,
    )

    print("\n✅ 合并完成：")
    print(f"  - 追加消息数: {added_msgs}")
    print(f"  - 更新 study_records 行数: {stats['study_records']}")
    print(f"  - 更新 episodic_log 行数: {stats['episodic_log']}")
    print("\n提示：如需多次运行，本脚本会根据 metadata.original_session_id 做简单去重，避免重复合并。")


if __name__ == "__main__":
    main()

