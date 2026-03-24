# MCP 项目说明

本目录包含 3 个 MCP (Model Context Protocol) 服务，用于扩展 Agent 的能力。

---

## 📋 MCP 总览


| MCP                       | 语言         | 功能          | 部署方式               | 依赖   |
| ------------------------- | ---------- | ----------- | ------------------ | ---- |
| **mcp-content-extractor** | Python     | 爬取牛客网/小红书内容 | stdio (子进程)        | 后端爬虫 |
| **mcp-content-fetcher**   | TypeScript | 通用网页内容爬取    | stdio (子进程) / 独立部署 | 无    |
| **mcp-image-extractor**   | TypeScript | 图片提取与压缩     | stdio (子进程) / 独立部署 | 无    |


---

## 1️⃣ mcp-content-extractor

### 📌 快速信息

- **语言**：Python
- **功能**：从牛客网和小红书 URL 提取内容和图片
- **部署方式**：**stdio (子进程)**
- **依赖**：**强依赖后端爬虫逻辑**
- **可独立部署**：❌ 否

### 🎯 功能详解

#### 提供的工具

1. `extract_nowcoder_content` - 提取牛客网帖子
  - 输入：牛客网 URL
  - 输出：标题、正文、图片 URL、作者、浏览量、点赞数
2. `extract_xhs_content` - 提取小红书笔记
  - 输入：小红书 URL
  - 输出：标题、正文、图片 URL、作者、点赞、评论、分享
3. `extract_content` - 自动识别平台并提取
  - 输入：任意 URL（牛客网或小红书）
  - 输出：自动识别平台后提取内容

### 🏗️ 架构

```
mcp-content-extractor/
├── server.py              # MCP 服务入口（stdio 模式）
├── requirements.txt       # Python 依赖
├── requirements-docker.txt
└── README.md
```

### 🔗 依赖关系

**强依赖后端爬虫逻辑**：

```
mcp-content-extractor
    ↓
backend/crawler/          # 后端爬虫模块
    ├── nowcoder_crawler.py
    ├── xhs_crawler.py
    └── ...
    ↓
backend/data/xhs_user_data/  # 小红书登录态
```

**需要的环境变量**：

- `XHS_USER_DATA_DIR` - 小红书登录态目录
- `NOWCODER_COOKIE` - 牛客网 Cookie（可选）

### 🚀 本地运行（stdio 模式）

```bash
# 必须在项目根目录运行
conda activate NewCoderAgent

# 直接运行（stdio 模式）
python mcp/mcp-content-extractor/server.py
```

### 🔧 Cursor 配置

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

### 📊 工作流程

```
Cursor/Claude
    ↓
调用 extract_content 工具
    ↓
mcp-content-extractor (stdio)
    ↓
后端爬虫模块
    ├── 检测平台（牛客网/小红书）
    ├── 获取登录态（如需要）
    └── 爬取内容
    ↓
返回结构化数据
    ↓
Cursor/Claude 使用数据
```

### ⚠️ 注意事项

1. **必须在项目根目录运行** - 否则无法 import 后端模块
2. **需要后端爬虫** - 不能独立运行
3. **小红书登录态** - 首次需要扫码登录
4. **防爬限制** - 云端部署时可能遇到防爬

### 📖 详细文档

见 `docs/MCP服务详解.md` 中的 "1️⃣ mcp-content-extractor" 部分

---

## 2️⃣ mcp-content-fetcher

### 📌 快速信息

- **语言**：TypeScript
- **功能**：通用网页内容爬取（支持牛客网、小红书、通用网页）
- **部署方式**：**stdio (子进程) / 独立部署**
- **依赖**：**无**
- **可独立部署**：✅ 是

### 🎯 功能详解

#### 提供的工具

1. `fetch_content` - 爬取单个 URL
  - 输入：URL
  - 输出：标题、正文、平台、元数据
2. `fetch_multiple_contents` - 批量爬取多个 URL
  - 输入：URL 数组
  - 输出：内容数组（并行处理）

#### 支持的平台

- **牛客网** - 提取标题、正文、作者、浏览量、点赞数
- **小红书** - 提取标题、正文、作者、点赞、评论、分享
- **通用网页** - 提取标题、正文、meta 描述、关键词

### 🏗️ 架构

