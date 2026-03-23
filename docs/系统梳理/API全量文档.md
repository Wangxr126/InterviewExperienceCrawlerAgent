# InterviewExperienceCrawlerAgent API 全量文档

本文档按「接口分组 → 接口清单 → 关键说明」整理当前后端 API，路由分布在 `backend/main.py`（主体）、`backend/api/scheduler_api.py`、`backend/api/reasoning_api.py`；后两者在 `main.py` 中通过 `include_router` 挂载。

## 1. 基础与系统接口

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/` | 根健康入口，返回服务状态与 docs 地址 |
| GET | `/app` | 生产模式返回前端构建产物 `index.html` |
| GET | `/api/config` | 返回前端运行配置（默认用户、会话、批大小、OCR/爬虫来源） |
| GET | `/api/health` | 简版健康检查 |

## 2. 题库与练习接口

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/questions` | 题库分页检索（公司/岗位/难度/标签/关键词/来源） |
| GET | `/api/questions/random` | 随机题目获取 |
| GET | `/api/questions/smart-practice` | 智能练习组题（结合薄弱项与随机补齐） |
| GET | `/api/questions/meta` | 题库元数据（公司、岗位、标签、来源等） |
| GET | `/api/questions/{q_id}` | 单题详情 |
| GET | `/api/posts/{crawl_task_id}` | 通过采集任务关联查看帖子信息 |

## 3. 对话与作答接口

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/chat` | 普通对话（非流式） |
| POST | `/api/chat/stream` | 流式对话（SSE） |
| POST | `/api/submit_answer/stream` | 流式评分（SSE） |
| POST | `/api/submit_answer` | 异步触发答题评估 |
| GET | `/api/submit_answer/status/{task_id}` | 查询答题评估任务状态 |
| POST | `/api/session/end` | 结束会话并做会话收口 |

## 4. 用户学习数据接口

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/user/{user_id}/mastery` | 标签掌握度画像 |
| GET | `/api/user/{user_id}/reviews` | 到期复习数据 |
| GET | `/api/user/{user_id}/practice-stats` | 练习统计（练习数/总题量/是否刷完） |
| GET | `/api/user/{user_id}/tool-usage` | Agent 工具调用统计 |
| GET | `/api/user/{user_id}/graph-rag` | GraphRAG 图数据（题库图 + 做题图） |
| GET | `/api/user/{user_id}/questions/{question_id}/study-records` | 某题历史作答记录 |
| GET | `/api/user/{user_id}/chat/history` | 聊天历史 |
| GET | `/api/user/{user_id}/chat/history/all` | 全量聊天历史（管理/导出场景） |
| POST | `/api/user/{user_id}/chat/clear` | 清空聊天历史 |
| GET | `/api/user/{user_id}/memory` | 用户记忆视图汇总 |

## 5. 收录与资源接口

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/ingest` | 手动收录 URL（进入内容处理链路） |
| GET | `/api/resources` | 学习资源查询 |

## 6. 爬虫与采集接口

### 6.1 统计与状态

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/crawler/stats` | 采集总体统计（含分状态、分平台、队列量） |
| GET | `/api/crawler/extraction-status` | 提取进度与状态 |
| GET | `/api/crawler/extraction-trace` | 最新提取推理轨迹快照 |
| GET | `/api/crawler/extraction-trace-stream` | 提取轨迹流式订阅 |
| GET | `/api/crawler/trace/{session_id}` | 指定会话的采集推理追踪 |
| GET | `/api/crawler/keywords` | 已使用关键词列表 |

### 6.2 任务触发与批处理

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/crawler/trigger` | 触发发现任务（牛客/小红书） |
| POST | `/api/crawler/process` | 拉取并处理任务队列（定时任务与手动调试用） |
| POST | `/api/crawler/clean-data` | 清洗无关/噪声数据 |
| POST | `/api/crawler/clear-all` | 清空采集相关数据 |

> 已移除（原过渡能力）：`/api/crawler/extract-pending`、`/api/crawler/retry-errors`、`/api/crawler/re-extract-all`、`/api/crawler/stage2-process`、`/api/crawler/re-extract-stage2-unfinished`。批量/单条重提取请用 `tasks/re-extract-batch` 与 `tasks/{id}/re-extract`。

### 6.3 小红书登录与修复

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/crawler/xhs/login-status` | 小红书登录状态检查 |
| POST | `/api/crawler/xhs/login` | 小红书登录触发（扫码链路） |
| POST | `/api/crawler/refetch-xhs-body` | 重抓小红书正文 |

