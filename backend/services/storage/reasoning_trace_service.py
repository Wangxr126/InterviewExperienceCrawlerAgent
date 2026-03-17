"""推理过程追踪服务 v1.0"""
import sqlite3
import logging
import json
import uuid
from typing import List, Dict, Any, Optional
from backend.config.config import settings

logger = logging.getLogger(__name__)


class ReasoningTraceService:
    def __init__(self):
        self.db_path = settings.sqlite_db_path
        self._init_tables()
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def _init_tables(self):
        with self._get_conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS reasoning_sessions (
                id INTEGER PRIMARY KEY, session_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL, interview_session_id TEXT, question_id TEXT,
                question_text TEXT, chat_type TEXT DEFAULT 'chat', model_name TEXT,
                model_version TEXT, total_steps INTEGER DEFAULT 0, total_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0,
                status TEXT DEFAULT 'in_progress', start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME, duration_seconds REAL, metadata TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
            
            conn.execute("""CREATE TABLE IF NOT EXISTS reasoning_steps (
                id INTEGER PRIMARY KEY, step_id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
                step_number INTEGER NOT NULL, step_type TEXT NOT NULL, thinking TEXT,
                action_type TEXT, action_name TEXT, action_input TEXT, observation TEXT,
                tool_result TEXT, reasoning_content TEXT, tokens_used INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0, status TEXT DEFAULT 'success', error_msg TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES reasoning_sessions(session_id))""")
            
            conn.execute("""CREATE TABLE IF NOT EXISTS reasoning_results (
                id INTEGER PRIMARY KEY, result_id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL UNIQUE,
                final_answer TEXT, answer_type TEXT, confidence_score REAL DEFAULT 0.0,
                reasoning_summary TEXT, key_insights TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES reasoning_sessions(session_id))""")
            
            conn.execute("""CREATE TABLE IF NOT EXISTS reasoning_tool_calls (
                id INTEGER PRIMARY KEY, call_id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
                step_id TEXT, tool_name TEXT NOT NULL, tool_input TEXT, tool_output TEXT,
                execution_time_ms INTEGER DEFAULT 0, status TEXT DEFAULT 'success', error_msg TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES reasoning_sessions(session_id))""")
            
            conn.commit()
        logger.info("✅ 推理过程追踪表初始化完成")
    
    def create_session(self, user_id: str, question_id: str = None, 
                      question_text: str = None, interview_session_id: str = None,
                      model_name: str = "deepseek", model_version: str = "v3",
                      chat_type: str = "chat", metadata: Dict = None) -> str:
        session_id = f"reasoning-{uuid.uuid4().hex[:16]}"
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        
        with self._get_conn() as conn:
            conn.execute("""INSERT INTO reasoning_sessions
                (session_id, user_id, interview_session_id, question_id, question_text,
                 chat_type, model_name, model_version, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, interview_session_id, question_id, question_text,
                 chat_type, model_name, model_version, meta_json))
            conn.commit()
        
        logger.info(f"创建推理会话: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM reasoning_sessions WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_session_status(self, session_id: str, status: str, 
                             end_time: str = None, duration_seconds: float = None,
                             total_steps: int = None, total_tokens: int = None,
                             reasoning_tokens: int = None, completion_tokens: int = None):
        with self._get_conn() as conn:
            updates = ["status = ?"]
            params = [status]
            
            if end_time:
                updates.append("end_time = ?")
                params.append(end_time)
            if duration_seconds is not None:
                updates.append("duration_seconds = ?")
                params.append(duration_seconds)
            if total_steps is not None:
                updates.append("total_steps = ?")
                params.append(total_steps)
            if total_tokens is not None:
                updates.append("total_tokens = ?")
                params.append(total_tokens)
            if reasoning_tokens is not None:
                updates.append("reasoning_tokens = ?")
                params.append(reasoning_tokens)
            if completion_tokens is not None:
                updates.append("completion_tokens = ?")
                params.append(completion_tokens)
            
            params.append(session_id)
            sql = f"UPDATE reasoning_sessions SET {', '.join(updates)} WHERE session_id = ?"
            conn.execute(sql, params)
            conn.commit()
    
    def add_step(self, session_id: str, step_number: int, step_type: str,
                thinking: str = None, action_type: str = None, action_name: str = None,
                action_input: str = None, observation: str = None, tool_result: str = None,
                reasoning_content: str = None, tokens_used: int = 0, 
                duration_ms: int = 0, status: str = "success", error_msg: str = None) -> str:
        step_id = f"step-{uuid.uuid4().hex[:12]}"
        
        with self._get_conn() as conn:
            conn.execute("""INSERT INTO reasoning_steps
                (step_id, session_id, step_number, step_type, thinking, action_type,
                 action_name, action_input, observation, tool_result, reasoning_content,
                 tokens_used, duration_ms, status, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (step_id, session_id, step_number, step_type, thinking, action_type,
                 action_name, action_input, observation, tool_result, reasoning_content,
                 tokens_used, duration_ms, status, error_msg))
            conn.commit()
        
        return step_id
    
    def get_steps(self, session_id: str) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM reasoning_steps WHERE session_id = ? ORDER BY step_number ASC",
                (session_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def save_result(self, session_id: str, final_answer: str, answer_type: str = "text",
                   confidence_score: float = 0.0, reasoning_summary: str = None,
                   key_insights: List[str] = None, metadata: Dict = None) -> str:
        result_id = f"result-{uuid.uuid4().hex[:12]}"
        insights_json = json.dumps(key_insights or [], ensure_ascii=False)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        
        with self._get_conn() as conn:
            conn.execute("""INSERT INTO reasoning_results
                (result_id, session_id, final_answer, answer_type, confidence_score,
                 reasoning_summary, key_insights, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (result_id, session_id, final_answer, answer_type, confidence_score,
                 reasoning_summary, insights_json, meta_json))
            conn.commit()
        
        return result_id
    
    def get_result(self, session_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM reasoning_results WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get('key_insights'):
                    result['key_insights'] = json.loads(result['key_insights'])
                if result.get('metadata'):
                    result['metadata'] = json.loads(result['metadata'])
                return result
        return None
    
    def record_tool_call(self, session_id: str, tool_name: str, tool_input: str = None,
                        tool_output: str = None, execution_time_ms: int = 0,
                        status: str = "success", error_msg: str = None, step_id: str = None) -> str:
        call_id = f"call-{uuid.uuid4().hex[:12]}"
        
        with self._get_conn() as conn:
            conn.execute("""INSERT INTO reasoning_tool_calls
                (call_id, session_id, step_id, tool_name, tool_input, tool_output,
                 execution_time_ms, status, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (call_id, session_id, step_id, tool_name, tool_input, tool_output,
                 execution_time_ms, status, error_msg))
            conn.commit()
        
        return call_id
    
    def get_tool_calls(self, session_id: str) -> List[Dict]:
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM reasoning_tool_calls WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_full_trace(self, session_id: str) -> Dict:
        session = self.get_session(session_id)
        if not session:
            return None
        
        steps = self.get_steps(session_id)
        result = self.get_result(session_id)
        tool_calls = self.get_tool_calls(session_id)
        
        if session.get('metadata'):
            session['metadata'] = json.loads(session['metadata'])
        
        return {
            'session': session,
            'steps': steps,
            'result': result,
            'tool_calls': tool_calls,
            'trace_format_version': '1.0'
        }
    
    def export_trace_json(self, session_id: str) -> str:
        trace = self.get_full_trace(session_id)
        return json.dumps(trace, ensure_ascii=False, indent=2, default=str) if trace else None
    
    def list_sessions(self, user_id: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        sql = "SELECT * FROM reasoning_sessions WHERE 1=1"
        params = []
        
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self._get_conn() as conn:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]


reasoning_trace_service = ReasoningTraceService()
