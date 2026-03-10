"""
LLM 解析失败记录服务

将 LLM 返回无法解析为 JSON 的样本保存到独立文件，便于后期微调或调试。
存储路径：backend/data/logs/llm_failures/{source}.jsonl
每行一个 JSON 对象，便于追加和批量处理。
"""
from backend.utils.time_utils import now_beijing, now_beijing_str, timestamp_to_beijing, timestamp_ms_to_beijing
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from backend.config.config import settings

logger = logging.getLogger(__name__)

_FAILURES_DIR = settings.logs_dir / "llm_failures"
_SOURCES = ("question_extract", "answer_eval", "architect_structure")


def _ensure_dir() -> Path:
    _FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    readme = _FAILURES_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# LLM 解析失败记录\n\n"
            "用于后期微调或调试。每行一个 JSON：ts, source, input_preview, raw_output, error, metadata。\n"
            "- question_extract.jsonl：题目提取失败\n"
            "- answer_eval.jsonl：答题评估失败\n",
            encoding="utf-8",
        )
    return _FAILURES_DIR


def save_failure(
    source: str,
    input_preview: str,
    raw_output: str,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    保存一次 LLM 解析失败记录。

    Args:
        source: 来源标识，如 question_extract / answer_eval / architect_structure
        input_preview: 输入内容摘要（截断，避免单条过大）
        raw_output: LLM 原始返回
        error: 解析错误信息
        metadata: 额外元数据（source_url、task_id 等）

    Returns:
        写入的文件路径
    """
    if source not in _SOURCES:
        source = "other"
    dir_path = _ensure_dir()
    file_path = dir_path / f"{source}.jsonl"

    # 输入/输出截断，单条记录控制在合理大小
    input_preview = (input_preview or "")[:2000]
    raw_output = (raw_output or "")[:8000]

    record = {
        "ts": now_beijing().isoformat(),
        "source": source,
        "input_preview": input_preview,
        "raw_output": raw_output,
        "error": error,
        "metadata": metadata or {},
    }

    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info(f"LLM 解析失败已记录: {file_path.name}")
        return str(file_path)
    except Exception as e:
        logger.warning(f"写入解析失败记录异常: {e}")
        return ""


def get_failures_path(source: str) -> Path:
    """获取某来源的失败记录文件路径"""
    _ensure_dir()
    return _FAILURES_DIR / f"{source}.jsonl"
