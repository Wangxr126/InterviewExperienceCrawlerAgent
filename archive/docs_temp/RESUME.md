# 简历项目描述 - MCP Content Fetcher

## 项目名称
**MCP Content Fetcher** - 基于 Model Context Protocol 的内容获取服务

## 一句话描述
开发了一个 MCP 服务器，能够从牛客网和小红书等平台自动获取和解析内容，支持批量处理和平台自适应解析。

## 详细描述（适合简历）

### 项目概述
设计并实现了一个 Model Context Protocol (MCP) 服务器，用于从多个网络平台自动获取和解析内容。该服务器支持牛客网（面试题库）、小红书（社交媒体）等平台的内容提取，并提供通用的网页内容解析能力。

### 核心功能
- **多平台支持**: 自动检测并针对不同平台（牛客网、小红书、通用网页）进行优化解析
- **内容提取**: 智能提取标题、正文、作者、互动数据（点赞、评论、浏览等）
- **批量处理**: 支持单个 URL 和批量 URL 处理，并行请求优化性能
- **错误处理**: 完善的异常处理机制，单个失败不影响批量操作

### 技术实现
- **语言**: TypeScript（完整的类型安全）
- **框架**: Model Context Protocol SDK（官方 MCP 实现）
- **HTTP 客户端**: axios（配置超时、User-Agent 等）
- **HTML 解析**: cheerio（轻量级、高效的 DOM 操作）
- **测试**: Jest 单元测试框架
- **代码质量**: ESLint 配置和 TypeScript strict 模式

### 项目结构
```
src/
  ├── index.ts              # MCP 服务器主文件，工具注册
  └── content-fetcher.ts    # 核心业务逻辑，平台适配解析
tests/
  └── content-fetcher.test.ts  # 单元测试
```

### 关键特性

#### 1. 平台自适应解析
- **牛客网**: 提取面试题、讨论内容、作者信息、浏览数、点赞数
- **小红书**: 提取笔记内容、作者、点赞、评论、分享数据
- **通用网页**: 提取标题、内容、元数据

#### 2. 两个 MCP 工具
- `fetch_content`: 单个 URL 内容获取
- `fetch_multiple_contents`: 批量 URL 并行处理

#### 3. 完善的错误处理
- 网络超时控制（10 秒）
- URL 验证（Zod schema）
- 批量处理中的错误隔离
- 详细的错误信息返回

### 代码示例

**平台检测逻辑:**
```typescript
private detectPlatform(url: string): string {
  if (url.includes('nowcoder.com')) return 'nowcoder';
  if (url.includes('xiaohongshu.com') || url.includes('xhs.com')) return 'xiaohongshu';
  return 'generic';
}
```

**内容解析:**
```typescript
async fetchContent(url: string): Promise<ContentResponse> {
  const response = await this.axiosInstance.get(url);
  const $ = cheerio.load(response.data);
  const platform = this.detectPlatform(url);
  
  // 根据平台选择相应的解析器
  const { title, content, metadata } = 
    platform === 'nowcoder' ? this.parseNowcoder($) : 
    platform === 'xiaohongshu' ? this.parseXiaohongshu($) :
    this.parseGeneric($);
  
  return { url, title, content, platform, fetchedAt, metadata };
}
```

### 学到的技能
1. **MCP 协议**: 理解和实现 Model Context Protocol 标准
2. **Web 爬虫**: HTTP 请求、HTML 解析、选择器优化
3. **平台适配**: 针对不同网站的结构差异进行灵活解析
4. **并发处理**: Promise.all 实现高效的批量请求
5. **TypeScript**: 严格的类型检查和接口设计
6. **测试驱动**: Jest 单元测试和代码覆盖

### 项目成果
- ✅ 完整的 MCP 服务器实现
- ✅ 支持 3 个平台的优化解析
- ✅ 单元测试覆盖核心功能
- ✅ ESLint 代码质量检查
- ✅ 完整的文档和快速开始指南
- ✅ 可发布到 npm 的生产级代码

### 使用场景
- 与 AI Agent 集成，自动获取面试题库进行分析
- 批量爬取社交媒体内容进行数据分析
- 作为 MCP 服务器示例，展示协议实现能力

### 项目链接
GitHub: `https://github.com/[your-username]/mcp-content-fetcher`

