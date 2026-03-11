#!/usr/bin/env python3
"""
mcp-image-extractor 测试脚本

测试通过 stdio 调用本地 mcp-image-extractor，提取图片为 base64。
注意：该工具只负责把图片转成 base64，OCR 识别由 AI 模型完成。
在 Cursor 中配置后，AI 可直接调用该工具读取图片内容。
"""
import subprocess
import json
import sys
import base64
from pathlib import Path

DIST_INDEX = Path(__file__).parent / "mcp-image-extractor" / "dist" / "index.js"
TEST_IMAGE = Path(__file__).parent / "test_ocr_image.png"


def send_mcp(proc, request: dict) -> dict:
    """向 MCP server 发送一条消息并读取响应"""
    line = json.dumps(request) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()
    while True:
        resp_line = proc.stdout.readline()
        if not resp_line:
            return {}
        resp_line = resp_line.strip()
        if not resp_line:
            continue
        try:
            resp = json.loads(resp_line)
            # 跳过 notification（无 id 字段）
            if "id" in resp:
                return resp
        except json.JSONDecodeError:
            continue


def main():
    print("=" * 60)
    print(" mcp-image-extractor 功能测试")
    print("=" * 60)

    # 检查构建产物
    if not DIST_INDEX.exists():
        print(f"[错误] 未找到构建产物: {DIST_INDEX}")
        print("请先在 mcp-image-extractor 目录执行: npm run build")
        sys.exit(1)
    print(f"[OK] 构建产物: {DIST_INDEX}")

    # 检查测试图片
    if not TEST_IMAGE.exists():
        print(f"[错误] 测试图片不存在: {TEST_IMAGE}")
        print("请先运行: python gen_test_image.py")
        sys.exit(1)
    print(f"[OK] 测试图片: {TEST_IMAGE}")

    # 启动 MCP server（长连接模式）
    print("\n[步骤1] 启动 MCP server...")
    proc = subprocess.Popen(
        ["node", str(DIST_INDEX)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    try:
        # --- initialize ---
        print("[步骤2] 发送 initialize...")
        resp = send_mcp(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"}
            }
        })
        print(f"  server info: {resp.get('result', {}).get('serverInfo', {})}")

        # initialized notification
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n")
        proc.stdin.flush()

        # --- tools/list ---
        print("\n[步骤3] 查询可用工具...")
        resp = send_mcp(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = resp.get("result", {}).get("tools", [])
        print(f"  可用工具数: {len(tools)}")
        for t in tools:
            print(f"    - {t['name']}: {t.get('description', '')}")

        # --- extract_image_from_file ---
        print(f"\n[步骤4] 调用 extract_image_from_file...")
        print(f"  图片: {TEST_IMAGE}")
        resp = send_mcp(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "extract_image_from_file",
                "arguments": {"file_path": str(TEST_IMAGE)}
            }
        })

        if "error" in resp:
            print(f"  [FAIL] 错误: {resp['error']}")
            sys.exit(1)

        content = resp.get("result", {}).get("content", [])
        if not content:
            print("  [FAIL] 未返回内容")
            sys.exit(1)

        result_text = content[0].get("text", "")
        print(f"  [OK] 返回内容类型: {content[0].get('type')}")

        # 检查返回的是否包含 base64 数据
        if "base64" in result_text.lower() or len(result_text) > 500:
            print(f"  [OK] 返回数据长度: {len(result_text)} 字符")
            # 截取前 200 字符预览
            preview = result_text[:200].replace("\n", " ")
            print(f"  预览: {preview}...")
            print("\n[SUCCESS] mcp-image-extractor 工作正常！")
            print("\n图片已成功转为 base64，可在 Cursor 中配置使用。")
        else:
            print(f"  返回内容: {result_text[:300]}")
            print("\n[OK] MCP server 响应正常")

        # --- 配置提示 ---
        print("\n" + "=" * 60)
        print(" Cursor 配置方法")
        print("=" * 60)
        index_path = str(DIST_INDEX).replace("\\", "/")
        config = {
            "mcpServers": {
                "image-extractor": {
                    "command": "node",
                    "args": [str(DIST_INDEX)],
                    "disabled": False
                }
            }
        }
        print("在 Cursor 设置 > MCP 中添加以下配置：")
        print(json.dumps(config, indent=2, ensure_ascii=False))
        print("\n或在项目根目录创建 .cursor/mcp.json 文件，内容如上。")

    finally:
        proc.stdin.close()
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
