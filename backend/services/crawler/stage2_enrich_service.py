"""
对已入库题目仅执行 Stage2（豆包等）精加工，回写 SQLite（及 Neo4j 答案字段）。
供帖子记录「选中 → Stage2 更新」使用；不要求当前 MINER_MODE=two_stage。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from hello_agents import SimpleAgent
from hello_agents.core.llm import HelloAgentsLLM

from backend.agents.prompts.two_stage_prompts import ENRICH_SYSTEM_PROMPT, ENRICH_USER_PROMPT_TEMPLATE
from backend.agents.two_stage_miner_agent import TwoStageExtractor, _is_quota_or_rate_limit_error
from backend.config.config import settings, warn_if_stage2_shares_remote_fallback
from backend.services.finetune.stage_merge_utils import merge_stage2_with_stage1
from backend.services.storage import sqlite_service
from backend.services.storage.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)


def _append_two_stage_log(
    content: str,
    stage1_output: str,
    stage2_output: str,
    stage2_model_used: str,
    source_url: str,
    post_title: str,
) -> None:
    log_path = settings.miner_two_stage_log_path
    if not log_path:
        return
    try:
        from pathlib import Path
        from datetime import datetime

        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now().isoformat(),
            "content_preview": (content or "")[:2000],
            "title": post_title or "",
            "source_url": source_url or "",
            "stage1_output": stage1_output[:8000] if stage1_output else "",
            "stage2_output": stage2_output[:8000] if stage2_output else "",
            "stage1_model": "(manual_stage2_only)",
            "stage2_model": stage2_model_used,
            "source": "manual_stage2_batch",
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Stage2 微调日志写入失败: %s", e)


def _run_stage2_merge(stage1_json: str, enrich_input: str, source_url: str, post_title: str) -> Tuple[Optional[str], str]:
    """调用 Stage2 模型链，返回 (合并后 JSON 字符串, 使用的 model 名或错误说明)。"""
    warn_if_stage2_shares_remote_fallback()
    models = settings.miner_stage2_models
    if not models:
        return None, "未配置 Stage2：请设置 MINER_STAGE2_MODEL / API_KEY / BASE_URL（及可选 FALLBACK）"

    last_err: Exception | None = None
    last_model = ""
    for idx, cfg in enumerate(models):
        model_name = cfg["model"]
        last_model = model_name
        logger.info("[Stage2Only] 精加工 model=%s (%d/%d) title=%s", model_name, idx + 1, len(models), post_title[:60])
        try:
            enrich_llm = HelloAgentsLLM(
                model=cfg["model"],
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                temperature=settings.miner_stage2_temperature,
                timeout=int(cfg.get("timeout") or settings.miner_stage2_timeout),
                max_tokens=settings.miner_stage2_max_tokens,
            )
            enrich_agent = SimpleAgent(
                name="Enrich Extractor",
                llm=enrich_llm,
                system_prompt=ENRICH_SYSTEM_PROMPT,
            )
            logger.info(
                "[Stage2Only] >>> Agent 输入 model=%s\n[SYSTEM]\n%s\n[USER]\n%s",
                model_name,
                ENRICH_SYSTEM_PROMPT,
                enrich_input,
            )
            enrich_result = (enrich_agent.run(enrich_input) or "").strip()
            logger.info(
                "[Stage2Only] <<< Agent 输出 model=%s\n%s",
                model_name,
                enrich_result,
            )
            if not enrich_result:
                last_err = RuntimeError("empty stage2 output")
                continue
            enrich_result = TwoStageExtractor._strip_think_tags(enrich_result)
            enrich_result = TwoStageExtractor._extract_json_if_direct_reply(enrich_result)
            merged = merge_stage2_with_stage1(enrich_result, stage1_json)
            _append_two_stage_log(
                content="",
                stage1_output=stage1_json,
                stage2_output=merged,
                stage2_model_used=model_name,
                source_url=source_url,
                post_title=post_title,
            )
            return merged, model_name
        except Exception as e:
            last_err = e
            if _is_quota_or_rate_limit_error(e) and idx + 1 < len(models):
                logger.warning("[Stage2Only] 额度/限流，切换备用: %s", e)
                continue
            logger.error("[Stage2Only] model=%s 失败: %s", model_name, e)
            break
    return None, f"{last_model}: {last_err}" if last_err else last_model


def _rows_to_stage1_items(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从 questions 表行构造 merge 用 Stage1 列表。"""
    items: List[Dict[str, Any]] = []
    for r in rows:
        qt = (r.get("question_text") or "").strip()
        if not qt:
            continue
        raw_stored = (r.get("raw_answer") or "").strip()
        ans_stored = (r.get("answer_text") or "").strip()
        rough = raw_stored if raw_stored else ans_stored
        tags = r.get("topic_tags") or "[]"
        if isinstance(tags, str):
            try:
                tags_list = json.loads(tags)
            except Exception:
                tags_list = []
        else:
            tags_list = tags if isinstance(tags, list) else []
        items.append(
            {
                "q_id": (r.get("q_id") or "").strip(),
                "question_text": qt,
                "answer_text": rough,
                "raw_answer": rough,
                "difficulty": r.get("difficulty") or "medium",
                "question_type": r.get("question_type") or "技术题",
                "topic_tags": tags_list,
                "company": (r.get("company") or "")[:500],
                "position": (r.get("position") or "")[:500],
            }
        )
    return items


