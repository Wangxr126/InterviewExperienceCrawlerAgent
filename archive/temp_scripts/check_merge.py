import json
import sys
sys.path.insert(0, 'e:/Agent/AgentProject/wxr_agent')

from backend.services.finetune.stage_merge_utils import merge_stage2_with_stage1

# 从日志取最新一条，模拟merge过程
log_path = 'e:/Agent/AgentProject/wxr_agent/微调/llm_logs/miner_two_stage_log.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 取最后5条，找有stage2_output的
for line in reversed(lines[-20:]):
    rec = json.loads(line)
    s2 = rec.get('stage2_output', '')
    s1 = rec.get('stage1_output', '')
    if s2 and '**' in s2:
        print('=== 找到含Markdown的Stage2日志 ===')
        print('stage2_output 前500字:', s2[:500])
        print()
        # 解析stage2_output里的answer_text
        try:
            s2_list = json.loads(s2)
            if isinstance(s2_list, list) and s2_list:
                first = s2_list[0]
                print('第一题 answer_text repr:', repr((first.get('answer_text') or '')[:400]))
        except Exception as e:
            print('解析stage2_output失败:', e)
        break
else:
    print('未找到含**的stage2记录，取最后一条：')
    rec = json.loads(lines[-1])
    s2 = rec.get('stage2_output', '')
    print('stage2_output repr:', repr(s2[:600]))
    try:
        s2_list = json.loads(s2)
        if isinstance(s2_list, list) and s2_list:
            first = s2_list[0]
            print('第一题 answer_text repr:', repr((first.get('answer_text') or '')[:400]))
    except Exception as e:
        print('解析失败:', e)
