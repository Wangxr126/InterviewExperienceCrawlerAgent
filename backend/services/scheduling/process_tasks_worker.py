"""
process_tasks 子进程入口。

用于将 _process_pending_tasks 放到独立子进程执行，避免主进程中的后台线程在父进程退出时中断。
"""
import argparse
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
    parser = argparse.ArgumentParser(description="Run crawler process_tasks in subprocess")
    parser.add_argument("--batch-size", type=int, default=30, help="batch size for process_tasks")
    args = parser.parse_args()

    _load_env()
    os.environ.setdefault("WXR_WORKER_SUBPROCESS", "1")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )
    logger = logging.getLogger(__name__)

    _ov = (os.environ.get("OPENAI_SDK_VERBOSE") or "").strip().lower() in ("1", "true", "yes")
    if _ov:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.DEBUG)
        logging.getLogger("openai").setLevel(logging.DEBUG)
        logging.getLogger("openai._base_client").setLevel(logging.DEBUG)
        logger.info("[ProcessTasksWorker] OPENAI_SDK_VERBOSE=1：httpx/httpcore/openai DEBUG 已开")

    logger.info("[ProcessTasksWorker] 启动 batch_size=%s pid=%s", args.batch_size, os.getpid())

    from backend.services.crawler.question_extractor import MinerFatalApiError
    from backend.services.crawler.task_executor import execute as task_execute

    try:
        result = task_execute(
            "process_tasks",
            "button",
            batch_size=args.batch_size,
            force_inline_process_tasks=True,
        )
    except MinerFatalApiError as e:
        logger.error("[ProcessTasksWorker] 上游 API 致命错误，子进程立即退出: %s", e)
        return 1
    except Exception as e:
        logger.error("[ProcessTasksWorker] 执行异常，子进程退出: %s", e)
        return 1
    logger.info(
        "[ProcessTasksWorker] 完成 questions_added=%s",
        result.get("questions_added", 0),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