---

## 简历中的不同版本

### 版本 1: 简短版（适合项目列表）
**MCP Content Fetcher** | TypeScript, MCP SDK, Web Scraping
- 开发了支持牛客网、小红书等多平台的 MCP 内容获取服务器
- 实现平台自适应解析、批量处理、完善的错误处理机制
- 使用 TypeScript、axios、cheerio 等技术栈

### 版本 2: 中等版（适合项目详情）
**MCP Content Fetcher** - 多平台内容获取 MCP 服务器
- 设计并实现了基于 Model Context Protocol 的内容获取服务
- 支持牛客网（面试题）、小红书（社交媒体）、通用网页三个平台
- 核心功能：平台自适应解析、单/批量 URL 处理、完善的错误处理
- 技术栈：TypeScript、MCP SDK、axios、cheerio、Jest
- 代码质量：ESLint、TypeScript strict 模式、单元测试覆盖

### 版本 3: 详细版（适合技术面试）
**MCP Content Fetcher** - Model Context Protocol 内容获取服务器
- **项目背景**: 为 AI Agent 开发的内容获取模块，支持多个网络平台
- **核心功能**:
  - 平台检测与自适应解析（牛客网、小红书、通用网页）
  - 单个/批量 URL 处理，支持并行请求
  - 智能元数据提取（作者、互动数据等）
  - 完善的错误处理和超时控制
- **技术实现**:
  - 使用 TypeScript 实现类型安全
  - MCP SDK 进行协议标准实现
  - axios 处理 HTTP 请求，cheerio 解析 HTML
  - Jest 单元测试，ESLint 代码质量检查
- **项目成果**: 生产级代码，支持 npm 发布，完整文档

---

## 面试可能的问题和回答

**Q: 为什么选择 MCP 协议？**
A: MCP 是 Anthropic 推出的标准协议，用于 AI 模型与外部工具的通信。选择它能够让我的服务与 Claude 等 AI 模型无缝集成，提高代码的可复用性和标准化程度。

**Q: 如何处理不同平台的差异？**
A: 通过 URL 模式匹配进行平台检测，然后为每个平台实现专门的解析器。每个解析器针对该平台的 HTML 结构进行优化，使用特定的 CSS 选择器。如果平台特定解析失败，会自动降级到通用解析器。

**Q: 批量处理是如何实现的？**
A: 使用 Promise.all 并行发送多个 HTTP 请求，提高吞吐量。同时使用 catch 进行错误隔离，确保单个 URL 的失败不会影响其他请求。

**Q: 如何保证代码质量？**
A: 使用 TypeScript strict 模式进行类型检查，ESLint 进行代码风格检查，Jest 进行单元测试。所有工具都在 npm scripts 中配置，可以在 CI/CD 中自动运行。

**Q: 遇到过什么挑战？**
A: 主要挑战是不同网站的 HTML 结构差异很大，需要针对每个平台进行选择器调试。解决方案是建立一个选择器优先级列表，从最特定的选择器开始尝试，逐步降级到更通用的选择器。

---

## 项目改进方向（可选）

如果想进一步完善项目，可以考虑：

1. **缓存机制**: 添加 Redis 缓存，避免重复请求相同 URL
2. **速率限制**: 实现请求队列和速率限制，避免被网站封 IP
3. **代理支持**: 支持 HTTP 代理，提高爬虫的稳定性
4. **更多平台**: 扩展支持 LeetCode、GitHub、Medium 等平台
5. **数据库存储**: 将爬取的内容存储到数据库，支持查询和搜索
6. **Web UI**: 开发简单的 Web 界面来管理和查看爬取的内容
7. **Docker 容器化**: 创建 Dockerfile，方便部署和分发
8. **性能优化**: 使用流式处理处理大量 URL，减少内存占用

---

## 总结

这个项目展示了：
- ✅ 对 MCP 协议的理解和实现能力
- ✅ Web 爬虫和 HTML 解析的实践经验
- ✅ TypeScript 和现代 JavaScript 的掌握
- ✅ 代码质量和测试的重视
- ✅ 完整的项目文档和代码组织
- ✅ 解决实际问题的能力

这是一个很好的作品集项目，能够在技术面试中展示你的全栈开发能力。
