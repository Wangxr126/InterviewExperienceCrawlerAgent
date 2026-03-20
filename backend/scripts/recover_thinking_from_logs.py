"""
从 interviewer_logs/thinking_*.jsonl 回补 interview_sessions.conversation_history 中缺失的 thinking 字段。

用法：
  conda activate NewCoderAgent
  python -m backend.scripts.recover_thinking_from_logs --user-id Wangxr --dry-run
  python -m backend.scripts.recover_thinking_from_logs --user-id Wangxr --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config.config import settings


def _parse_ts(v: Any) -> Optional[datetime]:
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _normalize_user_message(s: str) -> str:
    if not s:
        return ""
    # 去掉 q_id 内部标记，统一空白符，降低匹配噪音
    s = re.sub(r"【q_id:[^】]*】", "", s)
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


@dataclass
class MissingThinkingAssistant:
    index: int
    timestamp: Optional[datetime]
    prev_user_msg: str


@dataclass
class ThinkingLogRecord:
    timestamp: Optional[datetime]
    user_msg_norm: str
    thinking_steps: List[dict]


@dataclass
class ToolLogRecord:
    timestamp: Optional[datetime]
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: str
    success: bool


@dataclass
class TraceThinkingRecord:
    session_id: str
    timestamp: Optional[datetime]
    user_msg_norm: str
    ai_response_norm: str
    thinking_steps: List[dict]


def _load_thinking_logs(user_id: str, session_id: str) -> List[ThinkingLogRecord]:
    root = Path(settings.backend_data_dir).parent / "interviewer_logs"
    records: List[ThinkingLogRecord] = []
    for p in sorted(root.rglob("thinking_*.jsonl")):
        if not p.is_file():
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("user_id") != user_id:
                        continue
                    if rec.get("session_id") != session_id:
                        continue
                    steps = rec.get("thinking_steps")
                    if not isinstance(steps, list) or not steps:
                        continue
                    msg_norm = _normalize_user_message(str(rec.get("user_message") or ""))
                    records.append(
                        ThinkingLogRecord(
                            timestamp=_parse_ts(rec.get("timestamp")),
                            user_msg_norm=msg_norm,
                            thinking_steps=steps,
                        )
                    )
        except Exception:
            continue
    return records


def _normalize_assistant_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _extract_user_message_from_written(content: str) -> str:
    if not content:
        return ""
    marker = "[用户消息]"
    idx = content.find(marker)
    if idx >= 0:
        return _normalize_user_message(content[idx + len(marker):].strip())
    return _normalize_user_message(content)


def _extract_trace_thinking_records(user_id: str) -> List[TraceThinkingRecord]:
    trace_dir = Path(settings.backend_data_dir) / "memory" / "traces"
    if not trace_dir.exists():
        return []

    records: List[TraceThinkingRecord] = []
    marker = f"user_id={user_id}"

    for p in sorted(trace_dir.glob("trace-*.jsonl")):
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        if not lines:
            continue

        # 粗过滤：必须包含当前用户标记
        whole = "\n".join(lines[:40]) if len(lines) > 40 else "\n".join(lines)
        if marker not in whole and marker not in "\n".join(lines):
            continue

        first = None
        try:
            first = json.loads(lines[0])
        except Exception:
            pass
        agent_name = ""
        if isinstance(first, dict):
            payload = first.get("payload") or {}
            if isinstance(payload, dict):
                agent_name = str(payload.get("agent_name") or "")
        if "Interviewer" not in agent_name:
            continue

        trace_session_id = str((first or {}).get("session_id") or "")
        step_map: Dict[int, Dict[str, Any]] = {}
        call_index: Dict[str, Tuple[int, int]] = {}
        final_answer = ""
        session_end_ts: Optional[datetime] = None
        user_msg_norm = ""
        for line in lines:
            try:
                e = json.loads(line)
            except Exception:
                continue
            event = e.get("event")
            payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
            step = e.get("step")

            if event == "tool_call":
                if not isinstance(step, int):
                    continue
                if step not in step_map:
                    step_map[step] = {"__step": step, "thought": "", "tools": []}
                t = {
                    "name": str(payload.get("tool_name") or ""),
                    "args": payload.get("args") if isinstance(payload.get("args"), dict) else {},
                    "result": "",
                    "observation": "",
                    "observationIsJson": False,
                }
                step_map[step]["tools"].append(t)
                call_id = str(payload.get("tool_call_id") or "")
                if call_id:
                    call_index[call_id] = (step, len(step_map[step]["tools"]) - 1)
            elif event == "tool_result":
                call_id = str(payload.get("tool_call_id") or "")
                result = str(payload.get("result") or "")
                if call_id and call_id in call_index:
                    s_no, tool_idx = call_index[call_id]
                    tool_obj = step_map.get(s_no, {}).get("tools", [])[tool_idx]
                    tool_obj["result"] = result
                    tool_obj["observation"] = result
                    rs = result.strip()
                    if rs.startswith("{") or rs.startswith("["):
                        try:
                            json.loads(rs)
                            tool_obj["observationIsJson"] = True
                        except Exception:
                            pass
            elif event == "session_end":
                final_answer = str(payload.get("final_answer") or "")
                session_end_ts = _parse_ts(e.get("ts"))
            elif event == "message_written":
                role = str(payload.get("role") or "")
                if role == "user" and not user_msg_norm:
                    user_msg_norm = _extract_user_message_from_written(str(payload.get("content") or ""))

        thinking_steps = [step_map[k] for k in sorted(step_map.keys()) if step_map[k].get("tools")]
        if not thinking_steps:
            continue
        ans_norm = _normalize_assistant_text(final_answer)
        if not ans_norm:
            continue
        records.append(
            TraceThinkingRecord(
                session_id=trace_session_id,
                timestamp=session_end_ts,
                user_msg_norm=user_msg_norm,
                ai_response_norm=ans_norm,
                thinking_steps=thinking_steps,
            )
        )

    return records


def _load_tool_logs(user_id: str, session_id: str) -> List[ToolLogRecord]:
    root = Path(settings.backend_data_dir).parent / "interviewer_logs"
    records: List[ToolLogRecord] = []
    for p in sorted(root.rglob("tools_*.jsonl")):
        if not p.is_file():
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("user_id") != user_id:
                        continue
                    if rec.get("session_id") != session_id:
                        continue
                    records.append(
                        ToolLogRecord(
                            timestamp=_parse_ts(rec.get("timestamp")),
                            tool_name=str(rec.get("tool_name") or "").strip(),
                            tool_input=rec.get("tool_input") if isinstance(rec.get("tool_input"), dict) else {},
                            tool_output=str(rec.get("tool_output") or ""),
                            success=bool(rec.get("success")),
                        )
                    )
        except Exception:
            continue
    records.sort(key=lambda r: r.timestamp or datetime.min)
    return records


def _to_frontend_tools_step(tool_logs: List[ToolLogRecord]) -> List[dict]:
    if not tool_logs:
        return []

    def _is_json_like(s: str) -> bool:
        s = (s or "").strip()
        if not s or (not s.startswith("{") and not s.startswith("[")):
            return False
        try:
            json.loads(s)
            return True
        except Exception:
            return False

    tools = []
    for t in tool_logs:
        if not t.tool_name:
            continue
        obs = t.tool_output or ""
        tools.append(
            {
                "name": t.tool_name,
                "args": t.tool_input or {},
                "result": obs,
                "observation": obs,
                "observationIsJson": _is_json_like(obs),
            }
        )
    if not tools:
        return []
    return [{"__step": 1, "thought": "", "tools": tools}]


def _collect_missing_assistants(history: List[dict]) -> List[MissingThinkingAssistant]:
    missing: List[MissingThinkingAssistant] = []
    last_user_msg = ""
    for idx, m in enumerate(history):
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "user":
            last_user_msg = _normalize_user_message(str(m.get("content") or ""))
            continue
        if role != "assistant":
            continue
        if m.get("thinking"):
            continue
        missing.append(
            MissingThinkingAssistant(
                index=idx,
                timestamp=_parse_ts(m.get("timestamp") or m.get("ts")),
                prev_user_msg=last_user_msg,
            )
        )
    return missing


def _nearest_user_ts_before(history: List[dict], idx: int) -> Optional[datetime]:
    for i in range(idx - 1, -1, -1):
        m = history[i]
        if isinstance(m, dict) and m.get("role") == "user":
            return _parse_ts(m.get("timestamp") or m.get("ts"))
    return None


def _nearest_user_ts_after(history: List[dict], idx: int) -> Optional[datetime]:
    for i in range(idx + 1, len(history)):
        m = history[i]
        if isinstance(m, dict) and m.get("role") == "user":
            return _parse_ts(m.get("timestamp") or m.get("ts"))
    return None


def _pick_best_record(
    target: MissingThinkingAssistant,
    candidates: List[ThinkingLogRecord],
) -> Optional[int]:
    if not candidates:
        return None

    # 1) 文本精确匹配 + 时间最近
    exact = [i for i, r in enumerate(candidates) if r.user_msg_norm and r.user_msg_norm == target.prev_user_msg]
    if exact:
        if target.timestamp:
            exact.sort(
                key=lambda i: abs(
                    ((candidates[i].timestamp or target.timestamp) - target.timestamp).total_seconds()
                )
            )
        return exact[0]

    # 2) 文本包含匹配（双向）+ 时间最近
    fuzz = []
    if target.prev_user_msg:
        for i, r in enumerate(candidates):
            if not r.user_msg_norm:
                continue
            if target.prev_user_msg in r.user_msg_norm or r.user_msg_norm in target.prev_user_msg:
                fuzz.append(i)
    if fuzz:
        if target.timestamp:
            fuzz.sort(
                key=lambda i: abs(
                    ((candidates[i].timestamp or target.timestamp) - target.timestamp).total_seconds()
                )
            )
        return fuzz[0]

    # 3) 仅时间最近（兜底）
    if target.timestamp:
        by_ts = list(range(len(candidates)))
        by_ts.sort(
            key=lambda i: abs(
                ((candidates[i].timestamp or target.timestamp) - target.timestamp).total_seconds()
            )
        )
        return by_ts[0] if by_ts else None
    return 0


def recover_for_user(user_id: str, apply: bool, aggressive_tools: bool = False) -> Tuple[int, int, int, int, int, str]:
    db_path = settings.sqlite_db_path
    conn = sqlite3.connect(db_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        sess_id = f"sess_{user_id}"
        row = conn.execute(
            "SELECT session_id, conversation_history FROM interview_sessions WHERE session_id = ? AND user_id = ?",
            (sess_id, user_id),
        ).fetchone()
        if not row:
            return 0, 0, 0, 0, 0, f"未找到会话: {sess_id}"

        history = json.loads(row["conversation_history"] or "[]")
        original_history = json.loads(row["conversation_history"] or "[]")
        if not isinstance(history, list):
            return 0, 0, 0, 0, 0, "conversation_history 非数组，无法处理"

        missing = _collect_missing_assistants(history)
        logs = _load_thinking_logs(user_id=user_id, session_id=sess_id)
        trace_logs = _extract_trace_thinking_records(user_id=user_id)
        trace_total = len(trace_logs)
        tool_logs = _load_tool_logs(user_id=user_id, session_id=sess_id)
        if not missing:
            return 0, len(logs), trace_total, len(tool_logs), 0, "没有缺失 thinking 的 assistant 消息"

        used = set()
        used_tool_indices = set()
        recovered_by_thinking = 0
        recovered_by_trace = 0
        recovered_by_tools = 0
        for m in missing:
            # 0) 优先 trace（包含完整工具调用链）
            assistant_content_norm = _normalize_assistant_text(str(history[m.index].get("content") or ""))
            if assistant_content_norm:
                hit_idx = None
                for i, tr in enumerate(trace_logs):
                    if tr.ai_response_norm == assistant_content_norm:
                        hit_idx = i
                        break
                if hit_idx is not None:
                    history[m.index]["thinking"] = trace_logs[hit_idx].thinking_steps
                    trace_logs.pop(hit_idx)
                    recovered_by_trace += 1
                    continue

            # 0.5) trace 次优匹配：按上条 user 文本 + 时间最近
            if m.prev_user_msg:
                cand = []
                for i, tr in enumerate(trace_logs):
                    if not tr.user_msg_norm:
                        continue
                    if tr.user_msg_norm == m.prev_user_msg or m.prev_user_msg in tr.user_msg_norm or tr.user_msg_norm in m.prev_user_msg:
                        cand.append((i, tr))
                if cand:
                    if m.timestamp:
                        cand.sort(
                            key=lambda x: abs(((x[1].timestamp or m.timestamp) - m.timestamp).total_seconds())
                        )
                    hit_idx = cand[0][0]
                    history[m.index]["thinking"] = trace_logs[hit_idx].thinking_steps
                    trace_logs.pop(hit_idx)
                    recovered_by_trace += 1
                    continue

            # 1) 优先从 thinking 日志恢复完整步骤
            if logs:
                available = [r for i, r in enumerate(logs) if i not in used]
                available_index_map = [i for i in range(len(logs)) if i not in used]
                pick = _pick_best_record(m, available)
                if pick is not None:
                    real_idx = available_index_map[pick]
                    rec = logs[real_idx]
                    if rec.thinking_steps:
                        history[m.index]["thinking"] = rec.thinking_steps
                        used.add(real_idx)
                        recovered_by_thinking += 1
                        continue

            # 2) 回退：用 tools 日志恢复“仅工具调用步骤”
            prev_user_ts = _nearest_user_ts_before(history, m.index)
            next_user_ts = _nearest_user_ts_after(history, m.index)
            asst_ts = m.timestamp
            selected_tools: List[ToolLogRecord] = []
            for ti, t in enumerate(tool_logs):
                if ti in used_tool_indices:
                    continue
                if t.timestamp is None:
                    continue
                if prev_user_ts and t.timestamp < (prev_user_ts):
                    continue
                # 若存在下一条 user，工具调用不应越过它
                if next_user_ts and t.timestamp >= next_user_ts:
                    continue
                # assistant 时间通常在本轮末尾，给一个正向缓冲
                if asst_ts and t.timestamp > (asst_ts):
                    continue
                selected_tools.append(t)

            if selected_tools:
                tool_steps = _to_frontend_tools_step(selected_tools)
                if tool_steps:
                    history[m.index]["thinking"] = tool_steps
                    for ti, t in enumerate(tool_logs):
                        if t in selected_tools:
                            used_tool_indices.add(ti)
                    recovered_by_tools += 1
                    continue

            # 3) 激进模式：按 assistant 时间最近强制挂接工具（可能错配）
            if aggressive_tools and asst_ts is not None:
                near_indices = []
                for ti, t in enumerate(tool_logs):
                    if ti in used_tool_indices or t.timestamp is None:
                        continue
                    delta = abs((t.timestamp - asst_ts).total_seconds())
                    if delta <= 600:  # 10 分钟窗口
                        near_indices.append((delta, ti))
                near_indices.sort(key=lambda x: x[0])
                picked = [ti for _, ti in near_indices[:4]]  # 每条 assistant 最多挂 4 个工具
                if picked:
                    picked_tools = [tool_logs[ti] for ti in picked]
                    tool_steps = _to_frontend_tools_step(picked_tools)
                    if tool_steps:
                        history[m.index]["thinking"] = tool_steps
                        for ti in picked:
                            used_tool_indices.add(ti)
                        recovered_by_tools += 1

        recovered_total = recovered_by_thinking + recovered_by_tools
        recovered_total = recovered_by_trace + recovered_by_thinking + recovered_by_tools
        if apply and recovered_total > 0:
            backup_path = Path(settings.backend_data_dir) / f"thinking_recover_backup_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            backup_path.write_text(json.dumps(original_history, ensure_ascii=False, indent=2), encoding="utf-8")
            conn.execute(
                "UPDATE interview_sessions SET conversation_history = ? WHERE session_id = ? AND user_id = ?",
                (json.dumps(history, ensure_ascii=False), sess_id, user_id),
            )
            conn.commit()
            return len(missing), len(logs), trace_total, len(tool_logs), recovered_total, (
                f"已写入并备份到: {backup_path} "
                f"(trace={recovered_by_trace}, thinking={recovered_by_thinking}, tools={recovered_by_tools})"
            )

        return len(missing), len(logs), trace_total, len(tool_logs), recovered_total, (
            f"dry-run 完成（未写入，trace={recovered_by_trace}, thinking={recovered_by_thinking}, tools={recovered_by_tools})"
        )
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="从 thinking 日志回补 conversation_history.thinking")
    parser.add_argument("--user-id", required=True, help="用户 ID，如 Wangxr")
    parser.add_argument("--apply", action="store_true", help="执行写入（默认仅 dry-run）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    parser.add_argument("--aggressive-tools", action="store_true", help="激进模式：按时间近邻强制挂接工具调用（可能错配）")
    args = parser.parse_args()

    apply = bool(args.apply and not args.dry_run)
    missing_count, thinking_log_count, trace_count, tool_log_count, recovered_count, msg = recover_for_user(
        args.user_id,
        apply=apply,
        aggressive_tools=bool(args.aggressive_tools),
    )
    mode = "APPLY" if apply else "DRY_RUN"
    print(f"[{mode}] user={args.user_id}")
    print(f"  missing_assistant_without_thinking = {missing_count}")
    print(f"  thinking_log_records              = {thinking_log_count}")
    print(f"  trace_thinking_records            = {trace_count}")
    print(f"  tool_log_records                  = {tool_log_count}")
    print(f"  recoverable_and_matched           = {recovered_count}")
    print(f"  note: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
