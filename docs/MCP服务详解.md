# MCP 服务详解

本项目包含 3 个 MCP (Model Context Protocol) 服务，用于扩展 Agent 的能力。

---

## 📌 快速概览


| MCP                       | 语言         | 功能          | 依赖后端 | 可独立部署 |
| ------------------------- | ---------- | ----------- | ---- | ----- |
| **mcp-content-extractor** | Python     | 爬取牛客网/小红书内容 | ✅ 是  | ❌ 否   |
| **mcp-content-fetcher**   | TypeScript | 通用网页内容爬取    | ❌ 否  | ✅ 是   |
| **mcp-image-extractor**   | TypeScript | 图片提取与压缩     | ❌ 否  | ✅ 是   |


---

## 1️⃣ mcp-content-extractor (Python)

### 功能

从牛客网和小红书 URL 提取内容和图片。

### 提供的工具

- `extract_nowcoder_content` - 提取牛客网帖子（标题、正文、图片 URL）
- `extract_xhs_content` - 提取小红书笔记（标题、正文、图片 URL）
- `extract_content` - 自动识别平台并提取

### 架构

```
mcp-content-extractor/
├── server.py           # MCP 服务入口
├── requirements.txt    # Python 依赖
└── README.md
```

### 依赖关系

**强依赖后端爬虫逻辑**（`backend/` 目录中的爬虫模块）

- 需要后端的 `xhs-crawl`、`playwright` 等爬虫工具
- 需要后端的登录态管理（`backend/data/xhs_user_data`）
- 需要后端的 `.env` 配置

### 本地运行

```bash
# 必须在项目根目录运行
conda activate NewCoderAgent
python mcp/mcp-content-extractor/server.py
```

### Cursor 配置

```json
{
  "mcpServers": {
    "content-extractor": {
      "command": "python",
      "args": ["mcp/mcp-content-extractor/server.py"],
      "cwd": "e:/Agent/AgentProject/wxr_agent",
      "env": {
        "XHS_USER_DATA_DIR": "e:/Agent/AgentProject/wxr_agent/backend/data/xhs_user_data"
      }
    }
  }
}
```

### 云端部署

支持 Smithery Docker 部署（见 `README.md`）

### 评价

✅ **保留** - 这是面经 Agent 的核心功能，用于爬取面试题

---

## 2️⃣ mcp-content-fetcher (TypeScript)

### 功能

通用网页内容爬取，支持牛客网、小红书、通用网页。

### 提供的工具

- `fetch_content` - 爬取单个 URL
- `fetch_multiple_contents` - 批量爬取多个 URL

### 架构

```
mcp-content-fetcher/
├── src/
│   ├── index.ts              # MCP 服务入口
│   └── content-fetcher.ts    # 爬取逻辑
├── tests/
│   └── content-fetcher.test.ts
├── package.json
├── tsconfig.json
└── CLAUDE.md
```

### 支持的平台

1. **牛客网** - 提取标题、正文、作者、浏览量、点赞数
2. **小红书** - 提取标题、正文、作者、点赞、评论、分享
3. **通用网页** - 提取标题、正文、meta 描述、关键词

### 依赖关系

**完全独立**，无后端依赖

- 使用 `axios` 进行 HTTP 请求
- 使用 `cheerio` 进行 HTML 解析
- 支持自定义 User-Agent 避免被反爬

### 本地运行

```bash
cd mcp/mcp-content-fetcher
npm install
npm run build
npm start
```

### Cursor 配置

```json
{
  "mcpServers": {
    "content-fetcher": {
      "command": "node",
      "args": ["mcp/mcp-content-fetcher/dist/index.js"]
    }
  }
}
```

### 云端部署

已发布到 npm，支持 Smithery 部署

### 评价

✅ **保留** - 功能更通用，可作为 mcp-content-extractor 的备选方案

### 🚀 可独立部署

**是** - 可以单独拿出去作为独立项目

---

## 3️⃣ mcp-image-extractor (TypeScript)

### 功能

从文件、URL、Base64 提取图片，转换为 Base64 供 LLM 分析。

### 提供的工具

- `extract_image_from_file` - 从本地文件提取图片
- `extract_image_from_url` - 从 URL 下载并提取图片
- `extract_image_from_base64` - 处理 Base64 编码的图片

### 架构

```
mcp-image-extractor/
├── src/
│   ├── index.ts           # MCP 服务入口
│   └── image-utils.ts     # 图片处理逻辑
├── tests/
│   ├── file-tests.test.ts
│   ├── url-tests.test.ts
│   ├── base64-tests.test.ts
│   └── compression.test.ts
├── package.json
├── tsconfig.json
├── Dockerfile
└── CLAUDE.md
```

### 特性

- 自动压缩到 512x512 像素
- 支持多种格式：PNG、JPG、GIF、WebP、BMP、SVG
- 最大文件大小：10MB（可配置）
- 支持域名白名单（URL 提取时）

### 依赖关系

**完全独立**，无后端依赖

- 使用 `sharp` 进行图片处理
- 使用 `axios` 下载远程图片

