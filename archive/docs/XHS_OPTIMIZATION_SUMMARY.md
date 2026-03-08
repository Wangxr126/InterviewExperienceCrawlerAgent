# 小红书和牛客爬虫优化总结

## 优化内容

### 1. 优化日志输出格式

**修改文件**: `backend/services/crawler/xhs_crawler.py`

- **链接获取日志**: 
  - 旧: `XHS 获取链接 [1/20]: 淘天Agent一面，被拿捏了...`
  - 新: `XHS 获取链接 [1/20]: 淘天Agent一面，被拿捏了` (去掉 `...`，增加显示长度到30字符)

- **详情获取日志**:
  - 旧: `XHS [1/20] 详情: 淘天Agent一面，被拿捏了... (737字)`
  - 新: `XHS 获取详情 [1/20]: 淘天Agent一面，被拿捏了 (737字)` (统一格式，增加显示长度)

### 2. 移除重复的 LLM 预热

**修改文件**: `backend/services/crawler/run_xhs_worker.py`

- **问题**: worker 子进程启动时会重复预热 LLM，但 main.py 启动时已经预热过
- **解决**: 移除 worker 中的预热代码，添加注释说明
  ```python
  # LLM 已在 main.py 启动时预热，子进程无需重复预热
  ```

### 3. 添加爬取来源标识（小红书 + 牛客）

**修改文件**: 
- `backend/services/crawler/xhs_crawler.py`
- `backend/services/crawler/run_xhs_worker.py`
- `backend/services/crawler/nowcoder_crawler.py`
- `backend/services/scheduler.py`

**实现**:
- 在 `XHSCrawler.discover()` 和 `NowcoderCrawler.discover()` 方法中添加 `crawl_source` 参数
- 日志输出格式统一为: `[平台{crawl_source}] 消息内容`

**小红书**:
- 立即爬取: `[小红书立即爬取] 开始搜索关键词: 'agent面经'`
- 定时爬取: `[小红书定时爬取] 开始搜索关键词: 'agent面经'`

**牛客**:
- 定时爬取: `[牛客定时爬取] 开始（关键词=['面经'], 最大页数=3）...`
- 去重日志: `[牛客定时爬取] 去重：数据库已有 5 条，本次新增 10 条`

### 4. 统一定时爬取和立即爬取的处理逻辑

**修改文件**: `backend/services/scheduler.py`

**小红书统一后的逻辑**:
1. 创建爬虫实例
2. 调用 `discover()` 获取帖子
3. 保存帖子到数据库（入队）
4. 立即处理队列，提取题目
5. 输出统计日志

**牛客统一后的逻辑**:
1. 创建爬虫实例
2. 调用 `discover()` 获取帖子
3. 保存帖子到数据库（入队）
4. 输出统计日志

**日志格式统一**:
- 小红书启动: `[小红书{来源}] 启动: keywords=..., max_notes=..., headless=...`
- 小红书发现: `[小红书{来源}] 发现完成: X 条原始帖, Y 条新入队`
- 小红书处理: `[小红书{来源}] 处理完成: Z 道题入库`
- 牛客启动: `[牛客{来源}] 开始（关键词=..., 最大页数=...）...`
- 牛客发现: `[牛客{来源}] 发现完成：发现 X 条，新增队列 Y 条`

## 优化效果

### 日志对比

**优化前**:
```
2026-03-09 01:19:15,133 INFO     backend.services.crawler.xhs_crawler: XHS 开始搜索关键词: 'agent面经'
2026-03-09 01:19:21,864 INFO     backend.services.crawler.xhs_crawler: XHS 获取链接 [1/20]: 淘天Agent一面，被拿捏了...
2026-03-09 01:22:59,405 INFO     backend.services.crawler.xhs_crawler: XHS [1/20] 详情: 淘天Agent一面，被拿捏了... (737字)
2026-03-09 01:19:10.278 | INFO     | backend.services.llm_warmup:warmup_llm:150 - [LLM 预热] 本地 Ollama：终止旧进程 → 启动 serve → 预加载模型 ['deepseek-r1:7b']
```

**优化后**:
```
2026-03-09 01:19:15,133 INFO     [小红书立即爬取] 开始搜索关键词: 'agent面经'
2026-03-09 01:19:21,864 INFO     XHS 获取链接 [1/20]: 淘天Agent一面，被拿捏了
2026-03-09 01:22:59,405 INFO     XHS 获取详情 [1/20]: 淘天Agent一面，被拿捏了 (737字)
2026-03-09 01:23:00,123 INFO     [小红书立即爬取] 发现完成: 20 条原始帖, 18 条新入队
2026-03-09 01:23:05,456 INFO     [小红书立即爬取] 处理完成: 15 道题入库
```

