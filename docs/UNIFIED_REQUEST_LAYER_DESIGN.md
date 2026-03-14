# 统一请求层设计：按钮 + 定时任务 + 本地/MCP 区分

## 一、现状分析

### 1.1 当前入口分散

| 入口类型 | 调用方式 | 实际执行 |
|---------|---------|---------|
| **按钮** | `api.triggerCrawl()` | `crawl_scheduler.trigger_nowcoder_discovery` / `trigger_xhs_discovery` / `trigger_process_tasks` |
| **按钮** | `api.processQueue()` | `crawl_scheduler.trigger_process_tasks` |
| **按钮** | `api.extractPending()` | `crawl_scheduler.trigger_process_tasks`（仅处理 fetched） |
| **按钮** | `api.retryErrors()` | 更新 DB + `trigger_process_tasks` |
| **按钮** | `api.reExtractAll()` | 更新 DB + `trigger_process_tasks` |
| **按钮** | `api.cleanData()` | `check_contents_related_batch`（独立逻辑） |
| **定时任务** | APScheduler job | `_run_nowcoder_discovery` / `_run_xhs_discovery` / `_process_pending_tasks` |

### 1.2 本地 vs MCP 的维度

| 维度 | 配置项 | 可选值 | 说明 |
|-----|--------|--------|------|
| **正文抓取** | `CRAWLER_SOURCE` | `local` / `mcp` | 牛客详情页抓取：本地 NowcoderCrawler vs 远程 MCP Content Fetcher |
| **图片 OCR** | `OCR_METHOD` | `ollama_vl` / `qwen_vl` / `claude_vision` / `mcp` | 帖子内图片文字识别：本地 Ollama / 云 API / MCP image-extractor |

### 1.3 当前问题

1. **入口不统一**：按钮直接调不同 API，定时任务直接调 `_run_*`，逻辑分散
2. **来源不可见**：前端/日志无法直观知道本次请求用的是本地还是 MCP
3. **配置不透明**：`/api/config` 未返回 `crawler_source`、`ocr_method`，前端无法展示

---

## 二、设计方案

### 2.1 统一调度层（TaskExecutor）

新建 `backend/services/crawler/task_executor.py`，作为**唯一**执行入口：

```python
# 所有操作类型
ActionType = Literal[
    "nowcoder_discovery",   # 牛客发现
    "xhs_discovery",        # 小红书发现
    "process_tasks",        # 抓取+提取（pending→fetched→done）
    "extract_pending",      # 仅提取（fetched→done）
    "retry_errors",         # 重试失败项
    "re_extract_all",       # 重新提取所有
    "clean_data",           # 清洗无关帖
]

# 触发来源
TriggerSource = Literal["button", "scheduled"]

def execute(
    action: ActionType,
    trigger_source: TriggerSource = "button",
    **kwargs
) -> dict:
    """
    统一执行入口。
    返回包含 source_info 的 dict，便于前端/日志区分本地 vs MCP。
    """
```

### 2.2 响应中增加 source_info

所有 crawler 相关 API 的响应统一增加：

```json
{
  "status": "ok",
  "message": "...",
  "source_info": {
    "crawler_source": "local",      // 正文抓取：local | mcp
    "ocr_method": "ollama_vl",      // 图片 OCR：ollama_vl | qwen_vl | claude_vision | mcp
    "trigger_source": "button"      // 触发来源：button | scheduled
  }
}
```

### 2.3 扩展 /api/config

```json
{
  "default_user_id": "...",
  "crawler_source": "local",
  "ocr_method": "ollama_vl",
  "crawler_process_batch_size": 10
}
```

前端可据此展示「当前模式：本地抓取 + 本地 OCR」或「MCP 抓取 + MCP OCR」。

### 2.4 调用关系（统一后）

```
[按钮 / 定时任务]
       │
       ▼
  TaskExecutor.execute(action, trigger_source, **kwargs)
       │
       ├─► _run_nowcoder_discovery()
       ├─► _run_xhs_discovery()
       ├─► _process_pending_tasks()  ← 内部根据 CRAWLER_SOURCE 选 local/mcp
       ├─► retry_errors 逻辑
       ├─► re_extract_all 逻辑
       └─► clean_data 逻辑
       │
       ▼
  返回 { ..., source_info: { crawler_source, ocr_method, trigger_source } }
```

---

## 三、实现步骤

### Step 1：创建 TaskExecutor

- 新建 `backend/services/crawler/task_executor.py`
- 封装 `execute(action, trigger_source, **kwargs)`，内部调用现有 `_run_*` / `_process_pending_tasks` 等
- 从 `settings` 读取 `crawler_source`、`ocr_method`，构造 `source_info`

### Step 2：API 层改用 TaskExecutor

- `/api/crawler/trigger`、`/api/crawler/process`、`/api/crawler/extract-pending`、`/api/crawler/retry-errors`、`/api/crawler/re-extract-all`、`/api/crawler/clean-data` 全部改为调用 `TaskExecutor.execute(...)`
- 响应中合并 `source_info`

### Step 3：定时任务改用 TaskExecutor

- `scheduler.py` 中 `_make_job_fn` 改为调用 `TaskExecutor.execute(..., trigger_source="scheduled")`
- 保持现有 job 类型与参数不变

### Step 4：扩展 /api/config

- 增加 `crawler_source`、`ocr_method` 字段

### Step 5：前端展示（可选）

- CollectView 顶部或配置区域展示「正文抓取：本地 / MCP」「图片 OCR：本地 / MCP」
- 可从 `getConfig()` 或各 crawler API 响应的 `source_info` 获取

---

## 四、注意事项

1. **XHS 子进程**：小红书仍通过 `run_xhs_worker.py` 子进程执行，不经过 TaskExecutor 内部逻辑，但可在启动时传入 `trigger_source="button"`，子进程内通过 env 或参数传递
2. **clean_data**：逻辑独立（`check_contents_related_batch`），不涉及抓取/OCR，`source_info` 中 `crawler_source`/`ocr_method` 可填 `null` 或 `"n/a"`
3. **向后兼容**：现有 API 路径、请求体不变，仅响应增加 `source_info`，前端不消费时不影响

---

## 五、预期效果

- ✅ 所有按钮、定时任务统一走 `TaskExecutor.execute`
- ✅ 每次请求/执行都能明确知道：正文抓取用 local 还是 mcp，图片 OCR 用哪种方式
- ✅ 前端可展示当前模式，便于排查和切换环境
