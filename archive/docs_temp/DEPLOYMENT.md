# mcp-image-extractor 说明

## 📌 概览

- **语言**：TypeScript
- **功能**：从文件、URL、Base64 提取图片，转换为 Base64 供 LLM 分析
- **部署方式**：**stdio (子进程) / 独立部署**
- **依赖**：**无**
- **可独立部署**：✅ 是

---

## 🎯 功能

### 提供的工具

#### 1. `extract_image_from_file`
从本地文件提取图片

**输入**：
```json
{
  "path": "/path/to/image.png"
}
```

**输出**：
```json
{
  "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "metadata": {
    "width": 512,
    "height": 512,
    "format": "png",
    "size": 1024,
    "originalSize": 5120
  }
}
```

#### 2. `extract_image_from_url`
从 URL 下载并提取图片

**输入**：
```json
{
  "url": "https://example.com/image.jpg"
}
```

**输出**：
```json
{
  "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "metadata": {
    "width": 512,
    "height": 512,
    "format": "jpg",
    "size": 1024,
    "originalSize": 5120
  }
}
```

#### 3. `extract_image_from_base64`
处理 Base64 编码的图片

**输入**：
```json
{
  "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
}
```

**输出**：
```json
{
  "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "metadata": {
    "width": 512,
    "height": 512,
    "format": "png",
    "size": 1024,
    "originalSize": 5120
  }
}
```

### 支持的格式

- PNG、JPG、GIF、WebP、BMP、SVG
- 最大文件大小：10MB（可配置）

### 特性

- ✅ 自动压缩到 512x512 像素
- ✅ 优化 LLM 上下文使用
- ✅ 支持域名白名单（URL 提取时）
- ✅ 返回原始大小和压缩后大小

---

## 🏗️ 架构

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
├── dist/                  # 编译输出（build 后生成）
├── Dockerfile
├── docker-compose.yml
├── package.json
├── tsconfig.json
├── jest.config.js
├── .env.example
├── CLAUDE.md
└── README.md
```

### 核心模块

#### src/index.ts
- MCP 服务器初始化
- 工具注册
- stdio 通信处理
- 输入验证

#### src/image-utils.ts
- `extractImageFromFile()` - 文件提取
- `extractImageFromUrl()` - URL 提取
- `extractImageFromBase64()` - Base64 处理
- `compressImage()` - 图片压缩

### 依赖

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "axios": "^1.6.0",
    "sharp": "^0.32.0",
    "zod": "^3.22.0"
  }
}
```

---

## 🔗 依赖关系

### 完全独立

```
mcp-image-extractor
    ├── sharp          # 图片处理库
    ├── axios          # HTTP 请求库
    └── zod            # 数据验证库
```

**无后端依赖**，可以独立运行。

---

## 🚀 本地运行（stdio 模式）

### 前置条件

- Node.js 18+
- npm 或 yarn

### 方式 1：开发模式（直接运行）

```bash
cd mcp/mcp-image-extractor
npm install
npm run dev
```

**特点**：
- 使用 ts-node 直接运行 TypeScript
- 支持热重载
- 适合开发调试

### 方式 2：生产模式（编译后运行）

```bash
cd mcp/mcp-image-extractor
npm install
npm run build
npm start
```

**特点**：
- 编译为 JavaScript
- 性能更好
- 适合生产环境

### 工作原理

```
启动 npm start
    ↓
执行 dist/index.js
    ↓
MCP 服务器启动（stdio 模式）
    ↓
监听标准输入（stdin）
    ↓
接收来自 Cursor 的 JSON 请求
    ↓
调用图片处理函数
    ├── 读取/下载图片
    ├── 使用 sharp 处理
    ├── 压缩到 512x512
    └── 转换为 Base64
    ↓
返回 JSON 响应到标准输出（stdout）
    ↓
Cursor 接收并处理
```

---

## 🔧 Cursor 配置（stdio 模式）

### 配置文件位置

- **全局**：`~/.cursor/mcp.json`
- **项目级**：`e:/Agent/AgentProject/wxr_agent/.cursor/mcp.json`

### 配置内容

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

### 配置说明

| 字段 | 说明 |
|------|------|
| `command` | 执行命令（node） |
| `args` | 脚本路径（编译后的 JS） |

### 首次使用

```bash
# 1. 构建
cd mcp/mcp-image-extractor
npm install
npm run build

# 2. 配置 Cursor（见上面的配置内容）

# 3. 重启 Cursor
```

---

## 📊 使用流程

### 流程图

```
Cursor/Claude
    ↓
用户输入："分析这张图片"
    ↓
Cursor 调用 extract_image_from_file 工具
    ↓
发送 JSON 请求到 mcp-image-extractor (stdio)
    ↓
index.ts 接收请求
    ↓
调用 extractImageFromFile()
    ↓
读取图片文件
    ↓
使用 sharp 处理
    ├── 检测格式
    ├── 压缩到 512x512
    └── 转换为 Base64
    ↓
返回 Base64 + 元数据
    ↓
Cursor 接收并显示图片
```

### 示例交互

```
用户：分析这张图片
/path/to/screenshot.png

Cursor 调用：extract_image_from_file(path="/path/to/screenshot.png")

返回：
{
  "base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "metadata": {
    "width": 512,
    "height": 512,
    "format": "png",
    "size": 1024,
    "originalSize": 5120
  }
}

Cursor 显示：
✅ 成功提取图片
原始大小：5120 字节
压缩后：1024 字节
分辨率：512x512
格式：PNG
[显示图片]
```

