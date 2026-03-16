# MCP 独立部署指南

本文档详细说明如何将 `mcp-content-fetcher` 和 `mcp-image-extractor` 从主项目中独立出来，作为单独的 Git 项目和 npm 包。

---

## 📋 前置条件

- Node.js 18+
- npm 或 yarn
- Git
- GitHub 账户
- npm 账户（用于发布包）

---

## 🚀 方案 1：mcp-content-fetcher 独立部署

### 步骤 1：创建独立 Git 仓库

```bash
# 方式 A：从现有项目中提取（推荐）
git clone https://github.com/你的用户名/wxr_agent.git mcp-content-fetcher
cd mcp-content-fetcher

# 删除不需要的文件
rm -rf mcp/mcp-image-extractor mcp/mcp-content-extractor backend docs .github

# 保留核心文件
# mcp/mcp-content-fetcher/
# package.json
# .env.example
# .gitignore
# README.md
# LICENSE

# 方式 B：从头创建
mkdir mcp-content-fetcher
cd mcp-content-fetcher
git init
```

### 步骤 2：调整项目结构

```bash
# 将 mcp/mcp-content-fetcher 中的文件移到根目录
mv mcp/mcp-content-fetcher/* .
rm -rf mcp

# 最终结构
# mcp-content-fetcher/
# ├── src/
# │   ├── index.ts
# │   └── content-fetcher.ts
# ├── tests/
# │   └── content-fetcher.test.ts
# ├── dist/                    (build 后生成)
# ├── package.json
# ├── tsconfig.json
# ├── jest.config.js
# ├── .eslintrc.json
# ├── .gitignore
# ├── .npmignore
# ├── README.md
# ├── CLAUDE.md
# └── LICENSE
```

### 步骤 3：更新 package.json

```json
{
  "name": "@你的用户名/mcp-content-fetcher",
  "version": "1.0.0",
  "description": "MCP server for fetching and parsing content from URLs (Nowcoder, Xiaohongshu, generic web pages)",
  "main": "dist/index.js",
  "bin": {
    "mcp-content-fetcher": "dist/index.js"
  },
  "scripts": {
    "build": "tsc && chmod +x dist/index.js",
    "dev": "ts-node src/index.ts",
    "start": "node dist/index.js",
    "lint": "eslint src/**/*.ts",
    "test": "jest --no-cache",
    "prepublishOnly": "npm run build"
  },
  "keywords": [
    "mcp",
    "model-context-protocol",
    "nowcoder",
    "xiaohongshu",
    "web-scraping",
    "content-fetcher"
  ],
  "author": "你的名字",
  "license": "MIT",
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "axios": "^1.6.0",
    "cheerio": "^1.0.0-rc.12",
    "zod": "^3.22.0"
  },
  "devDependencies": {
    "@types/jest": "^29.5.0",
    "@types/node": "^20.0.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "eslint": "^8.0.0",
    "jest": "^29.5.0",
    "ts-jest": "^29.1.0",
    "ts-node": "^10.9.0",
    "typescript": "^5.0.0"
  },
  "files": [
    "dist",
    "README.md",
    "LICENSE"
  ],
  "publishConfig": {
    "access": "public"
  }
}
```

### 步骤 4：创建 .npmignore

```
src/
tests/
dist/**/*.map
*.ts
!dist/**/*.js
.eslintrc.json
jest.config.js
tsconfig.json
.gitignore
.env.example
CLAUDE.md
```

### 步骤 5：创建 README.md

```markdown
# mcp-content-fetcher

MCP (Model Context Protocol) server for fetching and parsing content from URLs.

## Features

- Fetch content from Nowcoder (牛客网)
- Fetch content from Xiaohongshu (小红书)
- Generic web page content extraction
- Batch processing support
- Automatic platform detection

## Installation

```bash
npm install @你的用户名/mcp-content-fetcher
```

## Usage

### Local Development

```bash
npm install
npm run build
npm start
```

### Cursor Configuration

```json
{
  "mcpServers": {
    "content-fetcher": {
      "command": "node",
      "args": ["node_modules/@你的用户名/mcp-content-fetcher/dist/index.js"]
    }
  }
}
```

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "content-fetcher": {
      "command": "node",
      "args": ["/path/to/node_modules/@你的用户名/mcp-content-fetcher/dist/index.js"]
    }
  }
}
```

