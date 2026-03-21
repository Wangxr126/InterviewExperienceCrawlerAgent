"""
检索重排服务：
- RERANK_MODE=ollama：优先 POST /api/rerank；旧版 Ollama 无该接口时降级为 Embedding 余弦重排。
- RERANK_MODE=remote：调用阿里云百炼 compatible-api/v1/reranks（如 qwen3-rerank）；失败时同样降级。
"""
import logging
from typing import List, Dict, Any, Optional

import numpy as np
import requests

from backend.config.config import settings

logger = logging.getLogger(__name__)


def _cosine_scores(query_vec: List[float], doc_vecs: List[List[float]]) -> np.ndarray:
    q = np.asarray(query_vec, dtype=np.float64)
    qn = float(np.linalg.norm(q))
    if qn <= 0:
        return np.zeros(len(doc_vecs), dtype=np.float64)
    mat = np.asarray(doc_vecs, dtype=np.float64)
    dn = np.linalg.norm(mat, axis=1)
    dn = np.where(dn <= 0, 1e-12, dn)
    return (mat @ q) / (qn * dn)


def _embed_texts_for_rerank_fallback(texts: List[str], timeout: int) -> Optional[List[List[float]]]:
    """批量取向量：Ollama 走 /api/embed 单次请求，失败则逐条 generate_embedding。"""
    if not texts:
        return []
    t = (settings.embed_model_type or "").lower().strip()
    if t == "ollama":
        url = f"{settings.embed_ollama_url.rstrip('/')}/api/embed"
        payload = {"model": settings.embed_model_name, "input": [str(x)[:2048] for x in texts]}
        try:
            to = max(int(timeout), 30 + len(texts) * 8)
            resp = requests.post(url, json=payload, timeout=to)
            if resp.status_code == 200:
                data = resp.json()
                embs = data.get("embeddings")
                if isinstance(embs, list) and len(embs) == len(texts):
                    return embs
        except Exception as e:
            logger.debug("[Rerank] 批量 Embedding 失败，尝试逐条: %s", e)
    try:
        from backend.tools.knowledge_manager_tools import generate_embedding
    except ImportError:
        return None
    out: List[List[float]] = []
    for x in texts:
        v = generate_embedding(str(x)[:2048])
        if not v:
            return None
        out.append(v)
    return out


def _parse_remote_rerank_response(
    data: Any, doc_texts: List[str]
) -> Optional[List[Dict[str, Any]]]:
    """解析百炼 compatible /reranks 或文档中的 output.results 结构。"""
    if not isinstance(data, dict):
        return None
    results = data.get("output", {}).get("results") if isinstance(data.get("output"), dict) else None
    if results is None:
        results = data.get("results")
    if not isinstance(results, list):
        return None
    out: List[Dict[str, Any]] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        idx = r.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(doc_texts):
            continue
        score = float(r.get("relevance_score", 0.0))
        out.append(
            {"index": idx, "document": doc_texts[idx], "relevance_score": score}
        )
    return out if out else None


def _rerank_remote_dashscope(
    query: str,
    doc_texts: List[str],
    top_n: int,
    timeout: int,
    model: str,
) -> Optional[List[Dict[str, Any]]]:
    """阿里云百炼文本重排（compatible-api/v1/reranks）。"""
    api_key = (getattr(settings, "rerank_remote_api_key", None) or "").strip()
    if not api_key:
        logger.warning("[Rerank] remote 模式需要配置 RERANK_API_KEY 或 EMBED_API_KEY")
        return None
    base = getattr(
        settings, "rerank_remote_base_url", "https://dashscope.aliyuncs.com/compatible-api/v1"
    ).rstrip("/")
    url = f"{base}/reranks"
    n_docs = len(doc_texts)
    tn = min(top_n, n_docs) if top_n else n_docs
    payload: Dict[str, Any] = {
        "model": model,
        "query": query[:2048],
        "documents": doc_texts,
        "top_n": tn,
    }
    instruct = (getattr(settings, "rerank_instruct", None) or "").strip()
    if instruct:
        payload["instruct"] = instruct
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        logger.info(
            "[Rerank] remote 调用 model=%s docs=%d top_n=%d",
            model,
            n_docs,
            tn,
        )
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            logger.warning(
                "[Rerank] remote HTTP %s %s",
                resp.status_code,
                resp.text[:300],
            )
            return None
        data = resp.json()
        if isinstance(data, dict) and data.get("code"):
            logger.warning(
                "[Rerank] remote 错误 %s: %s",
                data.get("code"),
                (data.get("message") or "")[:200],
            )
            return None
        parsed = _parse_remote_rerank_response(data, doc_texts)
        if not parsed:
            logger.warning("[Rerank] remote 响应无法解析: %s", str(data)[:400])
            return None
        logger.info("[Rerank] remote 完成 返回 %d 条", len(parsed))
        return parsed
    except Exception as e:
        logger.warning("[Rerank] remote 异常: %s", e)
        return None


