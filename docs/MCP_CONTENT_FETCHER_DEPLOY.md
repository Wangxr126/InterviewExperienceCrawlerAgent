# MCP Content Fetcher 部署指南

本文档记录 mcp-content-fetcher（牛客/小红书 URL 正文+图片提取）的完整部署流程。

## 一、项目概述

- **仓库**：https://github.com/Wangxr126/mcp-content-fetcher
- **功能**：从牛客网、小红书 URL 提取正文和元数据，支持 MCP 协议（`fetch_content` / `fetch_multiple_contents` 工具）
- **技术栈**：TypeScript + Node.js + Express + axios + cheerio
- **部署目标**：Render（已完成）、Smithery（可选）

---

## 二、Render 部署流程

### 2.1 前置准备

1. 在 [Render](https://render.com) 注册账号
2. 将 GitHub 仓库 `Wangxr126/mcp-content-fetcher` 与 Render 关联

### 2.2 创建 Web Service

1. 进入 Render Dashboard → **New** → **Web Service**
2. 连接 GitHub 仓库：`Wangxr126/mcp-content-fetcher`
3. 配置如下：

| 配置项 | 值 |
|--------|-----|
| **Name** | mcp-content-fetcher |
| **Region** | Oregon（或其他） |
| **Branch** | main |
| **Runtime** | Node |
| **Build Command** | `npm run build` |
| **Start Command** | `node dist/index.js` |
| **Instance Type** | Free |

### 2.3 环境变量

- `PORT`：Render 自动注入，无需手动配置
- 无其他必需环境变量

### 2.4 部署后验证

- **服务 URL**：`https://mcp-content-fetcher.onrender.com`
- **MCP 端点**：`POST https://mcp-content-fetcher.onrender.com/mcp`

### 2.5 自动部署

- 每次推送 `main` 分支后，Render 会通过 GitHub Webhook 自动触发重新部署
- 无需手动操作

---

## 三、Smithery 部署流程（可选）

### 3.1 Smithery 简介

Smithery 支持 MCP 服务器的托管部署，支持 TypeScript 和自定义容器。

### 3.2 在 mcp-content-fetcher 仓库添加配置

在 `mcp-content-fetcher` 仓库根目录创建 `smithery.yaml`：

```yaml
# Smithery MCP 部署配置
# 文档：https://smithery.ai/docs/build
runtime: typescript
```

### 3.3 部署步骤

1. 登录 [Smithery](https://smithery.ai)
2. 关联 GitHub 仓库 `Wangxr126/mcp-content-fetcher`
3. 按 Smithery 指引完成部署
4. 获取 Smithery 分配的 MCP URL

### 3.4 与 Render 对比

| 项目 | Render | Smithery |
|------|--------|----------|
| 免费额度 | 有，休眠后冷启动慢 | 视 Smithery 政策 |
| 构建 | 需解决内存限制 | 可能更宽松 |
| 适用场景 | 稳定生产 | 备选/测试 |

---

## 四、本地 Cursor 配置

在 `.cursor/mcp.json` 中配置远程 MCP：

```json
{
  "mcpServers": {
    "content-fetcher": {
      "url": "https://mcp-content-fetcher.onrender.com/mcp"
    }
  }
}
```

---

## 五、后端使用

### 5.1 配置 .env

```env
# 爬虫来源：local=本地后端爬虫 | mcp=远程 MCP Content Fetcher
CRAWLER_SOURCE=mcp

# MCP Content Fetcher 地址（CRAWLER_SOURCE=mcp 时生效）
# Render 部署：https://mcp-content-fetcher.onrender.com
# Smithery 部署：填写 Smithery 分配的 URL
MCP_CONTENT_FETCHER_URL=https://mcp-content-fetcher.onrender.com

# MCP 请求超时秒数（可选，默认 30）
MCP_CONTENT_FETCHER_TIMEOUT=30
```

### 5.2 兼容性

- **CrawlerTool**：当 `CRAWLER_SOURCE=mcp` 时，自动通过 `POST {MCP_CONTENT_FETCHER_URL}/fetch` 调用远程服务
- **输出格式**：与本地爬虫一致（【来源】【标题】【链接】【正文】），兼容原有 Agent 流程

### 5.3 REST 端点

除 MCP 协议 `/mcp` 外，服务还提供简单 REST 端点供后端直接调用：

- **POST /fetch**  
  - Body: `{"url": "https://..."}`  
  - 返回: `{url, title, content, platform, fetchedAt, metadata}`

详见 [部署错误排查](./DEPLOY_TROUBLESHOOTING.md) 和 `.env.example`。
