# 数据库字段迁移总结：extract_duration_sec → extract_duration_min

## 迁移完成时间
2026-03-11

## 迁移内容
将爬虫任务的耗时记录从"秒"改为"分钟"单位

## 修改的文件

### 1. 数据库迁移脚本
- **文件**: `migrate_duration_to_min.py`
- **操作**: 
  - 添加新列 `extract_duration_min`
  - 将现有数据从秒转换为分钟（除以 60）
  - 迁移了 11 条记录

### 2. 数据库服务层
- **文件**: `backend/services/storage/sqlite_service.py`
- **修改**:
  - 表初始化：`extract_duration_sec` → `extract_duration_min`
  - `update_task_status()` 方法参数：`extract_duration_sec` → `extract_duration_min`
  - 精度从 1 位小数改为 2 位小数（`round(x, 1)` → `round(x, 2)`）

### 3. 调度器
- **文件**: `backend/services/scheduling/scheduler.py`
- **修改**:
  - 所有 `update_task_status()` 调用：传入分钟值（`round((time.time()-_t0)/60, 2)`）
  - 日志输出：`耗时 {_dur}s` → `耗时 {_dur/60:.1f}min`

### 4. API 接口
- **文件**: `backend/main.py`
- **修改**:
  - SQL 查询字段：`extract_duration_sec` → `extract_duration_min`

## 数据示例（迁移前后对比）

| 帖子标题 | 秒 (旧) | 分钟 (新) |
|---------|---------|----------|
| 小米日常后端实习 | 11.2s | 0.19min |
| 3.4中厂Java后端面经 | 52.3s | 0.87min |
| 美团 后端开发 二面 | 53.8s | 0.90min |
| 京东零售秋招 后端 一二面 凉经 | 603.7s | 10.06min |
| 腾讯Golang开发一面-面经 | 131.8s | 2.20min |

## 注意事项
1. 旧字段 `extract_duration_sec` 仍保留在数据库中（未删除），可用于回滚
2. 新代码只使用 `extract_duration_min` 字段
3. 日志输出格式从 "耗时 X.Xs" 改为 "耗时 X.Xmin"
4. 精度提升：从 1 位小数改为 2 位小数，更精确

## 验证
运行 `findstr /S /N "extract_duration_sec" backend\*.py` 确认无遗漏，返回空结果 ✅
