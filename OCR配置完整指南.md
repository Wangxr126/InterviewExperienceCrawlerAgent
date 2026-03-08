# OCR 配置完整指南

## 问题诊断

### 错误信息
```
ERROR | backend.services.crawler.ocr_service_mcp:_call_claude_vision_ocr - Claude Vision OCR 失败: No module named 'anthropic'
```

### 原因
- 使用了新的 MCP OCR 服务（支持 Claude Vision）
- 但是缺少 `anthropic` Python 包

---

## 解决方案

### 1. 安装 anthropic 包 ✅

已完成：
```bash
pip install anthropic
```

验证安装：
```bash
python -c "import anthropic; print('anthropic version:', anthropic.__version__)"
# 输出: anthropic version: 0.84.0
```

### 2. 配置 Anthropic API Key ⚠️

**这是必须的步骤！**

编辑 `.env` 文件，找到这一行：
```bash
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

替换为你的真实 API Key：
```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx
```

**如何获取 API Key：**
1. 访问 https://console.anthropic.com/
2. 登录或注册账号
3. 进入 API Keys 页面
4. 创建新的 API Key
5. 复制并粘贴到 `.env` 文件

---

## OCR 配置选项

### 方式1：Claude Vision API（推荐，默认）

**优点：**
- ✅ 识别准确率高（90%+）
- ✅ 支持中英文混合
- ✅ 能理解图片中的面试题结构
- ✅ 无需额外安装依赖

**配置：**
```bash
# .env 文件
OCR_METHOD=claude_vision
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

**成本：**
- Claude 3.5 Sonnet: $3/MTok (输入), $15/MTok (输出)
- 一张图片约消耗 1000-2000 tokens
- 估算：$0.003-0.006/张图片

### 方式2：EasyOCR（本地，免费）

**优点：**
- ✅ 完全免费
- ✅ 本地运行，无需API Key
- ✅ 支持中英文

**缺点：**
- ❌ 准确率较低（60-70%）
- ❌ 首次运行需下载模型（约100MB）
- ❌ 需要较多内存

**配置：**
```bash
# .env 文件
OCR_METHOD=easyocr
```

**安装：**
```bash
pip install easyocr
```

### 方式3：MCP 自定义服务（高级）

如果你有自己的 OCR 服务器（如 Tesseract MCP、PaddleOCR MCP）：

**配置：**
```bash
# .env 文件
OCR_METHOD=mcp
MCP_OCR_SERVER=your-ocr-server-name
```

---

## 完整配置示例

### 推荐配置（Claude Vision）

```bash
# .env 文件

# ========== OCR 配置 ==========
# OCR 方法：claude_vision（使用Claude Vision API）或 mcp（使用MCP服务）
OCR_METHOD=claude_vision

# MCP OCR 服务器名称（当 OCR_METHOD=mcp 时使用）
MCP_OCR_SERVER=ocr-server

# Anthropic API Key（用于 Claude Vision OCR）
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx  # ⚠️ 必须填写真实的 API Key
```

---

## 测试 OCR 功能

### 1. 重启后端服务

```bash
python run.py
```

### 2. 触发 OCR

1. 打开数据采集页面
2. 添加一个有图片的牛客帖子
3. 等待爬取完成
4. 查看日志

### 3. 验证日志

**成功的日志：**
```
INFO | backend.services.crawler.ocr_service_mcp:ocr_images_to_text - 使用 OCR 方法: claude_vision
INFO | backend.services.crawler.ocr_service_mcp:ocr_images_to_text - 使用 Claude Vision API 识别图片 1
INFO | backend.services.crawler.ocr_service_mcp:ocr_images_to_text - OCR 完成，识别到 1 张图片的文字
```

**失败的日志：**
```
ERROR | backend.services.crawler.ocr_service_mcp:_call_claude_vision_ocr - Claude Vision OCR 失败: No module named 'anthropic'
# 解决：pip install anthropic

ERROR | backend.services.crawler.ocr_service_mcp:_call_claude_vision_ocr - Claude Vision OCR 失败: Invalid API key
# 解决：检查 .env 中的 ANTHROPIC_API_KEY

ERROR | backend.services.crawler.ocr_service_mcp:_call_claude_vision_ocr - Claude Vision OCR 失败: Rate limit exceeded
# 解决：等待一段时间或升级 API 套餐
```

---

## 故障排查

### 问题1：No module named 'anthropic'
**解决：**
```bash
pip install anthropic
```

### 问题2：Invalid API key
**原因：**
- API Key 未配置
- API Key 格式错误
- API Key 已过期

**解决：**
1. 检查 `.env` 文件中的 `ANTHROPIC_API_KEY`
2. 确认 API Key 以 `sk-ant-api03-` 开头
3. 在 Anthropic Console 验证 API Key 是否有效

### 问题3：Rate limit exceeded
**原因：**
- API 调用频率过高
- 超出免费额度

**解决：**
1. 等待一段时间（通常1分钟后恢复）
2. 升级 API 套餐
3. 减少并发请求数

### 问题4：图片未识别到文字
**可能原因：**
- 图片质量太差
- 图片中没有文字
- 图片格式不支持

**解决：**
1. 检查原始图片是否清晰
2. 尝试使用其他 OCR 方法
3. 手动输入图片内容

---

## 相关文件

- `backend/services/crawler/ocr_service_mcp.py` - MCP OCR 服务实现
- `backend/services/crawler/ocr_service.py` - 旧的 EasyOCR 实现（已弃用）
- `backend/config/config.py` - OCR 配置定义
- `.env` - OCR 配置值
- `requirements.txt` - Python 依赖（已添加 anthropic）

---

## 下一步

1. ✅ 安装 anthropic 包（已完成）
2. ⚠️ **配置 ANTHROPIC_API_KEY**（必须完成）
3. 🔄 重启后端服务
4. 🧪 测试 OCR 功能

---

## 🎉 完成后

OCR 功能将自动工作：
- 当帖子正文中没有提取到题目时
- 系统会自动识别图片中的文字
- 将 OCR 结果与正文合并
- 再次调用 LLM 提取题目

**无需手动操作，全自动！**
