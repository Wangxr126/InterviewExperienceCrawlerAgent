#!/usr/bin/env python3
"""
MCP OCR 服务器 - 提供图片 OCR 识别功能

使用 Claude Vision API 作为后端，通过 MCP 协议对外提供服务
这样可以统一接口，方便切换不同的 OCR 实现

启动方式：
    python mcp_ocr_server.py

MCP 客户端调用示例：
    通过 stdio 方式调用此服务器
"""
import sys
import json
import base64
import logging
from pathlib import Path
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)


def ocr_image_with_claude(image_path: str, api_key: str) -> Optional[str]:
    """
    使用 Claude Vision API 识别图片中的文字
    
    Args:
        image_path: 图片文件路径
        api_key: Anthropic API Key
        
    Returns:
        识别出的文本，失败返回 None
    """
    try:
        import anthropic
        
        # 读取图片并转为 base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        # 判断图片类型
        suffix = Path(image_path).suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(suffix, "image/jpeg")
        
        client = anthropic.Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "请识别图片中的所有文字内容，按原文输出。如果是面试题目，请完整提取题目和答案。"
                        }
                    ],
                }
            ],
        )
        
        return message.content[0].text
        
    except Exception as e:
        logger.error(f"Claude Vision OCR 失败: {e}")
        return None


def handle_mcp_request(request: dict) -> dict:
    """
    处理 MCP 请求
    
    MCP 协议格式：
    - 请求：{"method": "tools/call", "params": {"name": "ocr_image", "arguments": {...}}}
    - 响应：{"content": [{"type": "text", "text": "..."}]}
    """
    try:
        method = request.get("method")
        
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ocr-server",
                    "version": "1.0.0"
                }
            }
        
        elif method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "ocr_image",
                        "description": "识别图片中的文字内容（支持中英文）",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "image_path": {
                                    "type": "string",
                                    "description": "图片文件的完整路径"
                                },
                                "api_key": {
                                    "type": "string",
                                    "description": "Anthropic API Key（可选，如果环境变量中已配置则不需要）"
                                }
                            },
                            "required": ["image_path"]
                        }
                    }
                ]
            }
        
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "ocr_image":
                image_path = arguments.get("image_path")
                api_key = arguments.get("api_key") or sys.argv[1] if len(sys.argv) > 1 else None
                
                if not image_path:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "错误：缺少 image_path 参数"
                            }
                        ],
                        "isError": True
                    }
                
                if not api_key:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "错误：缺少 API Key，请通过参数传入或设置环境变量"
                            }
                        ],
                        "isError": True
                    }
                
                # 执行 OCR
                logger.info(f"开始识别图片: {image_path}")
                text = ocr_image_with_claude(image_path, api_key)
                
                if text:
                    logger.info(f"识别成功，文本长度: {len(text)}")
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": text
                            }
                        ]
                    }
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "OCR 识别失败"
                            }
                        ],
                        "isError": True
                    }
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"未知工具: {tool_name}"
                    }
                ],
                "isError": True
            }
        
        else:
            return {
                "error": {
                    "code": -32601,
                    "message": f"未知方法: {method}"
                }
            }
    
    except Exception as e:
        logger.error(f"处理请求失败: {e}", exc_info=True)
        return {
            "error": {
                "code": -32603,
                "message": f"内部错误: {str(e)}"
            }
        }


def main():
    """
    MCP 服务器主循环
    通过 stdio 接收 JSON-RPC 请求并返回响应
    """
    logger.info("MCP OCR 服务器启动")
    logger.info("等待 MCP 请求...")
    
    # 从 stdin 读取请求，向 stdout 输出响应
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            request = json.loads(line)
            logger.info(f"收到请求: {request.get('method')}")
            
            response = handle_mcp_request(request)
            
            # 添加请求 ID
            if "id" in request:
                response["id"] = request["id"]
            
            # 输出响应到 stdout
            print(json.dumps(response), flush=True)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            error_response = {
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }
            print(json.dumps(error_response), flush=True)
        except Exception as e:
            logger.error(f"处理请求异常: {e}", exc_info=True)


if __name__ == "__main__":
    main()
