"""
定时任务数据库服务
负责 scheduled_jobs 表的 CRUD 操作
"""
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from backend.services.storage.sqlite_service import sqlite_service


class SchedulerService:
    """定时任务配置管理服务"""

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        """确保 scheduled_jobs 表存在"""
        with sqlite_service._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    schedule_config TEXT NOT NULL,
                    job_params TEXT,
                    enabled INTEGER DEFAULT 1,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_run_at TIMESTAMP,
                    next_run_at TIMESTAMP,
                    run_count INTEGER DEFAULT 0,
                    last_status TEXT,
                    last_result TEXT
                )
            """)
            conn.commit()

    def add_job(self, job_config: dict) -> str:
        """
        添加新任务
        
        Args:
            job_config: {
                "job_name": str,
                "job_type": str,  # nowcoder_discovery / xhs_discovery / process_tasks
                "schedule_type": str,  # cron / interval
                "schedule_config": dict,
                "job_params": dict,
                "enabled": bool,
                "description": str
            }
        
        Returns:
            job_id
        """
        job_id = str(uuid.uuid4())
        
        with sqlite_service._get_conn() as conn:
            conn.execute("""
                INSERT INTO scheduled_jobs 
                    (job_id, job_name, job_type, schedule_type, schedule_config, 
                     job_params, enabled, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                job_config["job_name"],
                job_config["job_type"],
                job_config["schedule_type"],
                json.dumps(job_config["schedule_config"], ensure_ascii=False),
                json.dumps(job_config.get("job_params", {}), ensure_ascii=False),
                1 if job_config.get("enabled", True) else 0,
                job_config.get("description", "")
            ))
            conn.commit()
        
        return job_id

    def update_job(self, job_id: str, job_config: dict):
        """更新任务配置"""
        with sqlite_service._get_conn() as conn:
            conn.execute("""
                UPDATE scheduled_jobs 
                SET job_name = ?,
                    job_type = ?,
                    schedule_type = ?,
                    schedule_config = ?,
                    job_params = ?,
                    enabled = ?,
                    description = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
            """, (
                job_config["job_name"],
                job_config["job_type"],
                job_config["schedule_type"],
                json.dumps(job_config["schedule_config"], ensure_ascii=False),
                json.dumps(job_config.get("job_params", {}), ensure_ascii=False),
                1 if job_config.get("enabled", True) else 0,
                job_config.get("description", ""),
                job_id
            ))
            conn.commit()

    def delete_job(self, job_id: str):
        """删除任务"""
        with sqlite_service._get_conn() as conn:
            conn.execute("DELETE FROM scheduled_jobs WHERE job_id = ?", (job_id,))
            conn.commit()

    def enable_job(self, job_id: str):
        """启用任务"""
        with sqlite_service._get_conn() as conn:
            conn.execute("""
                UPDATE scheduled_jobs 
                SET enabled = 1, updated_at = CURRENT_TIMESTAMP 
                WHERE job_id = ?
            """, (job_id,))
            conn.commit()

    def disable_job(self, job_id: str):
        """禁用任务"""
        with sqlite_service._get_conn() as conn:
            conn.execute("""
                UPDATE scheduled_jobs 
                SET enabled = 0, updated_at = CURRENT_TIMESTAMP 
                WHERE job_id = ?
            """, (job_id,))
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict]:
        """获取任务详情"""
        with sqlite_service._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM scheduled_jobs WHERE job_id = ?", 
                (job_id,)
            ).fetchone()
        
        if not row:
            return None
        
        return self._row_to_dict(row)

    def list_jobs(self, enabled_only: bool = False) -> List[Dict]:
        """列出所有任务"""
        with sqlite_service._get_conn() as conn:
            if enabled_only:
                rows = conn.execute(
                    "SELECT * FROM scheduled_jobs WHERE enabled = 1 ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scheduled_jobs ORDER BY created_at DESC"
                ).fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    def update_job_run_info(self, job_id: str, status: str, result: dict = None, 
                           next_run_at: datetime = None):
        """更新任务运行信息"""
        with sqlite_service._get_conn() as conn:
            conn.execute("""
                UPDATE scheduled_jobs 
                SET last_run_at = CURRENT_TIMESTAMP,
                    next_run_at = ?,
                    run_count = run_count + 1,
                    last_status = ?,
                    last_result = ?
                WHERE job_id = ?
            """, (
                next_run_at.isoformat() if next_run_at else None,
                status,
                json.dumps(result, ensure_ascii=False) if result else None,
                job_id
            ))
            conn.commit()

    def _row_to_dict(self, row) -> Dict:
        """将数据库行转换为字典"""
        return {
            "job_id": row["job_id"],
            "job_name": row["job_name"],
            "job_type": row["job_type"],
            "schedule_type": row["schedule_type"],
            "schedule_config": json.loads(row["schedule_config"]),
            "job_params": json.loads(row["job_params"]) if row["job_params"] else {},
            "enabled": bool(row["enabled"]),
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_run_at": row["last_run_at"],
            "next_run_at": row["next_run_at"],
            "run_count": row["run_count"],
            "last_status": row["last_status"],
            "last_result": json.loads(row["last_result"]) if row["last_result"] else None
        }


# 全局单例
scheduler_service = SchedulerService()
