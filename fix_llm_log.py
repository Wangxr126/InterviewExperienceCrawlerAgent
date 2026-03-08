"""修复 LLM 日志记录，添加 system_prompt 等字段"""
import re

file_path = "backend/services/crawler/question_extractor.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 查找并替换微调日志部分
old_pattern = r'''    # ── 2\. 微调日志（按模型\+来源\+日期分文件）──
    try:
        ft_path = _get_finetune_log_path\(source\)
        ft_record = \{
            "ts": now_beijing_str\(\)\.isoformat\(timespec="seconds"\),
            "content": content,
            "llm_raw": llm_raw,
        \}
        with open\(ft_path, "a", encoding="utf-8", newline="\\n"\) as f:
            f\.write\(json\.dumps\(ft_record, ensure_ascii=False\) \+ "\\n"\)
    except Exception as e:
        logger\.debug\("微调日志写入失败: %s", e\)'''

new_code = '''    # ── 2. 微调日志（按模型+来源+日期分文件，包含完整 system prompt）──
    try:
        from backend.config.config import settings
        ft_path = _get_finetune_log_path(source)
        ft_record = {
            "ts": now_beijing_str(),
            "model": settings.llm_model_id or "unknown",
            "source": source,
            "title": title[:100] if title else "",
            "source_url": source_url,
            "system_prompt": get_miner_prompt(),  # 完整的 system prompt（不含标题和正文）
            "user_content": content,  # 提取的原始内容
            "llm_response": llm_raw,
            "response_time_sec": round(response_time_sec, 2) if response_time_sec is not None else None,
        }
        with open(ft_path, "a", encoding="utf-8", newline="\\n") as f:
            f.write(json.dumps(ft_record, ensure_ascii=False) + "\\n")
    except Exception as e:
        logger.debug("微调日志写入失败: %s", e)'''

if re.search(old_pattern, content):
    content = re.sub(old_pattern, new_code, content)
    print("✅ 找到并替换了微调日志部分")
else:
    print("❌ 未找到匹配的代码块，尝试手动查找...")
    # 手动查找关键行
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '"ts": now_beijing_str().isoformat(timespec="seconds"),' in line:
            print(f"找到目标行在第 {i+1} 行")
            print(f"前后内容：")
            for j in range(max(0, i-3), min(len(lines), i+10)):
                print(f"{j+1}: {lines[j]}")
            break

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("✅ 文件已更新")
