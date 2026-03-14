# MCP Content Extractor - Smithery / 云端部署
# 牛客+小红书 URL 内容+图片提取 MCP 服务
# 构建：docker build -t mcp-content-extractor .
FROM python:3.11-slim

# Playwright 需要这些系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    wget ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制 MCP 服务器和 backend 爬虫模块
COPY mcp/mcp-content-extractor/ ./mcp/mcp-content-extractor/
COPY backend/ ./backend/
COPY mcp/mcp-content-extractor/requirements-docker.txt ./requirements-docker.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements-docker.txt

# 安装 Chromium（小红书 Playwright 兜底用）
RUN playwright install chromium

# 设置环境变量
ENV PYTHONPATH=/app
ENV MCP_TRANSPORT=streamable-http
ENV PORT=8081

# Smithery 会注入 PORT，默认 8081
EXPOSE 8081

# 启动 MCP 服务器（HTTP 模式）
CMD ["python", "mcp/mcp-content-extractor/server.py"]