def probe_remote_rerank(timeout: Optional[int] = None) -> bool:
    """启动预热：发一条最小 remote rerank 请求验证 Key 与网络。"""
    t = timeout if timeout is not None else getattr(settings, "rerank_timeout", 60)
    model = settings.rerank_model
    got = _rerank_remote_dashscope(
        "warmup",
        ["warmup doc a", "warmup doc b"],
        2,
        min(int(t), 60),
        model,
    )
    return bool(got and len(got) >= 1)


def _rerank_via_embedding_cosine(
    query: str,
    doc_texts: List[str],
    top_n: int,
    timeout: int,
) -> Optional[List[Dict[str, Any]]]:
    all_texts = [query[:2048]] + [str(d) for d in doc_texts]
    vecs = _embed_texts_for_rerank_fallback(all_texts, timeout)
    if not vecs or len(vecs) != len(all_texts):
        return None
    qv, dvecs = vecs[0], vecs[1:]
    scores = _cosine_scores(qv, dvecs)
    n = len(doc_texts)
    order = list(range(n))
    order.sort(key=lambda i: scores[i], reverse=True)
    if top_n and top_n < n:
        order = order[:top_n]
    return [
        {"index": i, "document": doc_texts[i], "relevance_score": float(scores[i])}
        for i in order
    ]


def rerank(
    query: str,
    documents: List[str],
    top_n: Optional[int] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: int = 60,
) -> List[Dict[str, Any]]:
    """
    对文档按与 query 的相关性重排（Ollama /api/rerank 或百炼 remote，见 RERANK_MODE）。

    Args:
        query: 查询文本
        documents: 待重排的文档列表（文本）
        top_n: 返回前 N 条，None 则全部返回（已按分数降序）
        model: 重排模型名，None 用配置
        base_url: Ollama 地址（仅 ollama 模式），None 用配置
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
    top_n = top_n if top_n is not None else settings.rerank_top_n

    # 截断过长文档，避免超时
    max_doc_len = getattr(settings, "rerank_max_doc_length", 1024)
    doc_texts = [str(d)[:max_doc_len] for d in documents]

    eff_timeout = timeout if (timeout and timeout > 0) else getattr(
        settings, "rerank_timeout", 60
    )
    mode = getattr(settings, "rerank_mode", "ollama").lower().strip()

    if mode in ("remote", "dashscope", "bailian"):
        want_n = min(top_n, len(doc_texts)) if top_n else len(doc_texts)
        remote_out = _rerank_remote_dashscope(
            query, doc_texts, want_n, eff_timeout, model
        )
        if remote_out is not None:
            return remote_out
        fb = _rerank_via_embedding_cosine(query, doc_texts, want_n, eff_timeout)
        if fb is not None:
            logger.info(
                "[Rerank] remote 不可用，已用 Embedding(%s) 余弦重排",
                settings.embed_model_name,
            )
            return fb
        return [{"index": i, "document": d, "relevance_score": 0.0} for i, d in enumerate(documents)]

    base_url = (base_url or settings.rerank_ollama_url).rstrip("/")
    url = f"{base_url}/api/rerank"

    payload = {
        "model": model,
        "query": query[:2048],
        "top_n": min(top_n, len(doc_texts)) if top_n else len(doc_texts),
        "documents": doc_texts,
    }
    try:
        logger.info("[Rerank] 调用 model=%s query_len=%d docs=%d top_n=%d",
                    model, len(query), len(documents), payload["top_n"])
        resp = requests.post(url, json=payload, timeout=eff_timeout)
        if resp.status_code in (404, 501):
            fb = _rerank_via_embedding_cosine(query, doc_texts, payload["top_n"], eff_timeout)
            if fb is not None:
                logger.info(
                    "[Rerank] Ollama 无 /api/rerank（HTTP %s，常见于 0.18.x）；已用 Embedding(%s) 余弦重排",
                    resp.status_code,
                    settings.embed_model_name,
                )
                return fb
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
