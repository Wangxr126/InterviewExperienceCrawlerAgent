"""
定时任务管理 API
提供定时任务的 CRUD 接口，支持前端可视化管理
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/scheduler", tags=["定时任务管理"])


# ══════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════

class ScheduleConfig(BaseModel):
    """调度配置"""
    # Cron 表达式配置
    cron: Optional[str] = Field(None, description="Cron 表达式，如 '0 2 * * *'")
    
    # 或者使用间隔配置
    interval_seconds: Optional[int] = Field(None, description="间隔秒数")
    interval_minutes: Optional[int] = Field(None, description="间隔分钟数")
    interval_hours: Optional[int] = Field(None, description="间隔小时数")
    
    # Cron 字段（可选，用于更细粒度控制）
    hour: Optional[str] = Field(None, description="小时，如 '2,14' 或 '*/2'")
    minute: Optional[str] = Field(None, description="分钟")
    day: Optional[str] = Field(None, description="日期")
    month: Optional[str] = Field(None, description="月份")
    day_of_week: Optional[str] = Field(None, description="星期")


class JobParams(BaseModel):
    """任务参数"""
    # 牛客参数
    nowcoder_keywords: Optional[List[str]] = Field(None, description="牛客搜索关键词")
    nowcoder_max_pages: Optional[int] = Field(None, description="牛客最大页数")
    
    # 小红书参数
    xhs_keywords: Optional[List[str]] = Field(None, description="小红书搜索关键词")
    xhs_max_notes: Optional[int] = Field(None, description="小红书每个关键词最大帖子数")
    xhs_headless: Optional[bool] = Field(True, description="小红书是否无头模式")
    
    # 任务处理参数
    process_batch_size: Optional[int] = Field(None, description="处理任务批次大小")


class JobCreate(BaseModel):
    """创建任务请求"""
    job_name: str = Field(..., description="任务名称")
    job_type: str = Field(..., description="任务类型: nowcoder_discovery / xhs_discovery / process_tasks")
    schedule_type: str = Field(..., description="调度类型: cron / interval")
    schedule_config: ScheduleConfig = Field(..., description="调度配置")
    job_params: Optional[JobParams] = Field(None, description="任务参数")
    enabled: bool = Field(True, description="是否启用")
    description: Optional[str] = Field(None, description="任务描述")


class JobUpdate(BaseModel):
    """更新任务请求"""
    job_name: Optional[str] = None
    job_type: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_config: Optional[ScheduleConfig] = None
    job_params: Optional[JobParams] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


class JobResponse(BaseModel):
    """任务响应"""
    job_id: str
    job_name: str
    job_type: str
    schedule_type: str
    schedule_config: dict
    job_params: dict
    enabled: bool
    description: Optional[str]
    created_at: str
    updated_at: str
    last_run_at: Optional[str]
    next_run_at: Optional[str]
    run_count: int
    last_status: Optional[str]
    last_result: Optional[dict]


# ══════════════════════════════════════════════════════════════
# API 端点
# ══════════════════════════════════════════════════════════════

@router.get("/jobs", response_model=List[JobResponse])
def list_jobs(
    enabled_only: bool = Query(False, description="仅显示启用的任务")
):
    """获取所有定时任务列表"""
    from backend.services.scheduler_service import scheduler_service
    jobs = scheduler_service.list_jobs(enabled_only=enabled_only)
    return jobs


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """获取单个任务详情"""
    from backend.services.scheduler_service import scheduler_service
    job = scheduler_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.post("/jobs", response_model=dict)
def create_job(job: JobCreate):
    """创建新的定时任务"""
    from backend.services.scheduler_service import scheduler_service
    from backend.services.scheduler import scheduler as crawl_scheduler
    
    # 验证任务类型
    valid_types = ["nowcoder_discovery", "xhs_discovery", "process_tasks"]
    if job.job_type not in valid_types:
        raise HTTPException(
            status_code=400, 
            detail=f"无效的任务类型，必须是: {', '.join(valid_types)}"
        )
    
    # 验证调度类型
    if job.schedule_type not in ["cron", "interval"]:
        raise HTTPException(status_code=400, detail="调度类型必须是 cron 或 interval")
    
    # 转换为数据库格式
    job_config = {
        "job_name": job.job_name,
        "job_type": job.job_type,
        "schedule_type": job.schedule_type,
        "schedule_config": job.schedule_config.dict(exclude_none=True),
        "job_params": job.job_params.dict(exclude_none=True) if job.job_params else {},
        "enabled": job.enabled,
        "description": job.description or ""
    }
    
    # 保存到数据库
    job_id = scheduler_service.add_job(job_config)
    
    # 如果启用，立即添加到调度器
    if job.enabled:
        try:
            crawl_scheduler.reload_jobs()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"添加任务到调度器失败: {e}")
    
    return {"status": "ok", "job_id": job_id, "message": "任务创建成功"}


@router.put("/jobs/{job_id}", response_model=dict)
def update_job(job_id: str, job: JobUpdate):
    """更新定时任务"""
    from backend.services.scheduler_service import scheduler_service
    from backend.services.scheduler import scheduler as crawl_scheduler
    
    # 检查任务是否存在
    existing = scheduler_service.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 合并更新
    job_config = {
        "job_name": job.job_name or existing["job_name"],
        "job_type": job.job_type or existing["job_type"],
        "schedule_type": job.schedule_type or existing["schedule_type"],
        "schedule_config": job.schedule_config.dict(exclude_none=True) if job.schedule_config else existing["schedule_config"],
        "job_params": job.job_params.dict(exclude_none=True) if job.job_params else existing["job_params"],
        "enabled": job.enabled if job.enabled is not None else existing["enabled"],
        "description": job.description if job.description is not None else existing["description"]
    }
    
    # 更新数据库
    scheduler_service.update_job(job_id, job_config)
    
    # 重新加载调度器
    try:
        crawl_scheduler.reload_jobs()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"重新加载调度器失败: {e}")
    
    return {"status": "ok", "message": "任务更新成功"}


@router.delete("/jobs/{job_id}", response_model=dict)
def delete_job(job_id: str):
    """删除定时任务"""
    from backend.services.scheduler_service import scheduler_service
    from backend.services.scheduler import scheduler as crawl_scheduler
    
    # 检查任务是否存在
    existing = scheduler_service.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 删除数据库记录
    scheduler_service.delete_job(job_id)
    
    # 重新加载调度器
    try:
        crawl_scheduler.reload_jobs()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"重新加载调度器失败: {e}")
    
    return {"status": "ok", "message": "任务删除成功"}


@router.post("/jobs/{job_id}/enable", response_model=dict)
def enable_job(job_id: str):
    """启用定时任务"""
    from backend.services.scheduler_service import scheduler_service
    from backend.services.scheduler import scheduler as crawl_scheduler
    
    existing = scheduler_service.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    scheduler_service.enable_job(job_id)
    
    try:
        crawl_scheduler.reload_jobs()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"重新加载调度器失败: {e}")
    
    return {"status": "ok", "message": "任务已启用"}


@router.post("/jobs/{job_id}/disable", response_model=dict)
def disable_job(job_id: str):
    """禁用定时任务"""
    from backend.services.scheduler_service import scheduler_service
    from backend.services.scheduler import scheduler as crawl_scheduler
    
    existing = scheduler_service.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    scheduler_service.disable_job(job_id)
    
    try:
        crawl_scheduler.reload_jobs()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"重新加载调度器失败: {e}")
    
    return {"status": "ok", "message": "任务已禁用"}


@router.post("/jobs/{job_id}/run", response_model=dict)
async def run_job_now(job_id: str):
    """立即执行任务（不影响定时计划）- 异步执行"""
    import asyncio
    from backend.services.scheduler_service import scheduler_service
    from backend.services.scheduler import scheduler as crawl_scheduler
    
    job = scheduler_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 异步执行任务，不阻塞响应
    async def run_task_async():
        try:
            job_params = job.get("job_params", {})
            
            if job["job_type"] == "nowcoder_discovery":
                keywords = job_params.get('nowcoder_keywords')
                max_pages = job_params.get('nowcoder_max_pages')
                await asyncio.to_thread(
                    crawl_scheduler.trigger_nowcoder_discovery,
                    keywords=keywords,
                    max_pages=max_pages
                )
            elif job["job_type"] == "xhs_discovery":
                keywords = job_params.get('xhs_keywords')
                max_notes = job_params.get('xhs_max_notes')
                headless = job_params.get('xhs_headless', True)
                await asyncio.to_thread(
                    crawl_scheduler.trigger_xhs_discovery,
                    keywords=keywords,
                    max_notes=max_notes,
                    headless=headless
                )
            elif job["job_type"] == "process_tasks":
                batch_size = job_params.get('process_batch_size')
                await asyncio.to_thread(
                    crawl_scheduler.trigger_process_tasks,
                    batch_size=batch_size
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"后台任务执行失败: {e}", exc_info=True)
    
    # 在后台启动任务
    asyncio.create_task(run_task_async())
    
    return {"status": "ok", "message": "任务已在后台启动，不会阻塞其他操作"}


@router.get("/job-types", response_model=List[dict])
def get_job_types():
    """获取支持的任务类型列表"""
    return [
        {
            "type": "nowcoder_discovery",
            "name": "牛客面经发现",
            "description": "从牛客网搜索并发现新的面经帖子",
            "params": ["nowcoder_keywords", "nowcoder_max_pages"]
        },
        {
            "type": "xhs_discovery",
            "name": "小红书面经发现",
            "description": "从小红书搜索并发现新的面经帖子",
            "params": ["xhs_keywords", "xhs_max_notes", "xhs_headless"]
        },
        {
            "type": "process_tasks",
            "name": "任务队列处理",
            "description": "处理待爬取的任务队列，提取题目",
            "params": ["process_batch_size"]
        }
    ]


@router.get("/schedule-examples", response_model=List[dict])
def get_schedule_examples():
    """获取常用的调度配置示例"""
    return [
        {
            "name": "每天凌晨2点",
            "schedule_type": "cron",
            "schedule_config": {"hour": "2", "minute": "0"}
        },
        {
            "name": "每天上午10点和下午3点",
            "schedule_type": "cron",
            "schedule_config": {"hour": "10,15", "minute": "0"}
        },
        {
            "name": "每小时整点",
            "schedule_type": "cron",
            "schedule_config": {"minute": "0"}
        },
        {
            "name": "每30分钟",
            "schedule_type": "interval",
            "schedule_config": {"interval_minutes": 30}
        },
        {
            "name": "每2小时",
            "schedule_type": "interval",
            "schedule_config": {"interval_hours": 2}
        },
        {
            "name": "每天早上8点到晚上8点，每小时一次",
            "schedule_type": "cron",
            "schedule_config": {"hour": "8-20", "minute": "0"}
        }
    ]