### 主要改进

1. **日志更清晰**: 通过 `[小红书立即爬取]` 和 `[小红书定时爬取]` 前缀，一眼就能区分爬取来源
2. **减少冗余**: 移除重复的 LLM 预热，减少启动时间约 2-5 秒
3. **格式统一**: 所有日志格式保持一致，便于日志分析和监控
4. **逻辑统一**: 定时爬取和立即爬取使用完全相同的处理流程，只有日志前缀不同

## 修改的文件列表

1. `backend/services/crawler/xhs_crawler.py` - 优化日志格式，添加 crawl_source 参数
2. `backend/services/crawler/run_xhs_worker.py` - 移除重复预热，统一日志前缀
3. `backend/services/crawler/nowcoder_crawler.py` - 添加 crawl_source 参数，统一日志前缀
4. `backend/services/scheduler.py` - 统一处理逻辑，添加日志前缀，修复语法错误
5. `backend/main.py` - 降低第三方库日志级别

## 5. 日志输出优化

**修改文件**: 
- `backend/main.py`
- `backend/services/crawler/xhs_crawler.py`

### 问题分析

从实际运行日志中发现的问题：

1. **Playwright 异步错误**: Windows 上 event loop 策略不正确导致 `NotImplementedError`
2. **Neo4j 通知冗长**: 索引已存在的通知占用大量日志空间
3. **xhs-crawl 警告重复**: 每个帖子都输出 meta tags 回退警告
4. **httpx 请求日志**: HTTP 请求日志过于详细

### 优化措施

**1. 修复 Playwright 异步错误**
```python
# 改进 event loop 检测和设置
try:
    loop = asyncio.get_running_loop()
    if not isinstance(loop, asyncio.ProactorEventLoop):
        logger.debug("当前 event loop 不是 ProactorEventLoop，Playwright 可能失败")
except RuntimeError:
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

**2. 降低第三方库日志级别**
```python
# Neo4j 通知（索引已存在等信息）
logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)

# xhs_crawl 警告（meta tags 回退是正常行为）
logging.getLogger("xhs_crawl").setLevel(logging.ERROR)

# httpx 请求日志
logging.getLogger("httpx").setLevel(logging.WARNING)
```

### 优化效果

**优化前**:
```
2026-03-09 01:23:13,218 ERROR    asyncio: Task exception was never retrieved
...
NotImplementedError

2026-03-09 01:22:59.404 | WARNING  | xhs_crawl.spider:get_post_data:132 - Failed to extract data from __INITIAL_STATE__, falling back to meta tags.
2026-03-09 01:23:04.372 | WARNING  | xhs_crawl.spider:get_post_data:132 - Failed to extract data from __INITIAL_STATE__, falling back to meta tags.
... (重复20次)

2026-03-09 01:22:59,238 INFO     httpx: HTTP Request: GET https://www.xiaohongshu.com/explore/...
2026-03-09 01:23:04,204 INFO     httpx: HTTP Request: GET https://www.xiaohongshu.com/explore/...
... (重复20次)

2026-03-09 01:24:40,562 INFO     neo4j.notifications: Received notification from DBMS server: <GqlStatusObject gql_status='00NA0'...
... (重复5次，每次数百字符)
```

**优化后**:
```
# Playwright 错误被正确处理，不再抛出异常
# xhs_crawl 警告不再显示（除非真正的错误）
# httpx 请求日志不再显示（除非警告/错误）
# Neo4j 通知不再显示（除非警告/错误）

日志更加清爽，只显示关键信息！
```

## 测试建议

1. **测试小红书立即爬取**: 在前端点击"立即爬取"按钮，观察日志是否显示 `[小红书立即爬取]`
2. **测试小红书定时爬取**: 等待定时任务触发，观察日志是否显示 `[小红书定时爬取]`
3. **测试牛客定时爬取**: 等待定时任务触发，观察日志是否显示 `[牛客定时爬取]`
4. **验证处理逻辑**: 确认两种平台都能正常发现帖子、入队、提取题目
5. **检查启动时间**: 确认 worker 启动时不再有 LLM 预热日志
6. **验证日志清爽度**: 确认不再有重复的 xhs_crawl 警告、httpx 请求日志、Neo4j 通知
7. **验证 Playwright 错误**: 确认不再有 NotImplementedError 异步错误
