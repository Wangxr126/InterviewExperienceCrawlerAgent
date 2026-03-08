"""
添加OCR配置到.env文件
"""

ocr_config = """
# ========== OCR 配置 ==========
# OCR 方法：claude_vision（使用Claude Vision API）或 mcp（使用MCP服务）
OCR_METHOD=claude_vision

# MCP OCR 服务器名称（当 OCR_METHOD=mcp 时使用）
MCP_OCR_SERVER=ocr-server

# Anthropic API Key（用于 Claude Vision OCR）
ANTHROPIC_API_KEY=your_anthropic_api_key_here
"""

with open('.env', 'a', encoding='utf-8') as f:
    f.write(ocr_config)

print('[OK] 已添加 OCR 配置到 .env 文件')
print('')
print('添加的配置项：')
print('1. OCR_METHOD=claude_vision  # 默认使用Claude Vision')
print('2. MCP_OCR_SERVER=ocr-server  # MCP服务器名称')
print('3. ANTHROPIC_API_KEY=...  # 需要填写你的API Key')
print('')
print('⚠️ 请编辑 .env 文件，填写你的 ANTHROPIC_API_KEY')
