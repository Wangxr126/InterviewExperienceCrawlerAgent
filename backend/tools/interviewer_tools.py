from __future__ import annotations
import json, logging, re, random, requests
from typing import Any, List, Dict, Optional
from hello_agents.tools import Tool, ToolParameter
from hello_agents.tools.response import ToolResponse
from backend.agents.context import get_current_user_id, get_current_session_id, get_current_user_message
from backend.config.config import settings
from backend.services.storage.sqlite_service import sqlite_service
from backend.services.storage.neo4j_service import neo4j_service
from backend.services.rerank_service import rerank_candidates
from backend.services.multi_recall_recommender import multi_recall_recommender

logger = logging.getLogger(__name__)


# ===========================================================
# 评估辅助函数
# ===========================================================

def _fix_json_invalid_escape(s: str) -> str:
    """修复 LLM 返回的 JSON 中非法转义（如 \\x、\\N 等），避免 Invalid \\escape 解析失败。"""
    if not s or "\\" not in s:
        return s
    res = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n in '"\\/bfnrt':
                res.append(s[i])
                res.append(n)
                i += 2
                continue
            if n == "u" and i + 5 <= len(s):
                hex_part = s[i + 2 : i + 6]
                if all(c in "0123456789abcdefABCDEF" for c in hex_part):
                    res.append(s[i : i + 6])
                    i += 6
                    continue
            # 非法转义：保留反斜杠为双反斜杠，下一字符原样保留
            res.append("\\\\")
            res.append(n)
            i += 2
            continue
        res.append(s[i])
        i += 1
    return "".join(res)


def _save_eval_failure(input_preview: str, raw_output: str, error: str) -> None:
    try:
        from backend.services.logging.llm_parse_failures import save_failure
        save_failure(source="answer_eval", input_preview=input_preview,
                     raw_output=raw_output, error=error, metadata={})
    except Exception as e:
        logger.debug(f"保存评估失败记录异常: {e}")


def _evaluate_answer_structured(question_text: str,
                                user_answer: str,
                                reference_answer: Optional[str] = None) -> Dict[str, Any]:
    """
    结构化评估：直接调用 LLM（JSON mode），不走 ReAct 循环。
    Returns: {score, feedback, shortcomings, error_points, missed_points, strong_points, tags}
    """
    ref_block = ""
    if reference_answer and reference_answer.strip():
        ref_block = f"\n【参考答案/标准答案】（来自题库，用于对比）\n{reference_answer.strip()}\n"

    system = (
        "你是一位技术面试评委。用户将提交面试题目和他们的回答。"
        "你需要评估回答质量，严格按以下 JSON 格式返回，不得添加任何额外字段或注释：\n"
        '{"score":3,"feedback":"总体评价","shortcomings":["不足1"],'
        '"error_points":[{"wrong":"错误表述","correct":"正确表述"}],'
        '"missed_points":["遗漏点"],"strong_points":["答对的点"],"tags":["标签"]}'
        "\n\n【评分规则】"
        "\n1. score 取值仅为以下之一：0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0"
        "\n2. score<5 时，shortcomings 必须列出具体不足"
        "\n3. error_points：含 wrong（错误）和 correct（正确），用于纠正"
        "\n4. missed_points：用户遗漏的知识点"
        "\n5. feedback：分条列点，包含亮点、不足、错误纠正、遗漏补充、改进建议"
        "\n\n【评分细则】"
        "\n依据：①答对要点占比 ②遗漏要点数 ③混淆/错误数"
        "\n· 5.0：答对核心要点 ≥90%，无遗漏、无错误"
        "\n· 4.0-4.5：答对 ≥70%，遗漏 ≤1 个次要点，无错误"
        "\n· 3.0-3.5：答对 ≥50%，遗漏 1-2 个要点，无严重错误"
        "\n· 2.0-2.5：答对 30%-50%，或存在 1 处概念混淆/错误"
        "\n· 1.0-1.5：答对 <30%，或存在 2+ 处错误"
        "\n· 0-0.5：几乎未答对、大量错误或完全偏题"
    )
    prompt = f"【面试题目】\n{question_text}\n\n【用户回答】\n{user_answer}{ref_block}"

    default = {"score": 3, "feedback": "（评估服务暂时不可用，已记录原始答案）",
               "shortcomings": [], "error_points": [], "missed_points": [],
               "strong_points": [], "tags": [], "_eval_failed": True}
    try:
        _model = settings.interviewer_model or settings.llm_model_id
        # 优先使用 interviewer 专用配置，避免 base_url/api_key 混用导致 404
        _base = (settings.interviewer_base_url or settings.llm_base_url or "").rstrip("/")
        _api_key = settings.interviewer_api_key or settings.llm_api_key
        _timeout = settings.interviewer_timeout or settings.llm_timeout or 60
        _url = f"{_base}/chat/completions" if "/chat/completions" not in _base else _base
        resp = requests.post(
            _url,
            headers={"Authorization": f"Bearer {_api_key}",
                     "Content-Type": "application/json"},
            json={"model": _model,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}],
                  "temperature": 0.1,
                  "response_format": {"type": "json_object"}},
            timeout=_timeout,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            result = None
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                try:
                    result = json.loads(_fix_json_invalid_escape(content))
                except json.JSONDecodeError as e:
                    logger.error(f"_evaluate_answer_structured JSON 解析失败: {e}")
                    _save_eval_failure(prompt, content, error=str(e))
                    return default
            raw_score = result.get("score", 3)
            try:
                score_val = float(raw_score)
            except (TypeError, ValueError):
                score_val = 3.0
            # 支持 0.5 档位，四舍五入到最近 0.5 并限制在 [0, 5]
            result["score"] = max(0.0, min(5.0, round(score_val * 2) / 2))
            return result
        else:
            logger.warning(f"评估 LLM 返回 {resp.status_code}")
            _save_eval_failure(prompt, resp.text[:2000] if resp.text else "",
                               error=f"HTTP {resp.status_code}")
            return default
    except Exception as e:
        logger.error(f"_evaluate_answer_structured 异常: {e}")
        _save_eval_failure(prompt, "", error=str(e))
        return default