## Tools

### fetch_content
Fetch and parse content from a single URL.

**Parameters:**
- `url` (string, required): The URL to fetch

**Returns:**
- `url`: The fetched URL
- `title`: Page title
- `content`: Extracted content
- `platform`: Detected platform (nowcoder, xiaohongshu, generic)
- `fetchedAt`: Timestamp
- `metadata`: Additional metadata

### fetch_multiple_contents
Fetch and parse content from multiple URLs in parallel.

**Parameters:**
- `urls` (array of strings, required): URLs to fetch

**Returns:**
- Array of content objects (same as fetch_content)

## Supported Platforms

### Nowcoder (牛客网)
- Extracts: title, content, author, views, likes

### Xiaohongshu (小红书)
- Extracts: title, content, author, likes, comments, shares

### Generic Web Pages
- Extracts: title, content, meta description, keywords

## Environment Variables

```bash
# Optional: Custom timeout (default: 10000ms)
FETCH_TIMEOUT=10000

# Optional: Custom User-Agent
USER_AGENT="Mozilla/5.0..."
```

## Testing

```bash
npm test
```

## License

MIT
```

### 步骤 6：初始化 Git 仓库并推送

```bash
# 初始化 Git
git init
git add .
git commit -m "Initial commit: mcp-content-fetcher"

# 添加远程仓库
git remote add origin https://github.com/你的用户名/mcp-content-fetcher.git
git branch -M main
git push -u origin main

# 创建 GitHub Release
git tag v1.0.0
git push origin v1.0.0
```

### 步骤 7：发布到 npm

```bash
# 登录 npm
npm login

# 发布包
npm publish

# 验证发布
npm view @你的用户名/mcp-content-fetcher
```

### 步骤 8：配置 GitHub Actions 自动发布（可选）

创建 `.github/workflows/publish.yml`：

```yaml
name: Publish to npm

on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
          registry-url: 'https://registry.npmjs.org'
      - run: npm install
      - run: npm run build
      - run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

---

## 🚀 方案 2：mcp-image-extractor 独立部署

### 步骤 1-3：同上（创建仓库、调整结构、更新 package.json）

### 步骤 4：创建 Dockerfile

```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY dist ./dist

EXPOSE 3000

CMD ["node", "dist/index.js"]
```

### 步骤 5：创建 docker-compose.yml

```yaml
version: '3.8'

services:
  mcp-image-extractor:
    build: .
    ports:
      - "3000:3000"
    environment:
      - MAX_IMAGE_SIZE=10485760
      - ALLOWED_DOMAINS=
    volumes:
      - ./logs:/app/logs
```

### 步骤 6：更新 package.json

```json
{
  "name": "@你的用户名/mcp-image-extractor",
  "version": "1.0.0",
  "description": "MCP server for extracting and compressing images from files, URLs, and base64 strings",
  "main": "dist/index.js",
  "bin": {
    "mcp-image-extractor": "dist/index.js"
  },
  "scripts": {
    "build": "tsc && chmod +x dist/index.js",
    "dev": "ts-node src/index.ts",
    "start": "node dist/index.js",
    "lint": "eslint src/**/*.ts",
    "test": "jest --no-cache",
    "docker:build": "docker build -t mcp-image-extractor .",
    "docker:run": "docker run -p 3000:3000 mcp-image-extractor",
    "prepublishOnly": "npm run build"
  },
  "keywords": [
    "mcp",
    "model-context-protocol",
    "image-extraction",
    "image-compression",
    "base64"
  ],
  "author": "你的名字",
  "license": "MIT",
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "axios": "^1.6.0",
    "sharp": "^0.32.0",
    "zod": "^3.22.0"
  },
  "devDependencies": {
    "@types/jest": "^29.5.0",
    "@types/node": "^20.0.0",
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "eslint": "^8.0.0",
    "jest": "^29.5.0",
    "ts-jest": "^29.1.0",
    "ts-node": "^10.9.0",
    "typescript": "^5.0.0"
  },
  "files": [
    "dist",
    "README.md",
    "LICENSE"
  ],
  "publishConfig": {
    "access": "public"
  }
}
```

