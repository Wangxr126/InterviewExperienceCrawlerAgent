"""
MCP OCR 快速测试脚本

用于验证 MCP OCR 配置是否正确
"""
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()

def test_config():
    """测试配置是否正确"""
    print("=" * 60)
    print("1. 检查配置")
    print("=" * 60)
    
    from backend.config.config import settings
    
    print(f"OCR 方法: {settings.ocr_method}")
    print(f"API Key 已配置: {bool(settings.anthropic_api_key)}")
    
    if not settings.anthropic_api_key or settings.anthropic_api_key == "your_anthropic_api_key_here":
        print("\n[错误] ANTHROPIC_API_KEY 未配置或使用占位符")
        print("请在 .env 文件中配置真实的 API Key")
        return False
    
    print("\n[成功] 配置检查通过")
    return True


def test_anthropic_module():
    """测试 anthropic 模块是否安装"""
    print("\n" + "=" * 60)
    print("2. 检查 anthropic 模块")
    print("=" * 60)
    
    try:
        import anthropic
        print(f"anthropic 版本: {anthropic.__version__}")
        print("\n[成功] anthropic 模块已安装")
        return True
    except ImportError as e:
        print(f"\n[错误] anthropic 模块未安装: {e}")
        print("请运行: pip install anthropic>=0.39.0")
        return False


def test_mcp_server():
    """测试 MCP 服务器文件是否存在"""
    print("\n" + "=" * 60)
    print("3. 检查 MCP 服务器")
    print("=" * 60)
    
    mcp_server = project_root / "mcp_ocr_server.py"
    
    if mcp_server.exists():
        print(f"MCP 服务器路径: {mcp_server}")
        print("\n[成功] MCP 服务器文件存在")
        return True
    else:
        print(f"\n[错误] MCP 服务器文件不存在: {mcp_server}")
        return False


def test_mcp_communication():
    """测试 MCP 通信"""
    print("\n" + "=" * 60)
    print("4. 测试 MCP 通信")
    print("=" * 60)
    
    import subprocess
    import json
    
    mcp_server = project_root / "mcp_ocr_server.py"
    
    # 测试 tools/list 方法
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    
    try:
        result = subprocess.run(
            [sys.executable, str(mcp_server)],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8'
        )
        
        if result.returncode != 0:
            print(f"\n[错误] MCP 服务器返回错误码: {result.returncode}")
            print(f"stderr: {result.stderr}")
            return False
        
        # 解析响应
        for line in result.stdout.strip().split('\n'):
            if not line or line.startswith('20'):  # 跳过日志行
                continue
            try:
                response = json.loads(line)
                if "tools" in response:
                    tools = response["tools"]
                    print(f"可用工具数量: {len(tools)}")
                    for tool in tools:
                        print(f"  - {tool['name']}: {tool['description']}")
                    print("\n[成功] MCP 通信正常")
                    return True
            except json.JSONDecodeError:
                continue
        
        print("\n[警告] 未能解析 MCP 响应")
        return False
        
    except subprocess.TimeoutExpired:
        print("\n[错误] MCP 服务器响应超时")
        return False
    except Exception as e:
        print(f"\n[错误] MCP 通信失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("MCP OCR 配置测试")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    results.append(("配置检查", test_config()))
    results.append(("anthropic 模块", test_anthropic_module()))
    results.append(("MCP 服务器", test_mcp_server()))
    results.append(("MCP 通信", test_mcp_communication()))
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    for name, passed in results:
        status = "[通过]" if passed else "[失败]"
        print(f"{status} {name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n" + "=" * 60)
        print("[成功] 所有测试通过！MCP OCR 配置正确")
        print("=" * 60)
        print("\n下一步：")
        print("1. 确保 .env 中配置了真实的 ANTHROPIC_API_KEY")
        print("2. 重启后端服务: python run.py")
        print("3. 运行爬虫测试 OCR 功能")
    else:
        print("\n" + "=" * 60)
        print("[失败] 部分测试未通过，请根据上述错误信息修复")
        print("=" * 60)
        print("\n参考文档：MCP_OCR_配置指南.md")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
