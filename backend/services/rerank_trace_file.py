"""
向量召回 + Rerank 结果落盘：便于对照「初筛分数 / 重排分数 / 最终顺序」。
文件目录由 settings.rerank_trace_dir 决定，文件名 {slug}_{时间戳}.json。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config.config import settings

logger = logging.getLogger(__name__)

_SLUG_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_slug(slug: str) -> str:
    s = _SLUG_SAFE.sub("_", (slug or "rerank").strip())[:80]
    return s or "rerank"


def _qid(c: Dict[str, Any]) -> str:
    return str(c.get("id") or c.get("q_id") or "")


def _preview_record(
    c: Dict[str, Any],
    text_key: str,
    text_max: int,
) -> Dict[str, Any]:
    text = c.get(text_key) or c.get("question_text") or c.get("text") or ""
    text = str(text)
    if len(text) > text_max:
        text = text[:text_max] + f"...[截断,原长{len(c.get(text_key) or '')}]"
    return {
        "id": _qid(c),
        "vector_score": c.get("score"),
        "recall_score": c.get("recall_score"),
        "recall_source": c.get("recall_source"),
        "recall_sources": c.get("recall_sources"),
        "company": c.get("company"),
        "difficulty": c.get("difficulty"),
        "question_type": c.get("question_type"),
        "topic_tags": c.get("topic_tags") if isinstance(c.get("topic_tags"), list) else c.get("tags"),
        "question_text": text,
    }


def write_similar_rerank_trace(
    slug: str,
    query: str,
    text_key: str,
    pre_candidates: List[Dict[str, Any]],
    rerank_raw: List[Dict[str, Any]],
    post_candidates: List[Dict[str, Any]],
    trace_meta: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    写入 JSON 追踪文件。返回绝对路径；失败时返回 None。
    """
    if not getattr(settings, "rerank_trace_enabled", True):
        return None
    base = Path(settings.rerank_trace_dir)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("[RerankTrace] 无法创建目录 %s: %s", base, e)
        return None

    text_max = int(getattr(settings, "rerank_trace_text_max_len", 4000) or 4000)
    # 文件名用本地时间，便于与控制台日志对照；payload 内仍保留 UTC ISO
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    name = f"{_safe_slug(slug)}_{ts}.json"
    path = base / name

    pre_ranked = [
        {"rank": i + 1, **_preview_record(c, text_key, text_max)}
        for i, c in enumerate(pre_candidates)
    ]
    rerank_items = []
    for i, r in enumerate(rerank_raw):
        doc = r.get("document", "")
        if isinstance(doc, str) and len(doc) > text_max:
            doc = doc[:text_max] + f"...[截断,原长{len(r.get('document') or '')}]"
        rerank_items.append(
            {
                "rerank_order": i + 1,
                "index": r.get("index"),
                "relevance_score": r.get("relevance_score"),
                "document": doc,
            }
        )
    post_ranked = [
        {"rank": i + 1, **_preview_record(c, text_key, text_max), "rerank_score": c.get("rerank_score")}
        for i, c in enumerate(post_candidates)
    ]

    payload: Dict[str, Any] = {
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "slug": _safe_slug(slug),
        "rerank_mode": getattr(settings, "rerank_mode", ""),
        "rerank_model": getattr(settings, "rerank_model", ""),
        "query": (query or "")[:4096],
        "text_key": text_key,
        "pre_rerank_candidates": pre_ranked,
        "rerank_model_output": rerank_items,
        "post_rerank_candidates": post_ranked,
    }
    if trace_meta:
        payload["meta"] = trace_meta

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("[RerankTrace] 已写入追踪文件: %s", path)
        return str(path.resolve())
    except OSError as e:
        logger.warning("[RerankTrace] 写入失败 %s: %s", path, e)
        return None
