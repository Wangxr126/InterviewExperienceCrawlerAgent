from __future__ import annotations
import json, logging, re, random, requests
from typing import Any, List, Dict, Optional
from hello_agents.tools import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse
from backend.agents.context import get_current_user_id, get_current_session_id
from backend.config.config import settings
from backend.services.storage.sqlite_service import sqlite_service
from backend.services.storage.neo4j_service import neo4j_service
from backend.services.rerank_service import rerank_candidates
from backend.services.multi_recall_recommender import multi_recall_recommender

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


class GetRecommendedQuestionTool(Tool):
    def __init__(self):
        super().__init__(
            name="get_recommended_question",
            description=(
                "从题库推荐一道面试题。推荐策略：① 遗忘曲线到期复习题；② 薄弱标签新题；③ 按 topic/company 随机未做过题。"
                "支持填槽：topic（知识点）、difficulty（难度）、company（公司真题，如「字节的题」）。"
                "调用时机：① 用户主动要新题（「出一道题」「来一题」「字节的MySQL题」）；② 评分完成后用户说「下一题」。"
                "若用户说「某公司的题」但未指定公司，需先询问「请问您想练哪家公司的题？」完成填槽。"
                "**严禁**在「我想练习这道题：XXX」场景调用——用户已指定题目，直接按出题格式输出即可，不查库、不推荐。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("topic", "string",
                          "知识点/标签填槽，如 Redis、JVM、TCP，留空则自动选薄弱点", required=False),
            ToolParameter("company", "string",
                          "公司填槽，如 字节跳动、阿里巴巴、腾讯，限定公司真题", required=False),
            ToolParameter("difficulty", "string",
                          "难度填槽：easy / medium / hard，留空不限", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        topic = (parameters.get("topic") or "").strip()
        company = (parameters.get("company") or "").strip()
        difficulty = (parameters.get("difficulty") or "").strip().lower()
        seen_ids = set(_get_seen_question_ids(user_id))
        
        try:
            # 使用多路召回推荐器
            questions = multi_recall_recommender.recommend(
                user_id=user_id,
                query=topic or company or None,  # 用 topic/company 作为 query
                company=company or None,
                difficulty=difficulty or None,
                tags=[topic] if topic else None,
                top_n=1,  # 只返回 1 道题
                exclude_ids=seen_ids,
            )
            
            if not questions:
                return ToolResponse.error(
                    code="EXECUTION_ERROR",
                    message="题库暂无符合条件的题目，请先抓取面经数据或调整筛选条件。"
                )
            
            question = questions[0]
            return ToolResponse.success(
                text=json.dumps(question, ensure_ascii=False, indent=2)
            )
            
        except Exception as e:
            logger.exception("get_recommended_question failed")
            return ToolResponse.error(
                code="EXECUTION_ERROR",
                message=f"get_recommended_question failed: {e}"
            )


class FindSimilarQuestionsTool(Tool):
    """② 换个问法/出几道类似题：RAG 相似题，排除自身 top n"""
    def __init__(self):
        super().__init__(
            name="find_similar_questions",
            description=(
                "【② 换个问法/类似题】从 RAG 向量检索与当前题目语义相似的题目，排除自身，返回 top n。"
                "功能：基于题目文本做向量相似检索，排除 exclude_id 指定的当前题，返回最相似的 limit 道。"
                "支持填槽：company（同公司类似题，如「字节的类似题」）、difficulty（难度过滤）。"
                "调用时机：用户说「换个问法」「同公司的类似题」「出几道类似的」且对话中有上一题【q_id:xxx】时。"
                "若用户说「同公司的」但未指定公司，需先询问「请问您想找哪家公司的类似题？」完成填槽。"
                "**严禁**在「我想练习这道题：XXX」场景调用——用户已指定题目，直接格式化输出即可，不检索。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("question_text", "string",
                          "题目原文或描述/关键词，用于相似检索", required=True),
            ToolParameter("exclude_id", "string",
                          "要排除的题目 ID（换个问法时用，从【q_id:xxx】提取）", required=False),
            ToolParameter("company", "string",
                          "公司名称填槽：限定同公司类似题，如 字节跳动、阿里巴巴、腾讯", required=False),
            ToolParameter("difficulty", "string",
                          "难度填槽：easy / medium / hard，留空不限", required=False),
            ToolParameter("limit", "integer",
                          "返回数量，默认3，最多5", required=False),
        ]

    def run(self, parameters):
        question_text = (parameters.get("question_text") or "").strip()
        exclude_id = (parameters.get("exclude_id") or "").strip()
        company = (parameters.get("company") or "").strip()
        difficulty = (parameters.get("difficulty") or "").strip().lower()
        limit = min(int(parameters.get("limit") or 3), 5)
        if not question_text:
            return ToolResponse.error(code="INVALID_PARAM", message="question_text 不能为空")
        try:
            results = []
            exclude_ids = [exclude_id] if exclude_id else []

            # 场景0：优先向量语义检索（Neo4j 可用时），检索后重排
            if neo4j_service.available:
                try:
                    from backend.tools.knowledge_manager_tools import generate_embedding
                    emb = generate_embedding(question_text[:2048])
                    if emb:
                        search_top_k = settings.retrieval_search_top_k
                        score_threshold = settings.retrieval_score_threshold
                        vec_results = neo4j_service.search_similar(
                            emb, top_k=search_top_k + len(exclude_ids),
                            score_threshold=score_threshold, exclude_ids=exclude_ids
                        )
                        if vec_results:
                            # 重排：使用 Ollama Qwen3-Reranker
                            if settings.rerank_enabled and len(vec_results) > 1:
                                reranked = rerank_candidates(
                                    query=question_text[:2048],
                                    candidates=vec_results,
                                    text_key="text",
                                    top_n=limit,
                                )
                                for rec in reranked:
                                    results.append({
                                        "q_id": str(rec["id"]),
                                        "question_text": rec.get("text", ""),
                                        "difficulty": rec.get("difficulty", "medium"),
                                        "topic_tags": rec.get("tags", []) if isinstance(rec.get("tags"), list) else [],
                                        "company": rec.get("company", ""),
                                        "similarity_score": round(rec.get("rerank_score", rec.get("score", 0)), 3),
                                    })
                            else:
                                for rec in vec_results[:limit]:
                                    results.append({
                                        "q_id": str(rec["id"]),
                                        "question_text": rec.get("text", ""),
                                        "difficulty": rec.get("difficulty", "medium"),
                                        "topic_tags": rec.get("tags", []) if isinstance(rec.get("tags"), list) else [],
                                        "company": rec.get("company", ""),
                                        "similarity_score": round(rec.get("score", 0), 3),
                                    })
                            # 填槽过滤：company / difficulty（检索后再过滤）
                            if (company or difficulty) and results:
                                filtered = [
                                    r for r in results
                                    if (not company or company in (r.get("company") or ""))
                                    and (not difficulty or (r.get("difficulty") or "").lower() == difficulty)
                                ]
                                results = filtered[:limit]
                except Exception as e:
                    logger.debug("向量检索降级: %s", e)

            # 场景1：无向量结果时，有 exclude_id → 用 Neo4j 变体关系
            if not results and exclude_id and neo4j_service.available:
                results = neo4j_service.get_variants(exclude_id)
                results = [
                    {"q_id": str(r["id"]), "question_text": r.get("text", ""),
                     "difficulty": r.get("difficulty", "medium"),
                     "topic_tags": [], "company": ""}
                    for r in results
                ][:limit]

            # 场景2：按 keyword 搜索（SQLite），支持 company/difficulty 填槽
            if not results:
                sq = sqlite_service.filter_questions(
                    keyword=question_text[:80] if len(question_text) > 20 else question_text,
                    company=company or None,
                    difficulty=difficulty or None,
                    limit=limit + 10,
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

            # 场景3：有 exclude_id 且仍无结果 → 按相同标签兜底，支持 company 填槽
            if not results and exclude_id:
                tags = []
                sq = sqlite_service.filter_questions(
                    keyword=question_text[:30], limit=1)
                if sq:
                    tags = json.loads(sq[0].get("topic_tags") or "[]")
                if tags:
                    sim = sqlite_service.filter_questions(
                        tags=tags[:2], company=company or None, difficulty=difficulty or None,
                        limit=limit + 5)
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
                "按条件筛选题目列表（company/tags/difficulty/keyword/日期 等），返回题目列表供用户浏览选择。"
                "支持填槽：company、tags、difficulty、question_type、keyword、date_from、date_to。"
                "调用时机：用户说「列出字节的题」「这周收录的题」「Redis 中等难度」时。"
                "日期格式：YYYY-MM-DD，如 2025-03-01。date_from/date_to 用于按题目收录时间筛选。"
                "**严禁**在「我想练习这道题：XXX」场景调用——用户已指定题目，直接格式化输出即可。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("company", "string",
                          "公司填槽，如 字节跳动、阿里巴巴", required=False),
            ToolParameter("tags", "array",
                          "标签填槽，如 [\"Redis\", \"MySQL\"]", required=False),
            ToolParameter("difficulty", "string",
                          "难度填槽：easy / medium / hard", required=False),
            ToolParameter("question_type", "string",
                          "题型填槽：技术题 / 算法题 / 行为题", required=False),
            ToolParameter("keyword", "string",
                          "关键词搜索题目文本", required=False),
            ToolParameter("date_from", "string",
                          "日期填槽：起始日期 YYYY-MM-DD，如「这周的题」可填本周一", required=False),
            ToolParameter("date_to", "string",
                          "日期填槽：截止日期 YYYY-MM-DD，如「到昨天」", required=False),
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
                date_from=(parameters.get("date_from") or "").strip() or None,
                date_to=(parameters.get("date_to") or "").strip() or None,
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
                date_from=(parameters.get("date_from") or "").strip() or None,
                date_to=(parameters.get("date_to") or "").strip() or None,
            )
            return ToolResponse.success(text=json.dumps(
                {"total": total, "returned": len(result), "questions": result},
                ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("filter_questions failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"filter_questions failed: {e}")


class RecognizeIntentTool(Tool):
    """第一步必须调用的意图识别工具，解析用户消息并返回结构化 intent + slots。"""

    def __init__(self):
        super().__init__(
            name="recognize_intent",
            description=(
                "【第一步必须调用】解析用户消息，识别意图并提取槽位。"
                "输入：用户原始消息。输出：intent（意图）、slots（槽位）。"
                "调用时机：每轮对话开始时**必须**先调用此工具，再根据 intent 选择后续工具。"
                "对于【已作答】格式，会提取 question_id 和 user_answer，供 submit_answer 直接使用。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("user_message", "string",
                          "用户原始消息（完整复制）", required=True),
        ]

    def run(self, parameters):
        msg = (parameters.get("user_message") or "").strip()
        if not msg:
            return ToolResponse.error(code="INVALID_PARAM", message="user_message 不能为空")

        intent = "unknown"
        slots: Dict[str, Any] = {}

        # 【已作答】格式：提取 q_id、user_answer
        if "【已作答】" in msg or "已作答" in msg:
            q_match = re.search(r"【q_id[：:]\s*([a-f0-9\-]+)】", msg, re.I)
            ans_match = re.search(r"【我的作答】\s*([\s\S]*?)(?=【|$)", msg)
            if not ans_match:
                ans_match = re.search(r"我的作答[：:]\s*([\s\S]*?)(?=【|$)", msg)
            question_id = (q_match.group(1) or "").strip() if q_match else ""
            user_answer = (ans_match.group(1) or "").strip() if ans_match else ""
            if question_id and user_answer:
                intent = "submit_answer"
                slots = {"question_id": question_id, "user_answer": user_answer}
            elif question_id or user_answer:
                intent = "submit_answer"
                slots = {"question_id": question_id, "user_answer": user_answer}

        # 出题 / 推荐
        if intent == "unknown" and any(kw in msg for kw in ("出一道", "来一道", "来一题", "出题", "下一题", "推荐", "来道题")):
            intent = "get_recommended_question"
            if "字节" in msg or "bytedance" in msg.lower():
                slots["company"] = "字节跳动"
            if "mysql" in msg.lower() or "MySQL" in msg:
                slots["topic"] = "MySQL"
            if "redis" in msg.lower() or "Redis" in msg:
                slots["topic"] = "Redis"
            if "jvm" in msg.lower() or "JVM" in msg:
                slots["topic"] = "JVM"

        # 类似题 / 换个问法
        if intent == "unknown" and any(kw in msg for kw in ("换个问法", "类似题", "同类型")):
            intent = "find_similar_questions"
            slots["exclude_id"] = ""  # 需从上下文获取

        # 讲解 / 解释
        if intent == "unknown" and any(kw in msg for kw in ("讲解", "解释", "什么是", "讲讲")):
            intent = "explain"

        # 复习 / 薄弱点
        if intent == "unknown" and any(kw in msg for kw in ("复习", "薄弱点", "错题", "总结")):
            intent = "get_mastery_report"

        # 筛选
        if intent == "unknown" and any(kw in msg for kw in ("列出", "筛选", "这周收录")):
            intent = "filter_questions"

        # 笔记
        if intent == "unknown" and any(kw in msg for kw in ("我搞混了", "我漏了", "分不清", "记一下混淆", "记录遗漏", "我混淆了")):
            intent = "record_weakness"

        if intent == "unknown" and any(kw in msg for kw in ("记一下", "笔记", "保存笔记", "查看笔记")):
            intent = "manage_note"

        # 会话统计
        if intent == "unknown" and any(kw in msg for kw in ("做了几道", "会话进度", "统计")):
            intent = "get_session_context"

        # 练习指定题（不调用工具）
        if intent == "unknown" and any(kw in msg for kw in ("我想练习", "练习这道题", "练习：")):
            intent = "practice_specified"

        result = {"intent": intent, "slots": slots}
        return ToolResponse.success(
            text=json.dumps(result, ensure_ascii=False, indent=2))


class SubmitAnswerTool(Tool):
    def __init__(self):
        super().__init__(
            name="submit_answer",
            description=(
                "用户提交答案后调用：① LLM 评分（0-5分）+ 反馈；② 写入 study_records（SM-2 遗忘曲线）；③ 更新标签掌握度。"
                "调用时机：仅当用户发送【已作答】格式（含【q_id:xxx】【我的作答】yyy）时**必须**调用。"
                "必须传入 question_id（从【q_id:xxx】提取）和 user_answer（从【我的作答】提取）。"
                "评分完成后，用户说「下一题」「推荐同类题」时再调用 get_recommended_question 或 find_similar_questions。"
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
        session_id = get_current_session_id()
        question_id = (parameters.get("question_id") or "").strip()
        user_answer = (parameters.get("user_answer") or "").strip()
        question_text = (parameters.get("question_text") or "").strip()
        answer_text = (parameters.get("answer_text") or "").strip()

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
                        "SELECT question_text, answer_text, topic_tags FROM questions WHERE q_id = ?",
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
                "请对用户答案打分（0-5分整数）并给出简短反馈（3-5句话）。"
                '仅返回 JSON 格式：{\"score\": <int>, \"feedback\": \"<str>\"}\n'
                "评分标准：0=完全错误，1=方向对但内容严重缺失，"
                "2=基本思路对但细节错误，3=答案正确但不完整，"
                "4=答案完整，5=超出预期（有深度补充）。\n"
                "feedback 要求：\n"
                "- 3-5句话，不超过150字\n"
                "- 直接说优点和不足，不要加亮点、优化点等标题\n"
                "- 不要说您的答案、已为您提交等废话\n"
                "- 格式：先说对的地方，再说需要改进的地方，最后一句建议"
            )
            raw = _call_llm(score_prompt, json_mode=True, max_tokens=300)
            try:
                parsed = json.loads(raw)
                score = max(0, min(5, int(parsed.get("score", 2))))
                feedback = parsed.get("feedback", "")
            except Exception:
                score = 2
                feedback = raw[:200] if raw else "评分解析失败"

            # 生成 message_id 用于关联对话历史
            import time
            message_id = f"eval_{question_id}_{int(time.time()*1000)}"

            # 写入学习记录（SM-2 自动更新），关联 message_id
            sm2 = sqlite_service.add_study_record(
                user_id=user_id,
                question_id=question_id,
                score=score,
                user_answer=user_answer,
                ai_feedback=feedback,
                session_id=session_id,
                message_id=message_id,
            )

            # 同时更新对话历史，记录评分结果
            if session_id:
                sqlite_service.update_session_history(
                    session_id=session_id,
                    role="assistant",
                    content=f"✅ 评分完成：{score}/5\n\n{feedback}",
                    message_id=message_id,
                    metadata={
                        "type": "answer_evaluation",
                        "question_id": question_id,
                        "score": score,
                        "sm2": sm2
                    }
                )

            result = {
                "score": score,
                "feedback": feedback,
                "sm2": sm2,
                "message_id": message_id,
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

class RecordWeaknessTool(Tool):
    """记录用户自述的混淆点和遗漏点，供学习报告展示"""
    def __init__(self):
        super().__init__(
            name="record_weakness",
            description=(
                "记录用户自述的混淆点或遗漏点。"
                "调用时机：用户说「我搞混了X和Y」「我漏了Z」「我分不清A和B」等时。"
                "记录后会在学习报告中展示，帮助针对性复习。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("confusion_points", "array",
                          "混淆点列表，如 [\"重载与重写的区别\", \"TCP与UDP\"]", required=False),
            ToolParameter("missed_points", "array",
                          "遗漏点列表，如 [\"Java代码示例\", \"应用场景\"]", required=False),
            ToolParameter("tags", "array",
                          "关联的知识点标签", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        session_id = get_current_session_id()
        confusion = parameters.get("confusion_points") or []
        missed = parameters.get("missed_points") or []
        tags = parameters.get("tags") or []
        if isinstance(confusion, str):
            try:
                confusion = json.loads(confusion) if confusion.strip().startswith("[") else [confusion]
            except Exception:
                confusion = [confusion] if confusion else []
        if isinstance(missed, str):
            try:
                missed = json.loads(missed) if missed.strip().startswith("[") else [missed]
            except Exception:
                missed = [missed] if missed else []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags) if tags.strip().startswith("[") else [tags]
            except Exception:
                tags = [tags] if tags else []

        if not confusion and not missed:
            return ToolResponse.error(code="INVALID_PARAM", message="请提供 confusion_points 或 missed_points")

        count = 0
        for c in confusion:
            if c and str(c).strip():
                content = f"混淆点：{c}"
                if tags:
                    content += f" | 标签：{', '.join(str(t) for t in tags[:5])}"
                sqlite_service.add_episodic_log(
                    user_id=user_id,
                    content=content,
                    importance=0.85,
                    event_type="user_confusion",
                    session_id=session_id or "",
                )
                count += 1
        for m in missed:
            if m and str(m).strip():
                content = f"遗漏点：{m}"
                if tags:
                    content += f" | 标签：{', '.join(str(t) for t in tags[:5])}"
                sqlite_service.add_episodic_log(
                    user_id=user_id,
                    content=content,
                    importance=0.85,
                    event_type="user_missed",
                    session_id=session_id or "",
                )
                count += 1
        return ToolResponse.success(
            text=json.dumps({"message": f"已记录 {count} 条薄弱点", "count": count}, ensure_ascii=False)
        )


class ManageNoteTool(Tool):
    def __init__(self):
        super().__init__(
            name="manage_note",
            description=(
                "用户笔记 CRUD。action=create/list/update/delete。"
                "调用时机：用户说「记一下」「保存笔记」「查看我的笔记」「删除笔记」时。"
                "**严禁**在「我想练习这道题」或出题场景调用。"
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
                "调用时机：用户问「做了几道」「会话进度」「今天练了几题」时。"
                "**严禁**在「我想练习这道题」或出题场景调用——用户已指定题目，直接格式化输出即可。"
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
    """① 复习/薄弱点场景：调取以前答题记录+漏洞"""
    def __init__(self):
        super().__init__(
            name="get_mastery_report",
            description=(
                "【① 复习/薄弱点】调取用户历史答题记录、错题、薄弱标签、推荐复习题。"
                "支持填槽：date_from、date_to（按做题日期筛选，如「这周的错题」「3月以来的薄弱点」）。"
                "日期格式 YYYY-MM-DD。若用户说「这周的」但未给具体日期，可推算本周一/今天完成填槽。"
                "调用时机：用户说「复习之前做过的题」「回顾错题」「总结薄弱点」时。"
                "**严禁**在「我想练习这道题」场景调用——用户已指定题目，直接格式化输出即可。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("date_from", "string",
                          "日期填槽：起始日期 YYYY-MM-DD，如「这周的错题」填本周一", required=False),
            ToolParameter("date_to", "string",
                          "日期填槽：截止日期 YYYY-MM-DD，默认今天", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        date_from = (parameters.get("date_from") or "").strip() or None
        date_to = (parameters.get("date_to") or "").strip() or None
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
            
            # 获取具体的薄弱题目（得分 < 3），支持日期填槽
            weak_tags = [i["tag"] for i in (by_level.get("novice", []) + by_level.get("learning", []))]
            weak_records = sqlite_service.get_weak_study_records(
                user_id,
                tags=weak_tags,
                limit=5,
                date_from=date_from,
                date_to=date_to,
            ) if weak_tags else []
            weak_questions = [
                {
                    "question_text": (rec.get("question_text") or "")[:100],
                    "score": rec["score"],
                    "ai_feedback": (rec.get("ai_feedback") or "")[:150],
                    "studied_at": rec.get("studied_at", ""),
                    "tags": rec.get("topic_tags") or []
                }
                for rec in weak_records
            ]
            
            # 获取推荐复习的题目（遗忘曲线到期的题目）
            due_reviews = sqlite_service.get_due_reviews(user_id, limit=3)
            review_questions = [
                {
                    "question_id": str(r["question_id"]),
                    "question_text": (r.get("question_text") or "")[:100],
                    "last_score": r.get("score", 0),
                    "due_date": r.get("next_review_at", ""),
                    "tags": json.loads(r.get("topic_tags") or "[]")
                }
                for r in due_reviews
            ]
            
            weak_tags = [
                i["tag"] for i in
                (by_level.get("novice", [])
                 + by_level.get("learning", []))
            ][:10]
            
            report = {
                "total_questions_practiced": summary["total_questions_practiced"],
                "overall_avg_score": round(summary["overall_avg_score"], 2),
                "correct_rate_pct": round(summary["correct_rate"], 1),
                "mastery_by_level": by_level,
                "weak_tags": weak_tags,
                "weak_questions": weak_questions,
                "review_questions": review_questions,
                "advice": (
                    f"您的正确率为 {summary['correct_rate']:.0f}%。"
                    + f"薄弱标签：{', '.join(weak_tags[:3])}。"
                    + "建议重点练习这些标签，每天坚持 3-5 道题。"
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
    """③ 延伸知识点：GraphRAG 相关知识点 + RAG 对应题目"""
    def __init__(self):
        super().__init__(
            name="get_knowledge_recommendation",
            description=(
                "【③ 延伸知识点】从 GraphRAG 搜索相关知识点 + 从 RAG 检索对应知识点的题目。"
                "功能：① 若有 question_id，从知识图谱获取该题覆盖的 Concept，再找相关 Concept；"
                "② 若有 topic/concept，直接搜索相关概念；③ 从题库检索覆盖这些知识点的题目（排除自身）。"
                "调用时机：用户说「延伸一下」「拓展相关知识点」「还有哪些相关考点」「推荐学习资料」时。"
                "**严禁**在「我想练习这道题」或出题场景调用。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("topic", "string",
                          "知识点/概念名，如 Redis、MySQL、B+树；或从当前题提取",
                          required=False),
            ToolParameter("question_id", "string",
                          "当前题目 ID（若有，用于从 GraphRAG 获取该题覆盖的概念再延伸）",
                          required=False),
            ToolParameter("limit_concepts", "integer",
                          "返回相关知识点数量，默认5", required=False),
            ToolParameter("limit_questions", "integer",
                          "返回题目数量，默认5", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        try:
            topic = (parameters.get("topic") or "").strip()
            question_id = (parameters.get("question_id") or "").strip()
            limit_c = min(int(parameters.get("limit_concepts") or 5), 10)
            limit_q = min(int(parameters.get("limit_questions") or 5), 10)
            exclude_ids = [question_id] if question_id else []

            # 确定要延伸的 concept/topic 来源
            concepts_to_extend = []
            if neo4j_service.available:
                if question_id:
                    concepts_to_extend = neo4j_service.get_concepts_by_question(question_id)
                if topic and not concepts_to_extend:
                    concepts_to_extend = [{"name": topic, "description": ""}]
                # question_id 有值但 Neo4j 无 Concept 时，用题目 tags 作为概念
                if question_id and not concepts_to_extend:
                    q_info = neo4j_service.get_question_by_id(question_id)
                    if q_info and q_info.get("tags"):
                        concepts_to_extend = [{"name": t, "description": ""} for t in q_info["tags"][:3]]

            # GraphRAG：相关知识点
            related_concepts = []
            if neo4j_service.available and concepts_to_extend:
                seen = set()
                for c in concepts_to_extend[:3]:  # 最多从 3 个概念延伸
                    name = c.get("name") or ""
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    rel = neo4j_service.get_related_concepts(name, limit=limit_c)
                    for r in rel:
                        if r.get("name") and r["name"] not in seen:
                            related_concepts.append(r)
                            seen.add(r["name"])
                    if len(related_concepts) >= limit_c:
                        break
                related_concepts = related_concepts[:limit_c]

            # 若无 GraphRAG 相关概念，用 topic 或 concepts_to_extend 作为延伸起点
            if not related_concepts and (topic or concepts_to_extend):
                related_concepts = [{"name": topic, "description": ""}] if topic else concepts_to_extend[:3]

            # RAG：对应知识点的题目
            concepts_for_questions = related_concepts or (concepts_to_extend if concepts_to_extend else ([{"name": topic}] if topic else []))
            extension_questions = []
            if neo4j_service.available:
                for c in (concepts_for_questions or []):
                    name = c.get("name") or topic
                    if not name:
                        continue
                    qs = neo4j_service.get_questions_by_concept(
                        name, limit=limit_q, exclude_ids=exclude_ids)
                    for q in qs:
                        if q.get("id") not in exclude_ids:
                            extension_questions.append({
                                "q_id": q.get("id"),
                                "question_text": q.get("text", ""),
                                "difficulty": q.get("difficulty", "medium"),
                                "concept": name,
                            })
                            exclude_ids.append(q.get("id"))
                    if len(extension_questions) >= limit_q:
                        break
                extension_questions = extension_questions[:limit_q]

            # 降级：Neo4j 无 Concept 时，用 tag 查题
            if not extension_questions and (topic or related_concepts):
                tags = [c.get("name") for c in related_concepts if c.get("name")] or ([topic] if topic else [])
                if tags:
                    rows = neo4j_service.get_questions_by_tags(
                        tags[:3], limit=limit_q, exclude_ids=exclude_ids)
                    extension_questions = [
                        {"q_id": r.get("id"), "question_text": r.get("text", ""),
                         "difficulty": r.get("difficulty", "medium"), "concept": tags[0]}
                        for r in rows
                    ]

            # 学习资源（SQLite）
            tags_for_resources = [c.get("name") for c in related_concepts if c.get("name")] or ([topic] if topic else [])
            if not tags_for_resources:
                weak = sqlite_service.get_weak_tags(user_id)
                tags_for_resources = [t["tag"] for t in weak[:3]]
            resources = sqlite_service.get_resources_by_tags(tags_for_resources, limit=3)
            weak_records = sqlite_service.get_weak_study_records(
                user_id, tags=tags_for_resources[:3], limit=2)

            result = {
                "related_concepts": related_concepts,
                "extension_questions": extension_questions,
                "resources": [
                    {"title": r["title"], "url": r["url"],
                     "description": r["description"], "tags": r["tags"],
                     "resource_type": r["resource_type"]}
                    for r in resources
                ],
                "recent_mistakes": [
                    {"question_text": rec.get("question_text", "")[:80],
                     "score": rec["score"], "ai_feedback": (rec.get("ai_feedback") or "")[:120]}
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
                "分析用户简历，提取技术栈、目标岗位、经验级别，更新用户画像。"
                "调用时机：用户粘贴简历或说「分析我的简历」时。必须传入 resume_text。"
                "**严禁**在「我想练习这道题」或出题场景调用。"
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
        RecognizeIntentTool(),
        GetSessionContextTool(),
        GetRecommendedQuestionTool(),
        FindSimilarQuestionsTool(),
        FilterQuestionsTool(),
        SubmitAnswerTool(),
        RecordWeaknessTool(),
        ManageNoteTool(),
        GetMasteryReportTool(),
        GetKnowledgeRecommendationTool(),
        AnalyzeResumeTool(),
    ]
