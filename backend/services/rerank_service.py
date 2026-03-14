"""
检索重排服务：使用 Ollama Qwen3-Reranker 对向量检索结果进行重排
Ollama /api/rerank 接口：query + documents -> relevance_score 排序
"""
import logging
import requests
from typing import List, Dict, Any, Optional

from backend.config.config import settings

logger = logging.getLogger(__name__)


def rerank(
    query: str,
    documents: List[str],
    top_n: Optional[int] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    """
    使用 Ollama Reranker 对文档按与 query 的相关性重排。

    Args:
        query: 查询文本
        documents: 待重排的文档列表（文本）
        top_n: 返回前 N 条，None 则全部返回（已按分数降序）
        model: 重排模型名，None 用配置
        base_url: Ollama 地址，None 用配置
        timeout: 超时秒数

    Returns:
        [{"index": int, "document": str, "relevance_score": float}, ...]
        按 relevance_score 降序
    """
    if not query or not documents:
        return []
    enabled = getattr(settings, "rerank_enabled", True)
    if not enabled:
        return [{"index": i, "document": d, "relevance_score": 0.0} for i, d in enumerate(documents)]

    model = model or settings.rerank_model
    base_url = (base_url or settings.rerank_ollama_url).rstrip("/")
    top_n = top_n if top_n is not None else settings.rerank_top_n
    url = f"{base_url}/api/rerank"

    # 截断过长文档，避免超时
    max_doc_len = getattr(settings, "rerank_max_doc_length", 1024)
    doc_texts = [str(d)[:max_doc_len] for d in documents]

    payload = {
        "model": model,
        "query": query[:2048],
        "top_n": min(top_n, len(doc_texts)) if top_n else len(doc_texts),
        "documents": doc_texts,
    }
    timeout = timeout or getattr(settings, "rerank_timeout", 60)
    try:
        logger.info("[Rerank] 调用 model=%s query_len=%d docs=%d top_n=%d",
                    model, len(query), len(documents), payload["top_n"])
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("[Rerank] 失败 status=%d %s", resp.status_code, resp.text[:200])
            return [{"index": i, "document": d, "relevance_score": 0.0} for i, d in enumerate(documents)]

        data = resp.json()
        results = data.get("results") or []
        # Ollama 返回格式: [{"document": str, "relevance_score": float}, ...]
        out = []
        for i, r in enumerate(results):
            doc = r.get("document", "")
            score = float(r.get("relevance_score", 0))
            # 找回原始 index（通过 document 匹配，或按顺序）
            orig_idx = i
            for j, d in enumerate(doc_texts):
                if d == doc or doc in d or d in doc:
                    orig_idx = j
                    break
            out.append({"index": orig_idx, "document": doc, "relevance_score": score})
        logger.info("[Rerank] 完成 返回 %d 条", len(out))
        return out
    except Exception as e:
        logger.warning("[Rerank] 异常: %s，降级返回原序", e)
        return [{"index": i, "document": d, "relevance_score": 0.0} for i, d in enumerate(documents)]


def rerank_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    text_key: str = "text",
    top_n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    对候选列表（如题目列表）按 query 重排，保留原有字段并附加 rerank_score。

    Args:
        query: 查询文本
        candidates: 候选列表，每项为 dict，需含 text_key 指定字段作为文档内容
        text_key: 用作文档内容的字段名
        top_n: 返回前 N 条

    Returns:
        重排后的候选列表，每项附加 "rerank_score"
    """
    if not candidates:
        return []
    texts = [c.get(text_key) or c.get("question_text") or str(c) for c in candidates]
    reranked = rerank(query, texts, top_n=top_n or len(candidates))
    # rerank 返回 [{"index": int, "document": str, "relevance_score": float}] 按相关性降序
    # 通过 index 或 document 匹配回原候选
    out = []
    used_idx = set()
    for r in reranked:
        idx = r["index"]
        if idx < len(candidates) and idx not in used_idx:
            used_idx.add(idx)
            item = dict(candidates[idx])
            item["rerank_score"] = r["relevance_score"]
            out.append(item)
        else:
            # 兜底：按 document 文本匹配
            doc = r.get("document", "")
            for i, t in enumerate(texts):
                if i not in used_idx and (doc == t or doc in t or t in doc):
                    used_idx.add(i)
                    item = dict(candidates[i])
                    item["rerank_score"] = r["relevance_score"]
                    out.append(item)
                    break
        if top_n and len(out) >= top_n:
            break
    return out
