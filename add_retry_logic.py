import re

with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到函数定义到第一个 questions: List[Dict] = [] 之间的部分
pattern = r'(def extract_questions_from_post\(.*?\) -> Tuple\[List\[Dict\], str\]:.*?""".*?""".*?)(    t0 = time\.perf_counter\(\).*?)(    questions: List\[Dict\] = \[\])'

def replacement(match):
    func_def = match.group(1)
    old_logic = match.group(2)
    questions_start = match.group(3)
    
    # 修改函数文档字符串
    func_def = func_def.replace(
        'status 为 ok/unrelated/empty。',
        'status 为 ok/unrelated/empty/parse_error。\n    \n    支持重试机制：当返回为空或解析失败时，自动重试（最大次数由 EXTRACTOR_MAX_RETRIES 配置）。'
    )
    
    # 新的重试逻辑
    new_logic = '''    from backend.config.config import settings
    max_retries = settings.extractor_max_retries
    
    # 重试循环
    for attempt in range(1, max_retries + 1):
        t0 = time.perf_counter()
        raw = _call_llm(user_prompt)
        llm_response_time_sec = time.perf_counter() - t0

        items, status = _parse_json_from_llm(raw, user_prompt_for_debug=user_prompt)

        _append_llm_log_to_csv(user_prompt, raw or "", llm_response_time_sec, source=platform, 
                               title=post_title, source_url=source_url)

        # 成功或明确判定为无关，直接返回
        if status == "unrelated":
            logger.info(f"LLM 判定帖子与面经无关: {source_url}")
            return [], "unrelated"
        
        if status == "ok" and items:
            if attempt > 1:
                logger.info(f"重试成功（第 {attempt} 次）: 提取到 {len(items)} 道题目")
            break
        
        # 需要重试的情况：empty 或 parse_error
        if attempt < max_retries:
            logger.warning(f"提取失败（第 {attempt} 次，状态: {status}），{max_retries - attempt} 次重试机会剩余")
            time.sleep(1)  # 短暂延迟避免频繁请求
        else:
            logger.error(f"提取失败，已达最大重试次数 {max_retries}: {source_url}")
            if not items:
                logger.warning(f"LLM 未提取到题目: {source_url}")
                if raw:
                    logger.info(f"LLM 原始返回（前500字）: {raw[:500]}")
                return [], status

'''
    
    return func_def + new_logic + questions_start

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

if new_content != content:
    with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('[OK] 重试逻辑已添加！')
    print('')
    print('主要改进：')
    print('1. 添加重试循环，最大重试次数由 EXTRACTOR_MAX_RETRIES 配置（默认3次）')
    print('2. 只在 empty 或 parse_error 状态时重试')
    print('3. unrelated 状态直接返回，不重试')
    print('4. 成功提取到题目后立即返回')
    print('5. 重试间隔1秒，避免频繁请求')
    print('6. 记录重试日志，便于调试')
else:
    print('[WARN] 未找到目标代码或已经修改过')
