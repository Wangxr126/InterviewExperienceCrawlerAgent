"""
Stage2 未完成补跑子进程入口。

仅：1) 根据 questions 刷新 stage2_pending  2) 调用豆包 Stage2 写回答案。
不执行 batch_extract_worker / Rough Extractor。

用法：
  python -m backend.services.scheduling.stage2_retry_worker task_id1 task_id2 ...
"""
import logging
import sys
from pathlib import Path

_env_file = Path(__file__).resolve().parents[3] / ".env"
_env_loaded = False
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=str(_env_file), override=True)
    _env_loaded = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
if _env_loaded:
    logger.info("[Stage2RetryWorker] .env 已加载: %s", _env_file)
else:
    logger.warning("[Stage2RetryWorker] 未找到 .env: %s", _env_file)


def main() -> None:
    task_ids = [a.strip() for a in sys.argv[1:] if a and a.strip()]
    if not task_ids:
        logger.error("用法: python -m backend.services.scheduling.stage2_retry_worker <task_id> ...")
        sys.exit(1)

    from backend.services.stage2_unfinished_enqueue import ensure_stage2_pending_for_task_ids
    from backend.services.stage2_processor import run_stage2_retry_for_task_ids

    logger.info("[Stage2RetryWorker] 开始 Stage2 补跑，共 %d 个 task_id（仅豆包，不跑 Rough）", len(task_ids))
    prepared = ensure_stage2_pending_for_task_ids(task_ids)
    logger.info("[Stage2RetryWorker] 已写入/刷新 stage2_pending: %d 条", prepared)
    run_stage2_retry_for_task_ids(task_ids)
    logger.info("[Stage2RetryWorker] 结束")


if __name__ == "__main__":
    main()
