# MCP 目录结构完整说明

## 📁 目录结构

```
mcp/
├── README.md                          # ⭐ MCP 总览（新建）
├── mcp-content-extractor/
│   ├── DEPLOYMENT.md                  # ⭐ 部署说明（新建）
│   ├── README.md
│   ├── server.py
│   ├── requirements.txt
│   └── requirements-docker.txt
├── mcp-content-fetcher/
│   ├── DEPLOYMENT.md                  # ⭐ 部署说明（新建）
│   ├── src/
│   │   ├── index.ts
│   │   └── content-fetcher.ts
│   ├── tests/
│   ├── dist/                          # 编译输出
│   ├── package.json
│   ├── tsconfig.json
│   └── ...
└── mcp-image-extractor/
    ├── DEPLOYMENT.md                  # ⭐ 部署说明（新建）
    ├── src/
    │   ├── index.ts
    │   └── image-utils.ts
    ├── tests/
    ├── dist/                          # 编译输出
    ├── Dockerfile
    ├── docker-compose.yml
    ├── package.json
    ├── tsconfig.json
    └── ...
```

---

## 📖 文档导航

### 🎯 快速开始

**第一步**：阅读 `mcp/README.md`
- 了解 3 个 MCP 的功能
- 了解部署方式
- 了解依赖关系

### 📚 深入理解

**第二步**：阅读各 MCP 的 `DEPLOYMENT.md`

#### mcp-content-extractor
- 📄 `mcp/mcp-content-extractor/DEPLOYMENT.md`
- 功能：爬取牛客网/小红书
- 部署方式：**stdio (子进程)**
- 依赖：**后端爬虫**
- 可独立部署：❌ 否

#### mcp-content-fetcher
- 📄 `mcp/mcp-content-fetcher/DEPLOYMENT.md`
- 功能：通用网页爬取
- 部署方式：**stdio (子进程) / 独立部署**
- 依赖：**无**
- 可独立部署：✅ 是

#### mcp-image-extractor
- 📄 `mcp/mcp-image-extractor/DEPLOYMENT.md`
- 功能：图片提取与压缩
- 部署方式：**stdio (子进程) / 独立部署**
- 依赖：**无**
- 可独立部署：✅ 是

### 🚀 独立部署

**第三步**：阅读 `docs/MCP独立部署指南.md`
- 如何发布到 npm
- 如何部署到 Docker
- 如何部署到 Smithery

---

## 🔍 各文档的用途

### mcp/README.md
**用途**：MCP 目录总览

**内容**：
- 3 个 MCP 的快速信息表
- 各 MCP 的功能详解
- 部署方式对比
- 使用场景
- 快速决策树

**何时阅读**：
- 第一次了解 MCP
- 需要快速查阅

### mcp/mcp-content-extractor/DEPLOYMENT.md
**用途**：mcp-content-extractor 详细说明

**内容**：
- 功能详解（工具、平台）
- 架构说明
- 依赖关系
- 本地运行方式
- Cursor 配置
- 使用流程
- stdio 模式详解
- 为什么不能独立部署

**何时阅读**：
- 需要使用 mcp-content-extractor
- 需要理解 stdio 模式
- 需要配置 Cursor

### mcp/mcp-content-fetcher/DEPLOYMENT.md
**用途**：mcp-content-fetcher 详细说明

**内容**：
- 功能详解（工具、平台）
- 架构说明
- 依赖关系
- 本地运行方式（开发/生产）
- Cursor 配置
- 使用流程
- 独立部署方式（npm/Docker/Smithery）
- stdio 模式 vs 独立部署对比

**何时阅读**：
- 需要使用 mcp-content-fetcher
- 需要独立部署
- 需要发布到 npm

### mcp/mcp-image-extractor/DEPLOYMENT.md
**用途**：mcp-image-extractor 详细说明

