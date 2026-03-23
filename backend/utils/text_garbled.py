"""
乱码检测与轻量修复（题目 / 公司名等）。

- 识别：替换字符 U+FFFD、不可见控制符、典型 UTF-8 被按 Latin-1 解读的「åÃÂ」型模式等。
- 修复：NFKC、尝试 latin1→bytes→utf-8；若安装 ftfy 则优先使用（可选依赖）。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Tuple

# 常见「UTF-8 误当单字节编码显示」片段（启发式）
_MOJIBAKE_HINT = re.compile(
    r"(Ã.|Â[\u0080-\u024f]|å[\u0080-\u00ff]{1,3}|â€[™˜]|ï»¿)"
)


def _cjk_count(s: str) -> int:
    n = 0
    for c in s:
        if "\u4e00" <= c <= "\u9fff":
            n += 1
    return n


def control_char_ratio(s: str) -> float:
    if not s:
        return 0.0
    bad = 0
    for c in s:
        o = ord(c)
        if o in (9, 10, 13):
            continue
        if unicodedata.category(c) == "Cc" or (0xE000 <= o <= 0xF8FF):
            bad += 1
    return bad / len(s)


def looks_garbled(s: str) -> bool:
    """是否像乱码/严重污染（需修复或删除）。"""
    if not s or not s.strip():
        return False
    if "\ufffd" in s:
        return True
    if control_char_ratio(s) > 0.02:
        return True
    # 面试题预期以中文为主：很长但几乎无汉字、又含大量符号/拉丁
    if len(s) >= 24 and _cjk_count(s) == 0:
        if re.search(r"[\u0080-\u00ff]{4,}", s) or _MOJIBAKE_HINT.search(s):
            return True
    if _MOJIBAKE_HINT.search(s) and _cjk_count(s) < max(3, len(s) // 80):
        return True
    return False


def _try_latin1_utf8(s: str) -> Optional[str]:
    """UTF-8 字节被误解释为 Latin-1 时的回转。"""
    try:
        raw = s.encode("latin1")
        t = raw.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if not t.strip():
        return None
    # 回转后应更「正常」：更多 CJK 或更少 mojibake 痕迹
    if "\ufffd" in t:
        return None
    if _cjk_count(t) < _cjk_count(s) and _MOJIBAKE_HINT.search(t):
        return None
    if _cjk_count(t) > _cjk_count(s) or (not _MOJIBAKE_HINT.search(t) and _MOJIBAKE_HINT.search(s)):
        return t
    return None


def _ftfy_fix(s: str) -> Optional[str]:
    try:
        import ftfy  # type: ignore
    except ImportError:
        return None
    try:
        t = ftfy.fix_text(s)
        return t if t != s else None
    except Exception:
        return None


def repair_text(s: str) -> Tuple[str, bool]:
    """
    尽量修复字符串。返回 (新文本, 是否发生过变更)。
    正常中文题干不做 NFKC，避免全库无意义大更新；仅在疑似乱码时做强化归一与编码回转。
    """
    if not s:
        return s, False
    orig = s
    dirty = looks_garbled(s) or "\ufffd" in s or control_char_ratio(s) > 0.003
    t = unicodedata.normalize("NFKC", s) if dirty else s
    t = t.replace("\ufeff", "").replace("\ufffe", "")

    changed = t != orig
    if dirty or _MOJIBAKE_HINT.search(t):
        fx = _ftfy_fix(t)
        if fx is not None:
            t, changed = fx, True

        fixed = _try_latin1_utf8(t)
        if fixed is not None:
            t, changed = fixed, True

    if "\ufffd" in t:
        t2 = t.replace("\ufffd", "")
        if t2 != t:
            t, changed = t2, True

    t2 = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    if t2 != t:
        t, changed = t2, True
    return t.strip(), changed


def should_drop_question_text(s: str) -> bool:
    """修复前：明显乱码则可直接删。"""
    if not s or not s.strip():
        return True
    if looks_garbled(s):
        return True
    if control_char_ratio(s) > 0.01:
        return True
    if len(s.strip()) < 4:
        return True
    return False


def is_unusable_after_repair(s: str) -> bool:
    """修复后仍含替换符/控制符过多/过短 → 删除该题。"""
    if not s or not s.strip():
        return True
    if "\ufffd" in s:
        return True
    if control_char_ratio(s) > 0.015:
        return True
    if len(s.strip()) < 4:
        return True
    return False


def is_unusable_answer_after_repair(s: str) -> bool:
    """答案：允许较短；仅替换符/控制符过多时视为不可用并清空。"""
    if not s or not s.strip():
        return False
    if "\ufffd" in s:
        return True
    if control_char_ratio(s) > 0.025:
        return True
    return False


def company_should_be_cleared(repaired: str) -> bool:
    """公司字段修复后仍异常则清空。"""
    c = (repaired or "").strip()
    if not c:
        return True
    if looks_garbled(c):
        return True
    if control_char_ratio(c) > 0.05:
        return True
    if len(c) > 64:
        return True
    return False
