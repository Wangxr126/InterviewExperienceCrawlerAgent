"""
在配置文件中添加OCR相关配置
"""

with open('backend/config/config.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 在post_images_dir后面添加OCR配置
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    
    # 在post_images_dir定义后添加OCR配置
    if i > 0 and 'def post_images_dir' in lines[i-1]:
        # 跳过当前的docstring和return语句
        if '"""' in line or 'return' in line:
            continue
    
    # 在nowcoder_output_dir前添加OCR配置
    if 'def nowcoder_output_dir' in line:
        # 在这个函数前插入OCR配置
        new_lines.insert(-1, '    # ── OCR 配置 ──────────────────────────────────────────────\n')
        new_lines.insert(-1, '    @property\n')
        new_lines.insert(-1, '    def ocr_method(self) -> str:\n')
        new_lines.insert(-1, '        """OCR 方法：claude_vision（默认）或 mcp"""\n')
        new_lines.insert(-1, '        return _get("OCR_METHOD", "claude_vision")\n')
        new_lines.insert(-1, '\n')
        new_lines.insert(-1, '    @property\n')
        new_lines.insert(-1, '    def mcp_ocr_server(self) -> str:\n')
        new_lines.insert(-1, '        """MCP OCR 服务器名称"""\n')
        new_lines.insert(-1, '        return _get("MCP_OCR_SERVER", "ocr-server")\n')
        new_lines.insert(-1, '\n')
        new_lines.insert(-1, '    @property\n')
        new_lines.insert(-1, '    def anthropic_api_key(self) -> str:\n')
        new_lines.insert(-1, '        """Anthropic API Key（用于 Claude Vision OCR）"""\n')
        new_lines.insert(-1, '        return _get("ANTHROPIC_API_KEY", "")\n')
        new_lines.insert(-1, '\n')

with open('backend/config/config.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('[OK] 已添加 OCR 配置到 config.py')
print('添加的配置项：')
print('1. ocr_method - OCR 方法（claude_vision 或 mcp）')
print('2. mcp_ocr_server - MCP OCR 服务器名称')
print('3. anthropic_api_key - Anthropic API Key')
