"""
Stage2 未完成补跑：根据已有 questions + 正文写入 stage2_pending，供豆包精加工。
不调用 Rough Extractor / Stage1 ReAct。
"""
from __future__ import annotations

import json
import logging
from typing import List

from backend.agents.prompts.two_stage_prompts import ENRICH_USER_PROMPT_TEMPLATE
from backend.services.storage import sqlite_service

logger = logging.getLogger(__name__)


def _rows_to_valid_questions(rows: List[dict]) -> List[dict]:
    valid: List[dict] = []
    for r in rows:
        qt = (r.get("question_text") or "").strip()
        if not qt:
            continue
        tags = r.get("topic_tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags or "[]")
            except Exception:
                tags = []
        if not isinstance(tags, list):
            tags = []
        q = {
            "question_text": qt,
            "answer_text": r.get("answer_text") or "",
            "question_type": r.get("question_type") or "技术题",
            "difficulty": r.get("difficulty") or "medium",
            "topic_tags": tags,
            "company": r.get("company") or "",
            "position": r.get("position") or "",
        }
        ra = (r.get("raw_answer") or "").strip()
        q["raw_answer"] = ra if ra else q["answer_text"]
        valid.append(q)
    return valid


def ensure_stage2_pending_for_task_id(task_id: str) -> bool:
    """根据 crawl_tasks + questions 写入/刷新 stage2_pending，并视情况将任务标为 stage2_pending。"""
    with sqlite_service._get_conn() as conn:
        task = conn.execute("SELECT * FROM crawl_tasks WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        logger.warning("[Stage2Enqueue] task 不存在: %s", task_id)
        return False
    task = dict(task)
    source_url = task.get("source_url") or ""

    with sqlite_service._get_conn() as conn:
        qrows = conn.execute(
            """
            SELECT * FROM questions
            WHERE source_url=?
            ORDER BY created_at ASC, q_id ASC
            """,
            (source_url,),
        ).fetchall()
    rows = [dict(x) for x in qrows]
    valid_questions = _rows_to_valid_questions(rows)
    if not valid_questions:
        logger.warning("[Stage2Enqueue] 无题目可精加工 task_id=%s", task_id)
        return False

    questions_text = "\n".join(
        f"{i + 1}. {q.get('question_text', '')}" for i, q in enumerate(valid_questions)
    )
    enrich_input = ENRICH_USER_PROMPT_TEMPLATE.format(questions_text=questions_text)
    stage1_json = json.dumps(valid_questions, ensure_ascii=False)

    raw_content = task.get("raw_content") or ""
    image_paths_raw = task.get("image_paths") or "[]"
    try:
        imgs = json.loads(image_paths_raw) if isinstance(image_paths_raw, str) else image_paths_raw or []
    except Exception:
        imgs = []
    ocr_called = 1 if imgs else 0
    agent_used_tool = 1 if any((r.get("extraction_source") == "image") for r in rows) else 0

    sqlite_service.add_stage2_pending(
        task_id=task_id,
        content=raw_content,
        stage1_output=stage1_json,
        rough_questions=stage1_json,
        enrich_input=enrich_input,
        company=task.get("company") or "",
        position=task.get("position") or "",
        source_url=source_url,
        post_title=(task.get("post_title") or "").strip(),
        trace_session_id=(task.get("trace_session_id") or "") or "",
        agent_used_tool=agent_used_tool,
        ocr_called=ocr_called,
    )

    st = str(task.get("status") or "")
    if st in ("done", "stage2_unfinished"):
        sqlite_service.update_task_status(
            task_id,
            "stage2_pending",
            questions_count=len(valid_questions),
            error_msg="",
        )
    return True


def ensure_stage2_pending_for_task_ids(task_ids: List[str]) -> int:
    """对 task_id 列表去重后依次入队，返回成功入队条数。"""
    n = 0
    for tid in dict.fromkeys([t for t in task_ids if t and str(t).strip()]):
        if ensure_stage2_pending_for_task_id(str(tid).strip()):
            n += 1
    return n
