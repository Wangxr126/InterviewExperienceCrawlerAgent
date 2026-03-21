"""
Miner 提取结果质量校验：拦截明显乱码/损坏字符（控制符、NUL、U+FFFD 等）。
不再按「英文主导」或标签语种拦截，避免误伤技术英文题干。
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Tuple

_WS_CTRL_OK = frozenset("\t\n\r ")


def _garbled_issue(text: str) -> str:
    """若文本含明显损坏/非法字符则返回简短原因，否则返回空串。"""
    if not text:
        return ""
    if "\x00" in text:
        return "含空字节(NUL)"
    if "\ufffd" in text:
        return "含替换字符U+FFFD，疑似解码损坏"
    for c in text:
        if c in _WS_CTRL_OK:
            continue
        cat = unicodedata.category(c)
        if cat == "Cc":
            return f"含控制字符U+{ord(c):04X}"
        if cat == "Cs":
            return f"含无效代理码位U+{ord(c):04X}"
    return ""


def source_expects_chinese(text: str) -> bool:
    """原帖是否应以中文输出为主（有足够汉字即认为用户期望中文题库）。"""
    if not (text or "").strip():
        return False
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in text if "A" <= c <= "Z" or "a" <= c <= "z")
    if cjk >= 30:
        return True
    if cjk >= 12 and cjk >= latin * 0.22:
        return True
    if cjk >= 8 and latin < cjk * 4:
        return True
    return False


def validate_chinese_extraction(items: List[Dict[str, Any]], source_text: str) -> Tuple[bool, str]:
    """
    校验提取结果是否含明显乱码/非法字符。
    source_text 保留参数以兼容旧调用，当前不参与判定。
    通过返回 (True, "")；否则 (False, 原因) 供上层重试。
    """
    _ = source_text  # API 兼容保留，不再参与判定
    if not items:
        return True, ""

    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        q = str(it.get("question_text") or it.get("question") or "")
        issue = _garbled_issue(q)
        if issue:
            return False, f"第{idx + 1}题 question_text {issue}"

        a = str(it.get("answer_text") or it.get("answer") or "")
        issue = _garbled_issue(a)
        if issue:
            return False, f"第{idx + 1}题 answer_text {issue}"

        tags = it.get("topic_tags") or it.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)] if tags else []
        for t in tags:
            s = str(t)
            issue = _garbled_issue(s)
            if issue:
                return False, f"第{idx + 1}题 topic_tags {issue}"

    return True, ""
