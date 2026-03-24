"""
Demo Cases API
提供预置演示案例列表，供前端「模型对比」页展示。
GET /api/demo-cases          → 返回 demo_cases.json 列表
GET /api/demo-cases/{index}  → 返回单条案例（1-based）
"""
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/demo-cases", tags=["demo-cases"])
logger = logging.getLogger(__name__)

# demo_cases.json 位于 微调/ 目录下
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEMO_CASES_PATH = _PROJECT_ROOT / "微调" / "demo_cases.json"


def _load_cases() -> list:
    if not _DEMO_CASES_PATH.exists():
        logger.warning("demo_cases.json 不存在: %s", _DEMO_CASES_PATH)
        return []
    try:
        with open(_DEMO_CASES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("加载 demo_cases.json 失败: %s", e)
        return []


@router.get("")
def list_demo_cases(
    include_content: bool = Query(False, description="是否返回完整正文（默认只返回预览）"),
):
    """返回所有演示案例（默认不含完整正文，节省传输量）"""
    cases = _load_cases()
    if not include_content:
        # 只返回摘要字段
        result = []
        for c in cases:
            result.append({
                "case_index":    c.get("case_index"),
                "category":      c.get("category"),
                "id":            c.get("id"),
                "title":         c.get("title"),
                "company":       c.get("company", ""),
                "position":      c.get("position", ""),
                "platform":      c.get("platform", ""),
                "source_url":    c.get("source_url", ""),
                "content_preview": c.get("content_preview", ""),
                "questions_count": c.get("questions_count", 0),
                "is_modified":   c.get("is_modified", False),
                "has_irregular_numbering": c.get("has_irregular_numbering", False),
                "doubao_output": c.get("doubao_output", ""),
                "questions":     c.get("questions", []),
            })
        return {"total": len(result), "items": result}
    return {"total": len(cases), "items": cases}


@router.get("/{case_index}")
def get_demo_case(case_index: int):
    """返回单条案例（1-based index），含完整正文"""
    cases = _load_cases()
    for c in cases:
        if c.get("case_index") == case_index:
            return c
    raise HTTPException(status_code=404, detail=f"案例 {case_index} 不存在")
