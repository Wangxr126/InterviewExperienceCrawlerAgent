# 定时任务管理系统 - 完整实现文档

## 系统概述

已完成的定时任务管理系统，支持通过前端界面可视化管理定时任务，无需修改 .env 文件。

## 后端实现

### 1. 数据库表结构

**表名**: `scheduled_jobs`

已在 `backend/services/scheduler_service.py` 中实现，包含以下字段：

- `job_id` (TEXT PRIMARY KEY) - 任务唯一标识
- `job_name` (TEXT NOT NULL) - 任务名称
- `job_type` (TEXT NOT NULL) - 任务类型（nowcoder_discovery / xhs_discovery / process_tasks）
- `schedule_type` (TEXT NOT NULL) - 调度类型（cron / interval）
- `schedule_config` (TEXT NOT NULL) - 调度配置（JSON）
- `job_params` (TEXT) - 任务参数（JSON）
- `enabled` (INTEGER DEFAULT 1) - 是否启用
- `description` (TEXT) - 任务描述
- `created_at` (TIMESTAMP) - 创建时间
- `updated_at` (TIMESTAMP) - 更新时间
- `last_run_at` (TIMESTAMP) - 最后运行时间
- `next_run_at` (TIMESTAMP) - 下次运行时间
- `run_count` (INTEGER DEFAULT 0) - 运行次数
- `last_status` (TEXT) - 最后运行状态
- `last_result` (TEXT) - 最后运行结果（JSON）

### 2. API 接口

**文件**: `backend/api/scheduler_api.py`

#### 任务管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scheduler/jobs` | 获取所有任务列表 |
| GET | `/api/scheduler/jobs/{job_id}` | 获取单个任务详情 |
| POST | `/api/scheduler/jobs` | 创建新任务 |
| PUT | `/api/scheduler/jobs/{job_id}` | 更新任务 |
| DELETE | `/api/scheduler/jobs/{job_id}` | 删除任务 |
| POST | `/api/scheduler/jobs/{job_id}/enable` | 启用任务 |
| POST | `/api/scheduler/jobs/{job_id}/disable` | 禁用任务 |
| POST | `/api/scheduler/jobs/{job_id}/run` | 立即执行任务 |

#### 辅助接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scheduler/job-types` | 获取支持的任务类型 |
| GET | `/api/scheduler/schedule-examples` | 获取常用调度配置示例 |

### 3. 调度器集成

**文件**: `backend/services/scheduler.py`

已添加 `reload_jobs()` 方法到 `CrawlScheduler` 类：
- 从数据库加载启用的任务
- 动态添加到 APScheduler
- 支持热重载，无需重启服务

### 4. 路由注册

**文件**: `backend/main.py`

已添加路由注册：
```python
from backend.api.scheduler_api import router as scheduler_router
app.include_router(scheduler_router)
```

## 前端界面设计

### 页面结构

建议创建 `frontend/scheduler.html` 页面，包含以下部分：

#### 1. 任务列表视图

```
┌─────────────────────────────────────────────────────────────┐
│  定时任务管理                          [+ 新建任务]  [刷新]  │
├─────────────────────────────────────────────────────────────┤
│  筛选: [全部任务 ▼] [全部类型 ▼]                           │
├─────────────────────────────────────────────────────────────┤
│  任务名称          类型        调度时间      状态    操作    │
│  ─────────────────────────────────────────────────────────  │
│  牛客面经发现      牛客发现    每天 2:00    ●启用   [编辑]  │
│                                             [禁用]  [立即执行]│
│                                             [删除]           │
│  ─────────────────────────────────────────────────────────  │
│  小红书面经发现    小红书发现  每天 3:00    ○禁用   [编辑]  │
│                                             [启用]  [立即执行]│
│                                             [删除]           │
│  ─────────────────────────────────────────────────────────  │
│  任务队列处理      任务处理    每小时整点   ●启用   [编辑]  │
│                                             [禁用]  [立即执行]│
│                                             [删除]           │
└─────────────────────────────────────────────────────────────┘
```

#### 2. 任务详情/编辑表单