---

## 🚀 独立部署

### 方式 1：npm 包

#### 发布到 npm

```bash
# 1. 更新 package.json 中的版本号
npm version patch

# 2. 登录 npm
npm login

# 3. 发布
npm publish
```

#### 其他项目中使用

```bash
# 安装
npm install @你的用户名/mcp-image-extractor

# Cursor 配置
{
  "mcpServers": {
    "image-extractor": {
      "command": "node",
      "args": ["node_modules/@你的用户名/mcp-image-extractor/dist/index.js"]
    }
  }
}
```

### 方式 2：Docker

#### 构建镜像

```bash
# 在项目根目录
docker build -t mcp-image-extractor .
```

#### 运行容器

```bash
docker run -p 3000:3000 mcp-image-extractor
```

#### 使用 docker-compose

```bash
docker-compose up
```

#### 推送到 Docker Hub

```bash
# 标记镜像
docker tag mcp-image-extractor 你的用户名/mcp-image-extractor:latest

# 推送
docker push 你的用户名/mcp-image-extractor:latest
```

### 方式 3：Smithery（云端）

#### 部署步骤

```bash
# 1. 推送到 GitHub
git push origin main

# 2. 在 Smithery 中：
#    - 登录 smithery.ai
#    - 点击 "New Server"
#    - 选择 GitHub 仓库
#    - 自动构建并部署

# 3. 获得公网 URL
# https://xxx.smithery.ai/mcp
```

#### Cursor 配置（云端）

```json
{
  "mcpServers": {
    "image-extractor": {
      "url": "https://xxx.smithery.ai/mcp",
      "transport": "streamable-http"
    }
  }
}
```

---

## 🔧 环境变量

### 可配置的环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_IMAGE_SIZE` | `10485760` (10MB) | 最大图片文件大小（字节） |
| `ALLOWED_DOMAINS` | 空（允许所有） | 允许的域名（逗号分隔） |

### 使用示例

```bash
# 限制最大大小为 5MB
MAX_IMAGE_SIZE=5242880 npm start

# 限制允许的域名
ALLOWED_DOMAINS=example.com,cdn.example.com npm start

# 两者结合
MAX_IMAGE_SIZE=5242880 ALLOWED_DOMAINS=example.com npm start
```

### .env 文件

创建 `.env` 文件：

```bash
MAX_IMAGE_SIZE=5242880
ALLOWED_DOMAINS=example.com,cdn.example.com
```

然后运行：

```bash
npm start
```

---

## 🔄 stdio 模式 vs 独立部署

### stdio 模式（本地）

**优点**：
- ✅ 简单快速
- ✅ 与主进程通信
- ✅ 共享环境变量
- ✅ 自动生命周期管理

**缺点**：
- ❌ 不能跨机器
- ❌ 依赖主进程
- ❌ 不能独立扩展

**适用场景**：
- 本地开发
- 与后端集成

### 独立部署（npm/Docker/Smithery）

**优点**：
- ✅ 独立运行
- ✅ 可跨机器
- ✅ 可扩展
- ✅ 版本管理
- ✅ 公网访问

**缺点**：
- ❌ 需要额外配置
- ❌ 部署复杂度高

**适用场景**：
- 生产环境
- 云端部署
- 跨机器使用
- 多个项目共享

---

## ⚠️ 注意事项

### 1. 首次使用需要构建

```bash
cd mcp/mcp-image-extractor
npm install
npm run build
```

### 2. 支持的文件路径

✅ **支持**：
- 绝对路径：`/path/to/image.png`
- Windows 路径：`C:\Users\name\image.png`
- 相对路径：`./images/image.png`

❌ **不支持**：
- 不存在的文件
- 无读权限的文件

### 3. 支持的 URL

✅ **支持**：
- `https://example.com/image.png`
- `https://cdn.example.com/image.jpg`
- `http://example.com/image.gif`

❌ **不支持**：
- 相对 URL：`/image.png`
- 无效 URL：`not-a-url`
- 超时 URL（>10 秒）

### 4. Base64 输入

✅ **支持**：
- 标准 Base64 字符串
- 带 MIME 类型前缀：`data:image/png;base64,...`

❌ **不支持**：
- 无效 Base64
- 非图片数据

### 5. 压缩设置

默认压缩到 512x512 像素，可在 `src/image-utils.ts` 中修改：

```typescript
const MAX_WIDTH = 512;
const MAX_HEIGHT = 512;
```

---

## 🧪 测试

### 运行测试

```bash
cd mcp/mcp-image-extractor
npm test
```

### 测试文件

```
tests/
├── file-tests.test.ts
├── url-tests.test.ts
├── base64-tests.test.ts
├── compression.test.ts
└── ...
```

---

## 📚 相关文档

- **MCP 总览**：`mcp/README.md`
- **MCP 服务详解**：`docs/MCP服务详解.md`
- **独立部署指南**：`docs/MCP独立部署指南.md`

---

## ✅ 总结

| 项目 | 说明 |
|------|------|
| **部署方式** | stdio (子进程) / 独立部署 |
| **本地运行** | `npm run build && npm start` |
| **独立部署** | npm 包 / Docker / Smithery |
| **依赖** | 无 |
| **可独立部署** | ✅ 是 |
| **适用场景** | 本地开发、生产环境、云端部署 |

