import re

with open('backend/services/finetune_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到import_from_log_file函数
pattern = r'(def import_from_log_file\(log_path: str, skip_existing: bool = True\) -> Dict\[str, int\]:.*?)(    logger\.info\("导入完成:.*?\n    return \{"imported": imported, "skipped": skipped\})'

def replacement(match):
    func_start = match.group(1)
    
    # 新的实现
    new_impl = '''    
    imported = skipped = failed = 0
    failed_samples = []  # 收集失败的样本用于最后统一输出
    
    with _get_db_conn() as conn:
        for line_num, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                content = rec.get("content", "").strip()
                title = rec.get("title", "")
                source_url = rec.get("source_url", "")
                llm_raw = rec.get("llm_raw", "")
                ts = rec.get("ts", now_beijing_str().isoformat(timespec="seconds"))
                if not content:
                    continue
                if skip_existing:
                    exists = conn.execute(
                        "SELECT 1 FROM finetune_samples WHERE content=? AND created_at=?",
                        (content, ts)
                    ).fetchone()
                    if exists:
                        skipped += 1
                        continue
                conn.execute(
                    "INSERT INTO finetune_samples (content, title, source_url, llm_raw, status, created_at) VALUES (?,?,?,?,?,?)",
                    (content, title, source_url, llm_raw, "pending", ts)
                )
                imported += 1
            except Exception as e:
                failed += 1
                failed_samples.append({
                    "line": line_num,
                    "error": str(e),
                    "preview": line[:80]
                })
        conn.commit()
    
    # 统一输出结果
    logger.info("导入完成: imported=%d skipped=%d failed=%d from %s", imported, skipped, failed, p.name)
    
    # 只有失败时才输出详细信息
    if failed > 0:
        logger.warning("导入失败详情 (%d条):", failed)
        for sample in failed_samples[:5]:  # 最多显示前5条
            logger.warning("  行%d: %s | %s", sample["line"], sample["error"], sample["preview"])
        if failed > 5:
            logger.warning("  ... 还有 %d 条失败记录未显示", failed - 5)
    
    return {"imported": imported, "skipped": skipped, "failed": failed}'''
    
    # 找到函数体开始位置（返回值定义之后）
    func_body_start = func_start.find('return {"imported": 0')
    if func_body_start == -1:
        func_body_start = func_start.find('imported = skipped = 0')
    
    if func_body_start != -1:
        # 保留函数签名和文档字符串
        func_header = func_start[:func_body_start]
        return func_header + new_impl
    
    return match.group(0)

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

if new_content != content:
    with open('backend/services/finetune_service.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print('[OK] 已优化日志输出！')
    print('')
    print('主要改进：')
    print('1. 收集所有失败记录，最后统一输出')
    print('2. 只在有失败时才输出WARNING')
    print('3. 最多显示前5条失败详情')
    print('4. 统计信息包含：imported, skipped, failed')
else:
    print('[WARN] 未找到目标代码或已经修改过')
