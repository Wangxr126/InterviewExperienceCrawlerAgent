"""
面试官 Agent 日志查看工具

用法:
    python view_interviewer_logs.py                    # 显示统计信息
    python view_interviewer_logs.py --chat             # 查看今日对话
    python view_interviewer_logs.py --thinking         # 查看今日推理过程
    python view_interviewer_logs.py --tools            # 查看今日工具调用
    python view_interviewer_logs.py --stats            # 详细统计
    python view_interviewer_logs.py --date 20260308    # 查看指定日期
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter
import argparse


def load_jsonl(file_path):
    """加载 JSONL 文件"""
    if not file_path.exists():
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def print_chat_logs(logs):
    """打印对话日志"""
    print(f"\n{'='*80}")
    print(f"对话日志 ({len(logs)} 条)")
    print(f"{'='*80}\n")
    
    for i, log in enumerate(logs, 1):
        print(f"[{i}] {log['timestamp']}")
        print(f"用户 ({log['user_id']}): {log['user_message'][:100]}...")
        print(f"AI: {log['ai_response'][:200]}...")
        print(f"回复长度: {log['response_length']} 字 | 推理步骤: {log['thinking_steps_count']} 步")
        print(f"{'-'*80}\n")


def print_thinking_logs(logs):
    """打印推理日志"""
    print(f"\n{'='*80}")
    print(f"推理日志 ({len(logs)} 条)")
    print(f"{'='*80}\n")
    
    for i, log in enumerate(logs, 1):
        print(f"[{i}] {log['timestamp']}")
        print(f"用户消息: {log['user_message'][:80]}...")
        print(f"推理步骤 ({log['total_steps']} 步):")
        
        for step in log['thinking_steps']:
            print(f"  Step {step.get('step', '?')}: {step.get('thought', 'N/A')[:100]}...")
            if 'action' in step:
                print(f"    -> Action: {step['action']}")
            if 'observation' in step:
                print(f"    -> Result: {step['observation'][:80]}...")
        
        print(f"{'-'*80}\n")


def print_tool_logs(logs):
    """打印工具调用日志"""
    print(f"\n{'='*80}")
    print(f"工具调用日志 ({len(logs)} 条)")
    print(f"{'='*80}\n")
    
    for i, log in enumerate(logs, 1):
        status = "SUCCESS" if log['success'] else "FAILED"
        print(f"[{i}] {log['timestamp']} - {status}")
        print(f"工具: {log['tool_name']}")
        print(f"输入: {json.dumps(log['tool_input'], ensure_ascii=False)[:100]}...")
        print(f"输出: {log['tool_output'][:150]}...")
        if log['error']:
            print(f"错误: {log['error']}")
        print(f"{'-'*80}\n")


def print_statistics(chat_logs, thinking_logs, tool_logs):
    """打印统计信息"""
    print(f"\n{'='*80}")
    print(f"统计信息")
    print(f"{'='*80}\n")
    
    # 对话统计
    print(f"对话总数: {len(chat_logs)}")
    if chat_logs:
        avg_response_len = sum(c['response_length'] for c in chat_logs) / len(chat_logs)
        avg_thinking_steps = sum(c['thinking_steps_count'] for c in chat_logs) / len(chat_logs)
        print(f"平均回复长度: {avg_response_len:.0f} 字")
        print(f"平均推理步骤: {avg_thinking_steps:.1f} 步")
        
        # 用户分布
        users = Counter(c['user_id'] for c in chat_logs)
        print(f"\n用户分布:")
        for user, count in users.most_common():
            print(f"  - {user}: {count} 次对话")
    
    # 推理统计
    print(f"\n推理记录总数: {len(thinking_logs)}")
    if thinking_logs:
        step_counts = Counter(t['total_steps'] for t in thinking_logs)
        print(f"推理步骤分布:")
        for steps, count in sorted(step_counts.items()):
            print(f"  - {steps} 步: {count} 次")
    
    # 工具调用统计
    print(f"\n工具调用总数: {len(tool_logs)}")
    if tool_logs:
        tool_names = Counter(t['tool_name'] for t in tool_logs)
        success_count = sum(1 for t in tool_logs if t['success'])
        print(f"成功率: {success_count}/{len(tool_logs)} ({success_count/len(tool_logs)*100:.1f}%)")
        print(f"\n工具使用频率:")
        for tool, count in tool_names.most_common():
            print(f"  - {tool}: {count} 次")


def main():
    parser = argparse.ArgumentParser(description='查看面试官 Agent 日志')
    parser.add_argument('--chat', action='store_true', help='查看对话日志')
    parser.add_argument('--thinking', action='store_true', help='查看推理日志')
    parser.add_argument('--tools', action='store_true', help='查看工具调用日志')
    parser.add_argument('--stats', action='store_true', help='显示详细统计')
    parser.add_argument('--date', type=str, help='指定日期 (YYYYMMDD)', 
                       default=datetime.now().strftime('%Y%m%d'))
    parser.add_argument('--model', type=str, help='指定模型目录名称')
    
    args = parser.parse_args()
    
    # 查找日志目录
    base_dir = Path('interviewer_logs')
    if not base_dir.exists():
        print(f"错误: 日志目录不存在: {base_dir}")
        return
    
    # 确定模型目录
    if args.model:
        model_dir = base_dir / args.model
        if not model_dir.exists():
            print(f"错误: 模型目录不存在: {model_dir}")
            return
    else:
        # 使用最新的模型目录
        model_dirs = [d for d in base_dir.iterdir() if d.is_dir()]
        if not model_dirs:
            print(f"错误: 没有找到任何模型目录")
            return
        model_dir = max(model_dirs, key=lambda d: d.stat().st_mtime)
    
    print(f"模型目录: {model_dir.name}")
    print(f"日期: {args.date}")
    
    # 加载日志
    chat_logs = load_jsonl(model_dir / f"chat_{args.date}.jsonl")
    thinking_logs = load_jsonl(model_dir / f"thinking_{args.date}.jsonl")
    tool_logs = load_jsonl(model_dir / f"tools_{args.date}.jsonl")
    
    # 显示日志
    if args.chat:
        print_chat_logs(chat_logs)
    elif args.thinking:
        print_thinking_logs(thinking_logs)
    elif args.tools:
        print_tool_logs(tool_logs)
    elif args.stats or not any([args.chat, args.thinking, args.tools]):
        print_statistics(chat_logs, thinking_logs, tool_logs)


if __name__ == '__main__':
    main()
