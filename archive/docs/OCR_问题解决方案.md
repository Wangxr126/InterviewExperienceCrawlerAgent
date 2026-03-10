# OCR 图片识别问题解决方案

## 问题现象

运行爬虫时，OCR 图片识别失败，日志显示：
```
ERROR   | Claude Vision OCR 失败: No module named 'anthropic'
```

## 根本原因

1. **环境不匹配**：`anthropic` 模块安装在 base 环境，但程序运行在 NewCoderAgent 环境
2. **API Key 未配置**：`.env` 文件中 `ANTHROPIC_API_KEY` 使用的是占位符

## 解决步骤

### ✅ 步骤 1：安装 anthropic 模块（已完成）

```bash
C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe -m pip install anthropic>=0.39.0
```

验证安装：
```bash
C:\Users\Wangxr\.conda\envs\NewCoderAgent\python.exe -c "import anthropic; print(anthropic.__version__)"
# 输出：0.84.0
```

### ⚠️ 步骤 2：配置 Anthropic API Key（待完成）

1. **获取 API Key**：
   - 访问：https://console.anthropic.com/settings/keys
   - 登录/注册 Anthropic 账号
   - 点击 "Create Key" 创建新的 API Key
   - 复制生成的 Key（格式：`sk-ant-...`）

2. **配置到 .env 文件**：
   打开 `e:\Agent\AgentProject\wxr_agent\.env`，找到最后几行：
   ```env
   # 获取方式：访问 https://console.anthropic.com/settings/keys 创建 API Key
   # 注意：需要有可用余额才能调用 Vision API（约 $0.003/张图片）
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```
   
   将 `your_anthropic_api_key_here` 替换为你的真实 API Key：
   ```env
   ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx
   ```

3. **重启后端服务**：
   ```bash
   # 停止当前运行的服务（Ctrl+C）
   # 重新启动
   python run.py
   ```

## 费用说明

- Claude Vision API 按图片数量计费
- 大约 $0.003 - $0.015 每张图片（取决于图片大小和复杂度）
- 需要在 Anthropic 账户中充值才能使用

## 验证方法

配置完成后，再次运行爬虫，观察日志：
- ✅ 成功：`INFO | 使用 Claude Vision API 识别图片 1`，然后显示识别结果
- ❌ 失败：仍然显示 `No module named 'anthropic'` 或 API Key 错误

## 备选方案

如果不想使用付费的 Claude Vision API，可以考虑：

1. **使用本地 OCR（EasyOCR）**：
   - 修改 `.env` 中的 `OCR_METHOD=easyocr`
   - 免费，但识别准确率可能较低
   - 需要下载模型文件（首次使用）

2. **使用其他 Vision API**：
   - OpenAI GPT-4 Vision
   - Google Cloud Vision
   - 百度 OCR 等

## 相关文件

- 配置文件：`e:\Agent\AgentProject\wxr_agent\.env`
- OCR 服务代码：`backend\services\crawler\ocr_service_mcp.py`
- 启动脚本：`run.py`
- 依赖清单：`requirements.txt`
