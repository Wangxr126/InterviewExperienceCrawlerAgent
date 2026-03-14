# MCP Content Fetcher 下一步操作指南

## 一、已完成

- ✅ Render 部署成功：https://mcp-content-fetcher.onrender.com
- ✅ 部署文档：`docs/MCP_CONTENT_FETCHER_DEPLOY.md`
- ✅ 错误排查文档：`docs/DEPLOY_TROUBLESHOOTING.md`
- ✅ 后端 CrawlerTool 兼容 MCP 模式
- ✅ .env 配置项：`CRAWLER_SOURCE`、`MCP_CONTENT_FETCHER_URL`、`MCP_CONTENT_FETCHER_TIMEOUT`

---

## 二、部署到 Smithery（可选）

### 2.1 在 mcp-content-fetcher 仓库添加配置

在 `Wangxr126/mcp-content-fetcher` 仓库根目录已有 `smithery.yaml`：

```yaml
runtime: typescript
```

### 2.2 部署步骤

1. 登录 [Smithery](https://smithery.ai)
2. 关联 GitHub 仓库 `Wangxr126/mcp-content-fetcher`
3. 按 Smithery 指引完成部署
4. 获取 Smithery 分配的 MCP URL

### 2.3 更新 .env

若使用 Smithery 作为主服务，将：

```env
MCP_CONTENT_FETCHER_URL=<Smithery 分配的 URL>
```

---

## 三、后端以 MCP 方式请求

### 3.1 配置 .env

```env
# 爬虫来源：local=本地后端爬虫 | mcp=远程 MCP Content Fetcher
CRAWLER_SOURCE=mcp

# MCP Content Fetcher 地址
MCP_CONTENT_FETCHER_URL=https://mcp-content-fetcher.onrender.com

# 可选：超时秒数，默认 30
MCP_CONTENT_FETCHER_TIMEOUT=30
```

### 3.2 兼容原有 Tool 调用

- **CrawlerTool**：当 `CRAWLER_SOURCE=mcp` 时，自动通过 `POST {MCP_CONTENT_FETCHER_URL}/fetch` 调用远程服务
- **输出格式**：与本地爬虫一致（【来源】【标题】【链接】【正文】），无需修改 Agent 逻辑
- **切换方式**：`CRAWLER_SOURCE=local` 恢复使用本地后端爬虫

### 3.3 调用流程

```
CrawlerTool.run(url)
  → 检查 settings.crawler_source
  → 若 mcp：fetch_content_via_mcp(base_url, url)
  → 若 local：_crawl_nowcoder / _crawl_xhs（原有逻辑）
```

---

## 四、本地验证

1. 在 `.env` 中设置 `CRAWLER_SOURCE=mcp` 和 `MCP_CONTENT_FETCHER_URL`
2. 启动后端：`conda activate NewCoderAgent; python run.py`
3. 通过 CrawlerTool 或 Agent 抓取牛客/小红书 URL，确认返回正常

---

## 五、推送 mcp-content-fetcher 更新

若需将 `/fetch` 端点和 `smithery.yaml` 同步到远程仓库：

```powershell
cd e:\Agent\AgentProject\wxr_agent\mcp\mcp-content-fetcher
git add src/index.ts smithery.yaml
git commit -m "feat: add /fetch REST endpoint and smithery.yaml"
git push origin main
```

推送后 Render 会自动重新部署。
