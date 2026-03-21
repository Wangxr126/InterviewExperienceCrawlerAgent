"""DSML / 推理文本清洗（独立模块，避免运行时 NameError 与循环引用）。"""
from __future__ import annotations

import re
from typing import Optional


def strip_dsml_from_text(text: Optional[str]) -> str:
    """从推理/思考文本中移除 DeepSeek DSML 工具调用块（与前端 ChatView.stripDsmlBlocks 对齐）。"""
    if text is None:
        return ""
    s = str(text)
    if not s:
        return ""
    s = re.sub(
        r"<\s*[｜|]\s*DSML\s*[｜|]\s*function_calls\s*>.*?</\s*[｜|]\s*DSML\s*[｜|]\s*function_calls\s*>",
        "",
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )
    s = re.sub(
        r"^\s*<\s*/?\s*[｜|]\s*DSML\s*[｜|][^>]*>\s*$",
        "",
        s,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    m = re.search(r"<\s*[｜|]\s*DSML\s*[｜|]", s, flags=re.IGNORECASE)
    if m:
        s = s[: m.start()]
    s = re.sub(r"^\s*invoke\s+name=.*$", "", s, flags=re.IGNORECASE | re.MULTILINE)
    s = re.sub(r"^\s*parameter\s+name=.*$", "", s, flags=re.IGNORECASE | re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# 兼容旧名称（模块内与其它文件曾用下划线前缀）
_strip_dsml_from_text = strip_dsml_from_text
