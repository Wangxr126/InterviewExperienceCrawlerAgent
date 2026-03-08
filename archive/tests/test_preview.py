"""测试日志预览功能"""
import sys
sys.path.insert(0, 'backend')

from backend.services.finetune_service import preview_log_file

# 测试预览功能
log_path = r"微调\llm_logs\qwen3.5_4b\nowcoder_20260309.jsonl"
result = preview_log_file(log_path, limit=3)

print(f"总记录数: {result['total']}")
print(f"显示记录数: {result['showing']}")
print(f"样本数量: {len(result['samples'])}")

if result['samples']:
    print("\n第一条样本:")
    sample = result['samples'][0]
    print(f"标题: {sample['title']}")
    print(f"时间: {sample['ts']}")
    print(f"内容长度: {len(sample['content'])} 字符")
    print(f"LLM输出长度: {len(sample['llm_raw'])} 字符")
    if sample['llm_raw_obj']:
        print(f"LLM输出类型: {type(sample['llm_raw_obj'])}")
        if isinstance(sample['llm_raw_obj'], list):
            print(f"题目数量: {len(sample['llm_raw_obj'])}")
        elif isinstance(sample['llm_raw_obj'], dict) and 'reason' in sample['llm_raw_obj']:
            print(f"原因: {sample['llm_raw_obj']['reason']}")
else:
    print("没有样本数据")