```
┌─────────────────────────────────────────────────────────────┐
│  新建/编辑任务                                    [保存] [取消]│
├─────────────────────────────────────────────────────────────┤
│  基本信息                                                    │
│  ─────────────────────────────────────────────────────────  │
│  任务名称: [_____________________________________]           │
│  任务类型: [牛客面经发现 ▼]                                 │
│  任务描述: [_____________________________________]           │
│  启用状态: [✓] 启用                                         │
│                                                              │
│  调度配置                                                    │
│  ─────────────────────────────────────────────────────────  │
│  调度类型: ○ Cron表达式  ● 固定间隔                        │
│                                                              │
│  Cron配置:                                                   │
│    小时: [2,14___] (如: 2,14 或 */2 或 8-20)               │
│    分钟: [0______] (如: 0 或 */30)                         │
│    常用模板: [每天凌晨2点 ▼]                                │
│                                                              │
│  或 间隔配置:                                                │
│    间隔: [30___] [分钟 ▼]                                   │
│                                                              │
│  任务参数                                                    │
│  ─────────────────────────────────────────────────────────  │
│  (根据任务类型动态显示)                                      │
│                                                              │
│  牛客发现参数:                                               │
│    搜索关键词: [面经, agent面经___________]                 │
│    最大页数: [3___]                                         │
│                                                              │
│  小红书发现参数:                                             │
│    搜索关键词: [agent面经, 大模型面经_____]                 │
│    每个关键词最大帖子数: [20__]                             │
│    无头模式: [✓] 启用                                       │
│                                                              │
│  任务处理参数:                                               │
│    批次大小: [10__]                                         │
└─────────────────────────────────────────────────────────────┘
```

#### 3. 任务执行历史

```
┌─────────────────────────────────────────────────────────────┐
│  执行历史                                                    │
├─────────────────────────────────────────────────────────────┤
│  最后运行: 2026-03-09 02:00:15                              │
│  下次运行: 2026-03-10 02:00:00                              │
│  运行次数: 45 次                                             │
│  最后状态: ✓ 成功                                           │
│  最后结果: 发现 15 条，新增队列 12 条                       │
└─────────────────────────────────────────────────────────────┘
```

### 前端实现要点

#### 1. 获取任务列表

```javascript
async function loadJobs() {
    const response = await fetch('/api/scheduler/jobs');
    const jobs = await response.json();
    renderJobList(jobs);
}
```

#### 2. 创建任务

```javascript
async function createJob(jobData) {
    const response = await fetch('/api/scheduler/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            job_name: jobData.name,
            job_type: jobData.type,
            schedule_type: jobData.scheduleType,
            schedule_config: {
                hour: jobData.hour,
                minute: jobData.minute,
                // 或
                interval_minutes: jobData.intervalMinutes
            },
            job_params: {
                nowcoder_keywords: jobData.keywords,
                nowcoder_max_pages: jobData.maxPages
            },
            enabled: jobData.enabled,
            description: jobData.description
        })
    });
    return await response.json();
}
```

#### 3. 启用/禁用任务

```javascript
async function toggleJob(jobId, enable) {
    const action = enable ? 'enable' : 'disable';
    const response = await fetch(`/api/scheduler/jobs/${jobId}/${action}`, {
        method: 'POST'
    });
    return await response.json();
}
```

#### 4. 立即执行任务

```javascript
async function runJobNow(jobId) {
    const response = await fetch(`/api/scheduler/jobs/${jobId}/run`, {
        method: 'POST'
    });
    return await response.json();
}
```

#### 5. 获取任务类型和示例

```javascript
async function loadJobTypes() {
    const response = await fetch('/api/scheduler/job-types');
    return await response.json();
}

async function loadScheduleExamples() {
    const response = await fetch('/api/scheduler/schedule-examples');
    return await response.json();
}
```

### UI 组件建议

#### 1. 任务类型选择器

```html
<select id="jobType" onchange="updateParamsForm()">
    <option value="nowcoder_discovery">牛客面经发现</option>
    <option value="xhs_discovery">小红书面经发现</option>
    <option value="process_tasks">任务队列处理</option>
</select>
```

#### 2. 调度配置切换

