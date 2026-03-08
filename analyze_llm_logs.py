import json
import sys
import io
from pathlib import Path

# 设置输出编码为UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 读取最新的日志
log_file = Path('微调/llm_logs/gemma3_4b/nowcoder_20260308.jsonl')
if log_file.exists():
    lines = log_file.read_text(encoding='utf-8').strip().split('\n')
    print(f'总共 {len(lines)} 条记录')
    
    # 统计返回为空的情况
    empty_count = 0
    parse_error_count = 0
    success_count = 0
    unrelated_count = 0
    
    print('\n=== 最近10条记录分析 ===\n')
    
    for i, line in enumerate(lines[-10:], 1):
        try:
            data = json.loads(line)
            llm_raw = data.get('llm_raw', '').strip()
            content_preview = data.get('content', '')[:150]
            
            print(f'[记录 {i}]')
            print(f'输入: {content_preview}...')
            
            if not llm_raw:
                empty_count += 1
                print('结果: [空返回]')
            elif 'reason' in llm_raw and '无关' in llm_raw:
                unrelated_count += 1
                print('结果: [判定为无关内容]')
            elif 'question_text' in llm_raw or '[' in llm_raw:
                success_count += 1
                print(f'结果: [成功] 返回前100字: {llm_raw[:100]}')
            else:
                parse_error_count += 1
                print(f'结果: [解析失败] 返回: {llm_raw[:150]}')
            
            print()
        except Exception as e:
            print(f'[记录 {i}] 解析异常: {e}\n')
    
    print(f'\n=== 统计（最近10条）===')
    print(f'[OK] 成功: {success_count}')
    print(f'[FAIL] 空返回: {empty_count}')
    print(f'[FAIL] 解析失败: {parse_error_count}')
    print(f'[WARN] 无关内容: {unrelated_count}')
    print(f'\n成功率: {success_count/10*100:.1f}%')
    
    # 详细分析空返回的原因
    if empty_count > 0:
        print('\n=== 空返回详细分析 ===')
        for i, line in enumerate(lines[-10:], 1):
            try:
                data = json.loads(line)
                llm_raw = data.get('llm_raw', '').strip()
                if not llm_raw:
                    content = data.get('content', '')
                    print(f'\n[空返回 {i}]')
                    print(f'输入长度: {len(content)} 字符')
                    print(f'输入内容: {content[:300]}...')
            except:
                pass
else:
    print('日志文件不存在')
