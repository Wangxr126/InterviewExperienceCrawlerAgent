"""
Stage2 处理器：从 stage2_pending 队列取批，调用火山 API，写回 crawl_tasks + questions

触发方式：达到 MINER_STAGE2_BATCH_SIZE 时由 Stage1 入队后触发（无轮询）
"""
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from typing import List, Dict, Any

from backend.config.config import settings
from backend.services.logging.agent_tool_runtime_stats import agent_tool_runtime_stats
from backend.services.storage import sqlite_service
from backend.services.volcengine_stage2_client import call_single, call_batch
from backend.agents.prompts.two_stage_prompts import ENRICH_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# 工具统计页展示用：Stage2 不走 ReAct 工具循环，需单独打点
STAGE2_STATS_AGENT = "Stage2"
STAGE2_STATS_TOOL = "stage2_enrich"

# 防止并发执行 Stage2 处理器
_stage2_lock = threading.Lock()
_stage2_running = False


def _record_stage2_tool_call(success: bool, execution_time_ms: float = 0.0) -> None:
    agent_tool_runtime_stats.record(
        agent_name=STAGE2_STATS_AGENT,
        tool_name=STAGE2_STATS_TOOL,
        success=success,
        execution_time_ms=float(execution_time_ms or 0.0),
    )


def _extract_json_from_stage2(text: str) -> str:
    """从 Stage2 输出中提取 JSON 数组（可能被 Markdown 包裹）"""
    if not text:
        return "[]"
    stripped = text.strip()
    if stripped.startswith("["):
        return stripped
    import re
    clean = re.sub(r"```(?:json)?\s*", "", stripped).strip().rstrip("`").strip()
    if clean.startswith("["):
        return clean
    for m in re.finditer(r"\[", clean):
        start = m.start()
        depth, i, in_str, escape = 0, start, None, False
        while i < len(clean):
            c = clean[i]
            if in_str:
                escape = not escape and c == "\\"
                if not escape and c == in_str:
                    in_str = None
            elif c in ('"', "'"):
                in_str = c
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return clean[start : i + 1]
            i += 1
    return text


def _merge_stage2_with_stage1(enrich_result: str, stage1_output: str) -> str:
    """合并 Stage 2 输出与 Stage 1 元数据（支持 Stage1 旧格式 title/answer/type/tags）"""
    from backend.services.finetune.stage_merge_utils import merge_stage2_with_stage1
    return merge_stage2_with_stage1(enrich_result, stage1_output)


def _save_two_stage_log(content: str, stage1_output: str, stage2_output: str, stage2_model: str):
    """保存两阶段日志（微调用）"""
    log_path = getattr(settings, "miner_two_stage_log_path", None)
    if not log_path:
        return
    try:
        from pathlib import Path
        from datetime import datetime
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(),
            "content_preview": (content or "")[:500] + ("..." if len(content or "") > 500 else ""),
            "stage1_output": stage1_output,
            "stage2_output": stage2_output,
            "stage1_model": settings.miner_local_model,
            "stage2_model": stage2_model,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("保存两阶段日志失败: %s", e)