```html
<div class="schedule-type">
    <label>
        <input type="radio" name="scheduleType" value="cron" checked>
        Cron表达式
    </label>
    <label>
        <input type="radio" name="scheduleType" value="interval">
        固定间隔
    </label>
</div>

<div id="cronConfig" class="schedule-config">
    <label>小时: <input type="text" id="cronHour" placeholder="如: 2,14 或 */2"></label>
    <label>分钟: <input type="text" id="cronMinute" placeholder="如: 0 或 */30"></label>
    <select id="cronTemplate" onchange="applyCronTemplate()">
        <option value="">选择常用模板...</option>
        <option value="daily-2am">每天凌晨2点</option>
        <option value="twice-daily">每天上午10点和下午3点</option>
        <option value="hourly">每小时整点</option>
    </select>
</div>

<div id="intervalConfig" class="schedule-config" style="display:none;">
    <label>间隔: <input type="number" id="intervalValue"></label>
    <select id="intervalUnit">
        <option value="minutes">分钟</option>
        <option value="hours">小时</option>
    </select>
</div>
```

#### 3. 动态参数表单

```javascript
function updateParamsForm() {
    const jobType = document.getElementById('jobType').value;
    const paramsDiv = document.getElementById('jobParams');
    
    if (jobType === 'nowcoder_discovery') {
        paramsDiv.innerHTML = `
            <label>搜索关键词 (逗号分隔):
                <input type="text" id="nowcoderKeywords" value="面经">
            </label>
            <label>最大页数:
                <input type="number" id="nowcoderMaxPages" value="3">
            </label>
        `;
    } else if (jobType === 'xhs_discovery') {
        paramsDiv.innerHTML = `
            <label>搜索关键词 (逗号分隔):
                <input type="text" id="xhsKeywords" value="agent面经">
            </label>
            <label>每个关键词最大帖子数:
                <input type="number" id="xhsMaxNotes" value="20">
            </label>
            <label>
                <input type="checkbox" id="xhsHeadless" checked>
                无头模式
            </label>
        `;
    } else if (jobType === 'process_tasks') {
        paramsDiv.innerHTML = `
            <label>批次大小:
                <input type="number" id="processBatchSize" value="10">
            </label>
        `;
    }
}
```

## 使用流程

### 1. 创建新任务

1. 点击"新建任务"按钮
2. 填写任务名称和描述
3. 选择任务类型（牛客发现/小红书发现/任务处理）
4. 配置调度时间（Cron 或间隔）
5. 设置任务参数
6. 点击"保存"

### 2. 管理现有任务

- **启用/禁用**: 点击对应按钮，任务会立即生效/停止
- **编辑**: 修改任务配置，保存后自动重新加载
- **删除**: 删除任务，调度器自动移除
- **立即执行**: 手动触发一次执行，不影响定时计划

### 3. 查看执行历史

- 最后运行时间
- 下次运行时间
- 运行次数
- 最后状态和结果

## 优势

1. **可视化管理**: 无需修改 .env 文件或重启服务
2. **动态生效**: 任务修改后立即生效
3. **灵活配置**: 支持 Cron 表达式和固定间隔两种方式
4. **参数化**: 每个任务可以有独立的参数配置
5. **执行历史**: 记录每次执行的结果
6. **手动触发**: 支持立即执行，方便测试

## 测试建议

1. **创建测试任务**: 创建一个每分钟执行的任务，验证调度器工作正常
2. **修改任务**: 修改任务配置，确认立即生效
3. **启用/禁用**: 测试任务的启用和禁用功能
4. **立即执行**: 测试手动触发功能
5. **删除任务**: 确认任务被正确删除

## 注意事项

1. **时区**: 所有时间使用 Asia/Shanghai 时区
2. **并发**: 同一任务不会并发执行（APScheduler 默认行为）
3. **错过执行**: misfire_grace_time 设置为 3600 秒，错过的任务会在 1 小时内补执行
4. **数据库**: 任务配置存储在 SQLite，与题目数据在同一数据库
5. **重启**: 服务重启后会自动加载数据库中的任务

## 下一步

1. 创建前端页面 `frontend/scheduler.html`
2. 实现上述 UI 组件和交互逻辑
3. 测试完整流程
4. 根据需要添加更多功能（如任务执行日志、统计图表等）
