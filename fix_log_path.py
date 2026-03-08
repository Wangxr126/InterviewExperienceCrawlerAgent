#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复 question_extractor.py 中的日志路径问题
将旧路径也改为使用模型名子目录
"""

import re
import sys
from pathlib import Path

# 设置输出编码为 UTF-8
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

file_path = Path(__file__).parent / "backend" / "services" / "crawler" / "question_extractor.py"

# 读取文件
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 要替换的旧代码
old_code = """    # ── 1. 旧路径（调试用，保持不变）──
    try:
        from backend.config.config import settings
        path = settings.llm_prompt_log_csv
        if path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if str(p).lower().endswith(".csv"):
                p = p.with_suffix(".jsonl")
            if _llm_log_run_suffix:
                p = p.parent / f"{p.stem}_{_llm_log_run_suffix}{p.suffix}"
            record = {
                "原始": content[:_MAX_LOG_INPUT_PREVIEW],
                "输出": llm_raw[:_MAX_LOG_OUTPUT],
                "操作时间": round(response_time_sec, 2) if response_time_sec is not None else None,
            }
            with open(p, "a", encoding="utf-8", newline="\\n") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")
    except Exception as e:
        logger.debug("LLM 调试日志写入失败: %s", e)"""

# 新代码
new_code = """    # ── 1. 旧路径（调试用，使用模型名子目录）──
    try:
        from backend.config.config import settings
        path = settings.llm_prompt_log_csv
        if path:
            p = Path(path)
            # 使用模型名子目录
            _PROJECT_ROOT = Path(__file__).resolve().parents[3]
            model_name = (settings.llm_model_id or "unknown").replace(":", "_").replace(" ", "_")
            log_dir = _PROJECT_ROOT / "微调" / "llm_logs" / model_name
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取原始文件名
            if str(p).lower().endswith(".csv"):
                filename = p.stem + ".jsonl"
            else:
                filename = p.name
            
            if _llm_log_run_suffix:
                filename = f"{Path(filename).stem}_{_llm_log_run_suffix}{Path(filename).suffix}"
            
            p = log_dir / filename
            
            record = {
                "原始": content[:_MAX_LOG_INPUT_PREVIEW],
                "输出": llm_raw[:_MAX_LOG_OUTPUT],
                "操作时间": round(response_time_sec, 2) if response_time_sec is not None else None,
            }
            with open(p, "a", encoding="utf-8", newline="\\n") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\\n")
    except Exception as e:
        logger.debug("LLM 调试日志写入失败: %s", e)"""

# 替换
if old_code in content:
    content = content.replace(old_code, new_code)
    print("✅ 找到并替换了旧代码")
else:
    print("⚠️ 未找到完全匹配的旧代码，尝试模糊匹配...")
    # 尝试更宽松的匹配
    pattern = r"# ── 1\. 旧路径.*?logger\.debug\(\"LLM 调试日志写入失败: %s\", e\)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_code + content[match.end():]
        print("✅ 使用模糊匹配替换成功")
    else:
        print("❌ 无法找到匹配的代码块")
        exit(1)

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"✅ 已修复 {file_path}")
print("现在日志将写入: 微调/llm_logs/{{模型名}}/llm_prompt_log_{{时间戳}}.jsonl")
