# mcp-speech-to-text

基于 **OpenAI Whisper API** 的 MCP 语音转文字服务器。支持三种输入方式，供 Agent 在对话链路中直接调用。

## 提供的工具

| 工具名 | 描述 |
|---|---|
| `transcribe_audio_file` | 转录本地音频文件（绝对路径） |
| `transcribe_audio_url` | 下载远程 URL 音频并转录 |
| `transcribe_audio_base64` | 转录 base64 编码音频（适合前端直传） |

支持格式：`mp3` `wav` `m4a` `webm` `ogg` `flac`（≤25MB）

## 快速开始

```bash
# 安装依赖
npm install

# 编译
npm run build

# 运行（需设置 API Key）
OPENAI_API_KEY=sk-xxx npm start
```

## 注册到 Cursor MCP

在 Cursor 的 `~/.cursor/mcp.json`（或项目级 `.cursor/mcp.json`）中添加：

```json
{
  "mcpServers": {
    "speech-to-text": {
      "command": "node",
      "args": ["e:/Agent/AgentProject/wxr_agent/mcp/mcp-speech-to-text/dist/index.js"],
      "env": {
        "OPENAI_API_KEY": "sk-你的Key",
        "OPENAI_BASE_URL": "https://api.openai.com"
      }
    }
  }
}
```

## 注册到 Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "speech-to-text": {
      "command": "node",
      "args": ["/path/to/mcp-speech-to-text/dist/index.js"],
      "env": {
        "OPENAI_API_KEY": "sk-你的Key"
      }
    }
  }
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | **必填** | OpenAI API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com` | API 基础 URL，支持国内代理 |
| `WHISPER_MODEL` | `whisper-1` | 使用的 Whisper 模型 |
| `MAX_AUDIO_SIZE` | `26214400` (25MB) | 最大音频文件大小（字节） |

## 与前端集成说明

项目前端（`ChatView.vue`）已内置浏览器原生 **Web Speech API**，**无需后端、零成本、实时识别**。  
本 MCP server 与前端互补，适用于以下场景：

| 场景 | 推荐方案 |
|---|---|
| 用户在界面实时语音输入 | Web Speech API（前端内置，无需配置）|
| Agent 处理已录制的音频文件 | `transcribe_audio_file` 工具 |
| Agent 从 URL 获取音频并转录 | `transcribe_audio_url` 工具 |
| 前端录音后发给 Agent 高精度转录 | `transcribe_audio_base64` 工具 |
| 需要识别专业术语/方言 | Whisper API（可加 prompt 提示词）|

## 项目结构

```
mcp-speech-to-text/
├── src/
│   └── index.ts        # MCP server 主文件
├── dist/               # 编译输出（build 后生成）
├── package.json
├── tsconfig.json
├── .env.example        # 环境变量示例
└── README.md
```

## 注意事项

- Windows 下 `npm run build` 中的 `chmod` 命令可忽略报错，不影响运行
- 国内用户可设置 `OPENAI_BASE_URL` 指向代理（如 OneAPI、Ollama 兼容接口等）
- Whisper API 每次请求费用约 $0.006/分钟
- 本地 Whisper 方案：可将 `OPENAI_BASE_URL` 指向本地 faster-whisper 兼容服务
