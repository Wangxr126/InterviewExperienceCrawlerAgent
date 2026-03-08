# 调度器重构设计文档

## 📋 重构目标

1. **统一调用逻辑**：定时任务和手动触发共用同一套核心方法
2. **数据库管理定时任务**：将定时任务配置存储在 SQLite 中，支持动态增删改查
3. **前端可视化管理**：提供完整的定时任务管理界面
4. **灵活的调度策略**：支持 cron 表达式和间隔时间两种方式

## 🏗️ 架构设计

### 1. 数据库设计

#### 新增表：`scheduled_jobs`

```sql
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_id TEXT PRIMARY KEY,              -- 任务ID（UUID）
    job_name TEXT NOT NULL,               -- 任务名称
    job_type TEXT NOT NULL,               -- 任务类型：nowcoder_discovery / xhs_discovery / process_tasks
    schedule_type TEXT NOT NULL,          -- 调度类型：cron / interval
    schedule_config TEXT NOT NULL,        -- 调度配置（JSON）
    job_params TEXT,                      -- 任务参数（JSON）
    enabled INTEGER DEFAULT 1,            -- 是否启用（0/1）
    description TEXT,                     -- 任务描述
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run_at TIMESTAMP,                -- 上次运行时间
    next_run_at TIMESTAMP,                -- 下次运行时间
    run_count INTEGER DEFAULT 0,          -- 运行次数
    last_status TEXT,                     -- 上次运行状态：success / error
    last_result TEXT                      -- 上次运行结果（JSON）
);
```

**字段说明**：

- `schedule_type`：
  - `cron`：使用 cron 表达式（如 `0 2,14 * * *`）
  - `interval`：使用间隔时间（如每小时、每30分钟）

- `schedule_config`：JSON 格式
  ```json
  // cron 类型
  {
    "hour": "2,14",
    "minute": "0",
    "day": "*",
    "month": "*",
    "day_of_week": "*"
  }
  
  // interval 类型
  {
    "hours": 1,
    "minutes": 0,
    "seconds": 0
  }
  ```

- `job_params`：任务特定参数（JSON）
  ```json
  // nowcoder_discovery
  {
    "keywords": ["Java后端", "Python后端"],
    "max_pages": 2
  }
  
  // xhs_discovery
  {
    "keywords": ["Java面经", "Python面经"],
    "max_notes_per_keyword": 10,
    "headless": true
  }
  
  // process_tasks
  {
    "batch_size": 10
  }
  ```

### 2. 核心类重构

#### CrawlScheduler 类结构

```python
class CrawlScheduler:
    """面经爬取调度器（支持数据库配置）"""
    
    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._running = False
        self._job_registry = {}  # 任务注册表
    
    # ========== 核心执行方法（被定时任务和手动触发共用）==========
    
    async def run_nowcoder_discovery(self, keywords=None, max_pages=None):
        """牛客发现任务 - 核心逻辑"""
        pass
    
    async def run_xhs_discovery(self, keywords=None, max_notes=None, headless=True):
        """小红书发现任务 - 核心逻辑"""
        pass
    
    async def run_process_tasks(self, batch_size=None):
        """任务处理 - 核心逻辑"""
        pass
    
    # ========== 调度器管理 ==========
    
    def start(self):
        """启动调度器，从数据库加载所有启用的任务"""
        pass
    
    def stop(self):
        """停止调度器"""
        pass
    
    def reload_jobs(self):
        """重新加载数据库中的任务配置"""
        pass
    
    # ========== 任务管理（CRUD）==========
    
    def add_job(self, job_config: dict) -> str:
        """添加新任务"""
        pass
    
    def update_job(self, job_id: str, job_config: dict):
        """更新任务配置"""
        pass
    
    def delete_job(self, job_id: str):
        """删除任务"""
        pass
    
    def enable_job(self, job_id: str):
        """启用任务"""
        pass
    
    def disable_job(self, job_id: str):
        """禁用任务"""
        pass
    
    def get_job(self, job_id: str) -> dict:
        """获取任务详情"""
        pass
    
    def list_jobs(self) -> List[dict]:
        """列出所有任务"""
        pass
    
    # ========== 手动触发（调用核心方法）==========
    
    async def trigger_job(self, job_id: str):
        """手动触发指定任务"""
        pass
```

### 3. API 接口设计

#### 任务管理接口

```python
# 列出所有定时任务
GET /api/scheduler/jobs

# 获取任务详情
GET /api/scheduler/jobs/{job_id}

# 创建新任务
POST /api/scheduler/jobs
Body: {
    "job_name": "牛客每日爬取",
    "job_type": "nowcoder_discovery",
    "schedule_type": "cron",
    "schedule_config": {"hour": "2,14", "minute": "0"},
    "job_params": {"keywords": ["Java后端"], "max_pages": 2},
    "enabled": true,
    "description": "每天2点和14点爬取牛客面经"
}

# 更新任务
PUT /api/scheduler/jobs/{job_id}
Body: {同创建}

# 删除任务
DELETE /api/scheduler/jobs/{job_id}

# 启用/禁用任务
POST /api/scheduler/jobs/{job_id}/enable
POST /api/scheduler/jobs/{job_id}/disable

# 手动触发任务
POST /api/scheduler/jobs/{job_id}/trigger

# 获取任务运行历史
GET /api/scheduler/jobs/{job_id}/history
```

