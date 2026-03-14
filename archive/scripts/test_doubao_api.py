"""
测试豆包 API 配置
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.miner_agent_v3 import create_miner_agent

def test_doubao_api():
    """测试豆包 API 是否正常工作"""
    print("=" * 80)
    print("测试豆包 API 配置")
    print("=" * 80)
    
    # 测试用例
    test_content = """
1. 请介绍 Redis 持久化
2. MySQL 索引原理
3. 手撕 LRU
    """
    
    try:
        # 创建 Agent（single_stage 模式）
        print("\n创建 MinerAgent（使用豆包 API）...")
        agent = create_miner_agent(mode="single_stage")
        
        print("开始提取...")
        result, ocr_called, is_unrelated = agent.run(
            content=test_content,
            has_image=False,
            company="字节跳动",
            position="后端开发"
        )
        
        # 输出结果
        print("\n" + "=" * 80)
        print("✅ 提取成功！")
        print("=" * 80)
        print(f"OCR 调用: {ocr_called}")
        print(f"是否无关: {is_unrelated}")
        print(f"结果长度: {len(result)} 字符")
        
        # 解析 JSON
        if result and result != "__UNRELATED__":
            import json
            try:
                questions = json.loads(result)
                print(f"提取题目数: {len(questions)}")
                
                # 输出每道题的摘要
                for i, q in enumerate(questions, 1):
                    print(f"\n题目 {i}:")
                    print(f"  问题: {q.get('question_text', '')}")
                    print(f"  答案长度: {len(q.get('answer_text', ''))} 字")
                    print(f"  答案预览: {q.get('answer_text', '')[:100]}...")
                    print(f"  难度: {q.get('difficulty', '')}")
                    print(f"  类型: {q.get('question_type', '')}")
                    print(f"  标签: {q.get('topic_tags', [])}")
                
                # 统计答案长度
                answer_lengths = [len(q.get('answer_text', '')) for q in questions]
                avg_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0
                print(f"\n平均答案长度: {avg_length:.1f} 字")
                print(f"最短答案: {min(answer_lengths) if answer_lengths else 0} 字")
                print(f"最长答案: {max(answer_lengths) if answer_lengths else 0} 字")
                
                print("\n" + "=" * 80)
                print("🎉 豆包 API 配置成功！答案质量良好！")
                print("=" * 80)
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 解析失败: {e}")
                print(f"原始结果: {result[:500]}...")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_doubao_api()
