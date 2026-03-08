# OCR 服务配置说明

## 概述

系统现在支持两种OCR方式：
1. **Claude Vision API**（推荐，默认）- 使用Anthropic的Claude 3.5 Sonnet视觉模型
2. **MCP服务** - 通过Model Context Protocol调用自定义OCR服务

## 配置方式

### 方式1：使用 Claude Vision API（推荐）

这是最简单的方式，只需要配置Anthropic API Key。

**步骤：**

1. 编辑 `.env` 文件，设置：
```bash
OCR_METHOD=claude_vision
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx  # 你的Anthropic API Key
```

2. 重启后端服务

**优点：**
- ✅ 识别准确率高
- ✅ 支持中英文混合
- ✅ 能理解图片中的面试题结构
- ✅ 无需额外安装依赖

**成本：**
- Claude 3.5 Sonnet: $3/MTok (输入), $15/MTok (输出)
- 一张图片约消耗 1000-2000 tokens

### 方式2：使用 MCP OCR 服务

如果你有自己的MCP OCR服务器，可以使用这种方式。

**步骤：**

1. 启动你的MCP OCR服务器（例如：Tesseract MCP、PaddleOCR MCP）

2. 编辑 `.env` 文件，设置：
```bash
OCR_METHOD=mcp
MCP_OCR_SERVER=ocr-server  # 你的MCP服务器名称
```

3. 重启后端服务

**MCP服务器示例：**

你需要实现一个MCP服务器，提供 `ocr_image` 工具：

```python
# 示例：简单的MCP OCR服务器
from mcp.server import Server
from mcp.types import Tool, TextContent
import pytesseract
from PIL import Image

server = Server("ocr-server")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="ocr_image",
            description="识别图片中的文字",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "图片路径"}
                },
                "required": ["image_path"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "ocr_image":
        image_path = arguments["image_path"]
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        return [TextContent(type="text", text=text)]
```

## 工作流程

当帖子正文中没有提取到题目时，系统会：

1. 检查帖子是否有图片
2. 如果有图片，调用OCR服务识别图片中的文字
3. 将OCR结果与正文合并
4. 再次调用LLM提取题目

## 切换OCR方法

只需修改 `.env` 中的 `OCR_METHOD`：

```bash
# 使用 Claude Vision
OCR_METHOD=claude_vision

# 或使用 MCP
OCR_METHOD=mcp
```

重启后端即可生效。

## 故障排查

### Claude Vision 报错

**错误：`anthropic.AuthenticationError`**
- 检查 `ANTHROPIC_API_KEY` 是否正确
- 确认API Key有效且有余额

**错误：`anthropic.RateLimitError`**
- API调用频率过高，稍后重试
- 考虑升级API套餐

### MCP 报错

**错误：`MCP OCR 调用失败`**
- 检查MCP服务器是否启动
- 确认 `MCP_OCR_SERVER` 名称正确
- 查看MCP服务器日志

## 性能对比

| 方法 | 准确率 | 速度 | 成本 | 部署难度 |
|------|--------|------|------|----------|
| Claude Vision | ⭐⭐⭐⭐⭐ | 中等 | 按量付费 | 简单 |
| MCP (Tesseract) | ⭐⭐⭐ | 快 | 免费 | 中等 |
| MCP (PaddleOCR) | ⭐⭐⭐⭐ | 快 | 免费 | 中等 |

## 推荐配置

- **个人使用/小规模**：Claude Vision（简单可靠）
- **大规模/成本敏感**：MCP + PaddleOCR（免费但需要自己部署）
- **企业内网**：MCP + 自建OCR服务

## 相关文件

- `backend/services/crawler/ocr_service_mcp.py` - MCP OCR服务实现
- `backend/services/crawler/ocr_service.py` - 旧的EasyOCR实现（已弃用）
- `backend/config/config.py` - OCR配置定义
- `.env` - OCR配置值
