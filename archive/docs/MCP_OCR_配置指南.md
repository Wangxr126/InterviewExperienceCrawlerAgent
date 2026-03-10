# MCP OCR 配置指南

## 什么是 MCP OCR？

MCP (Model Context Protocol) 是一种标准化的协议，用于在不同服务之间进行通信。通过 MCP 方式调用 OCR，可以：

- **解耦服务**：OCR 服务独立运行，便于维护和升级
- **统一接口**：无论底层使用什么 OCR 引擎，接口保持一致
- **灵活切换**：可以轻松切换不同的 OCR 实现（Claude Vision、Tesseract、PaddleOCR 等）
- **更好的错误处理**：服务隔离，错误不会影响主程序

## 架构说明

```
爬虫程序 (backend/services/crawler)
    ↓ 调用
OCR 服务 (backend/services/crawler/ocr_service_mcp.py)
    ↓ MCP 协议 (stdio)
MCP OCR 服务器 (mcp_ocr_server.py)
    ↓ API 调用
Claude Vision API
```

## 配置步骤

### 1. 获取 Anthropic API Key

1. 访问：https://console.anthropic.com/settings/keys
2. 登录/注册账号
3. 点击 "Create Key" 创建 API Key
4. 复制生成的 Key（格式：`sk-ant-api03-...`）

### 2. 配置 .env 文件

打开 `e:\Agent\AgentProject\wxr_agent\.env`，找到 OCR 配置部分：

```env
# ========== OCR 配置 ==========
# OCR 方法：mcp（使用MCP服务，推荐）或 claude_vision（直接调用Claude API）
OCR_METHOD=mcp

# MCP OCR 服务器名称（当 OCR_METHOD=mcp 时使用）
MCP_OCR_SERVER=ocr-server

# Anthropic API Key（用于 Claude Vision OCR）
# 获取方式：访问 https://console.anthropic.com/settings/keys 创建 API Key
# 注意：需要有可用余额才能调用 Vision API（约 $0.003/张图片）
ANTHROPIC_API_KEY=sk-ant-api03-你的真实API_Key
```

**重要**：将 `your_anthropic_api_key_here` 替换为你的真实 API Key

### 3. 验证配置

```bash
# 在 NewCoderAgent 环境中测试
cd e:\Agent\AgentProject\wxr_agent
C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe -c "from backend.config.config import settings; print('API Key 已配置:', bool(settings.anthropic_api_key))"
```

应该输出：`API Key 已配置: True`

### 4. 测试 MCP OCR 服务器

```bash
# 手动测试 MCP 服务器
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python mcp_ocr_server.py
```

应该返回可用的工具列表。

### 5. 重启后端服务

```bash
# 停止当前服务（Ctrl+C）
# 重新启动
python run.py
```

## 工作流程

1. **爬虫提取图片**：从小红书/牛客网下载帖子中的图片
2. **调用 OCR 服务**：`ocr_service_mcp.py` 检测到需要识别图片
3. **启动 MCP 服务器**：通过 subprocess 启动 `mcp_ocr_server.py`
4. **发送 MCP 请求**：通过 stdio 发送 JSON-RPC 格式的请求
5. **MCP 服务器处理**：调用 Claude Vision API 识别图片
6. **返回结果**：通过 stdio 返回识别的文字
7. **提取题目**：将识别的文字交给 LLM 提取面试题

## 日志示例

成功的日志应该是这样的：

```
2026-03-09 10:40:02 | INFO    | 使用 OCR 方法: mcp
2026-03-09 10:40:02 | INFO    | 使用 MCP OCR 识别图片 1
2026-03-09 10:40:05 | INFO    | 图片 1 识别成功，文本长度: 245
2026-03-09 10:40:05 | INFO    | OCR 完成，识别到 3 张图片的文字
```

## 费用说明

- Claude Vision API 按图片计费
- 费用：约 **$0.003 - $0.015 每张图片**
- 计费因素：图片大小、复杂度、分辨率
- 需要在 Anthropic 账户中充值

## 故障排查

### 问题 1：No module named 'anthropic'

**原因**：anthropic 模块未安装在 NewCoderAgent 环境

**解决**：
```bash
C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe -m pip install anthropic>=0.39.0
```

### 问题 2：API Key 错误

**日志**：`错误：缺少 API Key` 或 `401 Unauthorized`

**解决**：
1. 检查 `.env` 文件中 `ANTHROPIC_API_KEY` 是否正确配置
2. 确认 API Key 格式正确（以 `sk-ant-` 开头）
3. 确认账户有可用余额

### 问题 3：MCP 服务器启动失败

**日志**：`MCP OCR 服务器脚本不存在`

**解决**：
确认 `mcp_ocr_server.py` 文件在项目根目录：
```bash
ls e:\Agent\AgentProject\wxr_agent\mcp_ocr_server.py
```

### 问题 4：超时错误

**日志**：`MCP OCR 调用超时`

**原因**：网络慢或图片太大

**解决**：
1. 检查网络连接
2. 增加超时时间（修改 `ocr_service_mcp.py` 中的 `timeout=60`）

## 切换回直接调用模式

如果 MCP 方式有问题，可以临时切换回直接调用：

```env
# .env 文件
OCR_METHOD=claude_vision
```

这样会跳过 MCP 服务器，直接调用 Claude API。

## 扩展：使用其他 OCR 引擎

MCP 架构的优势是可以轻松切换 OCR 引擎。你可以修改 `mcp_ocr_server.py` 中的 `ocr_image_with_claude` 函数，替换为：

- **Tesseract OCR**（免费，本地）
- **PaddleOCR**（免费，本地，中文效果好）
- **EasyOCR**（免费，本地）
- **Google Cloud Vision**（付费）
- **百度 OCR**（付费，中文效果好）

只需修改 MCP 服务器代码，主程序无需改动。

## 相关文件

- MCP 服务器：`mcp_ocr_server.py`
- OCR 服务：`backend/services/crawler/ocr_service_mcp.py`
- 配置文件：`.env`
- 依赖清单：`requirements.txt`

## 技术细节

### MCP 协议格式

**请求**：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "ocr_image",
    "arguments": {
      "image_path": "/path/to/image.jpg",
      "api_key": "sk-ant-..."
    }
  }
}
```

**响应**：
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "content": [
    {
      "type": "text",
      "text": "识别出的文字内容..."
    }
  ]
}
```

### 通信方式

- **stdio**：通过标准输入/输出进行通信
- **进程隔离**：每次调用启动新的 MCP 服务器进程
- **同步调用**：等待 OCR 完成后返回结果

## 总结

✅ **已完成**：
1. 安装 `anthropic` 模块到 NewCoderAgent 环境
2. 创建 MCP OCR 服务器 (`mcp_ocr_server.py`)
3. 更新 OCR 服务代码支持 MCP 调用
4. 配置 `.env` 使用 MCP 模式

⚠️ **待完成**：
1. 获取 Anthropic API Key
2. 配置到 `.env` 文件
3. 重启后端服务测试

完成这些步骤后，OCR 功能就能通过 MCP 方式正常工作了！
