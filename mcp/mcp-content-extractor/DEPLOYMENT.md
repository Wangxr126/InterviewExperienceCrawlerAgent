# mcp-content-extractor 说明

## 📌 概览

- **语言**：Python
- **功能**：从牛客网和小红书 URL 提取内容和图片
- **部署方式**：**stdio (子进程)**
- **依赖**：**强依赖后端爬虫逻辑**
- **可独立部署**：❌ 否

---

## 🎯 功能

### 提供的工具

#### 1. `extract_nowcoder_content`
从牛客网 URL 提取内容

**输入**：
```json
{
  "url": "https://www.nowcoder.com/discuss/..."
}
```

**输出**：
```json
{
  "url": "https://www.nowcoder.com/discuss/...",
  "title": "面试题标题",
  "content": "面试题正文内容",
  "author": "作者名称",
  "views": 1234,
  "likes": 56,
  "images": ["图片URL1", "图片URL2"],
  "platform": "nowcoder",
  "fetchedAt": "2024-01-01T00:00:00Z"
}
```

#### 2. `extract_xhs_content`
从小红书 URL 提取内容

**输入**：
```json
{
  "url": "https://www.xiaohongshu.com/explore/..."
}
```

**输出**：
```json
{
  "url": "https://www.xiaohongshu.com/explore/...",
  "title": "笔记标题",
  "content": "笔记内容",
  "author": "作者名称",
  "likes": 123,
  "comments": 45,
  "shares": 12,
  "images": ["图片URL1", "图片URL2"],
  "platform": "xiaohongshu",
  "fetchedAt": "2024-01-01T00:00:00Z"
}
```

#### 3. `extract_content`
自动识别平台并提取

**输入**：
```json
{
  "url": "https://www.nowcoder.com/discuss/... 或 https://www.xiaohongshu.com/explore/..."
}
```

**输出**：自动识别平台后返回相应格式

---

## 🏗️ 架构

```
mcp-content-extractor/
├── server.py              # MCP 服务入口（stdio 模式）
├── requirements.txt       # Python 依赖
├── requirements-docker.txt
└── README.md
```

### server.py 工作流程

```python
# 1. 启动 MCP 服务器（stdio 模式）
# 2. 注册三个工具
# 3. 监听来自 Cursor/Claude 的请求
# 4. 调用后端爬虫模块
# 5. 返回结构化数据
```

---

## 🔗 依赖关系

### 强依赖后端爬虫

```
mcp-content-extractor
    ↓
backend/crawler/
    ├── nowcoder_crawler.py    # 牛客网爬虫
    ├── xhs_crawler.py         # 小红书爬虫
    └── ...
    ↓
backend/data/
    ├── xhs_user_data/         # 小红书登录态
    └── ...
```

### 必需的环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `XHS_USER_DATA_DIR` | 小红书登录态目录 | ✅ 是 |
| `NOWCODER_COOKIE` | 牛客网 Cookie | ❌ 否 |

---

## 🚀 本地运行（stdio 模式）

### 前置条件

1. 激活 conda 环境
2. 后端爬虫模块已安装
3. 小红书登录态已配置（可选）

### 运行命令

```bash
# 必须在项目根目录运行
conda activate NewCoderAgent

# 直接运行（stdio 模式）
python mcp/mcp-content-extractor/server.py
```

### 工作原理

```
启动 server.py
    ↓
MCP 服务器启动（stdio 模式）
    ↓
监听标准输入（stdin）
    ↓
接收来自 Cursor 的 JSON 请求
    ↓
调用对应的工具函数
    ↓
调用后端爬虫模块
    ↓
返回 JSON 响应到标准输出（stdout）
    ↓
Cursor 接收并处理
```

---

## 🔧 Cursor 配置

### 配置文件位置

- **全局**：`~/.cursor/mcp.json`
- **项目级**：`e:/Agent/AgentProject/wxr_agent/.cursor/mcp.json`

### 配置内容

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

### 配置说明

| 字段 | 说明 |
|------|------|
| `command` | 执行命令（python） |
| `args` | 脚本路径 |
| `cwd` | 工作目录（必须是项目根目录） |
| `env.XHS_USER_DATA_DIR` | 小红书登录态目录 |