```
mcp-content-fetcher/
├── src/
│   ├── index.ts              # MCP 服务入口
│   └── content-fetcher.ts    # 爬取逻辑
├── tests/
│   └── content-fetcher.test.ts
├── dist/                     # 编译输出
├── package.json
├── tsconfig.json
├── jest.config.js
├── .eslintrc.json
├── .npmignore
├── CLAUDE.md
└── README.md
```

### 🔗 依赖关系

**完全独立**，无后端依赖：

```
mcp-content-fetcher
    ├── axios          # HTTP 请求
    ├── cheerio        # HTML 解析
    └── zod            # 数据验证
```

### 🚀 本地运行（stdio 模式）

#### 方式 1：直接运行（开发）

```bash
cd mcp/mcp-content-fetcher
npm install
npm run dev
```

#### 方式 2：编译后运行（生产）

```bash
cd mcp/mcp-content-fetcher
npm install
npm run build
npm start
```

### 🔧 Cursor 配置

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

### 📊 工作流程

```
Cursor/Claude
    ↓
调用 fetch_content 工具
    ↓
mcp-content-fetcher (stdio)
    ├── 检测平台
    ├── 发送 HTTP 请求
    ├── 解析 HTML
    └── 提取内容
    ↓
返回结构化数据
    ↓
Cursor/Claude 使用数据
```

### 🚀 独立部署方式

#### 方式 1：npm 包

```bash
# 发布到 npm
npm publish

# 其他项目中使用
npm install @你的用户名/mcp-content-fetcher
```

#### 方式 2：Docker

```bash
# 构建镜像
docker build -t mcp-content-fetcher .

# 运行容器
docker run -p 3000:3000 mcp-content-fetcher
```

#### 方式 3：Smithery（云端）

```bash
# 推送到 GitHub
git push origin main

# 在 Smithery 中部署
# 获得公网 URL：https://xxx.smithery.ai/mcp
```

### 📖 详细文档

- 本地运行：见 `docs/MCP服务详解.md` 中的 "2️⃣ mcp-content-fetcher" 部分
- 独立部署：见 `docs/MCP独立部署指南.md` 中的 "方案 1：mcp-content-fetcher 独立部署"

---

## 3️⃣ mcp-image-extractor

### 📌 快速信息

- **语言**：TypeScript
- **功能**：从文件、URL、Base64 提取图片，转换为 Base64 供 LLM 分析
- **部署方式**：**stdio (子进程) / 独立部署**
- **依赖**：**无**
- **可独立部署**：✅ 是

### 🎯 功能详解

#### 提供的工具

1. `extract_image_from_file` - 从本地文件提取图片
  - 输入：文件路径
  - 输出：Base64 编码、元数据（宽高、格式、大小）
2. `extract_image_from_url` - 从 URL 下载并提取图片
  - 输入：图片 URL
  - 输出：Base64 编码、元数据
3. `extract_image_from_base64` - 处理 Base64 编码的图片
  - 输入：Base64 字符串
  - 输出：压缩后的 Base64、元数据

#### 支持的格式

- PNG、JPG、GIF、WebP、BMP、SVG
- 最大文件大小：10MB（可配置）

#### 特性

- 自动压缩到 512x512 像素
- 优化 LLM 上下文使用
- 支持域名白名单（URL 提取时）

### 🏗️ 架构

```
mcp-image-extractor/
├── src/
│   ├── index.ts           # MCP 服务入口
│   └── image-utils.ts     # 图片处理逻辑
├── tests/
│   ├── file-tests.test.ts
│   ├── url-tests.test.ts
│   ├── base64-tests.test.ts
│   ├── compression.test.ts
│   └── ...
├── dist/                  # 编译输出
├── Dockerfile
├── docker-compose.yml
├── package.json
├── tsconfig.json
├── jest.config.js
├── .env.example
├── CLAUDE.md
└── README.md
```

### 🔗 依赖关系

**完全独立**，无后端依赖：

```
mcp-image-extractor
    ├── sharp          # 图片处理
    ├── axios          # 下载图片
    └── zod            # 数据验证
```

### 🚀 本地运行（stdio 模式）

#### 方式 1：直接运行（开发）

```bash
cd mcp/mcp-image-extractor
npm install
npm run dev
```

#### 方式 2：编译后运行（生产）

```bash
cd mcp/mcp-image-extractor
npm install
npm run build
npm start
```

### 🔧 Cursor 配置

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

### 📊 工作流程

```
Cursor/Claude
    ↓
调用 extract_image_from_* 工具
    ↓
mcp-image-extractor (stdio)
    ├── 读取/下载图片
    ├── 使用 sharp 处理
    ├── 压缩到 512x512
    └── 转换为 Base64
    ↓
返回 Base64 + 元数据
    ↓
Cursor/Claude 使用图片进行分析
```

