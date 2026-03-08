import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 读取最新的LLM日志
log_file = Path('微调/llm_logs/gemma3_4b/nowcoder_20260308.jsonl')
if log_file.exists():
    lines = log_file.read_text(encoding='utf-8').strip().split('\n')
    print(f'总共 {len(lines)} 条记录\n')
    
    empty_output = 0
    has_content = 0
    no_content = 0
    short_content = 0
    
    print('=== 检查最近10条记录 ===\n')
    
    for i, line in enumerate(lines[-10:], 1):
        try:
            data = json.loads(line)
            content = data.get('content', '')
            title = data.get('title', '')
            llm_raw = data.get('llm_raw', '').strip()
            source_url = data.get('source_url', '')
            
            print(f'[记录 {i}]')
            print(f'URL: {source_url[:60]}...')
            print(f'标题: {title[:50] if title else "无标题"}')
            print(f'内容长度: {len(content)} 字符')
            print(f'内容预览: {content[:100]}...')
            print(f'LLM返回长度: {len(llm_raw)} 字符')
            print(f'LLM返回预览: {llm_raw[:150] if llm_raw else "(空)"}')
            
            if not llm_raw:
                empty_output += 1
                print('状态: ❌ LLM返回为空！')
            elif len(content) < 100:
                no_content += 1
                print('状态: ⚠️ 输入内容过短！')
            elif len(content) < 200:
                short_content += 1
                print('状态: ⚠️ 输入内容较短（可能被截断）')
            else:
                has_content += 1
                print('状态: ✓ 正常')
            
            print('-' * 100)
            print()
        except Exception as e:
            print(f'解析失败: {e}\n')
    
    print(f'\n=== 统计（最近10条）===')
    print(f'❌ LLM返回为空: {empty_output}')
    print(f'⚠️ 输入内容过短(<100字): {no_content}')
    print(f'⚠️ 输入内容较短(<200字): {short_content}')
    print(f'✓ 正常: {has_content}')
    
    # 统计全部记录
    print(f'\n=== 全部记录统计 ===')
    total_empty = 0
    total_short = 0
    total_normal = 0
    
    for line in lines:
        try:
            data = json.loads(line)
            content = data.get('content', '')
            llm_raw = data.get('llm_raw', '').strip()
            
            if not llm_raw:
                total_empty += 1
            elif len(content) < 200:
                total_short += 1
            else:
                total_normal += 1
        except:
            pass
    
    print(f'总记录数: {len(lines)}')
    print(f'❌ LLM返回为空: {total_empty} ({total_empty/len(lines)*100:.1f}%)')
    print(f'⚠️ 输入内容过短: {total_short} ({total_short/len(lines)*100:.1f}%)')
    print(f'✓ 正常: {total_normal} ({total_normal/len(lines)*100:.1f}%)')
else:
    print('日志文件不存在')
