"""
MinerAgent V3 测试脚本
用于测试三种模式的效果对比
"""
import json
import logging
from pathlib import Path

# 加载 .env（两阶段模式需要豆包 API 配置）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from backend.agents.miner_agent_v3 import create_miner_agent

# ============================================================================
# 测试用例
# ============================================================================

TEST_CASES = [
    {
        "name": "纯题目列表（无答案）",
        "content": """
1. 请介绍 Redis 持久化
2. MySQL 索引原理
3. 手撕 LRU
        """,
        "has_image": False,
        "company": "字节跳动",
        "position": "后端开发",
    },
    {
        "name": "长答案提取",
        "content": """
面试官问了 Redis 持久化，我说了 RDB 和 AOF，RDB 是定时快照，优点是恢复快，缺点是可能丢数据；AOF 是实时日志，优点是数据安全，缺点是文件大恢复慢。
        """,
        "has_image": False,
        "company": "阿里巴巴",
        "position": "后端开发",
    },
    {
        "name": "系统设计题",
        "content": """
如何设计一个高并发订单系统？我从架构分层、存储设计、并发控制这几个方面回答，用了 Kafka 削峰、Redis 分布式锁、MySQL 分库分表。
        """,
        "has_image": False,
        "company": "美团",
        "position": "后端开发",
    },
    {
        "name": "多题分隔",
        "content": """
问了 Redis 持久化；MySQL 索引原理；手撕 LRU
        """,
        "has_image": False,
        "company": "腾讯",
        "position": "后端开发",
    },
]


# ============================================================================
# 测试函数
# ============================================================================

def test_single_mode(test_case: dict, mode: str):
    """测试单个模式"""
    print(f"\n{'='*80}")
    print(f"测试用例: {test_case['name']}")
    print(f"测试模式: {mode}")
    print(f"{'='*80}")
    
    try:
        # 创建 Agent
        agent = create_miner_agent(mode=mode)
        
        # 运行提取
        result, ocr_called, is_unrelated = agent.run(
            content=test_case["content"],
            has_image=test_case["has_image"],
            company=test_case["company"],
            position=test_case["position"],
        )
        
        # 输出结果
        print(f"\n✅ 提取成功")
        print(f"OCR 调用: {ocr_called}")
        print(f"是否无关: {is_unrelated}")
        print(f"结果长度: {len(result)} 字符")
        
        # 解析 JSON
        if result and result != "__UNRELATED__":
            try:
                questions = json.loads(result)
                print(f"提取题目数: {len(questions)}")
                
                # 输出每道题的摘要
                for i, q in enumerate(questions, 1):
                    print(f"\n题目 {i}:")
                    print(f"  问题: {q.get('question_text', '')[:50]}...")
                    print(f"  答案长度: {len(q.get('answer_text', ''))} 字")
                    print(f"  难度: {q.get('difficulty', '')}")
                    print(f"  类型: {q.get('question_type', '')}")
                    print(f"  标签: {q.get('topic_tags', [])}")
                
                # 统计答案长度
                answer_lengths = [len(q.get('answer_text', '')) for q in questions]
                avg_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0
                print(f"\n平均答案长度: {avg_length:.1f} 字")
                print(f"最短答案: {min(answer_lengths) if answer_lengths else 0} 字")
                print(f"最长答案: {max(answer_lengths) if answer_lengths else 0} 字")
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 解析失败: {e}")
                print(f"原始结果: {result[:500]}...")
        
        return {
            "success": True,
            "result": result,
            "ocr_called": ocr_called,
            "is_unrelated": is_unrelated,
        }
        
    except Exception as e:
        print(f"\n❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
        }


def test_all_modes():
    """测试所有模式"""
    modes = ["single_stage", "two_stage"]  # structured 需要特定 LLM 支持
    
    results = {}
    
    for test_case in TEST_CASES:
        case_name = test_case["name"]
        results[case_name] = {}
        
        for mode in modes:
            result = test_single_mode(test_case, mode)
            results[case_name][mode] = result
    
    # 输出对比总结
    print(f"\n\n{'='*80}")
    print("测试总结")
    print(f"{'='*80}")
    
    for case_name, mode_results in results.items():
        print(f"\n{case_name}:")
        for mode, result in mode_results.items():
            if result["success"]:
                try:
                    questions = json.loads(result["result"])
                    answer_lengths = [len(q.get('answer_text', '')) for q in questions]
                    avg_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0
                    print(f"  {mode:15s}: {len(questions)} 题, 平均答案 {avg_length:.1f} 字")
                except:
                    print(f"  {mode:15s}: 解析失败")
            else:
                print(f"  {mode:15s}: 提取失败")


def test_quick():
    """快速测试（只测试第一个用例）"""
    test_case = TEST_CASES[0]
    
    print("快速测试：只测试第一个用例（纯题目列表）")
    
    for mode in ["single_stage", "two_stage"]:
        test_single_mode(test_case, mode)


# ============================================================================
# 主函数
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        # 快速测试
        test_quick()
    else:
        # 完整测试
        test_all_modes()
