import json
import sys
import io
from pathlib import Path

# 设置UTF-8输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 读取最新的LLM日志
log_file = Path('微调/llm_logs/gemma3_4b/nowcoder_20260308.jsonl')
if not log_file.exists():
    print('日志文件不存在')
    exit(1)

lines = log_file.read_text(encoding='utf-8').strip().split('\n')
print(f'总共 {len(lines)} 条LLM调用记录\n')

# 统计输入内容长度分布
length_stats = {}
empty_returns = 0
success_returns = 0

print('=== 详细分析所有记录 ===\n')
for i, line in enumerate(lines, 1):
    try:
        data = json.loads(line)
        content = data.get('content', '')
        llm_raw = data.get('llm_raw', '').strip()
        
        # 统计输入长度
        content_len = len(content)
        length_range = f'{content_len//100*100}-{content_len//100*100+99}'
        length_stats[length_range] = length_stats.get(length_range, 0) + 1
        
        # 统计返回状态
        if not llm_raw or llm_raw == '{}':
            empty_returns += 1
        elif 'question_text' in llm_raw or '[' in llm_raw:
            success_returns += 1
        
        # 打印前3条详细信息
        if i <= 3:
            print(f'[记录 {i}]')
            print(f'输入长度: {content_len} 字符')
            print(f'输入内容前200字: {content[:200]}')
            print(f'LLM返回: {llm_raw[:100] if llm_raw else "(空)"}')
            print('-' * 80)
            print()
    except Exception as e:
        print(f'[记录 {i}] 解析异常: {e}')

print('\n=== 统计摘要 ===')
print(f'总记录数: {len(lines)}')
print(f'成功返回: {success_returns}')
print(f'空返回/空对象: {empty_returns}')
print(f'失败率: {empty_returns/len(lines)*100:.1f}%')

print('\n=== 输入长度分布 ===')
for length_range in sorted(length_stats.keys(), key=lambda x: int(x.split('-')[0])):
    print(f'{length_range} 字符: {length_stats[length_range]} 条')
