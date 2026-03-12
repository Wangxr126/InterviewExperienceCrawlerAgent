from __future__ import annotations
import json, logging, random, requests
from typing import Any, List, Dict, Optional
from hello_agents.tools import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse
from backend.agents.context import get_current_user_id, get_current_session_id
from backend.config.config import settings
from backend.services.storage.sqlite_service import sqlite_service
from backend.services.storage.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)


def _call_llm(prompt: str, system: str = "", temperature: float = 0.3,
              json_mode: bool = False, max_tokens: int = 1000) -> str:
    try:
        headers = {"Authorization": f"Bearer {settings.llm_api_key}",
                   "Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {"model": settings.llm_model_id,
                                    "messages": messages,
                                    "temperature": temperature,
                                    "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = requests.post(f"{settings.llm_base_url}/chat/completions",
                             headers=headers, json=payload,
                             timeout=settings.llm_timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning("_call_llm failed: %s", e)
        return ""


def _get_seen_question_ids(user_id: str, limit: int = 100) -> List[str]:
    history = sqlite_service.get_study_history(user_id, limit=limit)
    return [str(r["question_id"]) for r in history if r.get("question_id")]


class RecallMemoryTool(Tool):
    def __init__(self):
        super().__init__(
            name="recall_memory",
            description=(
                "召回当前用户的背景信息：技术栈、目标公司、薄弱标签、最近做题情况。"
                "在以下场景必须首先调用："
                "① 对话开始/用户第一条消息；"
                "② 话题切换时；"
                "③ 推荐题目前，需了解用户薄弱点。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return []

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        user_id = get_current_user_id()
        try:
            profile = sqlite_service.get_user_profile(user_id) or {}
            weak_tags = sqlite_service.get_weak_tags(user_id)
            history = sqlite_service.get_study_history(user_id, limit=5)
            recent = [
                {"question_id": r["question_id"],
                 "question_text": (r.get("question_text") or "")[:80],
                 "score": r["score"],
                 "studied_at": r.get("studied_at", "")}
                for r in history
            ]
            memory = {
                "user_id": user_id,
                "tech_stack": profile.get("tech_stack", []),
                "target_company": profile.get("target_company", ""),
                "target_position": profile.get("target_position", ""),
                "experience_level": profile.get("experience_level", "junior"),
                "preferred_topics": profile.get("preferred_topics", []),
                "weak_tags": [{"tag": t["tag"],
                               "mastery_level": t["mastery_level"],
                               "avg_score": round(t["avg_score"], 2)}
                              for t in weak_tags[:8]],
                "recent_questions": recent,
                "has_resume": bool((profile.get("resume_text") or "").strip()),
            }
            return ToolResponse.success(
                text=json.dumps(memory, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("recall_memory failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"recall_memory failed: {e}")

class GetRecommendedQuestionTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_recommended_question",
            description=(
                "为用户推荐一道面试题。推荐策略（按优先级）："
                "① 遗忘曲线到期的复习题；"
                "② 用户薄弱标签（novice/learning）的新题；"
                "③ 按 topic 随机一道未做过的题。"
                "用户说'出一道题'/'来一题'/'考我XX'/'练习XX'时调用。"
                "topic 参数指定知识点；difficulty 过滤难度。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("topic", "string",
                          "指定知识点/标签，如 Redis、JVM、TCP，留空则自动选薄弱点",
                          required=False),
            ToolParameter("difficulty", "string",
                          "难度过滤：easy / medium / hard，留空不限",
                          required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        topic = (parameters.get("topic") or "").strip()
        difficulty = (parameters.get("difficulty") or "").strip().lower()
        seen_ids = _get_seen_question_ids(user_id)
        try:
            question = None

            # 策略1: 遗忘曲线到期
            if not topic:
                due = sqlite_service.get_due_reviews(user_id, limit=3)
                if due:
                    c = random.choice(due)
                    tags_raw = c.get("topic_tags")
                    question = {
                        "q_id": str(c["question_id"]),
                        "question_text": c.get("question_text") or "",
                        "answer_text": c.get("answer_text") or "",
                        "difficulty": c.get("difficulty", "medium"),
                        "topic_tags": (json.loads(tags_raw)
                                       if isinstance(tags_raw, str)
                                       else (tags_raw or [])),
                        "company": c.get("company", ""),
                        "_source": "due_review",
                    }

            # 策略2: 薄弱标签/指定topic -> Neo4j
            if not question:
                tags_to_use = ([topic] if topic else
                               [t["tag"] for t in
                                sqlite_service.get_weak_tags(user_id)[:3]])
                if tags_to_use:
                    rows = neo4j_service.get_questions_by_tags(
                        tags_to_use, limit=10, exclude_ids=seen_ids)
                    if rows:
                        hit = random.choice(rows)
                        sq = sqlite_service.filter_questions(
                            keyword=hit["text"][:30], limit=1)
                        if sq:
                            r = sq[0]
                            question = {
                                "q_id": str(r["q_id"]),
                                "question_text": r["question_text"],
                                "answer_text": r.get("answer_text") or "",
                                "difficulty": r.get("difficulty", "medium"),
                                "topic_tags": json.loads(
                                    r.get("topic_tags") or "[]"),
                                "company": r.get("company", ""),
                                "_source": "neo4j_tag",
                            }
                        else:
                            question = {
                                "q_id": hit["id"],
                                "question_text": hit["text"],
                                "answer_text": hit.get("answer") or "",
                                "difficulty": hit.get("difficulty", "medium"),
                                "topic_tags": tags_to_use,
                                "company": hit.get("company", ""),
                                "_source": "neo4j_tag",
                            }

            # 策略3: SQLite 兜底
            if not question:
                kw: Dict[str, Any] = {"limit": 20, "sort_by": "created_at",
                                      "sort_order": "desc"}
                if topic:
                    kw["tags"] = [topic]
                if difficulty:
                    kw["difficulty"] = difficulty
                rows = sqlite_service.filter_questions(**kw)
                unseen = [r for r in rows
                          if str(r["q_id"]) not in seen_ids]
                pool = unseen or rows
                if pool:
                    r = random.choice(pool)
                    question = {
                        "q_id": str(r["q_id"]),
                        "question_text": r["question_text"],
                        "answer_text": r.get("answer_text") or "",
                        "difficulty": r.get("difficulty", "medium"),
                        "topic_tags": json.loads(
                            r.get("topic_tags") or "[]"),
                        "company": r.get("company", ""),
                        "_source": "sqlite_fallback",
                    }

            if not question:
                return ToolResponse.error(code="EXECUTION_ERROR", message="题库暂无符合条件的题目，请先抓取面经数据或调整筛选条件。")
            return ToolResponse.success(
                text=json.dumps(question, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("get_recommended_question failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"get_recommended_question failed: {e}")


class FindSimilarQuestionsTool(Tool):
    def __init__(self):
        super().__init__(
            name="find_similar_questions",
            description=(
                "找与题目相似/换个问法的题目，或按题目描述搜索。"
                "① 用户说'换一道'/'换个问法'/'类似的题'→ 传入 question_text（从对话历史提取上一道题）+ exclude_id；"
                "② 用户说'我想练习这道题：XXX'/'找跨域相关的题'→ 传入 question_text=XXX（题目描述/关键词），无需 exclude_id。"
                "优先 Neo4j 变体关系；无 exclude_id 时按 keyword 直接搜索 SQLite。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("question_text", "string",
                          "题目原文或描述/关键词，用于相似检索或按描述搜索", required=True),
            ToolParameter("exclude_id", "string",
                          "要排除的题目 ID（换个问法时用，按描述搜题时留空）", required=False),
            ToolParameter("limit", "integer",
                          "返回数量，默认3，最多5", required=False),
        ]

    def run(self, parameters):
        question_text = (parameters.get("question_text") or "").strip()
        exclude_id = (parameters.get("exclude_id") or "").strip()
        limit = min(int(parameters.get("limit") or 3), 5)
        if not question_text:
            return ToolResponse.error(code="INVALID_PARAM", message="question_text 不能为空")
        try:
            results = []
            exclude_ids = [exclude_id] if exclude_id else []

            # 场景1：有 exclude_id → 找相似/变体题（换个问法）
            if exclude_id and neo4j_service.available:
                results = neo4j_service.get_variants(exclude_id)

            # 场景2：无 exclude_id 或 Neo4j 无结果 → 按 question_text 作为 keyword 搜索
            # 用户说「我想练习这道题：跨域的概念...」时，直接用 keyword 搜题
            if not results:
                # 用题目描述/关键词搜索（支持「按描述练习」场景）
                sq = sqlite_service.filter_questions(
                    keyword=question_text[:80] if len(question_text) > 20 else question_text,
                    limit=limit + len(exclude_ids),
                )
                results = [
                    {"q_id": str(r["q_id"]),
                     "question_text": r["question_text"],
                     "difficulty": r.get("difficulty", "medium"),
                     "topic_tags": json.loads(r.get("topic_tags") or "[]"),
                     "company": r.get("company", "")}
                    for r in sq
                    if str(r["q_id"]) not in exclude_ids
                ][:limit]

            # 场景3：有 exclude_id 且 Neo4j 无结果 → 按相同标签兜底
            if not results and exclude_id:
                tags = []
                sq = sqlite_service.filter_questions(
                    keyword=question_text[:30], limit=1)
                if sq:
                    tags = json.loads(sq[0].get("topic_tags") or "[]")
                if tags:
                    sim = sqlite_service.filter_questions(
                        tags=tags[:2], limit=limit + 1)
                    results = [
                        {"q_id": str(r["q_id"]),
                         "question_text": r["question_text"],
                         "difficulty": r.get("difficulty", "medium"),
                         "topic_tags": json.loads(r.get("topic_tags") or "[]"),
                         "company": r.get("company", "")}
                        for r in sim
                        if str(r["q_id"]) not in exclude_ids
                    ][:limit]

            if not results:
                return ToolResponse.error(
                    code="INVALID_PARAM",
                    message="未找到匹配题目。若题库暂无该知识点，可尝试更通用的关键词（如「跨域」而非完整描述）。"
                )
            return ToolResponse.success(
                text=json.dumps(results, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("find_similar_questions failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"find_similar_questions failed: {e}")

class FilterQuestionsTool(Tool):
    def __init__(self):
        super().__init__(
            name="filter_questions",
            description=(
                "按条件筛选题目列表（纯 SQL，不需要 LLM）。"
                "用户说'列出XX公司的题'/'给我看难度为XX的题'/'按标签筛选'时调用。"
                "支持：company、tags、difficulty、question_type、keyword、limit。"
                "返回题目列表（不含标准答案），供用户浏览选择。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("company", "string",
                          "公司名称，如 字节跳动、阿里巴巴", required=False),
            ToolParameter("tags", "array",
                          "标签列表，如 [\"Redis\", \"MySQL\"]",
                          required=False),
            ToolParameter("difficulty", "string",
                          "难度：easy / medium / hard", required=False),
            ToolParameter("question_type", "string",
                          "题型：技术题 / 算法题 / 行为题", required=False),
            ToolParameter("keyword", "string",
                          "关键词搜索题目文本", required=False),
            ToolParameter("limit", "integer",
                          "返回数量，默认10，最多30", required=False),
        ]

    def run(self, parameters):
        try:
            limit = min(int(parameters.get("limit") or 10), 30)
            tags = parameters.get("tags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [tags]
            rows = sqlite_service.filter_questions(
                company=parameters.get("company") or None,
                tags=tags or None,
                difficulty=parameters.get("difficulty") or None,
                question_type=parameters.get("question_type") or None,
                keyword=parameters.get("keyword") or None,
                limit=limit,
            )
            result = [
                {
                    "q_id": str(r["q_id"]),
                    "question_text": r["question_text"],
                    "difficulty": r.get("difficulty", "medium"),
                    "topic_tags": json.loads(r.get("topic_tags") or "[]"),
                    "company": r.get("company", ""),
                    "source_platform": r.get("source_platform", ""),
                }
                for r in rows
            ]
            total = sqlite_service.count_questions(
                company=parameters.get("company") or None,
                tags=tags or None,
                difficulty=parameters.get("difficulty") or None,
                question_type=parameters.get("question_type") or None,
                keyword=parameters.get("keyword") or None,
            )
            return ToolResponse.success(text=json.dumps(
                {"total": total, "returned": len(result), "questions": result},
                ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("filter_questions failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"filter_questions failed: {e}")


class SubmitAnswerTool(Tool):
    def __init__(self):
        super().__init__(
            name="submit_answer",
            description=(
                "用户提交答案后调用：① 用 LLM 对答案评分（0-5分）并生成反馈；"
                "② 将得分写入 study_records（触发 SM-2 遗忘曲线更新）；"
                "③ 更新该题相关标签的掌握度。"
                "必须传入 question_id（题目ID）和 user_answer（用户答案）；"
                "可选 question_text/answer_text 用于评分时提供上下文；"
                "可选 session_id 关联当前会话。"
                "在用户说'我的答案是...'或直接作答后调用。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("question_id", "string",
                          "题目ID（q_id）", required=True),
            ToolParameter("user_answer", "string",
                          "用户提交的答案文本", required=True),
            ToolParameter("question_text", "string",
                          "题目原文（提供给评分 LLM 作为上下文）", required=False),
            ToolParameter("answer_text", "string",
                          "参考答案（提供给评分 LLM 作为评分依据）", required=False),
            ToolParameter("session_id", "string",
                          "当前会话 ID，用于统计本次面试得分", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        question_id = (parameters.get("question_id") or "").strip()
        user_answer = (parameters.get("user_answer") or "").strip()
        question_text = (parameters.get("question_text") or "").strip()
        answer_text = (parameters.get("answer_text") or "").strip()
        session_id = (parameters.get("session_id") or "").strip()

        if not question_id or not user_answer:
            return ToolResponse.error(code="INVALID_PARAM", message="question_id 和 user_answer 不能为空")

        try:
            # 若未提供题目文本，从 SQLite 补全
            if not question_text:
                rows = sqlite_service.filter_questions(
                    keyword=question_id, limit=1)
                # 尝试按 q_id 精确查
                with sqlite_service._get_conn() as conn:
                    row = conn.execute(
                        "SELECT question_text, answer_text FROM questions WHERE q_id = ?",
                        (question_id,)
                    ).fetchone()
                    if row:
                        question_text = row["question_text"] or ""
                        answer_text = answer_text or row["answer_text"] or ""

            # LLM 评分
            ref_ans = answer_text[:500] if answer_text else "（无）"
            score_prompt = (
                f"题目：{question_text}\n"
                f"参考答案：{ref_ans}\n"
                f"用户答案：{user_answer}\n\n"
                "请对用户答案打分（0-5分整数）并给出简短反馈。"
                '仅返回 JSON 格式：{\"score\": <int>, \"feedback\": \"<str>\"}\n'
                "评分标准：0=完全错误，1=方向对但内容严重缺失，"
                "2=基本思路对但细节错误，3=答案正确但不完整，"
                "4=答案完整，5=超出预期（有深度补充）。"
            )
            raw = _call_llm(score_prompt, json_mode=True, max_tokens=300)
            try:
                parsed = json.loads(raw)
                score = max(0, min(5, int(parsed.get("score", 2))))
                feedback = parsed.get("feedback", "")
            except Exception:
                score = 2
                feedback = raw[:200] if raw else "评分解析失败"

            # 写入学习记录（SM-2 自动更新）
            sm2 = sqlite_service.add_study_record(
                user_id=user_id,
                question_id=question_id,
                score=score,
                user_answer=user_answer,
                ai_feedback=feedback,
                session_id=session_id,
            )

            result = {
                "score": score,
                "feedback": feedback,
                "sm2": sm2,
                "message": (
                    f"得分 {score}/5。"
                    + ("下次复习：" + sm2["next_review_at"]
                       if sm2 else "")
                ),
            }
            return ToolResponse.success(
                text=json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("submit_answer failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"submit_answer failed: {e}")

class ManageNoteTool(Tool):
    def __init__(self):
        super().__init__(
            name="manage_note",
            description=(
                "用户笔记的 CRUD 操作。"
                "action=create：新建笔记（需 content，可选 title/tags/question_id）；"
                "action=list：列出笔记（可按 tags/keyword/question_id 过滤）；"
                "action=update：修改笔记（需 note_id，可改 content/title/tags）；"
                "action=delete：删除笔记（需 note_id）。"
                "用户说'记一下'/'保存笔记'/'查看我的笔记'/'删除笔记'时调用。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("action", "string",
                          "操作类型：create / list / update / delete",
                          required=True),
            ToolParameter("content", "string",
                          "笔记正文（create/update 时使用）", required=False),
            ToolParameter("title", "string", "笔记标题", required=False),
            ToolParameter("tags", "array",
                          "标签列表", required=False),
            ToolParameter("question_id", "string",
                          "关联题目 ID", required=False),
            ToolParameter("note_id", "string",
                          "笔记 ID（update/delete 时必填）", required=False),
            ToolParameter("keyword", "string",
                          "关键词（list 时搜索标题和正文）", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        action = (parameters.get("action") or "").strip().lower()
        try:
            if action == "create":
                content = (parameters.get("content") or "").strip()
                if not content:
                    return ToolResponse.error(code="INVALID_PARAM", message="create 操作需要 content")
                tags = parameters.get("tags") or []
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = [tags]
                note_id = sqlite_service.create_note(
                    user_id=user_id,
                    content=content,
                    title=(parameters.get("title") or "").strip(),
                    question_id=parameters.get("question_id") or None,
                    tags=tags,
                )
                return ToolResponse.success(
                    text=json.dumps({"note_id": note_id,
                                     "message": "笔记已保存"},
                                    ensure_ascii=False))
            elif action == "list":
                tags = parameters.get("tags") or []
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = [tags]
                notes = sqlite_service.get_notes(
                    user_id=user_id,
                    tags=tags or None,
                    question_id=parameters.get("question_id") or None,
                    keyword=parameters.get("keyword") or None,
                    limit=20,
                )
                return ToolResponse.success(
                    text=json.dumps({"count": len(notes), "notes": notes},
                                    ensure_ascii=False, indent=2))
            elif action == "update":
                note_id = (parameters.get("note_id") or "").strip()
                if not note_id:
                    return ToolResponse.error(code="INVALID_PARAM", message="update 操作需要 note_id")
                tags = parameters.get("tags")
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = [tags]
                ok = sqlite_service.update_note(
                    note_id=note_id, user_id=user_id,
                    content=parameters.get("content") or None,
                    title=parameters.get("title") or None,
                    tags=tags,
                )
                return ToolResponse.success(
                    text=json.dumps({"success": ok,
                                     "message": "笔记已更新" if ok else "笔记未找到"},
                                    ensure_ascii=False))
            elif action == "delete":
                note_id = (parameters.get("note_id") or "").strip()
                if not note_id:
                    return ToolResponse.error(code="INVALID_PARAM", message="delete 操作需要 note_id")
                ok = sqlite_service.delete_note(note_id=note_id, user_id=user_id)
                return ToolResponse.success(
                    text=json.dumps({"success": ok,
                                     "message": "笔记已删除" if ok else "笔记未找到"},
                                    ensure_ascii=False))
            else:
                return ToolResponse.error(code="EXECUTION_ERROR", message=f"未知 action: {action}，支持 create/list/update/delete")
        except Exception as e:
            logger.exception("manage_note failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"manage_note failed: {e}")


class GetSessionContextTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_session_context",
            description=(
                "读取本次会话统计：已做题数、已练标签、会话进度。"
                "用户问「做了几道」「会话进度」「今天练了几题」时调用。"
            ),
        )

    def get_parameters(self) -> List[ToolParameter]:
        return []

    def run(self, parameters: Dict[str, Any]) -> ToolResponse:
        user_id = get_current_user_id()
        session_id = get_current_session_id()
        try:
            if not session_id:
                return ToolResponse.success(
                    text=json.dumps({"message": "当前无活跃会话", "total": 0, "records": []},
                                    ensure_ascii=False, indent=2))
            records = sqlite_service.get_study_history(user_id, limit=50)
            session_records = [r for r in records if r.get("session_id") == session_id]
            total = len(session_records)
            tags = []
            for r in session_records:
                t = r.get("topic_tags") or r.get("tags") or "[]"
                if isinstance(t, str):
                    try:
                        tags.extend(json.loads(t))
                    except Exception:
                        pass
                elif isinstance(t, list):
                    tags.extend(t)
            tags = list(dict.fromkeys(tags))[:10]
            avg = sum(r.get("score", 0) for r in session_records) / total if total else 0
            result = {
                "total_questions": total,
                "avg_score": round(avg, 1),
                "tags_practiced": tags,
                "message": f"本次会话已练习 {total} 道题，平均得分 {avg:.1f}/5" if total else "本次会话暂无答题记录",
            }
            return ToolResponse.success(
                text=json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("get_session_context failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"get_session_context failed: {e}")


class GetMasteryReportTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_mastery_report",
            description=(
                "生成用户当前的知识点掌握度报告。"
                "包含：各级别标签统计（expert/proficient/learning/novice）、"
                "整体正确率、总做题数、薄弱点列表。"
                "用户说'我的掌握情况'/'复习报告'/'哪些地方还不熟'时调用。"
            ),
        )

    def get_parameters(self):
        return []

    def run(self, parameters):
        user_id = get_current_user_id()
        try:
            summary = sqlite_service.get_mastery_summary(user_id)
            by_level = {}
            for level, items in summary["by_level"].items():
                by_level[level] = [
                    {"tag": i["tag"],
                     "avg_score": round(i["avg_score"], 2),
                     "total_attempts": i["total_attempts"]}
                    for i in items
                ]
            report = {
                "total_questions_practiced": summary["total_questions_practiced"],
                "overall_avg_score": summary["overall_avg_score"],
                "correct_rate_pct": summary["correct_rate"],
                "mastery_by_level": by_level,
                "weak_tags": [
                    i["tag"] for i in
                    (by_level.get("novice", [])
                     + by_level.get("learning", []))
                ][:10],
                "advice": (
                    "建议重点练习薄弱标签，每天坚持 3-5 道题。"
                    if summary["correct_rate"] < 70
                    else "整体掌握良好，继续保持！"
                ),
            }
            return ToolResponse.success(
                text=json.dumps(report, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("get_mastery_report failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"get_mastery_report failed: {e}")

class GetKnowledgeRecommendationTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_knowledge_recommendation",
            description=(
                "根据用户薄弱标签推荐学习资源（文章/视频/题集）。"
                "可选 tags 指定关注的知识点；留空则自动取薄弱标签。"
                "用户说'推荐资料'/'怎么学XX'/'给我推荐学习资源'时调用。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("tags", "array",
                          "指定标签列表，留空则取用户薄弱标签",
                          required=False),
            ToolParameter("limit", "integer",
                          "返回资源数量，默认5", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        try:
            tags = parameters.get("tags") or []
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [tags]
            limit = min(int(parameters.get("limit") or 5), 10)

            # 若未指定标签，取用户薄弱标签
            if not tags:
                weak = sqlite_service.get_weak_tags(user_id)
                tags = [t["tag"] for t in weak[:5]]

            resources = sqlite_service.get_resources_by_tags(tags, limit=limit)

            # 同时附上近期错题摘要（便于 Agent 提示用户复习）
            weak_records = sqlite_service.get_weak_study_records(
                user_id, tags=tags[:3], limit=3)

            result = {
                "tags_focused": tags,
                "resources": [
                    {"title": r["title"],
                     "url": r["url"],
                     "description": r["description"],
                     "tags": r["tags"],
                     "resource_type": r["resource_type"]}
                    for r in resources
                ],
                "recent_mistakes": [
                    {"question_text": rec.get("question_text", "")[:80],
                     "score": rec["score"],
                     "ai_feedback": (rec.get("ai_feedback") or "")[:120]}
                    for rec in weak_records
                ],
            }
            return ToolResponse.success(
                text=json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("get_knowledge_recommendation failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"get_knowledge_recommendation failed: {e}")


class AnalyzeResumeTool(Tool):
    def __init__(self):
        super().__init__(
            name="analyze_resume",
            description=(
                "分析用户简历文本，提取技术栈、目标岗位、经验级别，"
                "并更新到用户画像（user_profiles）中。"
                "用户粘贴简历/说'分析我的简历'时调用。"
                "必须传入 resume_text（简历原文）。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("resume_text", "string",
                          "用户简历全文", required=True),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        resume_text = (parameters.get("resume_text") or "").strip()
        if not resume_text:
            return ToolResponse.error(code="INVALID_PARAM", message="resume_text 不能为空")
        try:
            prompt = (
                f"请从以下简历中提取关键信息，仅返回 JSON：\n"
                f"{resume_text[:3000]}\n\n"
                "返回格式：\n"
                "{\n"
                '  \"tech_stack\": [\"技术1\", \"技术2\"],\n'
                '  \"target_position\": \"岗位名\",\n'
                '  \"target_company\": \"目标公司（可空）\",\n'
                '  \"experience_level\": \"junior|mid|senior\",\n'
                '  \"preferred_topics\": [\"知识点1\", \"知识点2\"]\n'
                "}"
            )
            raw = _call_llm(prompt, json_mode=True, max_tokens=500,
                            temperature=0.1)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {}

            tech_stack = parsed.get("tech_stack") or []
            target_position = parsed.get("target_position") or ""
            target_company = parsed.get("target_company") or ""
            experience_level = parsed.get("experience_level") or "junior"
            preferred_topics = parsed.get("preferred_topics") or []

            sqlite_service.upsert_user_profile(
                user_id=user_id,
                resume_text=resume_text,
                tech_stack=tech_stack,
                target_company=target_company,
                target_position=target_position,
                experience_level=experience_level,
                preferred_topics=preferred_topics,
            )

            result = {
                "message": "简历分析完成，用户画像已更新。",
                "tech_stack": tech_stack,
                "target_position": target_position,
                "target_company": target_company,
                "experience_level": experience_level,
                "preferred_topics": preferred_topics,
            }
            return ToolResponse.success(
                text=json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("analyze_resume failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"analyze_resume failed: {e}")



# ===========================================================================
# KnowledgeRecommender：供 Orchestrator 代码层直接调用（非 Tool 子类）
# ===========================================================================

class KnowledgeRecommender:
    """
    无状态知识推荐器，供 Orchestrator 代码层直接调用。
    不继承 Tool，run() 直接返回推荐文本字符串。
    """

    def run(self, parameters: Dict[str, Any]) -> str:
        """
        参数：
            user_id      : 用户ID
            tags         : 薄弱标签列表
            max_resources: 最多返回资源数，默认2
            max_mistakes : 最多返回错题数，默认3
        返回：推荐文本字符串（空字符串表示无推荐）
        """
        user_id = parameters.get("user_id") or ""
        tags = parameters.get("tags") or []
        max_resources = int(parameters.get("max_resources") or 2)
        max_mistakes = int(parameters.get("max_mistakes") or 3)

        if not tags:
            return ""
        try:
            resources = sqlite_service.get_resources_by_tags(tags, limit=max_resources)
            weak_records = (
                sqlite_service.get_weak_study_records(user_id, tags=tags[:3], limit=max_mistakes)
                if user_id else []
            )

            lines = []
            if resources:
                lines.append("📚 推荐学习资源：")
                for r in resources:
                    title = r.get("title", "")
                    url = r.get("url", "")
                    desc = (r.get("description") or "")[:60]
                    lines.append(
                        f"  • {title}" +
                        (f"：{desc}" if desc else "") +
                        (f" ({url})" if url else "")
                    )
            if weak_records:
                lines.append("\n🔁 近期错题回顾：")
                for rec in weak_records:
                    q = (rec.get("question_text") or "")[:60]
                    score = rec.get("score", 0)
                    lines.append(f"  • {q}... （得分 {score}/5）")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"KnowledgeRecommender.run failed: {e}")
            return ""

# ===========================================================================
# 工具列表：供 InterviewerAgent 初始化时注册
# ===========================================================================

def get_interviewer_tools() -> list:
    """返回 Interviewer Agent 所有工具实例列表。"""
    return [
        RecallMemoryTool(),
        GetSessionContextTool(),
        GetRecommendedQuestionTool(),
        FindSimilarQuestionsTool(),
        FilterQuestionsTool(),
        SubmitAnswerTool(),
        ManageNoteTool(),
        GetMasteryReportTool(),
        GetKnowledgeRecommendationTool(),
        AnalyzeResumeTool(),
    ]