def _get_seen_question_ids(user_id: str, limit: int = 100) -> List[str]:
    history = sqlite_service.get_study_history(user_id, limit=limit)
    return [str(r["question_id"]) for r in history if r.get("question_id")]


class GetRecommendedQuestionTool(Tool):
    """查库：推荐多道面试题（遗忘曲线/薄弱点/随机）。"""
    def __init__(self):
        super().__init__(
            name="get_recommended_question",
            description=(
                "【意图】用户说“来道题/下一题/出题”，且未明确指定目标 q_id（不是“我想练习这道题【q_id:xxx】”）。"
                "【功能】从题库按：遗忘曲线到期、薄弱标签优先，并结合 topic/company/difficulty 做随机推荐（默认推荐多道，模型只展示其中一道）。"
                "【填槽】topic/company/difficulty 均为可选；若用户只说“某公司”但未给公司名，请先追问补全。"
                "【返回】JSON：{总数, 筛选条件, 题目列表[]}；每个题目包含 q_id、题目、难度、标签、公司、推荐理由。"
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
        
        # 从 .env 读取配置
        count = int(getattr(settings, "recommend_questions_count", 5))
        use_json = getattr(settings, "recommend_questions_json_format", True)
        show_detail = getattr(settings, "recommend_questions_show_detail", True)
        show_reason = getattr(settings, "recommend_questions_show_reason", True)
        
        try:
            # 使用多路召回推荐器
            questions = multi_recall_recommender.recommend(
                user_id=user_id,
                query=topic or company or None,  # 用 topic/company 作为 query
                company=company or None,
                difficulty=difficulty or None,
                tags=[topic] if topic else None,
                top_n=count,  # 返回 N 道题（默认 5）
                exclude_ids=seen_ids,
            )
            
            if not questions:
                return ToolResponse.error(
                    code="EXECUTION_ERROR",
                    message="题库暂无符合条件的题目，请先抓取面经数据或调整筛选条件。"
                )
            
            # 格式化输出
            if use_json:
                # JSON 格式化输出
                formatted_questions = []
                for idx, q in enumerate(questions, 1):
                    item = {
                        "序号": idx,
                        "题目ID": q.get("q_id", ""),
                        "题目": q.get("question_text", "")[:150] if show_detail else q.get("question_text", ""),
                        "难度": q.get("difficulty", "medium"),
                        "标签": q.get("topic_tags", []) if show_detail else None,
                        "公司": q.get("company", "") if show_detail else None,
                    }
                    
                    # 添加推荐理由
                    if show_reason:
                        reason = _get_recommendation_reason(q, topic, company, difficulty)
                        item["推荐理由"] = reason
                    
                    # 移除 None 值
                    item = {k: v for k, v in item.items() if v is not None}
                    formatted_questions.append(item)
                
                result = {
                    "总数": len(formatted_questions),
                    "筛选条件": {
                        "知识点": topic or "不限",
                        "公司": company or "不限",
                        "难度": difficulty or "不限",
                    },
                    "题目列表": formatted_questions,
                }
                
                return ToolResponse.success(
                    text=json.dumps(result, ensure_ascii=False, indent=2)
                )
            else:
                # 纯文本格式输出
                lines = [f"📚 为您推荐 {len(questions)} 道题目\n"]
                lines.append(f"筛选条件：知识点={topic or '不限'} | 公司={company or '不限'} | 难度={difficulty or '不限'}\n")
                lines.append("=" * 80)
                
                for idx, q in enumerate(questions, 1):
                    lines.append(f"\n【第 {idx} 题】")
                    lines.append(f"题目ID: {q.get('q_id', '')}")
                    if show_detail:
                        lines.append(f"难度: {q.get('difficulty', 'medium')}")
                        tags = q.get("topic_tags", [])
                        if tags:
                            lines.append(f"标签: {', '.join(tags)}")
                        if q.get("company"):
                            lines.append(f"公司: {q.get('company')}")
                    lines.append(f"\n题目: {q.get('question_text', '')}")
                    if show_reason:
                        reason = _get_recommendation_reason(q, topic, company, difficulty)
                        lines.append(f"\n推荐理由: {reason}")
                    lines.append("\n" + "-" * 80)
                
                return ToolResponse.success(text="\n".join(lines))
            
        except Exception as e:
            logger.exception("get_recommended_question failed")
            return ToolResponse.error(
                code="EXECUTION_ERROR",
                message=f"get_recommended_question failed: {e}"
            )


def _get_recommendation_reason(question: dict, topic: str, company: str, difficulty: str) -> str:
    """生成推荐理由"""
    reasons = []
    
    q_tags = question.get("topic_tags", [])
    q_company = question.get("company", "")
    q_difficulty = question.get("difficulty", "medium")
    
    # 匹配知识点
    if topic and topic in q_tags:
        reasons.append(f"✓ 匹配知识点「{topic}」")
    elif topic and any(t in topic for t in q_tags):
        reasons.append(f"✓ 相关知识点「{', '.join(q_tags[:2])}」")
    
    # 匹配公司
    if company and company in q_company:
        reasons.append(f"✓ 来自「{q_company}」真题")
    
    # 难度匹配
    if difficulty and difficulty == q_difficulty:
        reasons.append(f"✓ 符合「{difficulty}」难度")
    
    # 遗忘曲线
    if question.get("is_due_review"):
        reasons.append("⏰ 遗忘曲线到期，需复习")
    
    # 薄弱点
    if question.get("is_weak_tag"):
        reasons.append("📉 薄弱知识点，重点练习")
    
    # 默认理由
    if not reasons:
        reasons.append("🎯 精选推荐")
    
    return " | ".join(reasons)


class FindSimilarQuestionsTool(Tool):
    """查库：语义相似题，排除当前题。"""
    def __init__(self):
        super().__init__(
            name="find_similar_questions",
            description=(
                "【调用时机】用户说「换个问法」「同公司的类似题」「出几道类似的」且对话中有上一题时。"
                "【功能】向量检索相似题，排除 exclude_id，返回 limit 道。"
                "【填槽】question_text（必填）、exclude_id、company、difficulty。若说「同公司的」未指定公司，先询问。"
                "【返回】相似题列表（题目ID、题目、难度、标签、公司）；检索失败时返回失败原因。"
                "【严禁】用户说「我想练习这道题」时严禁调用。"
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
                          f"返回数量，默认 {settings.retrieval_similar_limit}（由 RETRIEVAL_SIMILAR_LIMIT 配置）", required=False),
        ]

    def run(self, parameters):
        question_text = (parameters.get("question_text") or "").strip()
        exclude_id = (parameters.get("exclude_id") or "").strip()
        company = (parameters.get("company") or "").strip()
        difficulty = (parameters.get("difficulty") or "").strip().lower()
        default_limit = settings.retrieval_similar_limit
        limit = min(int(parameters.get("limit") or default_limit), max(default_limit, 10))
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
                            emb,
                            top_k=search_top_k + len(exclude_ids),
                            score_threshold=score_threshold,
                            exclude_ids=exclude_ids,
                        )
                        if vec_results:
                            # 重排：使用 Ollama Qwen3-Reranker
                            if settings.rerank_enabled and len(vec_results) > 1:
                                # 打印向量检索原始结果（仅打印 id 和原始 score，避免日志过长）
                                try:
                                    logger.info(
                                        "[FindSimilarQuestions] 向量检索返回 %d 条，top_k=%d threshold=%.2f exclude_ids=%s",
                                        len(vec_results),
                                        search_top_k,
                                        score_threshold,
                                        exclude_ids,
                                    )
                                    logger.debug(
                                        "[FindSimilarQuestions] 原始向量结果前 %d 条: %s",
                                        min(10, len(vec_results)),
                                        [
                                            {
                                                "id": str(r.get("id")),
                                                "score": round(float(r.get("score", 0)), 4),
                                            }
                                            for r in vec_results[:10]
                                        ],
                                    )
                                except Exception:
                                    # 日志失败不影响主流程
                                    pass

                                reranked = rerank_candidates(
                                    query=question_text[:2048],
                                    candidates=vec_results,
                                    text_key="text",
                                    top_n=limit,
                                )

                                # 打印重排后的结果顺序及分数，便于排查「为何这道题排在前面」
                                try:
                                    logger.info(
                                        "[FindSimilarQuestions] 重排后取前 %d 条，实际返回 %d 条",
                                        limit,
                                        len(reranked),
                                    )
                                    logger.debug(
                                        "[FindSimilarQuestions] 重排结果: %s",
                                        [
                                            {
                                                "id": str(r.get("id")),
                                                "rerank_score": round(
                                                    float(r.get("rerank_score", 0)), 4
                                                ),
                                                "orig_score": round(
                                                    float(r.get("score", 0)), 4
                                                ),
                                            }
                                            for r in reranked
                                        ],
                                    )
                                except Exception:
                                    pass

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
    """查库：按条件筛选题目列表。"""
    def __init__(self):
        super().__init__(
            name="filter_questions",
            description=(
                "【意图】用户想“列出题目/筛选题库”：例如“列出字节的题”“这周的题”“Redis 中等难度”“按关键词找题”“按日期范围找题”。"
                "【功能】根据 company/tags/difficulty/question_type/keyword/date_from/date_to/limit 筛选题目（SQLite）。"
                "【填槽】tags 可传数组或 JSON 字符串；date_from/date_to 仅当用户明确说日期时才传 YYYY-MM-DD。"
                "【返回】JSON：{total, returned, questions[]}；questions 含 q_id、question_text、difficulty、topic_tags、company、source_platform。"
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


class GetQuestionDetailTool(Tool):
    """查库：获取题目详情（题目文本、参考答案）。"""
    def __init__(self):
        super().__init__(
            name="get_question_detail",
            description=(
                "【意图】用户要“看题目/查看详情/要参考答案/拿标准答案”。"
                "【功能】根据 question_id（q_id）读取：题目全文、参考答案、topic_tags、difficulty。"
                "【填槽】question_id 必填。"
                "【返回】JSON：{question_id, question_text, answer_text, topic_tags, difficulty}；找不到返回错误。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("question_id", "string", "题目ID（q_id）", required=True),
        ]

    def run(self, parameters):
        question_id = (parameters.get("question_id") or "").strip()
        if not question_id:
            return ToolResponse.error(code="INVALID_PARAM", message="question_id 不能为空")
        try:
            with sqlite_service._get_conn() as conn:
                row = conn.execute(
                    "SELECT question_text, answer_text, topic_tags, difficulty FROM questions WHERE q_id = ?",
                    (question_id,)
                ).fetchone()
            if not row:
                return ToolResponse.error(code="NOT_FOUND", message=f"未找到题目 {question_id}")
            # sqlite3.Row 无 .get，用索引
            topic_raw = row["topic_tags"] if row["topic_tags"] else None
            result = {
                "question_id": question_id,
                "question_text": row["question_text"] or "",
                "answer_text": row["answer_text"] or "",
                "topic_tags": json.loads(topic_raw) if topic_raw else [],
                "difficulty": row["difficulty"] or "medium",
            }
            return ToolResponse.success(text=json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("get_question_detail failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"get_question_detail failed: {e}")


class SubmitAnswerTool(Tool):
    """仅记录：由 Agent 自行评估后传入评分结果，工具只负责写入 study_records / SM-2 / 会话历史，不调用任何评估 LLM。"""
    def __init__(self):
        super().__init__(
            name="submit_answer",
            description=(
                "【意图】用户完成作答后，用于“记录+归档评分结果”。"
                "【功能】不做评估、不调用任何 LLM；只写入：study_records / SM-2（next_review_at）/ 会话历史 / 标签掌握度。"
                "【填槽】question_id、user_answer、score、feedback 必填；strong_points/missed_points/error_points 可选。"
                "【薄弱点写入】record_weakness_notes=true（默认）则把 missed_points/error_points 写入本地薄弱点 note；false 时交给 record_weakness。"
                "【返回】JSON：{score, feedback, missed_points, error_points, strong_points, tags, standard_answer, sm2, message_id, message}。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("question_id", "string", "题目ID（q_id），必填", required=True),
            ToolParameter("user_answer", "string", "用户作答内容，可不传（系统自动取本轮用户消息）", required=False),
            ToolParameter("score", "number", "你给出的分数，取值 0/0.5/1.0/.../5.0，必填", required=True),
            ToolParameter("feedback", "string", "你对作答的总体点评，必填", required=True),
            ToolParameter("record_weakness_notes", "string",
                          "是否写入薄弱点 note：true/false（或 1/0），默认 true；当 false 时由 record_weakness 工具负责写入。",
                          required=False),
            ToolParameter("strong_points", "array", "答对的要点列表，如 [\"要点1\", \"要点2\"]", required=False),
            ToolParameter("missed_points", "array", "遗漏的要点列表", required=False),
            ToolParameter("error_points", "array", "混淆/错误列表，每项为 {wrong:\"错误表述\", correct:\"正确表述\"}", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        session_id = get_current_session_id()
        question_id = (parameters.get("question_id") or "").strip()
        user_answer = (parameters.get("user_answer") or "").strip()
        if not user_answer:
            user_answer = (get_current_user_message() or "").strip()

        if not question_id or not user_answer:
            return ToolResponse.error(code="INVALID_PARAM", message="question_id 和 user_answer 不能为空")

        # 从 Agent 传入的评估结果取值（Agent 自行评估，工具只记录）
        score_raw = parameters.get("score")
        if score_raw is None:
            return ToolResponse.error(code="INVALID_PARAM", message="请先完成评估并传入 score（0～5，支持 0.5 档位）")
        try:
            score_val = float(score_raw)
        except (TypeError, ValueError):
            return ToolResponse.error(code="INVALID_PARAM", message="score 必须为数字（0～5）")
        score_display = max(0.0, min(5.0, round(score_val * 2) / 2))
        score = score_display

        feedback = (parameters.get("feedback") or "").strip()
        if not feedback:
            return ToolResponse.error(code="INVALID_PARAM", message="请传入 feedback（你对作答的点评）")

        def _norm_list(v, default=None):
            if v is None:
                return default or []
            if isinstance(v, list):
                return v
            if isinstance(v, str):
                try:
                    return json.loads(v) if v.strip() else []
                except Exception:
                    return [v] if v.strip() else []
            return []

        strong_points: List[str] = _norm_list(parameters.get("strong_points"), [])
        missed_points: List[str] = _norm_list(parameters.get("missed_points"), [])
        error_points_raw = _norm_list(parameters.get("error_points"), [])
        error_points: List[dict] = []
        for ep in error_points_raw:
            if isinstance(ep, dict):
                error_points.append(ep)
            elif isinstance(ep, str):
                try:
                    error_points.append(json.loads(ep))
                except Exception:
                    error_points.append({"wrong": ep, "correct": ""})

        # 是否把 missed_points/error_points 写入本地薄弱点 note。
        # 说明：默认 true，保证即使 prompt 没显式拆分也不会丢失薄弱点。
        record_weakness_notes = True
        raw_flag = parameters.get("record_weakness_notes")
        if raw_flag is not None:
            if isinstance(raw_flag, bool):
                record_weakness_notes = raw_flag
            else:
                s = str(raw_flag).strip().lower()
                record_weakness_notes = s not in ("false", "0", "no", "off")

        # ── 从题库获取题目信息（仅用于校验与返回 standard_answer）──────────────────────
        question_text = ""
        reference_answer = ""
        question_tags: List[str] = []
        try:
            with sqlite_service._get_conn() as conn:
                row = conn.execute(
                    "SELECT question_text, answer_text, topic_tags FROM questions WHERE q_id = ?",
                    (question_id,)
                ).fetchone()
            if row:
                question_text = row["question_text"] or ""
                reference_answer = row["answer_text"] or ""
                try:
                    question_tags = json.loads(row["topic_tags"] or "[]") or []
                except Exception:
                    question_tags = []
        except Exception as e:
            logger.warning("[submit_answer] 获取题目详情失败: %s", e)

        if not question_text:
            return ToolResponse.error(code="NOT_FOUND", message=f"未找到题目 {question_id}，请确认 question_id 正确")

        # 校验：禁止将题目当答案
        a_clean = user_answer.strip()
        q_clean = question_text.strip()
        if q_clean and (a_clean == q_clean or (a_clean in q_clean and len(a_clean) < 30)):
            return ToolResponse.error(
                code="INVALID_PARAM",
                message="user_answer 与题目相同或为题目片段，用户尚未作答。"
            )

        logger.info("📝 [submit_answer] 记录 q=%s score=%s（由 Agent 评估）", question_id, score_display)
        merged_tags = list(dict.fromkeys(question_tags))
        eval_details = {
            "shortcomings": [],
            "error_points": error_points,
            "missed_points": missed_points,
            "strong_points": strong_points,
        }

        try:
            import time
            message_id = f"eval_{question_id}_{int(time.time()*1000)}"

            sm2 = sqlite_service.add_study_record(
                user_id=user_id,
                question_id=question_id,
                score=score_display,
                user_answer=user_answer,
                ai_feedback=feedback,
                session_id=session_id,
                message_id=message_id,
                eval_details=eval_details,
            )
            # 同步标签掌握度
            if merged_tags:
                try:
                    sqlite_service.update_tag_mastery(user_id, merged_tags, score)
                except Exception as _te:
                    logger.debug("update_tag_mastery 忽略: %s", _te)

            # 同步 next_review_at 到 Neo4j，供多路召回+rerank(时间)推荐
            if sm2 and sm2.get("next_review_at"):
                try:
                    from backend.services.storage import neo4j_service
                    neo4j_service.upsert_user_study_record(
                        user_id=user_id,
                        question_id=question_id,
                        next_review_at=sm2["next_review_at"],
                        score=score,
                    )
                except Exception as ex:
                    logger.debug("Neo4j 同步复习时间失败（不影响主流程）: %s", ex)

            # 薄弱点写入：可选地由 submit_answer 内联完成（默认），或交给 record_weakness 负责（record_weakness_notes=false）
            note_count_log = len(missed_points) + len(error_points)
            if record_weakness_notes and note_count_log:
                logger.info(
                    "[submit_answer] 内联记录 %d 条遗漏/混淆点到 episodic_log + user_notes",
                    note_count_log,
                )
                for m in missed_points:
                    if not (m and str(m).strip()):
                        continue
                    content = f"遗漏点：{m}"
                    if merged_tags:
                        content += f" | 标签：{', '.join(str(t) for t in merged_tags[:5])}"
                    try:
                        sqlite_service.add_episodic_log(
                            user_id=user_id, content=content, importance=0.85,
                            event_type="user_missed", session_id=session_id or "",
                            question_id=question_id, score=score_display,
                        )
                        sqlite_service.add_note(
                            user_id=user_id, content=content,
                            question_id=question_id,
                            note_type="weakness", tags=["遗漏点"] + [str(t) for t in merged_tags[:3]],
                        )
                    except Exception as _ex:
                        logger.debug("submit_answer 内联记录遗漏点失败: %s", _ex)
                for ep in error_points:
                    if not isinstance(ep, dict):
                        continue
                    w, c = ep.get("wrong", ""), ep.get("correct", "")
                    content = (
                        f"混淆点：用户说的「{w}」应改为「{c}」"
                        if w and c and w != c else f"混淆点：{w or c}"
                    )
                    if merged_tags:
                        content += f" | 标签：{', '.join(str(t) for t in merged_tags[:5])}"
                    try:
                        sqlite_service.add_episodic_log(
                            user_id=user_id, content=content, importance=0.85,
                            event_type="user_confusion", session_id=session_id or "",
                            question_id=question_id, score=score_display,
                        )
                        sqlite_service.add_note(
                            user_id=user_id, content=content,
                            question_id=question_id,
                            note_type="confusion", tags=["混淆点"] + [str(t) for t in merged_tags[:3]],
                        )
                    except Exception as _ex:
                        logger.debug("submit_answer 内联记录混淆点失败: %s", _ex)

            # 同时更新对话历史，记录评分结果
            if session_id:
                sqlite_service.update_session_history(
                    session_id=session_id,
                    role="assistant",
                    content=f"✅ 评分完成：{score_display:.1f}/5\n\n{feedback}",
                    message_id=message_id,
                    metadata={
                        "type": "answer_evaluation",
                        "question_id": question_id,
                        "score": score_display,
                        "sm2": sm2
                    }
                )

            note_count = len(missed_points) + len(error_points)
            if record_weakness_notes:
                weak_msg = (f" 已自动记录 {note_count} 条遗漏/混淆点。" if note_count else "")
            else:
                weak_msg = (f" 薄弱点（遗漏/混淆）将由 record_weakness 工具记录（预计 {note_count} 条）。"
                            if note_count else " 薄弱点（遗漏/混淆）由 record_weakness 工具记录。")
            result = {
                "score": score_display,
                "feedback": feedback,
                "shortcomings": [],
                "strong_points": strong_points,
                "missed_points": missed_points,
                "error_points": error_points,
                "tags": merged_tags,
                "standard_answer": reference_answer or "",
                "sm2": sm2,
                "message_id": message_id,
                "message": (
                    f"评分完成：{score_display:.1f}/5。"
                    + ("下次复习：" + sm2["next_review_at"] if sm2 else "")
                    + weak_msg
                ),
            }
            return ToolResponse.success(
                text=json.dumps(result, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.exception("submit_answer failed")
            return ToolResponse.error(code="EXECUTION_ERROR", message=f"submit_answer failed: {e}")

class RecordWeaknessTool(Tool):
    """记录：混淆点、遗漏点，供学习报告展示。"""
    def __init__(self):
        super().__init__(
            name="record_weakness",
            description=(
                "【意图】把“遗漏点/混淆点”写入本地薄弱点 note（episodic_log + user_notes），用于学习报告展示。"
                "【功能】不打分、不评估；只做持久化。"
                "【填槽】confusion_points 与 missed_points 至少提供一个；tags 可选。"
                "【返回】{success, reason, message, count}；失败也返回结构化原因。"
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
            return ToolResponse.success(
                text=json.dumps(
                    {
                        "success": False,
                        "reason": "参数不足：请提供 confusion_points 或 missed_points",
                        "message": "未记录任何薄弱点",
                        "count": 0,
                    },
                    ensure_ascii=False,
                )
            )

        try:
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
                    # 同步写入 user_notes，供「我记录的薄弱点」页面展示
                    try:
                        sqlite_service.add_note(
                            user_id=user_id,
                            content=content,
                            note_type="confusion",
                            tags=["混淆点"] + [str(t) for t in tags[:3]],
                        )
                    except Exception as _ex:
                        logger.debug("RecordWeaknessTool add_note(混淆) 忽略: %s", _ex)
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
                    # 同步写入 user_notes，供「我记录的薄弱点」页面展示
                    try:
                        sqlite_service.add_note(
                            user_id=user_id,
                            content=content,
                            note_type="weakness",
                            tags=["遗漏点"] + [str(t) for t in tags[:3]],
                        )
                    except Exception as _ex:
                        logger.debug("RecordWeaknessTool add_note(遗漏) 忽略: %s", _ex)
                    count += 1
            return ToolResponse.success(
                text=json.dumps(
                    {
                        "success": True,
                        "reason": "记录成功",
                        "message": f"已记录 {count} 条薄弱点",
                        "count": count,
                    },
                    ensure_ascii=False,
                )
            )
        except Exception as e:
            logger.exception("record_weakness failed")
            return ToolResponse.success(
                text=json.dumps(
                    {
                        "success": False,
                        "reason": f"记录失败: {str(e)[:200]}",
                        "message": "写入薄弱点时出现异常",
                        "count": 0,
                    },
                    ensure_ascii=False,
                )
            )


class ManageNoteTool(Tool):
    """查库+写：笔记 CRUD。"""
    def __init__(self):
        super().__init__(
            name="manage_note",
            description=(
                "【调用时机】用户说「记一下」「保存笔记」→ create；「查看笔记」→ list；「修改/删除笔记」→ update/delete。"
                "【功能】笔记增删改查。action=create/list/update/delete。"
                "【填槽】action 必填；create 需 content；update/delete 需 note_id；list 可选 keyword/tags/question_id。"
                "【返回】create：记录成功返回 note_id、message；记录失败返回原因（如缺少 content）。list：返回笔记列表、count。update/delete：记录成功返回 success、message；记录失败或未找到返回原因。"
                "【严禁】出题、练习、评分场景严禁调用。"
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
    """查库：本次会话统计。"""
    def __init__(self):
        super().__init__(
            name="get_session_context",
            description=(
                "【调用时机】用户说「做了几道」「会话进度」「今天练了几题」时。"
                "【功能】根据当前 session_id 统计本次会话内的答题记录。"
                "【返回】本次会话已做题数（total_questions）、平均分（avg_score）、已练标签（tags_practiced）、说明文案；无活跃会话时返回 total=0、空 records。失败时返回原因。"
                "【严禁】用户说「我想练习这道题」时严禁调用。"
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
    """查库：历史掌握度、薄弱点、复习建议。"""
    def __init__(self):
        super().__init__(
            name="get_mastery_report",
            description=(
                "【意图】用户要“复习/薄弱点/错题总结/总结薄弱点/今天的遗漏/这周的错题”。"
                "【功能】汇总历史掌握度与薄弱标签，返回薄弱题样例、用户记录的遗漏/混淆点（note）、以及遗忘曲线待复习题 + 建议文案。"
                "【填槽】date_from/date_to 可选：仅当用户明确说时间时才传（今天/近三天/近7天/或 YYYY-MM-DD）。"
                "【返回】JSON：{total_questions_practiced, overall_avg_score, correct_rate_pct, mastery_by_level, weak_tags, weak_questions, weakness_notes, review_questions, advice}。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("date_from", "string",
                          "仅当用户明确说时间时填：今天/今日、近三天、近7天、YYYY-MM-DD；未指定时不传（全部）", required=False),
            ToolParameter("date_to", "string",
                          "仅当用户明确说时间时填：今天/今日、YYYY-MM-DD；未指定时不传（全部）", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        date_from = (parameters.get("date_from") or "").strip() or None
        date_to = (parameters.get("date_to") or "").strip() or None

        # 日期填槽：今天、近三天、这周 等口语化解析
        from datetime import datetime, timedelta
        _now = datetime.now()
        _today = _now.strftime("%Y-%m-%d")
        if date_from and date_from in ("今天", "今日"):
            date_from, date_to = _today, _today
        elif date_from and "近" in date_from and "天" in date_from:
            try:
                n = int("".join(c for c in date_from if c.isdigit()) or "3")
                date_from = (_now - timedelta(days=n)).strftime("%Y-%m-%d")
                date_to = _today
            except (ValueError, TypeError):
                date_from = (_now - timedelta(days=3)).strftime("%Y-%m-%d")
                date_to = _today
        elif date_to and date_to in ("今天", "今日"):
            date_to = _today
        if not date_to:
            date_to = _today

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

            # 从 note（episodic_log）获取日期范围内的薄弱点
            weakness_notes = sqlite_service.get_user_weakness_notes(
                user_id, limit=15, date_from=date_from, date_to=date_to
            )
            
            report = {
                "total_questions_practiced": summary["total_questions_practiced"],
                "overall_avg_score": round(summary["overall_avg_score"], 2),
                "correct_rate_pct": round(summary["correct_rate"], 1),
                "mastery_by_level": by_level,
                "weak_tags": weak_tags,
                "weak_questions": weak_questions,
                "weakness_notes": [{"content": n["content"], "event_type": n["event_type"], "created_at": n["created_at"]} for n in weakness_notes],
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
    """查库+图库：延伸知识点、相关题目、学习资源。"""
    def __init__(self):
        super().__init__(
            name="get_knowledge_recommendation",
            description=(
                "【调用时机】用户说「延伸一下」「拓展考点」「还有哪些相关」「推荐学习资料」时。"
                "【功能】根据 topic 或当前 question_id 从知识图谱取相关概念、延伸题目、学习资源及近期错题。"
                "【填槽】topic（知识点名）、question_id（当前题 ID 可选）、limit_concepts、limit_questions。"
                "【返回】related_concepts（相关知识点）、extension_questions（延伸题列表）、resources（学习资源）、recent_mistakes（近期错题）；失败时返回原因。"
                "【严禁】用户说「我想练习这道题」时严禁调用。"
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
    """记录：更新用户画像。Agent 解析简历，工具只持久化。"""
    def __init__(self):
        super().__init__(
            name="analyze_resume",
            description=(
                "【调用时机】用户粘贴简历或说「分析我的简历」时，你解析后调用此工具记录。"
                "【功能】将解析出的技术栈、目标岗位、经验级别等写入用户画像（user_profiles），不调用外部 LLM。"
                "【填槽】resume_text、tech_stack、target_position、experience_level 必填；target_company、preferred_topics 可选。"
                "【返回】记录成功：message（简历分析完成，用户画像已更新）、tech_stack、target_position、experience_level 等摘要；记录失败：返回失败原因（如 resume_text 为空）。"
                "【严禁】出题、练习、评分场景严禁调用。"
            ),
        )

    def get_parameters(self):
        return [
            ToolParameter("resume_text", "string", "用户简历全文", required=True),
            ToolParameter("tech_stack", "array", "技术栈列表，如 [\"Java\", \"Redis\"]", required=True),
            ToolParameter("target_position", "string", "目标岗位", required=True),
            ToolParameter("experience_level", "string", "经验级别：junior|mid|senior", required=True),
            ToolParameter("target_company", "string", "目标公司（可空）", required=False),
            ToolParameter("preferred_topics", "array", "偏好知识点，如 [\"JVM\", \"MySQL\"]", required=False),
        ]

    def run(self, parameters):
        user_id = get_current_user_id()
        resume_text = (parameters.get("resume_text") or "").strip()
        if not resume_text:
            return ToolResponse.error(code="INVALID_PARAM", message="resume_text 不能为空")
        try:
            tech_stack = parameters.get("tech_stack") or []
            target_position = (parameters.get("target_position") or "").strip()
            experience_level = (parameters.get("experience_level") or "junior").strip().lower()
            target_company = (parameters.get("target_company") or "").strip()
            preferred_topics = parameters.get("preferred_topics") or []
            if isinstance(tech_stack, str):
                try:
                    tech_stack = json.loads(tech_stack) if tech_stack.strip().startswith("[") else [tech_stack]
                except Exception:
                    tech_stack = [tech_stack] if tech_stack else []
            if isinstance(preferred_topics, str):
                try:
                    preferred_topics = json.loads(preferred_topics) if preferred_topics.strip().startswith("[") else [preferred_topics]
                except Exception:
                    preferred_topics = [preferred_topics] if preferred_topics else []
            if experience_level not in ("junior", "mid", "senior"):
                experience_level = "junior"

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
        GetSessionContextTool(),
        GetRecommendedQuestionTool(),
        FindSimilarQuestionsTool(),
        FilterQuestionsTool(),
        GetQuestionDetailTool(),
        SubmitAnswerTool(),
        RecordWeaknessTool(),
        ManageNoteTool(),
        GetMasteryReportTool(),
        GetKnowledgeRecommendationTool(),
        AnalyzeResumeTool(),
    ]
