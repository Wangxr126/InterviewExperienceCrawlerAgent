"""
Agent 工具调用运行时统计（内存态，实时）。

说明：
- 数据直接来自 Agent 工具调用过程，不读取日志文件。
- 进程重启后统计会清空（符合“实时看板”场景）。
"""

from __future__ import annotations

import sqlite3
import threading
import time
import json
from collections import defaultdict
from typing import Any, Dict, Optional

from backend.config.config import settings


def tool_execution_success_for_stats(
    result_str: Optional[str] = None,
    *,
    response_status: Any = None,
) -> bool:
    """
    与控制台/框架约定对齐的「是否计为成功」判定，用于工具统计看板。

    - 若传入 hello_agents 的 ToolStatus，则仅 SUCCESS 计成功（ERROR / PARTIAL 计失败）。
    - 否则根据返回给模型的字符串：以 ❌ / ⚠️ 开头计失败（覆盖部分成功、错误前缀）。
    """
    if response_status is not None:
        try:
            from hello_agents.tools.response import ToolStatus

            return response_status == ToolStatus.SUCCESS
        except Exception:
            pass
    s = (result_str or "").strip()
    if s.startswith("❌") or s.startswith("⚠️"):
        return False
    return True


class AgentToolRuntimeStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._updated_at = 0.0
        self._db_path = settings.sqlite_db_path
        self._init_db()
        # stats[agent_name][tool_name] -> counters
        self._stats: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    "count": 0,
                    "success": 0,
                    "failed": 0,
                    "total_execution_time_ms": 0.0,
                    "user_calls": defaultdict(int),
                }
            )
        )

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_tool_runtime_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    user_id TEXT,
                    agent_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    success INTEGER NOT NULL DEFAULT 0,
                    execution_time_ms REAL NOT NULL DEFAULT 0,
                    params_input_text TEXT
                )
                """
            )
            cols = {
                str(r["name"]) for r in conn.execute("PRAGMA table_info(agent_tool_runtime_calls)").fetchall()
            }
            if "params_input_text" not in cols:
                conn.execute("ALTER TABLE agent_tool_runtime_calls ADD COLUMN params_input_text TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_tool_runtime_user ON agent_tool_runtime_calls(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_tool_runtime_agent ON agent_tool_runtime_calls(agent_name)"
            )
            conn.commit()

    def record(
        self,
        *,
        agent_name: str,
        tool_name: str,
        success: bool,
        execution_time_ms: float = 0.0,
        user_id: Optional[str] = None,
        params_input: Optional[Dict[str, Any]] = None,
    ) -> None:
        agent = (agent_name or "").strip() or "UnknownAgent"
        tool = (tool_name or "").strip() or "unknown_tool"
        uid = (user_id or "").strip()
        cost = float(execution_time_ms or 0.0)
        if cost < 0:
            cost = 0.0
        params_input_text: Optional[str] = None
        if isinstance(params_input, dict):
            try:
                params_input_text = json.dumps(params_input, ensure_ascii=False)
            except Exception:
                params_input_text = str(params_input)

        with self._lock:
            item = self._stats[agent][tool]
            item["count"] += 1
            if success:
                item["success"] += 1
            else:
                item["failed"] += 1
            item["total_execution_time_ms"] += cost
            if uid:
                item["user_calls"][uid] += 1
            self._updated_at = time.time()

        # 跨进程可见：每次调用落一条轻量记录到 SQLite
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_tool_runtime_calls
                    (ts, user_id, agent_name, tool_name, success, execution_time_ms, params_input_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (time.time(), uid or None, agent, tool, 1 if success else 0, cost, params_input_text),
                )
                conn.commit()
        except Exception:
            # 统计失败不应影响主业务
            pass

    def snapshot(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        uid = (user_id or "").strip()
        sql = """
            SELECT
                agent_name,
                tool_name,
                COUNT(*) AS count,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed,
                AVG(execution_time_ms) AS avg_execution_time_ms,
                MAX(ts) AS latest_ts,
                MAX(id) AS latest_id
            FROM agent_tool_runtime_calls
        """
        params = []
        if uid:
            sql += " WHERE user_id = ? OR user_id IS NULL"
            params.append(uid)
        sql += " GROUP BY agent_name, tool_name"

        rows = []
        latest_ids = []
        latest_ts = 0.0
        try:
            with self._get_conn() as conn:
                cur = conn.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]
                latest_ids = [int(r.get("latest_id") or 0) for r in rows if int(r.get("latest_id") or 0) > 0]
                latest_params_map: Dict[int, Optional[str]] = {}
                if latest_ids:
                    placeholders = ",".join(["?"] * len(latest_ids))
                    pcur = conn.execute(
                        f"SELECT id, params_input_text FROM agent_tool_runtime_calls WHERE id IN ({placeholders})",
                        latest_ids,
                    )
                    for p in pcur.fetchall():
                        latest_params_map[int(p["id"])] = p["params_input_text"]
        except Exception:
            rows = []
            latest_params_map = {}

        by_agent: Dict[str, Dict[str, Any]] = {}
        total_calls = 0
        for r in rows:
            agent_name = r.get("agent_name") or "UnknownAgent"
            tool_name = r.get("tool_name") or "unknown_tool"
            count = int(r.get("count") or 0)
            success = int(r.get("success") or 0)
            failed = int(r.get("failed") or 0)
            avg_ms = float(r.get("avg_execution_time_ms") or 0.0)
            latest_id = int(r.get("latest_id") or 0)
            latest_params_input = None
            _raw_params = latest_params_map.get(latest_id)
            if _raw_params:
                try:
                    latest_params_input = json.loads(_raw_params)
                except Exception:
                    latest_params_input = _raw_params
            latest_ts = max(latest_ts, float(r.get("latest_ts") or 0.0))

            if count <= 0:
                continue

            if agent_name not in by_agent:
                by_agent[agent_name] = {
                    "agent_name": agent_name,
                    "total_calls": 0,
                    "tools_count": 0,
                    "tools": [],
                }
            by_agent[agent_name]["tools"].append(
                {
                    "tool_name": tool_name,
                    "count": count,
                    "success": success,
                    "failed": failed,
                    "success_rate": round((success / count) * 100.0, 2) if count else 0.0,
                    "avg_execution_time_ms": round(avg_ms, 2),
                    "latest_params_input": latest_params_input,
                }
            )
            by_agent[agent_name]["total_calls"] += count
            total_calls += count

        agents = list(by_agent.values())
        for a in agents:
            a["tools"].sort(key=lambda x: (-x["count"], x["tool_name"]))
            a["tools_count"] = len(a["tools"])
        agents.sort(key=lambda x: (-x["total_calls"], x["agent_name"]))

        flattened_tools = []
        for agent in agents:
            for tool in agent["tools"]:
                row = dict(tool)
                row["agent_name"] = agent["agent_name"]
                flattened_tools.append(row)

        return {
            "mode": "runtime",
            "user_id": uid or None,
            "total_calls": total_calls,
            "agents": agents,
            "tools": flattened_tools,
            "updated_at": latest_ts or self._updated_at,
        }


agent_tool_runtime_stats = AgentToolRuntimeStats()

