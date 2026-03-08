# 日志格式统一 & ID 列显示修复

## 修改时间
2026-03-09

## 问题描述

1. **ID 列不显示**：前端表格添加了 ID 列，但没有数据显示
2. **日志格式混乱**：多种日志格式混杂，难以阅读
   - `02:36:33 | INFO | ✅ 编排器初始化完成` (loguru 短格式)
   - `INFO:     127.0.0.1:64326 - "GET /api/finetune/stats HTTP/1.1" 200 OK` (uvicorn 原始格式)
   - 堆栈跟踪格式不统一

## 解决方案

### 1. ID 列显示修复

#### 后端修改 (`backend/main.py`)
```python
# 在 /api/crawler/tasks 接口中
SELECT id, task_id, source_url, source_platform, post_title, status, ...
FROM crawl_tasks {where} ORDER BY id ASC LIMIT ? OFFSET ?
```

**关键改动：**
- ✅ 添加 `id` 字段到 SELECT 查询
- ✅ 排序改为 `ORDER BY id ASC`（按插入顺序）

#### 前端修改 (`web/src/views/CollectView.vue`)
```vue
<el-table-column label="ID" prop="id" width="60" align="center" />
```

**关键改动：**
- ✅ 添加 ID 列作为第一列
- ✅ 列宽 60px，居中对齐

### 2. 日志格式统一

#### 统一格式标准
```
YYYY-MM-DD HH:mm:ss | LEVEL   | MESSAGE
```

**示例：**
```
2026-03-09 02:36:33 | INFO    | ✅ 日志系统已启动（统一格式）
2026-03-09 02:36:35 | INFO    | [HTTP] GET /api/crawler/tasks → 200
2026-03-09 02:37:17 | ERROR   | 加载任务失败 小红书面经发现: unsupported type...
```

#### 修改内容 (`backend/main.py`)

1. **统一时间格式**：从 `HH:mm:ss` 改为 `YYYY-MM-DD HH:mm:ss`
2. **统一级别宽度**：从 `<4` 改为 `<7`（对齐 WARNING）
3. **简化 HTTP 日志**：
   - 原格式：`INFO:     127.0.0.1:64326 - "GET /api/finetune/stats HTTP/1.1" 200 OK`
   - 新格式：`2026-03-09 02:36:33 | INFO    | [HTTP] GET /api/finetune/stats → 200`
4. **移除冗余信息**：去掉 `{name}:{function}` 部分

#### 代码改动
```python
# 统一的日志格式
_log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"

# 简化 uvicorn 访问日志
if record.name == "uvicorn.access":
    import re
    match = re.search(r'"([A-Z]+)\s+([^\s]+)[^"]*"\s+(\d+)', msg)
    if match:
        method, path, status = match.groups()
        msg = f"[HTTP] {method} {path} → {status}"
```

## 使用说明

### 重启后端服务（必须！）
```bash
# 停止当前服务（Ctrl+C）
# 重新启动
python run.py
```

### 验证修改

1. **验证 ID 列显示**：
   - 刷新前端页面
   - 查看帖子记录表格第一列是否显示 ID
   - ID 应该按从小到大排序（最早插入的在最上面）

2. **验证日志格式**：
   - 查看终端输出
   - 所有日志应该使用统一格式：`YYYY-MM-DD HH:mm:ss | LEVEL | MESSAGE`
   - HTTP 请求日志应该简化为：`[HTTP] METHOD PATH → STATUS`

## 效果对比

### 日志格式对比

**修改前：**
```
02:36:33 | INFO | ✅ 编排器初始化完成
INFO:     127.0.0.1:64326 - "GET /api/finetune/stats HTTP/1.1" 200 OK
02:37:17 | ERROR | 加载任务失败...
```

**修改后：**
```
2026-03-09 02:36:33 | INFO    | ✅ 编排器初始化完成
2026-03-09 02:36:33 | INFO    | [HTTP] GET /api/finetune/stats → 200
2026-03-09 02:37:17 | ERROR   | 加载任务失败...
```

### ID 列显示对比

**修改前：**
- 表格没有 ID 列
- 无法看到插入顺序

**修改后：**
- 第一列显示数据库主键 ID
- 按 ID 从小到大排序（插入顺序）
- 可以清楚看到每个帖子的插入顺序

## 技术细节

### 为什么需要重启？
- Python 是解释型语言
- 修改代码后，只有重新加载模块才会生效
- 重启服务会重新加载所有模块，包括修改的 `main.py`

### 日志格式设计原则
1. **时间完整**：包含日期和时间，便于追溯
2. **级别对齐**：固定宽度，便于扫描
3. **信息简洁**：移除冗余信息（IP、协议版本等）
4. **格式统一**：所有日志使用相同格式

### ID 列的意义
- **主键**：数据库自增主键，唯一标识每条记录
- **插入顺序**：ID 越小，插入越早
- **爬取顺序**：插入顺序 = 爬取顺序（因为是按爬取顺序插入的）

## 相关文件

- `backend/main.py` - 后端主文件（日志配置 + API 接口）
- `web/src/views/CollectView.vue` - 前端帖子列表页面
- `backend/services/sqlite_service.py` - 数据库服务（表结构定义）

## 注意事项

1. **必须重启后端**：修改代码后必须重启才能生效
2. **数据库已有 ID**：数据库中的记录本来就有 ID，只是之前 API 没返回
3. **日志文件格式**：文件日志也使用统一格式，便于后续分析
4. **HTTP 日志简化**：只保留关键信息（方法、路径、状态码）

## 验证清单

- [ ] 后端服务已重启
- [ ] 前端页面已刷新
- [ ] ID 列正常显示
- [ ] ID 按从小到大排序
- [ ] 日志格式统一
- [ ] HTTP 日志简化
- [ ] 无报错信息
