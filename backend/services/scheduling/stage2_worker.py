"""
Stage2 子进程入口。

用于在独立进程中执行 Stage2 队列消费，避免父进程退出导致后台线程被终止。
"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=str(env_file), override=True)


def main() -> int:
    _load_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    logger = logging.getLogger(__name__)
    logger.info("[Stage2Worker] 启动 pid=%s", os.getpid())

    from backend.services.stage2_processor import run_stage2_processor_now

    run_stage2_processor_now()
    logger.info("[Stage2Worker] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
