"""
HelloAgents AgentLogger 工厂：
- 日志目录由 .env 配置
- 每个 agent 单独文件
- 不输出到控制台
"""
from __future__ import annotations

import logging
from pathlib import Path


def build_agent_logger(agent_name: str, log_dir: str):
    """
    优先使用 hello_agents.core.logging.AgentLogger；
    若当前安装版本不支持，则回退为标准 logging 的文件 logger。
    """
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (agent_name or "agent"))
    out_dir = Path(log_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_file = str(out_dir / f"{safe_name}.log")

    try:
        # 按官方文档优先走 AgentLogger；不同版本可能签名差异较大，因此做分层尝试。
        from hello_agents.core.logging import AgentLogger  # type: ignore

        for kwargs in (
            {
                "name": safe_name,
                "level": "INFO",
                "output_file": output_file,
                "console": False,
            },
            {
                "name": safe_name,
                "level": "INFO",
                "output_file": output_file,
            },
            {
                "name": safe_name,
                "output_file": output_file,
            },
            {
                "name": safe_name,
                "level": "INFO",
            },
            {
                "name": safe_name,
            },
        ):
            try:
                obj = AgentLogger(**kwargs)
                # 强制关闭向上冒泡，避免被 root logger 打到控制台
                if hasattr(obj, "propagate"):
                    obj.propagate = False
                if hasattr(obj, "handlers"):
                    # 若 AgentLogger 默认挂了 StreamHandler，则移除
                    obj.handlers = [h for h in obj.handlers if not isinstance(h, logging.StreamHandler)]
                    # 确保至少有一个文件 handler
                    if not obj.handlers:
                        fh = logging.FileHandler(output_file, encoding="utf-8")
                        fh.setFormatter(
                            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s")
                        )
                        obj.addHandler(fh)
                return obj
            except TypeError:
                continue
    except Exception:
        pass

    # 回退：标准 logging 文件 logger（无控制台）
    logger = logging.getLogger(f"hello_agents.{safe_name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()
    file_handler = logging.FileHandler(output_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
    logger.addHandler(file_handler)
    return logger