---

## 📊 使用流程

### 流程图

```
Cursor/Claude
    ↓
用户输入："从这个牛客网链接提取面试题"
    ↓
Cursor 调用 extract_content 工具
    ↓
发送 JSON 请求到 mcp-content-extractor (stdio)
    ↓
server.py 接收请求
    ↓
调用 extract_content 函数
    ↓
检测 URL 平台（牛客网）
    ↓
调用 backend/crawler/nowcoder_crawler.py
    ↓
爬虫获取内容
    ↓
返回结构化数据
    ↓
server.py 返回 JSON 响应
    ↓
Cursor 接收并显示结果
```

### 示例交互

```
用户：从这个链接提取面试题
https://www.nowcoder.com/discuss/123456

Cursor 调用：extract_content(url="https://www.nowcoder.com/discuss/123456")

返回：
{
  "title": "如何实现一个 LRU 缓存？",
  "content": "详细的面试题内容...",
  "author": "面试官",
  "views": 5000,
  "likes": 200,
  "images": ["图片URL1", "图片URL2"],
  "platform": "nowcoder"
}

Cursor 显示：
✅ 成功提取面试题
标题：如何实现一个 LRU 缓存？
内容：...
```

---

## ⚠️ 注意事项

### 1. 必须在项目根目录运行

❌ **错误**：
```bash
cd mcp/mcp-content-extractor
python server.py  # 会找不到 backend 模块
```

✅ **正确**：
```bash
cd e:/Agent/AgentProject/wxr_agent
python mcp/mcp-content-extractor/server.py
```

### 2. 需要后端爬虫

- 不能独立运行
- 必须有后端爬虫模块
- 必须有后端的 `.env` 配置

### 3. 小红书登录态

**首次使用**：
```bash
# 启动后端
python run.py

# 在另一个终端扫码登录
curl -X POST "http://localhost:8000/api/crawler/xhs/login?wait_seconds=120"

# 登录态保存到 backend/data/xhs_user_data
```

**后续使用**：
- MCP 会自动使用保存的登录态
- 无需重复登录

### 4. 防爬限制

- **本地**：一般无限制
- **云端**：可能遇到防爬，需要配置代理或 Cookie

---

## 🔄 stdio 模式详解

### 什么是 stdio 模式？

stdio (标准输入/输出) 模式是 MCP 的一种通信方式：

```
Cursor
    ↓ (JSON 请求)
stdin
    ↓
mcp-content-extractor (子进程)
    ↓ (JSON 响应)
stdout
    ↓
Cursor
```

### 优点

- ✅ 简单快速
- ✅ 与主进程通信
- ✅ 共享环境变量
- ✅ 自动生命周期管理

### 缺点

- ❌ 不能跨机器
- ❌ 依赖主进程
- ❌ 不能独立扩展

---

## 🚫 为什么不能独立部署？

### 原因

1. **强依赖后端爬虫**
   - 需要 `backend/crawler/` 模块
   - 需要 `backend/data/` 目录
   - 需要后端的 `.env` 配置

2. **紧耦合架构**
   ```
   mcp-content-extractor
       ↓
   backend/crawler/
       ↓
   backend/data/
   ```

3. **无法分离**
   - 爬虫逻辑在后端
   - 登录态在后端
   - 配置在后端

### 解决方案

如果需要独立部署，可以：
1. 将爬虫逻辑提取到独立模块
2. 创建独立的登录态管理
3. 分离配置文件
4. 重新架构为微服务

但这超出了当前项目的范围。

---

## 📚 相关文档

- **MCP 总览**：`mcp/README.md`
- **MCP 服务详解**：`docs/MCP服务详解.md`
- **后端爬虫**：`backend/crawler/README.md`（如存在）

---

## ✅ 总结

| 项目 | 说明 |
|------|------|
| **部署方式** | stdio (子进程) |
| **运行命令** | `python mcp/mcp-content-extractor/server.py` |
| **工作目录** | 项目根目录 |
| **依赖** | 后端爬虫模块 |
| **可独立部署** | ❌ 否 |
| **适用场景** | 本地开发、与后端集成 |

