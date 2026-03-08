#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""添加预览函数到finetune_service.py"""

# 读取原文件
with open('backend/services/finetune_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 预览函数代码
preview_function = '''

def preview_log_file(log_path: str, limit: int = 10) -> Dict:
    """
    预览日志文件的前N条记录
    返回 {"samples": [...], "total": N}
    """
    p = Path(log_path)
    if not p.exists():
        return {"error": "文件不存在", "samples": [], "total": 0}
    
    samples = []
    total = 0
    
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            total += 1
            if len(samples) < limit:
                try:
                    rec = json.loads(line)
                    
                    # 兼容不同的字段名
                    content = rec.get("user_content") or rec.get("content", "")
                    llm_raw = rec.get("llm_response") or rec.get("llm_raw", "")
                    
                    # 解析 llm_raw 为对象
                    llm_raw_obj = None
                    if llm_raw:
                        try:
                            llm_raw_obj = json.loads(llm_raw)
                        except:
                            llm_raw_obj = {"error": "无效JSON", "raw": llm_raw}
                    
                    samples.append({
                        "content": content,
                        "title": rec.get("title", ""),
                        "source_url": rec.get("source_url", ""),
                        "llm_raw": llm_raw,
                        "llm_raw_obj": llm_raw_obj,
                        "ts": rec.get("ts", ""),
                    })
                except Exception as e:
                    logger.warning("解析日志行失败: %s", e)
                    continue
    except Exception as e:
        logger.error("读取日志文件失败: %s", e)
        return {"error": str(e), "samples": [], "total": 0}
    
    return {"samples": samples, "total": total, "showing": len(samples)}
'''

# 写入文件
with open('backend/services/finetune_service.py', 'w', encoding='utf-8') as f:
    f.write(content + preview_function)

print("预览函数已添加成功！")
