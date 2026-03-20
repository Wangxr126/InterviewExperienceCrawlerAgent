"""
批量提取子进程入口

用于将耗时的 TwoStageExtractor（OCR + LLM 2-5 分钟/条）放到独立子进程中执行，
避免阻塞主进程的 API 请求（如 loadTasks、loadStats、提交作答等）。

使用方式：
  python -m backend.services.scheduling.batch_extract_worker task_id1 task_id2 ...

子进程日志写入 batch_extract.log（主进程启动时指定 stdout/stderr 重定向）
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

# 子进程独立运行，必须手动加载 .env，否则 MINER_MODE/LLM_PROVIDER 等配置读取不到
_env_file = Path(__file__).parent.parent.parent.parent / ".env"
_env_loaded = False
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(_env_file), override=True)
    _env_loaded = True

# 子进程独立运行，需配置基础 logging 输出到 stderr（主进程会重定向到 batch_extract.log）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ── 子进程配置确认日志（验证 .env 已加载）──────────────────────────────────────
if _env_loaded:
    import os as _os
    _miner_mode   = _os.environ.get("MINER_MODE", "(未设置)")
    _miner_model  = _os.environ.get("MINER_LOCAL_MODEL", "(未设置)")
    _stage2_model = _os.environ.get("MINER_STAGE2_MODEL", "(未设置)")
    _stage2_key   = _os.environ.get("MINER_STAGE2_API_KEY", "")
    _stage2_key_masked = (_stage2_key[:8] + "...") if len(_stage2_key) > 8 else "(未设置)"
    _llm_mode     = _os.environ.get("LLM_MODE", "(未设置)")
    logger.info("[BatchExtractWorker] ✅ .env 已加载: %s", _env_file)
    logger.info("[BatchExtractWorker] 配置确认：")
    logger.info("  LLM_MODE         = %s", _llm_mode)
    logger.info("  MINER_MODE       = %s", _miner_mode)
    logger.info("  MINER_LOCAL_MODEL= %s", _miner_model)
    logger.info("  MINER_STAGE2_MODEL=%s", _stage2_model)
    logger.info("  MINER_STAGE2_KEY  = %s", _stage2_key_masked)
else:
    logger.warning("[BatchExtractWorker] ⚠️  .env 文件不存在: %s，将使用系统环境变量", _env_file)


def run_batch_extract(task_ids: list) -> None:
    """在子进程中执行批量提取，与主进程完全隔离"""
    from backend.services.scheduling.scheduler import process_single_task

    logger.info("[BatchExtractWorker] 开始批量提取，共 %d 条", len(task_ids))
    for i, tid in enumerate(task_ids):
        try:
            logger.info("[BatchExtractWorker] 处理 %d/%d task_id=%s", i + 1, len(task_ids), tid)
            process_single_task(tid)
            logger.info("[BatchExtractWorker] 完成 task_id=%s", tid)
        except Exception as e:
            logger.error("[BatchExtractWorker] 批量提取异常 task_id=%s: %s", tid, e)
    logger.info("[BatchExtractWorker] 全部完成")


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
