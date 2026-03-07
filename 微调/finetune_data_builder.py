#!/usr/bin/env python3
"""
面经题目提取 - 微调数据构造脚本

用途：从现有日志中筛选样本，或手动构造「面经原文 → 标准 JSON 数组」训练数据。
输出格式兼容 LLaMA-Factory、Ollama Modelfile 等 SFT 格式。

用法（在项目根目录执行）：
  python 微调/finetune_data_builder.py --from-log     # 从 llm_prompt_log.jsonl 提取可用的样本
  python 微调/finetune_data_builder.py --from-manual  # 从 manual_samples.jsonl 读取并校验
  python 微调/finetune_data_builder.py --template     # 输出一条空模板供手动填写
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 项目根目录（微调文件夹的上一级）
ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "backend" / "data" / "logs" / "llm_prompt_log.jsonl"
OUTPUT_PATH = ROOT / "微调" / "finetune_samples.jsonl"
MANUAL_PATH = ROOT / "微调" / "manual_samples.jsonl"


def _parse_json_array(text: str) -> list | None:
    """尝试从文本中解析 JSON 数组"""
    if not text or not text.strip():
        return None
    text = re.sub(r"```(?:json)?\s*", "", text.strip()).rstrip("`").strip()
    for start in range(len(text)):
        if text[start] == "[":
            depth = 0
            for i in range(start, len(text)):
                c = text[i]
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
            break
    return None


def _is_valid_question_item(obj: dict) -> bool:
    """检查是否为有效的题目项"""
    if not isinstance(obj, dict):
        return False
    q = obj.get("question_text") or obj.get("question")
    return isinstance(q, str) and len(q.strip()) >= 4


def _normalize_item(obj: dict) -> dict:
    """归一化为标准格式"""
    q = obj.get("question_text") or obj.get("question") or ""
    return {
        "question_text": str(q).strip(),
        "answer_text": str(obj.get("answer_text", "")).strip(),
        "difficulty": str(obj.get("difficulty", "")).strip(),
        "question_type": str(obj.get("question_type", "技术题")).strip() or "技术题",
        "topic_tags": obj.get("topic_tags") if isinstance(obj.get("topic_tags"), list) else [],
        "company": str(obj.get("company", "")).strip(),
        "position": str(obj.get("position", "")).strip(),
    }


def from_log():
    """从 llm_prompt_log.jsonl 中筛选可用的样本（输出为合法 JSON 数组且题目与原文匹配）"""
    if not LOG_PATH.exists():
        logger.warning("日志不存在: %s", LOG_PATH)
        return []
    samples = []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw = rec.get("原始", "")
            out = rec.get("输出", "")
            if not raw or not out:
                continue
            # 日志中的「原始」已是面经原文；若含模板则尝试提取
            m = re.search(r"## 面经原文[^\n]*\n(.*?)(?=\n## 任务|\Z)", raw, re.DOTALL)
            content = (m.group(1).strip() if m else raw).replace("...[截断]", "").strip()
            if len(content) < 50:
                continue
            arr = _parse_json_array(out)
            if not arr or not isinstance(arr, list):
                continue
            valid = [x for x in arr if _is_valid_question_item(x)]
            if len(valid) < 2:
                continue
            # 检查是否大量照抄 OOM/LRU 等（答案含这些关键词且原文没有则视为污染）
            oom_lru = "堆内存溢出" in out or "LRU" in out or "HashMap + 双向链表" in out
            if oom_lru and "堆内存" not in content and "LRU" not in content and "OOM" not in content:
                continue
            normalized = [_normalize_item(x) for x in valid]
            samples.append({"input": content, "output": normalized})
    return samples


def from_manual():
    """从 manual_samples.jsonl 读取并校验"""
    if not MANUAL_PATH.exists():
        logger.warning("手动样本文件不存在: %s", MANUAL_PATH)
        logger.info("请创建该文件，每行一个 JSON：{\"input\": \"面经原文\", \"output\": [{...}]}")
        return []
    samples = []
    with open(MANUAL_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("第 %d 行 JSON 解析失败: %s", i, e)
                continue
            inp = rec.get("input", "")
            out = rec.get("output", [])
            if not inp or not isinstance(out, list):
                logger.warning("第 %d 行格式错误: 需要 input 和 output 数组", i)
                continue
            valid = [x for x in out if _is_valid_question_item(x)]
            if not valid:
                logger.warning("第 %d 行无有效题目", i)
                continue
            samples.append({"input": inp, "output": [_normalize_item(x) for x in valid]})
    return samples


def to_sft_format(samples: list, output_path: Path) -> None:
    """转换为 SFT 格式并写入"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sys_prompt = "你是面经题目提取专家。仅从面经原文中提取所有面试题，输出一个 JSON 数组。每个元素包含 question_text、answer_text、difficulty、question_type、topic_tags、company、position。原文无答案则 answer_text 填空。只输出 JSON，不要解释。"
    with open(output_path, "w", encoding="utf-8") as f:
        for s in samples:
            inp = s["input"]
            out = s["output"]
            out_str = json.dumps(out, ensure_ascii=False)
            # LLaMA-Factory / Alpaca 格式
            conv = [
                {"from": "human", "value": f"{sys_prompt}\n\n【面经原文】\n{inp}"},
                {"from": "gpt", "value": out_str},
            ]
            f.write(json.dumps({"conversations": conv}, ensure_ascii=False) + "\n")
    logger.info("已写入 %d 条样本到 %s", len(samples), output_path)


def print_template():
    """打印一条空模板供手动填写"""
    t = {
        "input": "（在此粘贴面经原文，例如：1. 介绍一下你的项目\n2. Redis持久化方式有哪些？）",
        "output": [
            {
                "question_text": "介绍一下你的项目",
                "answer_text": "",
                "difficulty": "",
                "question_type": "技术题",
                "topic_tags": ["项目"],
                "company": "",
                "position": "",
            },
            {
                "question_text": "Redis持久化方式有哪些？",
                "answer_text": "",
                "difficulty": "",
                "question_type": "技术题",
                "topic_tags": ["Redis", "持久化"],
                "company": "",
                "position": "",
            },
        ],
    }
    logger.info("空模板:\n%s", json.dumps(t, ensure_ascii=False, indent=2))


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="面经题目提取微调数据构造")
    parser.add_argument("--from-log", action="store_true", help="从 llm_prompt_log.jsonl 提取")
    parser.add_argument("--from-manual", action="store_true", help="从 manual_samples.jsonl 读取")
    parser.add_argument("--template", action="store_true", help="输出空模板")
    parser.add_argument("-o", "--output", default=str(OUTPUT_PATH), help="输出路径")
    args = parser.parse_args()

    if args.template:
        print_template()
        return

    samples = []
    if args.from_log:
        samples = from_log()
        logger.info("从日志提取到 %d 条可用样本", len(samples))
    elif args.from_manual:
        samples = from_manual()
        logger.info("从手动样本读取到 %d 条", len(samples))
    else:
        parser.print_help()
        return

    if samples:
        to_sft_format(samples, Path(args.output))
    else:
        logger.warning("无可用样本，请使用 --from-manual 并编辑 微调/manual_samples.jsonl")


if __name__ == "__main__":
    main()