**内容**：
- 功能详解（工具、格式、特性）
- 架构说明
- 依赖关系
- 本地运行方式（开发/生产）
- Cursor 配置
- 使用流程
- 独立部署方式（npm/Docker/Smithery）
- 环境变量配置
- stdio 模式 vs 独立部署对比

**何时阅读**：
- 需要使用 mcp-image-extractor
- 需要独立部署
- 需要配置环境变量

---

## 🎯 使用场景对应的文档

### 场景 1：本地开发（所有 MCP）

**阅读顺序**：
1. `mcp/README.md` - 了解总体
2. `mcp/mcp-content-extractor/DEPLOYMENT.md` - 了解 stdio 模式
3. `mcp/mcp-content-fetcher/DEPLOYMENT.md` - 了解本地运行
4. `mcp/mcp-image-extractor/DEPLOYMENT.md` - 了解本地运行

**关键信息**：
- 所有 MCP 都支持 stdio 模式
- 需要构建 TypeScript MCP
- 需要配置 Cursor

### 场景 2：独立部署 mcp-content-fetcher

**阅读顺序**：
1. `mcp/README.md` - 了解总体
2. `mcp/mcp-content-fetcher/DEPLOYMENT.md` - 了解独立部署方式
3. `docs/MCP独立部署指南.md` - 详细部署步骤

**关键信息**：
- 支持 npm 包、Docker、Smithery
- 无后端依赖
- 可跨机器使用

### 场景 3：独立部署 mcp-image-extractor

**阅读顺序**：
1. `mcp/README.md` - 了解总体
2. `mcp/mcp-image-extractor/DEPLOYMENT.md` - 了解独立部署方式
3. `docs/MCP独立部署指南.md` - 详细部署步骤

**关键信息**：
- 支持 npm 包、Docker、Smithery
- 无后端依赖
- 可配置环境变量

### 场景 4：理解 stdio 模式

**阅读顺序**：
1. `mcp/README.md` - 了解 stdio 模式
2. `mcp/mcp-content-extractor/DEPLOYMENT.md` - 详细的 stdio 模式说明

**关键信息**：
- stdio 是 MCP 的通信方式
- 基于标准输入/输出
- 适合本地开发

---

## 📊 MCP 对比表

### 功能对比

| 功能 | content-extractor | content-fetcher | image-extractor |
|------|------------------|-----------------|-----------------|
| 爬取牛客网 | ✅ | ✅ | ❌ |
| 爬取小红书 | ✅ | ✅ | ❌ |
| 通用网页爬取 | ❌ | ✅ | ❌ |
| 图片提取 | ❌ | ❌ | ✅ |
| 图片压缩 | ❌ | ❌ | ✅ |

### 部署方式对比

| 部署方式 | content-extractor | content-fetcher | image-extractor |
|---------|------------------|-----------------|-----------------|
| stdio (子进程) | ✅ | ✅ | ✅ |
| npm 包 | ❌ | ✅ | ✅ |
| Docker | ❌ | ✅ | ✅ |
| Smithery | ❌ | ✅ | ✅ |

### 依赖对比

| 依赖 | content-extractor | content-fetcher | image-extractor |
|------|------------------|-----------------|-----------------|
| 后端爬虫 | ✅ | ❌ | ❌ |
| 后端登录态 | ✅ | ❌ | ❌ |
| 后端配置 | ✅ | ❌ | ❌ |
| 外部依赖 | ❌ | axios, cheerio | axios, sharp |

---

## 🚀 快速命令参考

### 本地运行

```bash
# mcp-content-extractor (stdio)
conda activate NewCoderAgent
python mcp/mcp-content-extractor/server.py

# mcp-content-fetcher (stdio)
cd mcp/mcp-content-fetcher
npm install && npm run build && npm start

# mcp-image-extractor (stdio)
cd mcp/mcp-image-extractor
npm install && npm run build && npm start
```

### 独立部署

