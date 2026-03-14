#!/usr/bin/env python3
"""修复日志重复打印问题"""
import re

# 读取文件
with open('backend/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 定位要替换的代码块
old_code = '''    _loguru_logger.remove()

    # 统一的日志格式：完整日期时间 | 级别（7字符宽） | 消息
    _log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"

    _loguru_logger.add(

        sys.stderr,

        colorize=True,

        format=_log_format,

        level="INFO",

    )

    _loguru_logger.add(

        _BACKEND_LOGS / "backend.log",

        rotation="10 MB",

        retention=5,

        encoding="utf-8",

        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",

        level="INFO",

    )'''

new_code = '''    _loguru_logger.remove()

    # 统一的日志格式：完整日期时间 | 级别（7字符宽） | 消息
    _log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"

    # 多进程模式：只在主进程输出到终端，避免重复打印
    # uvicorn多进程模式下，worker进程会设置 UVICORN_WORKER_ID 环境变量
    is_main_process = os.environ.get('UVICORN_WORKER_ID') is None
    
    if is_main_process:
        _loguru_logger.add(

            sys.stderr,

            colorize=True,

            format=_log_format,

            level="INFO",

        )

    # 所有进程都写入文件（enqueue=True 确保多进程安全）
    _loguru_logger.add(

        _BACKEND_LOGS / "backend.log",

        rotation="10 MB",

        retention=5,

        encoding="utf-8",

        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",

        level="INFO",

        enqueue=True,

    )'''

# 替换
if old_code in content:
    content = content.replace(old_code, new_code)
    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ 日志配置已修复")
else:
    print("❌ 未找到目标代码块，请手动修改")
