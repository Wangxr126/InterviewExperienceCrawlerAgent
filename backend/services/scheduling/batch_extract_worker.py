"""
批量提取子进程入口

用于将耗时的 TwoStageExtractor（OCR + LLM 2-5 分钟/条）放到独立子进程中执行，
避免阻塞主进程的 API 请求（如 loadTasks、loadStats、提交作答等）。

使用方式：
  python -m backend.services.scheduling.batch_extract_worker task_id1 task_id2 ...
"""
import logging
import sys

logger = logging.getLogger(__name__)


def run_batch_extract(task_ids: list) -> None:
    """在子进程中执行批量提取，与主进程完全隔离"""
    from backend.services.scheduling.scheduler import process_single_task

    for tid in task_ids:
        try:
            process_single_task(tid)
        except Exception as e:
            logger.error(f"[BatchExtractWorker] 批量提取异常 task_id={tid}: {e}")


def main():
    if len(sys.argv) < 2:
        logger.error("用法: python -m backend.services.scheduling.batch_extract_worker task_id1 task_id2 ...")
        sys.exit(1)
    task_ids = [a.strip() for a in sys.argv[1:] if a and a.strip()]
    if not task_ids:
        logger.error("未提供有效的 task_id")
        sys.exit(1)
    run_batch_extract(task_ids)


if __name__ == "__main__":
    main()