### 🚀 独立部署方式

#### 方式 1：npm 包

```bash
# 发布到 npm
npm publish

# 其他项目中使用
npm install @你的用户名/mcp-image-extractor
```

#### 方式 2：Docker

```bash
# 构建镜像
npm run docker:build

# 运行容器
npm run docker:run

# 或手动
docker build -t mcp-image-extractor .
docker run -p 3000:3000 mcp-image-extractor
```

#### 方式 3：Docker Hub

```bash
# 推送到 Docker Hub
docker tag mcp-image-extractor 你的用户名/mcp-image-extractor:latest
docker push 你的用户名/mcp-image-extractor:latest
```

#### 方式 4：Smithery（云端）

```bash
# 推送到 GitHub
git push origin main

# 在 Smithery 中部署
# 获得公网 URL：https://xxx.smithery.ai/mcp
```

### 📖 详细文档

- 本地运行：见 `docs/MCP服务详解.md` 中的 "3️⃣ mcp-image-extractor" 部分
- 独立部署：见 `docs/MCP独立部署指南.md` 中的 "方案 2：mcp-image-extractor 独立部署"

---

## 🔄 部署方式对比

### stdio (子进程) 模式

**适用于**：本地开发、与后端集成

**特点**：

- ✅ 简单快速
- ✅ 与主进程通信
- ✅ 共享环境变量
- ❌ 不能跨机器
- ❌ 依赖主进程

**配置示例**：

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

### 独立部署模式

**适用于**：生产环境、云端部署、跨机器使用

**特点**：

- ✅ 独立运行
- ✅ 可跨机器
- ✅ 可扩展
- ✅ 版本管理
- ❌ 需要额外配置

**部署方式**：

1. **npm 包** - 简单、易于集成
2. **Docker** - 隔离、可扩展
3. **Smithery** - 一键部署、公网 URL

---

## 📊 使用场景

### 场景 1：本地开发（所有 MCP）

```bash
# 启动后端
conda activate NewCoderAgent
python run.py

# Cursor 配置 stdio 模式
# 所有 MCP 作为子进程运行
```

### 场景 2：独立使用 content-fetcher

```bash
# 不需要后端，直接使用
npm install @你的用户名/mcp-content-fetcher

# 或 Docker
docker run mcp-content-fetcher
```

### 场景 3：独立使用 image-extractor

```bash
# 不需要后端，直接使用
npm install @你的用户名/mcp-image-extractor

# 或 Docker
docker run mcp-image-extractor
```

### 场景 4：云端部署

```bash
# 使用 Smithery 部署
# 获得公网 URL
# 在 Cursor 中配置 streamable-http
```

---

## 🎯 快速决策树

```
我想使用 MCP
    ├─ 本地开发？
    │   ├─ 需要爬取牛客网/小红书？
    │   │   └─ 使用 mcp-content-extractor (stdio)
    │   ├─ 需要通用网页爬取？
    │   │   └─ 使用 mcp-content-fetcher (stdio)
    │   └─ 需要处理图片？
    │       └─ 使用 mcp-image-extractor (stdio)
    │
    └─ 独立部署？
        ├─ 需要通用网页爬取？
        │   └─ 部署 mcp-content-fetcher (npm/Docker/Smithery)
        └─ 需要处理图片？
            └─ 部署 mcp-image-extractor (npm/Docker/Smithery)
```

---

## 📚 文档导航


| 文档   | 位置                  | 用途        |
| ---- | ------------------- | --------- |
| 快速上手 | `docs/MCP服务详解.md` 开篇表格 | 1 分钟对照三个 MCP |
| 服务详解 | `docs/MCP服务详解.md`   | 深入理解各 MCP |
| 独立部署 | `docs/MCP独立部署指南.md` | 如何独立部署    |
| 本文档  | `mcp/README.md`     | MCP 目录说明  |


---

## ✅ 总结


| MCP                   | 本地运行    | 独立部署                  | 依赖   |
| --------------------- | ------- | --------------------- | ---- |
| **content-extractor** | ✅ stdio | ❌ 否                   | 后端爬虫 |
| **content-fetcher**   | ✅ stdio | ✅ npm/Docker/Smithery | 无    |
| **image-extractor**   | ✅ stdio | ✅ npm/Docker/Smithery | 无    |


