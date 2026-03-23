"""
题干清洗：去掉开头的题号/枚举标记；供入库与全库批处理使用。
"""
from __future__ import annotations

import re
import unicodedata


# 常见前缀：(7) （8） 7. 7、 Q1: 第3题 [12] 12） 等；可重复多轮剥除
_ENUM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.UNICODE)
    for p in (
        r"^[\(（]\s*\d+\s*[\)）]\s*",
        r"^\d+\s*[\.、．]\s*",
        r"^[QqＱｑ]\s*\d+\s*[：:．.\s]*",
        r"^第\s*\d+\s*[题問问]\s*[：:、．.\s]*",
        r"^\d+\s*[)）]\s*",
        r"^\[\s*\d+\s*\]\s*",
        r"^[（\(]\s*[一二三四五六七八九十百千]+\s*[）\)]\s*",
    )
)


def strip_question_enumeration(text: str) -> str:
    """去掉题干最前面的编号/括号序号，可循环剥多层。"""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).strip()
    for _ in range(12):
        prev = s
        for pat in _ENUM_PATTERNS:
            s = pat.sub("", s, count=1)
        s = s.strip()
        if s == prev:
            break
    return s


def normalize_text_for_dedupe(text: str) -> str:
    """去重键：NFKC + 去枚举 + 空白归一 + 英文小写。"""
    s = strip_question_enumeration(text)
    s = unicodedata.normalize("NFKC", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s.casefold()
