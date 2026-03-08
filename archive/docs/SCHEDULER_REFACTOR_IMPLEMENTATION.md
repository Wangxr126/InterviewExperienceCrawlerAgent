# 调度器重构实施指南

## 📋 已完成的文件

### 1. 设计文档
- ✅ `SCHEDULER_REFACTOR_DESIGN.md` - 完整的重构设计文档

### 2. 后端文件
- ✅ `backend/services/scheduler_service.py` - 数据库服务（CRUD）
- ✅ `backend/services/scheduler_refactored.py` - 重构后的调度器
- ✅ `backend/api/scheduler_api.py` - API 接口
- ✅ `backend/scripts/migrate_scheduler_config.py` - 配置迁移脚本

### 3. 前端文件
- ✅ `frontend/scheduler.html` - 定时任务管理界面

## 🚀 实施步骤

### Step 1: 备份现有代码

```bash
# 备份原有调度器
cp backend/services/scheduler.py backend/services/scheduler_old.py
```

### Step 2: 运行配置迁移

```bash
# 迁移 .env 配置到数据库
python -m backend.scripts.migrate_scheduler_config
```

**预期输出**：
```
🔄 开始迁移调度器配置...

📋 迁移牛客定时任务...
   ✅ 已创建任务：牛客面经定时爬取 (ID: xxx)

📋 迁移任务处理器...
   ✅ 已创建任务：面经题目提取处理器 (ID: xxx)

✅ 迁移完成！共创建 2 个定时任务
```

### Step 3: 修改 backend/main.py

在 `backend/main.py` 中，将调度器导入改为新版本：

```python
# 原来的导入（注释掉）
# from backend.services.scheduler import crawl_scheduler

# 新的导入
from backend.services.scheduler_refactored import crawl_scheduler

# 添加新的 API 路由
from backend.api.scheduler_api import router as scheduler_router
app.include_router(scheduler_router)
```

**完整修改位置**：

```python
# 在文件顶部导入部分（约第 100 行）
from backend.services.scheduler_refactored import crawl_scheduler  # 修改这行

# 在 app 创建后添加路由（约第 200 行）
from backend.api.scheduler_api import router as scheduler_router
app.include_router(scheduler_router)

# startup_event 中的调度器启动保持不变
@app.on_event("startup")
async def startup_event():
    # ... 其他代码 ...
    crawl_scheduler.start()  # 这行不变
```

### Step 4: 添加前端路由

在 `backend/main.py` 中添加静态文件服务：

```python
# 在 app 创建后添加（约第 210 行）
from fastapi.responses import FileResponse

@app.get("/scheduler")
async def scheduler_page():
    """定时任务管理页面"""
    return FileResponse("frontend/scheduler.html")
```

### Step 5: 重启应用

```bash
python run.py
```

### Step 6: 验证功能

1. **访问管理界面**：http://localhost:8000/scheduler
2. **检查任务列表**：应该看到迁移的 2-3 个任务
3. **测试手动触发**：点击"运行"按钮测试任务执行
4. **测试创建任务**：创建一个新的测试任务
5. **测试编辑任务**：修改任务配置
6. **测试启用/禁用**：切换任务状态
7. **测试删除任务**：删除测试任务

## 🔍 验证清单

### 数据库验证

```bash
# 进入 SQLite
sqlite3 backend/data/interview_agent.db

# 查看任务表
.schema scheduled_jobs
SELECT * FROM scheduled_jobs;
```

### API 验证

```bash
# 获取任务列表
curl http://localhost:8000/api/scheduler/jobs

# 获取统计信息
curl http://localhost:8000/api/scheduler/stats

# 手动触发任务（替换 JOB_ID）
curl -X POST http://localhost:8000/api/scheduler/jobs/JOB_ID/trigger
```

### 日志验证

查看日志文件 `backend/logs/backend.log`，确认：
- ✅ 调度器启动成功
- ✅ 任务加载成功
- ✅ 定时任务按时执行
- ✅ 手动触发正常工作

## 🐛 常见问题

### 问题 1: 迁移脚本报错 "table already exists"

**原因**：数据库表已存在

**解决**：
```bash
# 删除旧表（谨慎操作！）
sqlite3 backend/data/interview_agent.db "DROP TABLE IF EXISTS scheduled_jobs;"

# 重新运行迁移
python -m backend.scripts.migrate_scheduler_config
```

### 问题 2: 前端页面 404

**原因**：路由未添加

**解决**：确认 `backend/main.py` 中添加了 `/scheduler` 路由

### 问题 3: 任务不执行

**原因**：调度器未启动或任务被禁用

**解决**：
1. 检查日志确认调度器已启动
2. 在前端界面检查任务状态
3. 手动触发测试任务是否正常

### 问题 4: API 返回 500 错误

**原因**：导入错误或数据库连接问题

**解决**：
1. 检查 `backend/main.py` 的导入语句
2. 确认数据库文件存在
3. 查看详细错误日志

## 📊 性能对比

### 重构前
- ❌ 配置硬编码在代码中
- ❌ 修改需要重启应用
- ❌ 无法动态管理任务
- ❌ 定时任务和手动触发逻辑重复

### 重构后
- ✅ 配置存储在数据库
- ✅ 支持热重载（无需重启）
- ✅ 完整的 CRUD 管理
- ✅ 统一的核心执行逻辑
- ✅ 可视化管理界面
- ✅ 运行历史追踪

## 🎯 后续优化建议

### 1. 任务运行历史表

创建 `job_run_history` 表记录每次运行的详细信息：

```sql
CREATE TABLE job_run_history (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status TEXT,
    result TEXT,
    error_message TEXT,
    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(job_id)
);
```

### 2. 任务依赖关系

支持任务之间的依赖关系（A 完成后才能运行 B）

### 3. 任务失败重试

自动重试失败的任务，支持配置重试次数和间隔

### 4. 任务执行超时

设置任务最大执行时间，超时自动终止

### 5. 邮件/钉钉通知

任务失败时发送通知

### 6. 任务执行日志

在前端界面查看任务的详细执行日志

### 7. 任务分组

支持任务分组管理（如：爬虫任务组、处理任务组）

### 8. 任务优先级

支持设置任务优先级，高优先级任务优先执行

## 📝 回滚方案

如果重构后出现问题，可以快速回滚：

```bash
# 1. 恢复旧的调度器
cp backend/services/scheduler_old.py backend/services/scheduler.py

# 2. 修改 main.py 导入
# 将 scheduler_refactored 改回 scheduler

# 3. 注释掉新的 API 路由
# app.include_router(scheduler_router)

# 4. 重启应用
python run.py
```

## ✅ 验收标准

重构完成后，需要满足以下标准：

1. ✅ 所有原有定时任务正常运行
2. ✅ 手动触发功能正常工作
3. ✅ 前端界面可以访问和操作
4. ✅ 可以创建、编辑、删除任务
5. ✅ 可以启用、禁用任务
6. ✅ 任务运行状态正确更新
7. ✅ 日志记录完整清晰
8. ✅ 无性能下降
9. ✅ 无内存泄漏
10. ✅ 向后兼容（旧的触发接口仍可用）

## 🎉 完成

重构完成后，你将拥有：

- 🎨 现代化的任务管理界面
- 🔧 灵活的任务配置系统
- 📊 完整的运行状态追踪
- 🚀 更好的可维护性
- 💪 更强的扩展性

恭喜！你已经完成了调度器的重构！🎊