### 6.4 任务管理

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/crawler/tasks` | 任务列表（状态/平台/关键词/标题/分页排序） |
| GET | `/api/crawler/tasks/{task_id}` | 单任务详情 |
| GET | `/api/crawler/tasks/{task_id}/questions` | 单任务提取到的题目列表 |
| POST | `/api/crawler/tasks/{task_id}/re-extract` | 单任务重提取 |
| POST | `/api/crawler/tasks/re-extract-batch` | 批量重提取 |
| POST | `/api/crawler/tasks/resume-batch` | 恢复上次中断的批量提取（配合 shutdown 进度文件） |
| DELETE | `/api/crawler/tasks/{task_id}` | 删除单任务及关联数据 |
| POST | `/api/crawler/tasks/delete-batch` | 批量删除任务 |

## 7. 微调接口

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/finetune/stats` | 微调样本统计 |
| GET | `/api/finetune/log-files` | 可导入日志文件列表 |
| POST | `/api/finetune/import-all` | 批量导入日志 |
| POST | `/api/finetune/import` | 导入单日志 |
| POST | `/api/finetune/fix-merged` | 修复合并后的样本结构 |
| GET | `/api/finetune/samples` | 样本列表检索 |
| GET | `/api/finetune/samples/{sample_id}` | 样本详情 |
| POST | `/api/finetune/assist` | 助手改写（辅助标注） |
| POST | `/api/finetune/label` | 样本标注提交 |
| POST | `/api/finetune/export` | 导出训练数据 |
| GET | `/api/finetune/run-config` | 读取训练配置 |
| POST | `/api/finetune/run-config` | 保存训练配置 |
| GET | `/api/finetune/runs` | 训练运行记录 |
| POST | `/api/finetune/generate-training` | 生成 `train_lora.py` 与 Alpaca 数据并写入 `finetune_runs`；默认 `run_training: true` 时在后台启动 `微调/train_lora.py`（`run_training: false` 则仅生成脚本） |
| GET | `/api/finetune/compare-presets` | 模型对比页：可选端点预设列表（无密钥） |
| POST | `/api/finetune/compare` | 模型对比：Body `preset_ids`（2～4）、`content`、`title`；并行调用多模型返回 `results` |
| DELETE | `/api/finetune/samples/{sample_id}` | 删除样本 |
| POST | `/api/finetune/delete-log` | 删除日志文件 |
| POST | `/api/finetune/preview-log` | 预览日志内容 |
| POST | `/api/finetune/upload-faq` | FAQ 上传并转样本 |

## 8. 定时任务接口（`/api/scheduler`）

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/scheduler/jobs` | 查询任务列表（可仅启用项） |
| GET | `/api/scheduler/jobs/{job_id}` | 任务详情 |
| POST | `/api/scheduler/jobs` | 创建任务 |
| PUT | `/api/scheduler/jobs/{job_id}` | 更新任务 |
| DELETE | `/api/scheduler/jobs/{job_id}` | 删除任务 |
| POST | `/api/scheduler/jobs/{job_id}/enable` | 启用任务 |
| POST | `/api/scheduler/jobs/{job_id}/disable` | 禁用任务 |
| POST | `/api/scheduler/jobs/{job_id}/run` | 立即执行任务（后台异步） |
| GET | `/api/scheduler/job-types` | 任务类型元数据 |
| GET | `/api/scheduler/schedule-examples` | 常用调度模板 |

## 9. 推理追踪接口（`/api/reasoning`）

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/reasoning/sessions` | 推理会话列表 |
| GET | `/api/reasoning/sessions/{session_id}` | 推理会话详情 |
| GET | `/api/reasoning/sessions/{session_id}/trace` | 完整 trace |
| GET | `/api/reasoning/sessions/{session_id}/steps` | 步骤明细 |
| GET | `/api/reasoning/sessions/{session_id}/result` | 推理结果 |
| GET | `/api/reasoning/sessions/{session_id}/tool-calls` | 工具调用记录 |
| GET | `/api/reasoning/sessions/{session_id}/stats` | 统计信息 |
| GET | `/api/reasoning/sessions/{session_id}/export?format=json/html` | 导出 trace |

## 10. 接口调用关系（前端视角）

- `web/src/api.js` 已对主要接口封装，前端页面基本不直接写 `fetch`。
- 页面与后端接口是强绑定关系：`CollectView` 对应 `crawler`；`FinetuneView` / `ModelCompareView` 对应 `finetune`（对比接口为 `compare-presets`、`compare`）；`SchedulerView` 对应 `scheduler`；`ChatView` 对应 `chat/submit_answer`。
- 流式接口统一使用 SSE：`/api/chat/stream`、`/api/submit_answer/stream`、`/api/crawler/extraction-trace-stream`。

## 11. 后端源码与路由位置（速查）

| 职责 | 主要文件 |
|------|----------|
| HTTP 路由主体（题库、对话、爬虫、微调、用户数据等） | `backend/main.py` |
| 定时任务相关路由 | `backend/api/scheduler_api.py` |
| 推理会话 / trace 相关路由 | `backend/api/reasoning_api.py` |
| 微调与模型对比业务逻辑 | `backend/services/finetune/finetune_service.py`（路由在 `main.py` 中注册） |
| SQLite 与持久化 | `backend/services/storage/sqlite_service.py` 等 |
| 采集执行与提取 | `backend/services/crawler/` |
| Agent 实现 | `backend/agents/` |

更完整的目录说明见 [`docs/README.md`](../README.md)。
