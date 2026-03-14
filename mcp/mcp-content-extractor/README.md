# MCP Content Extractor

从 **牛客网** 和 **小红书** URL 提取正文和图片的 MCP 服务器，供 Cursor / Claude Desktop / Agent 使用。

## 工具

| 工具 | 描述 |
|-----|------|
| `extract_nowcoder_content` | 牛客帖子 URL → 标题、正文、图片 URL 列表 |
| `extract_xhs_content` | 小红书笔记 URL → 标题、正文、图片 URL 列表 |
| `extract_content` | 自动识别平台并提取（牛客/小红书） |

---

## 本地运行（stdio）

**必须在项目根目录**运行（依赖 backend 爬虫逻辑）：

```bash
# 激活 conda 环境
conda activate NewCoderAgent

# 安装 MCP 依赖（若未安装）
pip install fastmcp python-dotenv

# 运行 MCP 服务器（stdio 模式）
python mcp/mcp-content-extractor/server.py
```

---

## 云端部署（Smithery）

项目已配置 Smithery Docker 部署，可将 MCP 托管到云端，Cursor 通过 HTTP 连接。

### 部署步骤

1. **推送代码到 GitHub**（若尚未推送）

2. **连接 Smithery**
   - 打开 [smithery.ai](https://smithery.ai)
   - 使用 GitHub 登录
   - 点击「New Server」或「Publish」
   - 选择「Import from GitHub」，选中 `wxr_agent` 仓库
   - Smithery 会自动检测根目录的 `Dockerfile` 和 `smithery.yaml`

3. **构建与发布**
   - Smithery 会执行 `docker build` 并部署
   - 部署完成后获得一个公网 URL（如 `https://xxx.smithery.ai`）

4. **Cursor 配置**（使用云端 URL）

```json
{
  "mcpServers": {
    "content-extractor": {
      "url": "https://你的Smithery部署URL/mcp",
      "transport": "streamable-http"
    }
  }
}
```

### 本地 Docker 测试

在项目根目录执行：

```bash
docker build -t mcp-content-extractor .
docker run -p 8081:8081 -e MCP_TRANSPORT=streamable-http mcp-content-extractor
```

服务启动后，MCP 端点为 `http://localhost:8081/mcp`。

### 注意事项

- **小红书**：云端无登录态，xhs-crawl 可用，但遇防爬时可能返回「页面不见了」
- **牛客**：一般无需登录，云端可正常使用
- 可选环境变量：`NOWCODER_COOKIE`、`XHS_USER_DATA_DIR`（云端通常不配置）

---

## Cursor 本地配置（stdio）

在 `~/.cursor/mcp.json` 或项目 `.cursor/mcp.json` 中添加：

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

- `cwd` 必须为项目根目录，否则无法 import backend
- `XHS_USER_DATA_DIR`：小红书登录态目录，与后端一致时可复用已扫码的 session

---

## 小红书登录说明

小红书内容获取有两种方式：

1. **xhs-crawl**：无需登录，但遇防爬时可能返回「页面不见了」
2. **Playwright 兜底**：需要登录态，使用 `XHS_USER_DATA_DIR` 中的浏览器 profile

**首次使用（本地）**：请先在后端完成扫码登录：

```bash
# 启动后端后
curl -X POST "http://localhost:8000/api/crawler/xhs/login?wait_seconds=120"
# 在弹出的浏览器中扫码，登录状态会保存到 backend/data/xhs_user_data
```

之后 MCP 会复用该目录的登录态。若 MCP 与后端在同一机器，配置相同的 `XHS_USER_DATA_DIR` 即可。

## 牛客说明

牛客公开帖子一般无需登录。若需登录才能查看，可在 `.env` 中配置 `NOWCODER_COOKIE`（从浏览器 F12 → Network 复制）。