### 本地运行

```bash
cd mcp/mcp-image-extractor
npm install
npm run build
npm start
```

### Cursor 配置

```json
{
  "mcpServers": {
    "image-extractor": {
      "command": "node",
      "args": ["mcp/mcp-image-extractor/dist/index.js"]
    }
  }
}
```

### 环境变量

```bash
MAX_IMAGE_SIZE=10485760        # 最大图片大小（字节）
ALLOWED_DOMAINS=example.com    # 允许的域名（逗号分隔）
```

### 云端部署

支持 Docker 部署，已配置 Dockerfile 和 Smithery

### 评价

✅ **保留** - 对于处理面试题中的图片很有用

### 🚀 可独立部署

**是** - 可以单独拿出去作为独立项目

---

## 🔗 独立部署方案

### 可独立部署的 MCP

#### mcp-content-fetcher

**优点**：

- 无后端依赖
- 功能完整（支持多平台）
- 已发布到 npm
- 可作为通用爬虫服务

**独立部署步骤**：

```bash
# 1. 创建独立项目
git clone <wxr_agent_repo> mcp-content-fetcher-standalone
cd mcp-content-fetcher-standalone
rm -rf mcp/mcp-image-extractor mcp/mcp-content-extractor backend docs

# 2. 保留核心文件
# mcp/mcp-content-fetcher/
# package.json (根目录)
# .env.example

# 3. 发布到 npm
npm publish

# 4. 云端部署
# 推送到 GitHub，在 Smithery 部署
```

#### mcp-image-extractor

**优点**：

- 无后端依赖
- 功能单一明确
- 已配置 Docker
- 可作为通用图片处理服务

**独立部署步骤**：

```bash
# 1. 创建独立项目
git clone <wxr_agent_repo> mcp-image-extractor-standalone
cd mcp-image-extractor-standalone
rm -rf mcp/mcp-content-fetcher mcp/mcp-content-extractor backend docs

# 2. 保留核心文件
# mcp/mcp-image-extractor/
# Dockerfile
# package.json (根目录)
# .env.example

# 3. 发布到 npm
npm publish

# 4. Docker 部署
docker build -t mcp-image-extractor .
docker push <registry>/mcp-image-extractor

# 5. 云端部署
# 推送到 GitHub，在 Smithery 部署
```

### 不可独立部署的 MCP

#### mcp-content-extractor

**原因**：

- 强依赖后端爬虫逻辑
- 需要后端的登录态管理
- 需要后端的 `.env` 配置
- 与后端紧耦合

**建议**：

- 保留在主项目中
- 作为后端的一部分
- 不单独发布

---

## 📊 使用场景

### 场景 1：本地开发（所有 MCP）

```json
{
  "mcpServers": {
    "content-extractor": {
      "command": "python",
      "args": ["mcp/mcp-content-extractor/server.py"],
      "cwd": "e:/Agent/AgentProject/wxr_agent"
    },
    "content-fetcher": {
      "command": "node",
      "args": ["mcp/mcp-content-fetcher/dist/index.js"]
    },
    "image-extractor": {
      "command": "node",
      "args": ["mcp/mcp-image-extractor/dist/index.js"]
    }
  }
}
```

### 场景 2：云端部署（独立 MCP）

```json
{
  "mcpServers": {
    "content-fetcher": {
      "url": "https://content-fetcher.smithery.ai/mcp",
      "transport": "streamable-http"
    },
    "image-extractor": {
      "url": "https://image-extractor.smithery.ai/mcp",
      "transport": "streamable-http"
    }
  }
}
```

### 场景 3：混合部署（后端 + 独立 MCP）

```json
{
  "mcpServers": {
    "content-extractor": {
      "command": "python",
      "args": ["mcp/mcp-content-extractor/server.py"],
      "cwd": "e:/Agent/AgentProject/wxr_agent"
    },
    "content-fetcher": {
      "url": "https://content-fetcher.smithery.ai/mcp",
      "transport": "streamable-http"
    },
    "image-extractor": {
      "url": "https://image-extractor.smithery.ai/mcp",
      "transport": "streamable-http"
    }
  }
}
```

---

## 🔧 开发指南

### 添加新工具

1. 在 `src/index.ts` 中注册工具
2. 在对应的工具文件中实现逻辑
3. 编写测试用例
4. 更新文档

### 测试

```bash
# mcp-content-fetcher
cd mcp/mcp-content-fetcher
npm test

# mcp-image-extractor
cd mcp/mcp-image-extractor
npm test
```

### 构建

```bash
# mcp-content-fetcher
npm run build

# mcp-image-extractor
npm run build
```

---

## 📝 总结


| MCP                   | 后端依赖 | 独立部署 | 推荐     |
| --------------------- | ---- | ---- | ------ |
| mcp-content-extractor | ✅ 是  | ❌ 否  | 保留在主项目 |
| mcp-content-fetcher   | ❌ 否  | ✅ 是  | 可独立部署  |
| mcp-image-extractor   | ❌ 否  | ✅ 是  | 可独立部署  |


