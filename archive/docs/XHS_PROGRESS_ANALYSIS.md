# 小红书【获取帖子】进度更新问题分析

## 问题描述

用户点击小红书【获取帖子】按钮后，进度条不更新。

## 问题原因

查看 `CollectView.vue` 代码发现：

### 1. 小红书是独立子进程运行

```javascript
// 小红书通过 subprocess.Popen 启动独立进程
subprocess.Popen(cmd, cwd=str(_PROJECT_ROOT), creationflags=0)
```

这意味着：
- 小红书抓取在**独立的 Python 进程**中运行
- 不会实时返回进度给前端
- 前端只能通过**轮询数据库状态**来显示进度

### 2. 前端确实有轮询逻辑

```javascript
// 点击小红书【获取帖子】后
crawlPolling.value = true  // 启动轮询
crawlDiscovered.value = 999  // 设置一个固定值

// watch 监听 crawlPolling，每 5 秒轮询一次
watch(crawlPolling, (polling) => {
  if (polling) {
    crawlPollTimer = setInterval(async () => {
      await loadStats(true)  // 静默刷新统计数据
      // 检查是否完成
      if (crawlProgressPct.value >= 100 || (pending === 0 && fetched === 0)) {
        stopCrawlPolling()
      }
    }, 5000)
  }
})
```

### 3. 进度条显示逻辑

```javascript
// 进度条显示条件
<div v-if="crawlPolling" class="progress-bar-wrap">
  <!-- 待抓取进度条 -->
  <div class="progress-item">
    <span class="progress-count">{{ pendingCount }} 条</span>
    <div class="progress-fill pending" :style="{ width: pendingProgressPct + '%' }"></div>
  </div>
  <!-- 待提取进度条 -->
  <div class="progress-item">
    <span class="progress-count">{{ fetchedCount }} 条</span>
    <div class="progress-fill fetched" :style="{ width: fetchedProgressPct + '%' }"></div>
  </div>
</div>
```

## 实际问题

**进度条应该是在更新的！** 因为：

1. ✅ `crawlPolling.value = true` 已设置
2. ✅ watch 会启动定时器，每 5 秒调用 `loadStats(true)`
3. ✅ `loadStats` 会更新 `pendingCount` 和 `fetchedCount`
4. ✅ 进度条会根据这些值自动更新

## 可能的原因

### 原因1：小红书子进程没有启动成功

检查后端日志，看是否有：
```
启动 XHS worker 子进程: ...
```

如果没有，说明子进程启动失败。

### 原因2：小红书需要扫码登录

小红书抓取需要登录，如果没有登录：
- 子进程会弹出浏览器窗口
- 等待用户扫码
- **在扫码完成前，不会有任何帖子被抓取**
- 所以 `pendingCount` 和 `fetchedCount` 不会变化

### 原因3：进度条初始值问题

```javascript
crawlInitialPending.value = pendingCount.value  // 记录初始值
crawlInitialFetched.value = fetchedCount.value

// 进度计算
const pendingProgressPct = computed(() => {
  if (!crawlPolling.value || crawlInitialPending.value <= 0) return 0
  const processed = Math.max(0, crawlInitialPending.value - pendingCount.value)
  return Math.min(100, Math.round((processed / crawlInitialPending.value) * 100))
})
```

**如果初始值为 0，进度永远是 0%！**

## 解决方案

### 方案1：先完成小红书登录

1. 点击【获取帖子】
2. 等待浏览器弹出
3. 扫码登录
4. 登录成功后，子进程才会开始抓取
5. 此时进度条才会开始更新

### 方案2：改进前端提示

在小红书抓取时，显示更明确的提示：

```javascript
if (platform === 'xiaohongshu') {
  xhsMsg.value = { 
    ok: true, 
    msg: '🌸 小红书爬取已启动，请在弹出的浏览器中完成扫码登录。登录成功后，进度条将自动更新。' 
  }
  // 显示一个"等待登录"的状态
  crawlPolling.value = true
}
```

### 方案3：检查后端日志

查看后端日志，确认：
1. 子进程是否成功启动
2. 是否有错误信息
3. 扫码登录是否成功

## 验证步骤

1. **打开浏览器开发者工具**（F12）
2. **点击小红书【获取帖子】**
3. **查看 Network 标签**，确认每 5 秒有一个请求到 `/api/crawler/stats`
4. **查看 Console 标签**，看是否有 JavaScript 错误
5. **查看后端终端**，确认子进程是否启动

## 总结

进度更新逻辑是正常的，问题可能是：
- ❌ 小红书未登录，子进程在等待扫码
- ❌ 子进程启动失败
- ❌ 初始值为 0，导致进度计算错误

**建议**：先完成小红书扫码登录，然后再观察进度条是否更新。
