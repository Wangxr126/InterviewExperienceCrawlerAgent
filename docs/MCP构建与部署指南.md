# MCP Content Fetcher 构建与部署指南

本文档记录 mcp-content-fetcher（牛客/小红书 URL 正文+图片提取）的本地构建、Render 部署及错误排查。

---

## 一、项目概述

- **仓库**：https://github.com/Wangxr126/mcp-content-fetcher
- **本地路径**：`mcp/mcp-content-fetcher`（相对 **wxr_agent 仓库根**；根目录结构见 [`docs/README.md`](README.md)）
- **功能**：从牛客网、小红书 URL 提取正文和元数据，支持 MCP 协议（`fetch_content` / `fetch_multiple_contents` 工具）
- **技术栈**：TypeScript + Node.js + Express + axios + cheerio
- **部署目标**：Render（推荐）、Smithery（可选）

---

## 二、本地构建

### 2.1 安装与构建

```bash
cd mcp/mcp-content-fetcher
npm install
npm run build
```

### 2.2 构建产物

- `dist/index.js`：打包后的入口文件
- 使用 esbuild 替代 tsc，避免内存溢出（Render 免费实例约 512MB）

### 2.3 本地运行

```bash
npm start          # 运行 dist/index.js
npm run dev        # 开发模式（ts-node）
npm test           # 单元测试
```

---

## 三、Render 部署

### 3.1 前置准备

1. 在 [Render](https://render.com) 注册账号
2. 将 GitHub 仓库 `Wangxr126/mcp-content-fetcher` 与 Render 关联

### 3.2 创建 Web Service

| 配置项 | 值 |
|--------|-----|
| **Name** | mcp-content-fetcher |
| **Region** | Oregon（或其他） |
| **Branch** | main |
| **Runtime** | Node |
| **Build Command** | `npm run build` |
| **Start Command** | `node dist/index.js` |
| **Instance Type** | Free |

### 3.3 环境变量

- `PORT`：Render 自动注入，无需手动配置
- 无其他必需环境变量

### 3.4 部署后验证

- **服务 URL**：`https://mcp-content-fetcher.onrender.com`
- **MCP 端点**：`POST https://mcp-content-fetcher.onrender.com/mcp`
- **REST 端点**：`POST https://mcp-content-fetcher.onrender.com/fetch`（Body: `{"url": "https://..."}`）

### 3.5 自动部署

- 每次推送 `main` 分支后，Render 通过 GitHub Webhook 自动触发重新部署

---

## 四、Smithery 部署（可选）

### 4.1 配置

在 `mcp-content-fetcher` 仓库根目录创建 `smithery.yaml`：

```yaml
runtime: typescript
```

### 4.2 部署步骤

1. 登录 [Smithery](https://smithery.ai)
2. 关联 GitHub 仓库
3. 按指引完成部署
4. 获取 Smithery 分配的 MCP URL

### 4.3 与 Render 对比

| 项目 | Render | Smithery |
|------|--------|-----------|
| 免费额度 | 有，休眠后冷启动慢 | 视政策 |
| 构建 | 需解决内存限制（esbuild） | 可能更宽松 |
| 适用场景 | 稳定生产 | 备选/测试 |

---

## 五、后端集成

### 5.1 配置 .env

```env
# 爬虫来源：local=本地后端爬虫 | mcp=远程 MCP Content Fetcher
CRAWLER_SOURCE=mcp

# MCP Content Fetcher 地址（CRAWLER_SOURCE=mcp 时生效）
MCP_CONTENT_FETCHER_URL=https://mcp-content-fetcher.onrender.com

# MCP 请求超时秒数（可选，默认 30）
MCP_CONTENT_FETCHER_TIMEOUT=30
```

### 5.2 兼容性

- **CrawlerTool**：当 `CRAWLER_SOURCE=mcp` 时，自动通过 `POST {MCP_CONTENT_FETCHER_URL}/fetch` 调用远程服务
- **输出格式**：与本地爬虫一致，兼容原有 Agent 流程
- **切换方式**：`CRAWLER_SOURCE=local` 恢复使用本地后端爬虫

### 5.3 Cursor 配置

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

## 六、部署错误排查

### 6.1 TypeScript 编译失败 - 找不到模块

**现象**：`Cannot find module 'axios'`、`Cannot find name 'process'` 等

**原因**：tsconfig 未配置 Node 类型，回调参数缺少类型注解

**解决**：
- 为 map 回调添加类型：`(_: number, el: unknown) =>`
- 为工具回调、Express 请求/响应添加类型：`async (args: { url: string }) => { ... }`

### 6.2 找不到 @types/node

**现象**：`Cannot find type definition file for 'node'`

**原因**：Render 构建时可能跳过 `devDependencies`

**解决**：将 `@types/node` 移到 `dependencies`

### 6.3 JavaScript 堆内存溢出 (OOM)

**现象**：`FATAL ERROR: Ineffective mark-compacts near heap limit`

**原因**：tsc 内存占用高，超出 Render 免费实例限制

**解决**：用 esbuild 替代 tsc
- `esbuild` 移到 `dependencies`
- 创建 `build.mjs` 使用 esbuild 打包
- build 脚本：`npm install && node build.mjs && node -e "require('fs').chmodSync('dist/index.js', '755')"`

### 6.4 找不到 esbuild 模块

**现象**：`Cannot find package 'esbuild'`

**原因**：esbuild 在 devDependencies 或构建前未执行 npm install

**解决**：
- 将 `esbuild` 移到 `dependencies`
- build 脚本中显式执行 `npm install`

### 6.5 错误汇总表

| 错误类型 | 根本原因 | 解决方式 |
|----------|----------|----------|
| 找不到模块/类型 | tsconfig 缺少 Node 类型、参数未显式类型 | 添加类型、移除/调整 types 配置 |
| 找不到 @types/node | devDependencies 被跳过 | 移到 dependencies |
| OOM | tsc 内存占用高 | 用 esbuild 替代 tsc |
| 找不到 esbuild | dev 依赖未安装 | 移到 dependencies + build 中 npm install |

---

## 七、附录

### 7.1 最终有效配置

- **package.json**：`esbuild`、`@types/node` 在 `dependencies`，build 脚本含 `npm install`
- **build.mjs**：使用 esbuild 打包，external 依赖不打包进产物
- **Start Command**：`node dist/index.js`

### 7.2 推送更新

```powershell
cd mcp/mcp-content-fetcher
git add .
git commit -m "feat: xxx"
git push origin main
```

推送后 Render 会自动重新部署。