def _process_single_item(
    item: Dict,
    enrich_result: str,
    model_used: str,
) -> bool:
    """处理单条：合并、写库、更新状态"""
    try:
        rough_questions = json.loads(item.get("rough_questions") or "[]")
        if not isinstance(rough_questions, list):
            rough_questions = []
        enrich_clean = _extract_json_from_stage2(enrich_result)
        try:
            stage1_str = item.get("stage1_output") or json.dumps(rough_questions, ensure_ascii=False)
            merged = _merge_stage2_with_stage1(enrich_clean, stage1_str)
        except Exception:
            # Stage2 解析失败，降级用 Stage1 结果
            merged = json.dumps([
                {**q, "answer_text": q.get("answer_text", ""), "raw_answer": q.get("answer_text", "")}
                for q in rough_questions if isinstance(q, dict) and q.get("question_text")
            ], ensure_ascii=False)
        # 允许 answer_text 中保留 Markdown 换行等控制字符（不做清洗）
        # 只要求整体结构是 JSON 数组对象：[{...}, {...}]
        questions = json.loads(merged, strict=False)
        # 语种/标签校验仅在 miner 提取路径（question_extractor）执行；Stage2 精加工不再拦截英文题干等。
        raw_content = item.get("content") or ""
        task_id = item["task_id"]
        content = raw_content
        stage1_output = item.get("stage1_output") or ""
        source_url = item.get("source_url") or ""

        # 写 questions 表（与 scheduler._save_questions 一致）
        company = item.get("company") or ""
        position = item.get("position") or ""
        crawl_task_id = None
        with sqlite_service._get_conn() as conn:
            r = conn.execute("SELECT id FROM crawl_tasks WHERE task_id=?", (task_id,)).fetchone()
            if r:
                crawl_task_id = r["id"]
            # 幂等：同一条 crawl_task 可能因崩溃/重试被重复消费
            # 先清空 questions，避免生成随机 q_id 造成重复数据。
            if source_url:
                conn.execute("DELETE FROM questions WHERE source_url=?", (source_url,))
            for q in questions:
                if not isinstance(q, dict) or not q.get("question_text"):
                    continue
                q_id = str(uuid.uuid4())
                tags = q.get("topic_tags") or []
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = []
                conn.execute("""
                    INSERT OR IGNORE INTO questions
                        (q_id, question_text, answer_text, raw_answer, difficulty, question_type,
                         source_platform, source_url, company, position, business_line,
                         topic_tags, extraction_source, crawl_task_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    q_id, q.get("question_text", ""), q.get("answer_text", ""), q.get("raw_answer", ""),
                    q.get("difficulty", "medium"), q.get("question_type", "技术题"),
                    "", source_url, company, position, "",
                    json.dumps(tags, ensure_ascii=False),
                    "image" if item.get("ocr_called") else "content",
                    crawl_task_id,
                ))
            conn.commit()

        # 更新 crawl_tasks（须写入 extraction_source，否则默认空串会变成 NULL，列表「来源」一直为 --）
        extraction_src = "image" if bool(item.get("agent_used_tool")) else "content"
        sqlite_service.update_task_status(
            task_id,
            "done",
            questions_count=len(questions),
            extraction_source=extraction_src,
            agent_used_tool=bool(item.get("agent_used_tool")),
            trace_session_id=item.get("trace_session_id") or None,
        )

        # 保存两阶段日志
        _save_two_stage_log(content, stage1_output, merged, model_used)

        logger.info("[Stage2Processor] 完成 task_id=%s 题目数=%d", task_id, len(questions))
        try:
            sqlite_service.mark_stage2_pending_done(task_id)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("[Stage2Processor] 处理失败 task_id=%s: %s", item.get("task_id"), e)
        # 降级：标记 error
        try:
            sqlite_service.update_task_status(
                item["task_id"],
                "error",
                error_msg=f"Stage2 处理失败: {str(e)[:200]}",
            )
            try:
                sqlite_service.mark_stage2_pending_error(item["task_id"], str(e)[:400])
            except Exception:
                pass
        except Exception:
            pass
        return False


def _is_retryable_api_error(e: Exception) -> bool:
    """429/503 等可重试的 API 错误，应切换备用模型"""
    msg = str(e).lower()
    return "429" in msg or "503" in msg or "setlimit" in msg or "toomanyrequests" in msg


def _execute_stage2_on_leased_items(items: List[Dict]) -> None:
    """
    对已 lease 的一批 stage2_pending 项调用豆包并写库。
    不负责 lease / _stage2_running；结束时打印本轮 success/fail 与剩余队列长度。
    """
    use_batch = settings.miner_stage2_use_batch
    models = settings.miner_stage2_models
    if not models or not items:
        return

    logger.info(
        "[Stage2Processor] 开始处理 %d 条，use_batch=%s，模型链=%s",
        len(items),
        use_batch,
        [m["model"] for m in models],
    )
    success_count = 0
    fail_count = 0
    temperature = settings.miner_stage2_temperature
    max_tokens = settings.miner_stage2_max_tokens
    timeout = settings.miner_stage2_timeout
    last_error = None

    try:
        for model_idx, cfg in enumerate(models):
            model_name = cfg["model"]
            api_key = cfg["api_key"]
            base_url = cfg["base_url"]
            try:
                if use_batch and len(items) > 1:
                    user_contents = [it["enrich_input"] for it in items]
                    _t_batch = time.perf_counter()
                    results = call_batch(
                        model=model_name,
                        api_key=api_key,
                        base_url=base_url,
                        system_prompt=ENRICH_SYSTEM_PROMPT,
                        user_contents=user_contents,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    )
                    batch_ms = (time.perf_counter() - _t_batch) * 1000.0
                    n_items = len(items)
                    per_item_ms = (batch_ms / n_items) if n_items else 0.0
                    for i, item in enumerate(items):
                        enrich_result = results[i] if i < len(results) else ""
                        if enrich_result:
                            enrich_result = (enrich_result or "").strip()
                            enrich_result = re.sub(r"<think>[\s\S]*?</think>", "", enrich_result, flags=re.IGNORECASE)
                            enrich_result = enrich_result.strip()
                        enrich_result = _extract_json_from_stage2(enrich_result or "")
                        logger.info("[Stage2Processor] 处理中 %d/%d task_id=%s model=%s", i + 1, len(items), item.get("task_id"), model_name)
                        ok = _process_single_item(item, enrich_result or "[]", model_name)
                        _record_stage2_tool_call(ok, per_item_ms)
                        if ok:
                            success_count += 1
                        else:
                            fail_count += 1
                    last_error = None
                    break
                else:
                    # 单条 API：每条 item 独立尝试模型链，某条 429 时只对该条切换备用
                    for i, item in enumerate(items):
                        enrich_input = item.get("enrich_input") or ""
                        item_ok = False
                        item_err = None
                        for m_cfg in models:
                            m_name = m_cfg["model"]
                            m_key = m_cfg["api_key"]
                            m_url = m_cfg["base_url"]
                            logger.info("[Stage2Processor] 处理中 %d/%d task_id=%s model=%s", i + 1, len(items), item.get("task_id"), m_name)
                            try:
                                _t_single = time.perf_counter()
                                enrich_result = call_single(
                                    model=m_name,
                                    api_key=m_key,
                                    base_url=m_url,
                                    system_prompt=ENRICH_SYSTEM_PROMPT,
                                    user_content=enrich_input,
                                    temperature=temperature,
                                    max_tokens=max_tokens,
                                    timeout=timeout,
                                )
                                api_ms = (time.perf_counter() - _t_single) * 1000.0
                                enrich_result = (enrich_result or "").strip()
                                enrich_result = re.sub(r"<think>[\s\S]*?</think>", "", enrich_result, flags=re.IGNORECASE)
                                enrich_result = _extract_json_from_stage2(enrich_result or "")
                                if _process_single_item(item, enrich_result or "[]", m_name):
                                    success_count += 1
                                    item_ok = True
                                    _record_stage2_tool_call(True, api_ms)
                                else:
                                    fail_count += 1
                                    _record_stage2_tool_call(False, api_ms)
                                break
                            except Exception as e:
                                item_err = e
                                if _is_retryable_api_error(e) and models.index(m_cfg) + 1 < len(models):
                                    logger.warning("[Stage2Processor] task_id=%s model=%s 失败: %s，尝试备用", item.get("task_id"), m_name, str(e)[:100])
                                else:
                                    logger.error("[Stage2Processor] task_id=%s 所有模型失败: %s", item.get("task_id"), e)
                                    break
                        if not item_ok and item_err:
                            fail_count += 1
                            _record_stage2_tool_call(False, 0.0)
                            try:
                                sqlite_service.update_task_status(item["task_id"], "error", error_msg=f"Stage2 失败: {str(item_err)[:200]}")
                                sqlite_service.mark_stage2_pending_error(item["task_id"], str(item_err)[:400])
                            except Exception:
                                pass
                    last_error = None
                    break
            except Exception as e:
                last_error = e
                if _is_retryable_api_error(e) and model_idx + 1 < len(models):
                    logger.warning("[Stage2Processor] 模型 %s 失败(可重试): %s，切换备用模型", model_name, str(e)[:150])
                else:
                    logger.error("[Stage2Processor] 模型 %s 失败: %s", model_name, e)
                    break

        if last_error is not None:
            logger.error("[Stage2Processor] 所有模型均已失败，将任务标记为 error")
            for item in items:
                _record_stage2_tool_call(False, 0.0)
                try:
                    sqlite_service.update_task_status(
                        item["task_id"],
                        "error",
                        error_msg=f"Stage2 批量失败: {str(last_error)[:200]}",
                    )
                    try:
                        sqlite_service.mark_stage2_pending_error(item["task_id"], f"Stage2 批量失败: {str(last_error)[:200]}")
                    except Exception:
                        pass
                except Exception:
                    pass
    finally:
        try:
            remain = sqlite_service.get_stage2_pending_count()
        except Exception:
            remain = -1
        if remain >= 0:
            logger.info(
                "[Stage2Processor] 本轮完成 success=%d fail=%d，剩余待处理=%d",
                success_count,
                fail_count,
                remain,
            )
        else:
            logger.info(
                "[Stage2Processor] 本轮完成 success=%d fail=%d",
                success_count,
                fail_count,
            )


def run_stage2_retry_for_task_ids(task_ids: List[str]) -> None:
    """
    仅处理给定 task_id 在 stage2_pending 中的条目，循环 lease + 豆包直到这些 id 无 pending。
    供子进程「Stage2 未完成补跑」调用；不跑 Stage1 / Rough Extractor。
    """
    if not task_ids:
        return
    if not settings.miner_stage2_models:
        logger.warning("[Stage2Processor] 未配置 Stage2 模型，跳过补跑")
        return
    ids = list(dict.fromkeys([t for t in task_ids if t]))
    sqlite_service.recover_stale_stage2_pending(settings.miner_stage2_recovery_stale_seconds)
    batch_size = settings.miner_stage2_batch_size
    worker_base = f"stage2-retry-{uuid.uuid4().hex[:8]}"
    batch_num = 0
    while True:
        worker_id = f"{worker_base}-b{batch_num}"
        items = sqlite_service.lease_stage2_pending_batch_for_task_ids(
            batch_size, worker_id, ids
        )
        if not items:
            break
        _execute_stage2_on_leased_items(items)
        batch_num += 1
    logger.info("[Stage2Processor] 指定 task 的 Stage2 补跑已结束（批次=%d）", batch_num)


def _run_stage2_processor_impl():
    """实际执行 Stage2 批量处理，主模型失败时按序尝试备用模型"""
    global _stage2_running
    batch_size = settings.miner_stage2_batch_size
    models = settings.miner_stage2_models
    if not models:
        logger.warning("[Stage2Processor] 未配置 Stage2 模型，跳过")
        _stage2_running = False
        return

    # 先做一次陈旧 in_progress 回收，避免队列永远卡死
    sqlite_service.recover_stale_stage2_pending(settings.miner_stage2_recovery_stale_seconds)
    worker_id = f"stage2-{uuid.uuid4().hex[:8]}"
    items = sqlite_service.lease_stage2_pending_batch(batch_size, worker_id=worker_id)
    if not items:
        _stage2_running = False
        return

    try:
        _execute_stage2_on_leased_items(items)
    finally:
        _stage2_running = False


def trigger_stage2_if_ready():
    """
    检查队列是否达到 batch_size，达到则触发 Stage2 处理器（后台线程）。
    由 Stage1 入队后调用，无轮询。
    """
    global _stage2_running
    if _stage2_running:
        return
    # 启动消费前回收陈旧项，避免刚重启/崩溃后长期不处理
    sqlite_service.recover_stale_stage2_pending(settings.miner_stage2_recovery_stale_seconds)
    count = sqlite_service.get_stage2_pending_count()
    batch_size = settings.miner_stage2_batch_size
    if count < batch_size:
        return
    with _stage2_lock:
        if _stage2_running:
            return
        _stage2_running = True
    run_mode = getattr(settings, "miner_stage2_run_mode", "process")
    if run_mode == "process":
        cmd = [sys.executable, "-m", "backend.services.scheduling.stage2_worker"]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(
            cmd,
            cwd=str(settings.backend_data_dir.parent.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
            **kwargs,
        )
        logger.info("[Stage2Processor] 队列 %d >= %d，已触发子进程处理", count, batch_size)
        _stage2_running = False
        return

    t = threading.Thread(target=_run_stage2_processor_impl, daemon=True)
    t.start()
    logger.info("[Stage2Processor] 队列 %d >= %d，已触发后台线程处理", count, batch_size)


def run_stage2_processor_now(batch_size: int = None):
    """
    立即执行 Stage2 处理器（同步，用于手动触发或定时补漏）。
    batch_size 不传时用配置值。
    """
    global _stage2_running
    with _stage2_lock:
        if _stage2_running:
            logger.info("[Stage2Processor] 已有处理任务运行中，跳过")
            return
        _stage2_running = True
    try:
        if batch_size is not None:
            orig = settings.miner_stage2_batch_size
            # 临时覆盖（通过 env 无法动态改，这里直接传 limit 给 pop）
            # 需要修改 pop 逻辑支持传入 limit
            pass
        _run_stage2_processor_impl()
    finally:
        _stage2_running = False
