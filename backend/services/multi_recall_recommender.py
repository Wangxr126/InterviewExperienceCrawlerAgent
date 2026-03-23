"""
?????????? + ?? + ???? + ????
"""
import json
import logging
from typing import Any, Dict, List, Optional, Set

from backend.config.config import settings
from backend.services.storage.neo4j_service import neo4j_service
from backend.services.storage.sqlite_service import sqlite_service
from backend.services.rerank_service import rerank_candidates

logger = logging.getLogger(__name__)

DEFAULT_RECALL_WEIGHTS = {
    "vector": 0.4,
    "popular": 0.3,
    "review": 0.3,
}


def _to_question_item(row: Dict, source: str, score: float = 0.5) -> Dict[str, Any]:
    """????????"""
    q_id = str(row.get("id") or row.get("q_id") or row.get("question_id") or "")
    text = row.get("text") or row.get("question_text") or ""
    tags = row.get("topic_tags") or row.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags) if tags else []
        except Exception:
            tags = []
    return {
        "q_id": q_id,
        "question_text": text,
        "answer_text": row.get("answer") or row.get("answer_text") or "",
        "difficulty": row.get("difficulty") or "medium",
        "company": row.get("company") or "",
        "topic_tags": tags if isinstance(tags, list) else [],
        "recall_source": source,
        "recall_sources": [source],
        "recall_score": score,
    }