```bash
# mcp-content-fetcher - npm
cd mcp/mcp-content-fetcher
npm publish

# mcp-content-fetcher - Docker
cd mcp/mcp-content-fetcher
docker build -t mcp-content-fetcher .
docker run -p 3000:3000 mcp-content-fetcher

# mcp-image-extractor - npm
cd mcp/mcp-image-extractor
npm publish

# mcp-image-extractor - Docker
cd mcp/mcp-image-extractor
docker build -t mcp-image-extractor .
docker run -p 3000:3000 mcp-image-extractor
```

---

## ✅ 文件清单

### 新建文件

| 文件 | 位置 | 用途 |
|------|------|------|
| **README.md** | `mcp/` | MCP 总览 |
| **DEPLOYMENT.md** | `mcp/mcp-content-extractor/` | content-extractor 部署说明 |
| **DEPLOYMENT.md** | `mcp/mcp-content-fetcher/` | content-fetcher 部署说明 |
| **DEPLOYMENT.md** | `mcp/mcp-image-extractor/` | image-extractor 部署说明 |

### 相关文档

| 文件 | 位置 | 用途 |
|------|------|------|
| **MCP服务详解.md** | `docs/` | 开篇表格 + 各 MCP 详解 |
| **MCP构建与部署指南.md** | `docs/` | 构建与发布流程 |
| **MCP独立部署指南.md** | `docs/` | 独立部署详细步骤 |
| **环境配置说明.md** | `docs/` | Conda、`.env`、MCP 相关 |

---

## 🎓 学习路径

### 初级（快速了解）
1. 阅读 `mcp/README.md` - 5 分钟
2. 阅读 `docs/MCP服务详解.md` 快速概览表格 - 5 分钟
3. **总耗时**：10 分钟

### 中级（深入理解）
1. 阅读 `mcp/README.md` - 10 分钟
2. 阅读 `mcp/mcp-content-extractor/DEPLOYMENT.md` - 15 分钟
3. 阅读 `mcp/mcp-content-fetcher/DEPLOYMENT.md` - 15 分钟
4. 阅读 `mcp/mcp-image-extractor/DEPLOYMENT.md` - 15 分钟
5. **总耗时**：55 分钟

### 高级（独立部署）
1. 完成中级学习 - 55 分钟
2. 阅读 `docs/MCP独立部署指南.md` - 30 分钟
3. 实际部署一个 MCP - 30 分钟
4. **总耗时**：115 分钟

---

## 💡 关键要点

### 三个 MCP 的核心区别

1. **mcp-content-extractor**
   - 依赖后端爬虫
   - 只能 stdio 模式
   - 不能独立部署

2. **mcp-content-fetcher**
   - 无后端依赖
   - stdio + 独立部署
   - 可发布到 npm

3. **mcp-image-extractor**
   - 无后端依赖
   - stdio + 独立部署
   - 可发布到 npm

### 部署方式的选择

- **本地开发**：使用 stdio 模式
- **生产环境**：使用独立部署（npm/Docker/Smithery）
- **跨机器使用**：必须独立部署

### 文档的使用

- **快速查阅**：`mcp/README.md`
- **详细了解**：各 MCP 的 `DEPLOYMENT.md`
- **独立部署**：`docs/MCP独立部署指南.md`

---

## 🎉 总结

✅ **已完成**：
- 删除冗余 MCP（mcp-speech-to-text）
- 创建 MCP 总览文档（`mcp/README.md`）
- 为每个 MCP 创建部署说明（`DEPLOYMENT.md`）
- 详细说明 stdio 模式和独立部署方式
- 提供快速命令参考

📖 **文档完整**：
- 快速对照：`docs/MCP服务详解.md` 开篇表格
- 详细说明：55 分钟深入理解（`mcp/README.md` + 各 `DEPLOYMENT.md`）
- 部署指南：30 分钟独立部署（`docs/MCP独立部署指南.md`）

🚀 **可立即使用**：
- 本地开发：按快速命令运行
- 独立部署：按部署指南操作