def enrich_task_stage2(task_id: str) -> Dict[str, Any]:
    """
    对单个 crawl_task 下已入库题目跑 Stage2，并 UPDATE questions + Neo4j 答案字段。
    """
    out: Dict[str, Any] = {"task_id": task_id, "ok": False, "updated": 0, "message": ""}
    with sqlite_service._get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM crawl_tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        out["message"] = "task_id 不存在"
        return out
    task = dict(row)
    url = (task.get("source_url") or "").strip()
    if not url:
        out["message"] = "无 source_url"
        return out
    if (task.get("questions_count") or 0) <= 0 and task.get("status") != "done":
        # 仍尝试按 URL 查题
        pass

    qrows = sqlite_service.get_questions_by_source_url(url)
    if not qrows:
        out["message"] = "该帖无已入库题目"
        return out

    valid = _rows_to_stage1_items(qrows)
    if not valid:
        out["message"] = "无有效题干"
        return out

    sqlite_service.ensure_raw_answer_backup_for_source_url(url)

    stage1_json = json.dumps(valid, ensure_ascii=False)
    questions_text = "\n".join(f"{i + 1}. {q.get('question_text', '')}" for i, q in enumerate(valid))
    enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)

    merged_str, meta = _run_stage2_merge(
        stage1_json,
        enrich_input,
        source_url=url,
        post_title=(task.get("post_title") or "")[:200],
    )
    if not merged_str:
        out["message"] = f"Stage2 失败: {meta}"
        return out

    try:
        merged_list = json.loads(merged_str)
    except json.JSONDecodeError as e:
        out["message"] = f"合并结果非合法 JSON: {e}"
        return out
    if not isinstance(merged_list, list):
        out["message"] = "合并结果不是数组"
        return out

    updated = 0
    for item in merged_list:
        if not isinstance(item, dict):
            continue
        qid = (item.get("q_id") or "").strip()
        if not qid:
            continue
        at = item.get("answer_text")
        answer_text = (at if isinstance(at, str) else str(at or "")).strip()
        ra = item.get("raw_answer")
        raw_answer = (ra if isinstance(ra, str) else str(ra or "")).strip()
        if sqlite_service.apply_stage2_to_question(q_id=qid, answer_text=answer_text, raw_answer=raw_answer):
            updated += 1
            if neo4j_service.available:
                try:
                    neo4j_service.update_question_answer_fields(
                        q_id=qid,
                        answer=answer_text,
                        raw_answer=raw_answer or answer_text,
                    )
                except Exception as ge:
                    logger.debug("Neo4j 更新答案跳过 q_id=%s: %s", qid, ge)

    out["ok"] = True
    out["updated"] = updated
    out["message"] = f"Stage2 完成（{meta}），已更新 {updated} 道题"

    # 更新 crawl_tasks.questions_count 为实际题数（Stage1 记录可能偏少）
    actual_count = len(qrows)
    try:
        with sqlite_service._get_conn() as _conn:
            _conn.execute(
                "UPDATE crawl_tasks SET questions_count = ? WHERE task_id = ?",
                (actual_count, task_id),
            )
            _conn.commit()
    except Exception as _ce:
        logger.debug("更新 questions_count 失败: %s", _ce)

    # 捕获本次 Stage2 的 trace session_id 并写入 crawl_tasks
    try:
        from backend.services.crawler.question_extractor import _get_latest_trace_session_id
        s2_trace = _get_latest_trace_session_id()
        if s2_trace:
            sqlite_service.update_task_stage2_trace_session_id(
                task_id=task_id,
                stage2_trace_session_id=s2_trace,
            )
    except Exception as _te:
        logger.debug("写入 stage2_trace_session_id 失败: %s", _te)

    return out