#### 统计接口（保持兼容）

```python
# 获取调度器状态
GET /api/scheduler/stats
Response: {
    "running": true,
    "total_jobs": 3,
    "enabled_jobs": 2,
    "disabled_jobs": 1,
    "crawl_stats": {...},
    "keywords": [...]
}
```

### 4. 前端界面设计

#### 定时任务管理页面

**路由**：`/scheduler`

**功能模块**：

1. **任务列表**
   - 显示所有定时任务
   - 状态标识（启用/禁用）
   - 下次运行时间
   - 上次运行结果
   - 操作按钮（编辑/删除/启用/禁用/立即运行）

2. **添加/编辑任务表单**
   - 任务名称
   - 任务类型（下拉选择）
   - 调度类型（Cron / 间隔）
   - 调度配置（动态表单）
   - 任务参数（根据类型动态显示）
   - 任务描述

3. **任务详情弹窗**
   - 基本信息
   - 运行统计
   - 最近运行历史

## 🔄 重构步骤

### Phase 1: 数据库层

1. ✅ 创建 `scheduled_jobs` 表
2. ✅ 实现 SQLite 服务的 CRUD 方法
3. ✅ 数据迁移：将现有 .env 配置导入数据库

### Phase 2: 后端重构

1. ✅ 重构 `CrawlScheduler` 类
2. ✅ 实现核心执行方法（统一逻辑）
3. ✅ 实现任务管理方法
4. ✅ 实现 API 接口
5. ✅ 向后兼容：保留原有触发接口

### Phase 3: 前端开发

1. ✅ 创建定时任务管理页面
2. ✅ 实现任务列表组件
3. ✅ 实现任务表单组件
4. ✅ 实现任务详情组件
5. ✅ 集成到主导航

### Phase 4: 测试与优化

1. ✅ 单元测试
2. ✅ 集成测试
3. ✅ 性能优化
4. ✅ 文档更新

## 📝 配置迁移

### 从 .env 迁移到数据库

**迁移脚本**：`backend/scripts/migrate_scheduler_config.py`

```python
"""
将 .env 中的调度器配置迁移到数据库
运行：python -m backend.scripts.migrate_scheduler_config
"""

def migrate_config():
    # 读取 .env 配置
    nowcoder_enabled = settings.scheduler_enable_nowcoder
    nowcoder_hours = settings.scheduler_nowcoder_hours
    nowcoder_keywords = settings.nowcoder_keywords
    nowcoder_max_pages = settings.nowcoder_max_pages
    
    # 创建牛客任务
    if nowcoder_enabled:
        add_job({
            "job_name": "牛客面经定时爬取",
            "job_type": "nowcoder_discovery",
            "schedule_type": "cron",
            "schedule_config": {
                "hour": nowcoder_hours,
                "minute": "0"
            },
            "job_params": {
                "keywords": nowcoder_keywords,
                "max_pages": nowcoder_max_pages
            },
            "enabled": True,
            "description": "从 .env 迁移的牛客定时任务"
        })
    
    # 创建任务处理器
    process_minute = settings.scheduler_process_minute
    batch_size = settings.crawler_process_batch_size
    
    add_job({
        "job_name": "面经题目提取处理器",
        "job_type": "process_tasks",
        "schedule_type": "cron",
        "schedule_config": {
            "minute": process_minute
        },
        "job_params": {
            "batch_size": batch_size
        },
        "enabled": True,
        "description": "从 .env 迁移的任务处理器"
    })
```

## 🎯 优势总结

### 1. 代码复用
- 定时任务和手动触发共用核心方法
- 减少重复代码，易于维护

### 2. 灵活配置
- 无需修改代码即可调整定时任务
- 支持动态增删改查
- 支持多种调度策略

### 3. 可视化管理
- 前端界面直观操作
- 实时查看任务状态
- 运行历史追踪

### 4. 向后兼容
- 保留原有 API 接口
- 支持 .env 配置迁移
- 平滑升级路径

### 5. 扩展性强
- 易于添加新的任务类型
- 支持复杂的调度策略
- 便于集成监控告警

## 📌 注意事项

1. **数据库事务**：任务配置的增删改需要事务保护
2. **并发控制**：同一任务不能同时运行多次
3. **错误处理**：任务失败需要记录详细日志
4. **性能优化**：大量任务时需要优化查询
5. **安全性**：任务参数需要验证，防止注入攻击

## 🚀 下一步

1. 实现数据库表和 CRUD 方法
2. 重构 CrawlScheduler 类
3. 实现 API 接口
4. 开发前端界面
5. 编写迁移脚本
6. 测试和文档更新