class MultiRecallRecommender:
    """???? + ???"""

    def recommend(
        self,
        user_id: str,
        query: Optional[str] = None,
        company: Optional[str] = None,
        difficulty: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_n: int = 10,
        exclude_ids: Optional[Set[str]] = None,
        recall_weights: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        ???? + ???? + ???
        """
        exclude_ids = exclude_ids or set()
        weights = recall_weights or DEFAULT_RECALL_WEIGHTS
        merged: Dict[str, Dict] = {}

        # 自动注入薄弱标签：当无 query/tags 且有 user_id 时，用薄弱点作为召回依据
        effective_query = (query or company or "").strip()
        effective_tags = list(tags) if tags else []
        if not effective_query and not effective_tags and user_id:
            weak = sqlite_service.get_weak_tags(user_id)[:5]
            if weak:
                effective_tags = [w.get("tag", "") for w in weak if w.get("tag")]
                effective_query = " ".join(effective_tags) if effective_tags else ""

        if not effective_tags and tags:
            effective_tags = list(tags)
        if not effective_query and effective_tags:
            effective_query = effective_tags[0] if effective_tags else ""

        # 1. 向量召回（薄弱点相似题 / query 语义相似）
        if weights.get("vector", 0) > 0:
            try:
                from backend.services.knowledge.knowledge_tools import generate_embedding
                q = effective_query or (effective_tags[0] if effective_tags else "")
                if q:
                    emb = generate_embedding(q[:2048])
                    if emb and neo4j_service.available:
                        vec_results = neo4j_service.search_similar(
                            emb,
                            top_k=min(settings.retrieval_search_top_k, top_n * 3),
                            score_threshold=settings.retrieval_score_threshold,
                            exclude_ids=list(exclude_ids),
                        )
                        for r in vec_results:
                            q_id = str(r.get("id", ""))
                            if q_id and q_id not in exclude_ids:
                                item = _to_question_item(r, "vector", float(r.get("score", 0.5)))
                                _merge_item(merged, item, "vector", weights["vector"])
            except Exception as e:
                logger.debug("[MultiRecall] ??????: %s", e)

        # 2. 热门/标签 SQLite 召回
        if weights.get("popular", 0) > 0:
            try:
                sq = sqlite_service.filter_questions(
                    company=company,
                    difficulty=difficulty,
                    tags=effective_tags or tags,
                    keyword=(effective_query or query or "")[:80] if (effective_query or query) and len(effective_query or query or "") > 10 else None,
                    limit=top_n * 2,
                )
                for r in sq:
                    q_id = str(r.get("q_id", ""))
                    if q_id and q_id not in exclude_ids:
                        item = _to_question_item(r, "popular", 0.5)
                        _merge_item(merged, item, "popular", weights["popular"])
            except Exception as e:
                logger.debug("[MultiRecall] ??????: %s", e)

        # 3. ??????
        if weights.get("review", 0) > 0 and user_id:
            try:
                due = sqlite_service.get_due_reviews(user_id, limit=top_n)
                for r in due:
                    q_id = str(r.get("question_id", ""))
                    if q_id and q_id not in exclude_ids:
                        item = _to_question_item(
                            {
                                "q_id": q_id,
                                "question_text": r.get("question_text", ""),
                                "answer_text": r.get("answer_text", ""),
                                "topic_tags": r.get("topic_tags"),
                                "difficulty": r.get("difficulty", "medium"),
                                "company": r.get("company", ""),
                            },
                            "review",
                            0.8,
                        )
                        _merge_item(merged, item, "review", weights["review"])
            except Exception as e:
                logger.debug("[MultiRecall] ????????: %s", e)

        candidates = list(merged.values())
        if not candidates:
            return []

        # 4. Rerank
        query_text = (effective_query or query or company or (effective_tags or tags or [""])[0] or "").strip()
        if query_text and settings.rerank_enabled and len(candidates) > 1:
            try:
                reranked = rerank_candidates(
                    query=query_text[:2048],
                    candidates=candidates,
                    text_key="question_text",
                    top_n=top_n,
                    trace_slug="multi_recall",
                    trace_meta={
                        "top_n": top_n,
                        "user_id": user_id,
                        "exclude_count": len(exclude_ids),
                    },
                )
                return _normalize_output(reranked)
            except Exception as e:
                logger.warning("[MultiRecall] ????: %s??????????", e)

        candidates.sort(key=lambda x: x.get("recall_score", 0), reverse=True)
        return _normalize_output(candidates[:top_n])

    def recommend_smart_practice(
        self,
        user_id: str,
        top_n: Optional[int] = None,
        company: Optional[str] = None,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source_platform: Optional[str] = None,
    ) -> tuple[List[Dict[str, Any]], bool]:
        """
        智能练习：按规则「知识点不足 N 条 + 随机 M 条」出题。
        - 知识点不足：薄弱点向量相似 + 到期复习（遗忘曲线）多路召回，召回条数 = N * RECALL_RATIO，再经 Reranker 取 top N。
        - 随机：纯随机 M 条，排除已选与已做。
        总题数 = N + M，N/M 及召回比例等均由 .env 配置。
        返回 (questions, is_review_mode)。
        """
        kg_count = settings.smart_practice_knowledge_gap_count
        random_count = settings.smart_practice_random_count
        recall_ratio = settings.smart_practice_recall_ratio
        rerank_enabled = settings.smart_practice_rerank_enabled
        w_vector = settings.smart_practice_vector_weight
        w_review = settings.smart_practice_review_weight
        w_popular = settings.smart_practice_popular_weight
        weak_tags_limit = settings.smart_practice_weak_tags_limit

        seen_ids: Set[str] = set()
        if user_id:
            history = sqlite_service.get_study_history(user_id, limit=500)
            seen_ids = {str(r["question_id"]) for r in history if r.get("question_id")}

        # 1) 知识点不足一路：召回量 = N * 比例
        recall_k = max(kg_count, int(kg_count * recall_ratio))
        effective_query = ""
        effective_tags: List[str] = list(tags) if tags else []
        if user_id:
            weak = sqlite_service.get_weak_tags(user_id)[:weak_tags_limit]
            if weak:
                effective_tags = [w.get("tag", "") for w in weak if w.get("tag")]
                effective_query = " ".join(effective_tags) if effective_tags else ""
        if not effective_query and effective_tags:
            effective_query = effective_tags[0] if effective_tags else ""

        merged: Dict[str, Dict] = {}

        # 1a) 向量召回（薄弱点相似）
        if w_vector > 0 and effective_query:
            try:
                from backend.services.knowledge.knowledge_tools import generate_embedding
                emb = generate_embedding(effective_query[:2048])
                if emb and neo4j_service.available:
                    vec_results = neo4j_service.search_similar(
                        emb,
                        top_k=min(settings.retrieval_search_top_k, recall_k * 2),
                        score_threshold=settings.retrieval_score_threshold,
                        exclude_ids=list(seen_ids),
                    )
                    for r in vec_results:
                        q_id = str(r.get("id", ""))
                        if q_id and q_id not in seen_ids:
                            item = _to_question_item(r, "vector", float(r.get("score", 0.5)))
                            _merge_item(merged, item, "vector", w_vector)
            except Exception as e:
                logger.debug("[SmartPractice] 向量召回异常: %s", e)

        # 1b) 到期复习（遗忘曲线）
        if w_review > 0 and user_id:
            try:
                due = sqlite_service.get_due_reviews(user_id, limit=recall_k)
                for r in due:
                    q_id = str(r.get("question_id", ""))
                    if q_id and q_id not in seen_ids:
                        item = _to_question_item(
                            {
                                "q_id": q_id,
                                "question_text": r.get("question_text", ""),
                                "answer_text": r.get("answer_text", ""),
                                "topic_tags": r.get("topic_tags"),
                                "difficulty": r.get("difficulty", "medium"),
                                "company": r.get("company", ""),
                            },
                            "review",
                            0.8,
                        )
                        _merge_item(merged, item, "review", w_review)
            except Exception as e:
                logger.debug("[SmartPractice] 到期复习召回异常: %s", e)

        # 1c) 热门/标签补充（可选）
        if w_popular > 0:
            try:
                sq = sqlite_service.filter_questions(
                    company=company,
                    difficulty=difficulty,
                    tags=effective_tags or tags,
                    keyword=effective_query[:80] if len(effective_query or "") > 10 else None,
                    limit=recall_k,
                )
                for r in sq:
                    q_id = str(r.get("q_id", ""))
                    if q_id and q_id not in seen_ids:
                        item = _to_question_item(r, "popular", 0.5)
                        _merge_item(merged, item, "popular", w_popular)
            except Exception as e:
                logger.debug("[SmartPractice] 热门召回异常: %s", e)

        knowledge_gap_candidates = list(merged.values())
        if rerank_enabled and effective_query and len(knowledge_gap_candidates) > 1:
            try:
                knowledge_gap_list = rerank_candidates(
                    query=effective_query[:2048],
                    candidates=knowledge_gap_candidates,
                    text_key="question_text",
                    top_n=kg_count,
                    trace_slug="smart_practice",
                    trace_meta={
                        "kg_count": kg_count,
                        "recall_k": recall_k,
                        "user_id": user_id,
                    },
                )
            except Exception as e:
                logger.warning("[SmartPractice] Rerank 失败，降级按分数取 top: %s", e)
                knowledge_gap_candidates.sort(key=lambda x: x.get("recall_score", 0), reverse=True)
                knowledge_gap_list = knowledge_gap_candidates[:kg_count]
        else:
            knowledge_gap_candidates.sort(key=lambda x: x.get("recall_score", 0), reverse=True)
            knowledge_gap_list = knowledge_gap_candidates[:kg_count]

        knowledge_gap_list = _normalize_output(knowledge_gap_list)
        # 标记智能练习类型：推荐题（知识点不足）
        for q in knowledge_gap_list:
            q.setdefault("smart_type", "recommend")
            _attach_smart_practice_meta(q, effective_tags)
        chosen_ids = {q.get("q_id", "") for q in knowledge_gap_list if q.get("q_id")}
        chosen_ids |= seen_ids
        chosen_ids = {x for x in chosen_ids if x}

        # 2) 随机一路：固定 M 条
        need_random = random_count
        random_list: List[Dict[str, Any]] = []
        if need_random > 0:
            extra = sqlite_service.filter_questions_random_exclude(
                user_id=user_id or "",
                limit=need_random,
                exclude_ids=list(chosen_ids),
                company=company,
                difficulty=difficulty,
                question_type=question_type,
                tags=tags,
                source_platform=source_platform,
            )
            random_list = _normalize_output(extra)
            for q in random_list:
                q.setdefault("smart_type", "random")
                _attach_smart_practice_meta(q, effective_tags)

        result = knowledge_gap_list + random_list
        is_review_mode = any(
            (q.get("recall_sources") or []) and "review" in (q.get("recall_sources") or [])
            for q in knowledge_gap_list
        )
        return result, is_review_mode


def _merge_item(merged: Dict, item: Dict, source: str, weight: float):
    q_id = item.get("q_id", "")
    if not q_id:
        return
    score = item.get("recall_score", 0) * weight
    if q_id in merged:
        merged[q_id]["recall_score"] += score
        if source not in merged[q_id]["recall_sources"]:
            merged[q_id]["recall_sources"].append(source)
    else:
        item["recall_score"] = score
        merged[q_id] = item


def _normalize_output(items: List[Dict]) -> List[Dict]:
    """??????????"""
    out = []
    for x in items:
        o = dict(x)
        o.setdefault("topic_tags", [])
        if isinstance(o.get("topic_tags"), str):
            try:
                o["topic_tags"] = json.loads(o["topic_tags"]) if o["topic_tags"] else []
            except Exception:
                o["topic_tags"] = []
        out.append(o)
    return out


def _attach_smart_practice_meta(q: Dict[str, Any], effective_tags: List[str]) -> None:
    """
    为智能练习题目附加推荐理由与薄弱标签上下文，供前端展示「为何推荐本题」。
    """
    st = q.get("smart_type") or "recommend"
    if st == "random":
        q["smart_weak_tags"] = []
        q["smart_recommend_reason"] = "随机拓展练习，均衡覆盖面"
        return
    sources = list(q.get("recall_sources") or [])
    tags_clean = [t for t in (effective_tags or []) if t]
    q["smart_weak_tags"] = tags_clean
    parts: List[str] = []
    if "vector" in sources:
        if tags_clean:
            shown = "、".join(tags_clean[:8])
            parts.append(f"结合你的薄弱标签「{shown}」做的相似题召回")
        else:
            parts.append("向量语义相似召回（当前筛选条件）")
    if "review" in sources:
        parts.append("遗忘曲线到期，适合巩固复习")
    if "popular" in sources and not parts:
        parts.append("在当前筛选条件下的标签/热门补充")
    if not parts:
        parts.append("知识点补强推荐")
    q["smart_recommend_reason"] = "；".join(parts)


multi_recall_recommender = MultiRecallRecommender()
