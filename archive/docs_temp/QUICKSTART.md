# 快速开始指南 - MCP Content Fetcher

## 项目结构

```
mcp-content-fetcher/
├── src/
│   ├── index.ts                 # MCP Server 主文件
│   └── content-fetcher.ts       # 内容获取和解析逻辑
├── tests/
│   └── content-fetcher.test.ts  # 单元测试
├── package.json                 # 项目依赖配置
├── tsconfig.json                # TypeScript 配置
├── jest.config.js               # Jest 测试配置
├── .eslintrc.json               # ESLint 配置
├── README.md                    # 项目文档
└── CLAUDE.md                    # Claude 开发指南
```

## 安装和运行

### 1. 安装依赖
```bash
cd mcp-content-fetcher
npm install
```

### 2. 开发模式运行
```bash
npm run dev
```

### 3. 构建项目
```bash
npm run build
```

### 4. 启动 MCP Server
```bash
npm start
```

## 功能说明

### 工具 1: `fetch_content`
从单个 URL 获取并解析内容

**输入:**
```json
{
  "url": "https://www.nowcoder.com/discuss/123"
}
```

**输出:**
```json
{
  "url": "https://www.nowcoder.com/discuss/123",
  "title": "面试题标题",
  "content": "完整的内容文本...",
  "platform": "nowcoder",
  "fetchedAt": "2024-03-12T10:30:00.000Z",
  "metadata": {
    "author": "用户名",
    "views": "1000",
    "likes": "50"
  }
}
```

### 工具 2: `fetch_multiple_contents`
批量获取多个 URL 的内容

**输入:**
```json
{
  "urls": [
    "https://www.nowcoder.com/discuss/123",
    "https://www.xiaohongshu.com/explore/456"
  ]
}
```

**输出:**
返回数组，每个元素格式同上

## 支持的平台

### 牛客网 (Nowcoder)
- 自动检测 URL 中的 `nowcoder.com`
- 提取: 标题、内容、作者、浏览数、点赞数
- 选择器: `.nc-discuss-content`, `.discuss-content` 等

### 小红书 (Xiaohongshu)
- 自动检测 URL 中的 `xiaohongshu.com` 或 `xhs.com`
- 提取: 标题、内容、作者、点赞数、评论数、分享数
- 选择器: `.desc`, `.content`, `.note-content` 等

### 通用网页 (Generic)
- 任何其他 URL
- 提取: 标题、内容、元描述、关键词
- 使用通用选择器: `article`, `.content`, `.main-content` 等

## 简历亮点

这个项目展示了以下技能：

1. **MCP 协议实现** - 使用 Model Context Protocol SDK 构建服务器
2. **Web 爬虫开发** - 使用 axios 和 cheerio 进行 HTTP 请求和 HTML 解析
3. **平台适配** - 针对不同平台的内容结构进行优化解析
4. **错误处理** - 完善的错误处理和批量处理机制
5. **TypeScript** - 完整的类型安全实现
6. **测试** - Jest 单元测试覆盖
7. **代码质量** - ESLint 配置和最佳实践

## 下一步

### 本地测试
```bash
# 运行测试
npm test

# 运行 linter
npm run lint

# 构建
npm run build
```

### 集成到你的 Agent
在你的 Agent 中配置这个 MCP Server：

```json
{
  "mcpServers": {
    "content-fetcher": {
      "command": "node",
      "args": ["path/to/mcp-content-fetcher/dist/index.js"]
    }
  }
}
```

### 发布到 npm (可选)
```bash
npm publish
```

## 技术栈

- **TypeScript** - 类型安全的 JavaScript
- **MCP SDK** - Model Context Protocol 官方 SDK
- **axios** - HTTP 客户端
- **cheerio** - jQuery 风格的 HTML 解析
- **Jest** - 单元测试框架
- **ESLint** - 代码质量检查

## 许可证

MIT
