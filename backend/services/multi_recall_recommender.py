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

        # 1. ????
        if weights.get("vector", 0) > 0:
            try:
                from backend.tools.knowledge_manager_tools import generate_embedding
                q = (query or company or "").strip() or (tags[0] if tags else "")
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

        # 2. ??/?????SQLite?
        if weights.get("popular", 0) > 0:
            try:
                sq = sqlite_service.filter_questions(
                    company=company,
                    difficulty=difficulty,
                    tags=tags,
                    keyword=query[:80] if query and len(query) > 10 else None,
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

        # 4. ???
        query_text = (query or company or (tags[0] if tags else "") or "").strip()
        if query_text and settings.rerank_enabled and len(candidates) > 1:
            try:
                reranked = rerank_candidates(
                    query=query_text[:2048],
                    candidates=candidates,
                    text_key="question_text",
                    top_n=top_n,
                )
                return _normalize_output(reranked)
            except Exception as e:
                logger.warning("[MultiRecall] ????: %s??????????", e)

        candidates.sort(key=lambda x: x.get("recall_score", 0), reverse=True)
        return _normalize_output(candidates[:top_n])


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


multi_recall_recommender = MultiRecallRecommender()
