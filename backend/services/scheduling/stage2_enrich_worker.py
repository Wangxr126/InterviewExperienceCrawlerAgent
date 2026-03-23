"""
Stage2 精答子进程入口

对已入库题目批量跑 Stage2（MINER_STAGE2_* 豆包等），合并后更新 questions.answer_text / raw_answer，
并同步 Neo4j 答案字段。放到独立子进程中执行，避免阻塞主进程的 API 请求。

使用方式：
  python -m backend.services.scheduling.stage2_enrich_worker task_id1 task_id2 ...

子进程日志写入 stage2_enrich.log（主进程启动时指定 stdout/stderr 重定向）
"""
import logging
import os
import sys
from pathlib import Path

# 供子进程内各模块识别当前运行环境
os.environ.setdefault("WXR_WORKER_SUBPROCESS", "1")

# 子进程独立运行，必须手动加载 .env
_env_file = Path(__file__).parent.parent.parent.parent / ".env"
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
    _stage2_model = os.environ.get("MINER_STAGE2_MODEL", "(未设置)")
    _stage2_key = os.environ.get("MINER_STAGE2_API_KEY", "")
    _stage2_key_masked = (_stage2_key[:8] + "...") if len(_stage2_key) > 8 else "(未设置)"
    _stage2_base = os.environ.get("MINER_STAGE2_BASE_URL", "(未设置)")
    logger.info("[Stage2EnrichWorker] ✅ .env 已加载: %s", _env_file)
    logger.info("[Stage2EnrichWorker] 配置确认：")
    logger.info("  MINER_STAGE2_MODEL   = %s", _stage2_model)
    logger.info("  MINER_STAGE2_BASE_URL= %s", _stage2_base)
    logger.info("  MINER_STAGE2_API_KEY = %s", _stage2_key_masked)
else:
    logger.warning("[Stage2EnrichWorker] ⚠️  .env 文件不存在: %s，将使用系统环境变量", _env_file)


def run_stage2_enrich(task_ids: list) -> None:
    """在子进程中批量执行 Stage2 精答，与主进程完全隔离。"""
    from backend.services.crawler.stage2_enrich_service import enrich_task_stage2

    logger.info("[Stage2EnrichWorker] 开始批量 Stage2 精答，共 %d 条", len(task_ids))
    ok_count = 0
    for i, tid in enumerate(task_ids):
        try:
            logger.info("[Stage2EnrichWorker] 处理 %d/%d task_id=%s", i + 1, len(task_ids), tid)
            result = enrich_task_stage2(tid)
            if result.get("ok"):
                ok_count += 1
                logger.info(
                    "[Stage2EnrichWorker] 完成 task_id=%s，更新 %d 题: %s",
                    tid, result.get("updated", 0), result.get("message", ""),
                )
            else:
                logger.warning(
                    "[Stage2EnrichWorker] ⚠️  task_id=%s 失败: %s",
                    tid, result.get("message", "未知原因"),
                )
        except Exception as e:
            logger.error("[Stage2EnrichWorker] 异常 task_id=%s: %s", tid, e)
    logger.info(
        "[Stage2EnrichWorker] 全部完成，成功 %d/%d 条",
        ok_count, len(task_ids),
    )


def main():
    if len(sys.argv) < 2:
        logger.error("用法: python -m backend.services.scheduling.stage2_enrich_worker task_id1 task_id2 ...")
        sys.exit(1)
    task_ids = [a.strip() for a in sys.argv[1:] if a and a.strip()]
    if not task_ids:
        logger.error("未提供有效的 task_id")
        sys.exit(1)
    run_stage2_enrich(task_ids)


if __name__ == "__main__":
    main()
