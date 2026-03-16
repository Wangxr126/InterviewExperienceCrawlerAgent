"""
Stage1/Stage2 合并工具
当 Stage2 为节省 token 只返回 answer_text 等部分字段时，从 Stage1 补齐缺失字段。
支持 Stage1 的多种格式：question_text/answer_text 或 title/answer/type/tags
"""
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 标准输出字段（下游微调期望的 7 字段）
STD_FIELDS = ["question_text", "answer_text", "raw_answer", "difficulty", "question_type", "topic_tags", "company", "position"]

# Stage1 旧格式字段映射
S1_OLD_TO_STD = {
    "title": "question_text",
    "answer": "answer_text",
    "type": "question_type",
    "tags": "topic_tags",
}


def _normalize_s1_item(item: Dict) -> Dict:
    """将 Stage1 单条转为标准格式（兼容 title/answer/type/tags 旧格式）"""
    if not isinstance(item, dict):
        return {}
    out = {}
    for std_key in STD_FIELDS:
        val = item.get(std_key)
        # 尝试旧格式映射
        if val is None or val == "" or (isinstance(val, list) and len(val) == 0):
            for old_key, mapped in S1_OLD_TO_STD.items():
                if mapped == std_key and item.get(old_key) is not None:
                    val = item.get(old_key)
                    break
        if val is None:
            val = "" if std_key not in ("topic_tags",) else []
        if std_key == "topic_tags" and isinstance(val, str):
            try:
                val = json.loads(val) if val.strip().startswith("[") else []
            except Exception:
                val = []
        out[std_key] = val
    # raw_answer 默认用 answer_text
    if not out.get("raw_answer") and out.get("answer_text"):
        out["raw_answer"] = out["answer_text"]
    return out


def _get_qt(item: Dict) -> str:
    """获取题目文本（兼容 question_text / title）"""
    qt = (item or {}).get("question_text") or (item or {}).get("title") or ""
    return (qt or "").strip()


def merge_stage2_with_stage1(stage2_output: str, stage1_output: str) -> str:
    """
    将 Stage2 输出与 Stage1 合并：Stage2 缺失的字段从 Stage1 补齐。
    支持：
    - Stage1 旧格式：title/answer/type/tags
    - Stage2 仅返回 answer_text（或 question_text+answer_text）时补齐其余字段
    - 按 question_text 匹配；若无则按索引匹配
    返回合并后的 JSON 字符串。
    """
    if not stage1_output or not stage1_output.strip():
        return stage2_output or "[]"

    try:
        s1_list = json.loads(stage1_output)
    except json.JSONDecodeError:
        return stage2_output or "[]"

    if not isinstance(s1_list, list):
        return stage2_output or "[]"

    s1_normalized = [_normalize_s1_item(q) for q in s1_list if isinstance(q, dict)]
    s1_by_qt = {_get_qt(q): q for q in s1_normalized if _get_qt(q)}
    s1_by_idx = {i: q for i, q in enumerate(s1_normalized)}

    if not stage2_output or not stage2_output.strip():
        return json.dumps(s1_normalized, ensure_ascii=False)

    try:
        s2_list = json.loads(stage2_output)
    except json.JSONDecodeError:
        return stage2_output

    if not isinstance(s2_list, list):
        return stage2_output

    merged = []
    for i, item in enumerate(s2_list):
        if not isinstance(item, dict):
            continue
        qt = _get_qt(item)
        s1 = s1_by_qt.get(qt) or s1_by_idx.get(i) or {}

        # 标准字段：Stage2 有且非空则用 Stage2，否则用 Stage1
        row = {}
        for f in STD_FIELDS:
            s2_val = item.get(f)
            s1_val = s1.get(f)
            # 判断「空」：None、""、[]（对 topic_tags）
            is_empty = (
                s2_val is None
                or s2_val == ""
                or (f == "topic_tags" and (not s2_val or (isinstance(s2_val, list) and len(s2_val) == 0)))
            )
            if not is_empty:
                row[f] = s2_val
            elif s1_val is not None and s1_val != "":
                row[f] = s1_val
            elif f == "topic_tags":
                row[f] = []
            elif f == "difficulty":
                row[f] = "medium"
            elif f == "question_type":
                row[f] = "基础类"
            else:
                row[f] = ""
        # raw_answer：若为空，用 Stage1 的 answer_text
        if not row.get("raw_answer") and s1.get("answer_text"):
            row["raw_answer"] = s1["answer_text"]
        # question_text：若仍空，用 Stage1
        if not row.get("question_text") and s1.get("question_text"):
            row["question_text"] = s1["question_text"]
        merged.append(row)

    return json.dumps(merged, ensure_ascii=False)


def is_stage2_incomplete(stage2_output: str, stage1_output: str) -> bool:
    """
    判断 Stage2 是否不完整（缺少 Stage1 中存在的字段）。
    用于决定是否需要执行 merge。
    支持 Stage1 旧格式：title/answer/type/tags。
    """
    if not stage2_output or not stage1_output:
        return False
    try:
        s2_list = json.loads(stage2_output)
        s1_list = json.loads(stage1_output)
    except json.JSONDecodeError:
        return False
    if not isinstance(s2_list, list) or not isinstance(s1_list, list) or len(s2_list) == 0:
        return False
    s1_sample = _normalize_s1_item(next((q for q in s1_list if isinstance(q, dict)), {}))
    s2_sample = next((q for q in s2_list if isinstance(q, dict)), {})
    # 检查关键字段：若 Stage1 有而 Stage2 空，则认为不完整
    for key in ["difficulty", "question_type", "topic_tags", "company", "position"]:
        s1_val = s1_sample.get(key)
        s2_val = s2_sample.get(key)
        if s1_val and (s2_val is None or s2_val == "" or (key == "topic_tags" and (not s2_val or len(s2_val) == 0))):
            return True
    return False