### 步骤 7：创建 README.md

```markdown
# mcp-image-extractor

MCP (Model Context Protocol) server for extracting and compressing images.

## Features

- Extract images from local files
- Download and extract images from URLs
- Process base64-encoded images
- Automatic compression to 512x512
- Support for multiple formats (PNG, JPG, GIF, WebP, BMP, SVG)
- Domain whitelist support for URL extraction

## Installation

```bash
npm install @你的用户名/mcp-image-extractor
```

## Usage

### Local Development

```bash
npm install
npm run build
npm start
```

### Docker

```bash
npm run docker:build
npm run docker:run
```

### Cursor Configuration

```json
{
  "mcpServers": {
    "image-extractor": {
      "command": "node",
      "args": ["node_modules/@你的用户名/mcp-image-extractor/dist/index.js"]
    }
  }
}
```

## Tools

### extract_image_from_file
Extract image from a local file.

### extract_image_from_url
Download and extract image from a URL.

### extract_image_from_base64
Process base64-encoded image.

## Environment Variables

```bash
MAX_IMAGE_SIZE=10485760        # Max image size in bytes (default: 10MB)
ALLOWED_DOMAINS=example.com    # Comma-separated domain whitelist (default: all)
```

## Testing

```bash
npm test
```

## License

MIT
```

### 步骤 8-9：同方案 1（Git 推送、npm 发布）

---

## 📊 部署对比

### 本地开发（原始方式）
```json
{
  "mcpServers": {
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

### 使用 npm 包（推荐）
```json
{
  "mcpServers": {
    "content-fetcher": {
      "command": "node",
      "args": ["node_modules/@你的用户名/mcp-content-fetcher/dist/index.js"]
    },
    "image-extractor": {
      "command": "node",
      "args": ["node_modules/@你的用户名/mcp-image-extractor/dist/index.js"]
    }
  }
}
```

### Docker 部署（云端）
```bash
# 构建镜像
docker build -t mcp-image-extractor .

# 运行容器
docker run -p 3000:3000 mcp-image-extractor

# 推送到 Docker Hub
docker tag mcp-image-extractor 你的用户名/mcp-image-extractor:latest
docker push 你的用户名/mcp-image-extractor:latest
```

### Smithery 部署（云端）
```bash
# 推送到 GitHub
git push origin main

# 在 Smithery 中：
# 1. 登录 smithery.ai
# 2. 点击 "New Server"
# 3. 选择 GitHub 仓库
# 4. 自动构建并部署
# 5. 获得公网 URL
```

---

## 🔄 版本管理

### 语义化版本（Semantic Versioning）

```
MAJOR.MINOR.PATCH
1.0.0

- MAJOR: 不兼容的 API 变更
- MINOR: 向后兼容的功能添加
- PATCH: 向后兼容的 bug 修复
```

### 发布流程

```bash
# 1. 更新版本号
npm version patch    # 1.0.0 -> 1.0.1
npm version minor    # 1.0.0 -> 1.1.0
npm version major    # 1.0.0 -> 2.0.0

# 2. 推送到 GitHub
git push origin main
git push origin v1.0.1

# 3. 发布到 npm
npm publish
```

---

## 📝 总结

| 方式 | 优点 | 缺点 | 适用场景 |
|------|------|------|--------|
| 本地开发 | 简单、快速 | 依赖项目结构 | 开发阶段 |
| npm 包 | 可复用、版本管理 | 需要发布 | 生产环境 |
| Docker | 隔离、可扩展 | 需要 Docker | 云端部署 |
| Smithery | 一键部署、公网 URL | 需要 GitHub | 云端服务 |

