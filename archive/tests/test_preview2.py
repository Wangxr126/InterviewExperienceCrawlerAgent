"""直接测试预览函数"""
import sys
sys.path.insert(0, 'backend')

from backend.services.finetune_preview import preview_log_file

# 测试预览功能
log_path = r"微调\llm_logs\qwen3.5_4b\nowcoder_20260309.jsonl"
result = preview_log_file(log_path, limit=1)

print(f"总记录数: {result['total']}")
print(f"显示记录数: {result['showing']}")
print(f"样本数量: {len(result['samples'])}")

if result['samples']:
    sample = result['samples'][0]
    print(f"\n标题: {sample['title']}")
    print(f"时间: {sample['ts']}")
    print(f"内容长度: {len(sample['content'])} 字符")
    print(f"内容前100字: {sample['content'][:100]}")
    print(f"LLM输出长度: {len(sample['llm_raw'])} 字符")
    print(f"LLM输出前100字: {sample['llm_raw'][:100]}")
