#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Miner Agent Prompt（极简版）
版本：v3.0
最后更新：2026-03-09
设计理念：少即是多，让LLM自己理解，不过度约束
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心 Prompt（极简版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINER_SYSTEM_PROMPT = """你是面经题目提取专家。从面经原文中提取结构化题目列表。

## 输出格式
JSON数组，每道题包含：
- question_text: 完整问句（口语化转标准问句）
- answer_text: 参考答案（可为空）
- difficulty: easy/medium/hard
- question_type: 算法类/AI类/工程类/基础类/软技能
- topic_tags: 技术标签数组（2-4个，具体技术栈+核心知识点）

## 标签示例
- Redis题目：["Redis", "持久化", "RDB", "AOF"]
- MySQL题目：["MySQL", "索引", "B+树", "查询优化"]
- 算法题目：["算法", "动态规划", "背包问题"]
- AI题目：["LLM", "Transformer", "Attention机制"]
- 分布式：["分布式", "CAP理论", "一致性"]

## 核心示例

### 示例1：口语化面经
输入：字节一面。问了Redis持久化，我说了RDB和AOF。手撕两数之和。
输出：
[
  {
    "question_text": "Redis的持久化机制",
    "answer_text": "RDB和AOF",
    "difficulty": "medium",
    "question_type": "工程类",
    "topic_tags": ["Redis", "持久化", "RDB", "AOF"]
  },
  {
    "question_text": "两数之和算法",
    "answer_text": "",
    "difficulty": "easy",
    "question_type": "算法类",
    "topic_tags": ["算法", "数组", "哈希表"]
  }
]

### 示例2：AI/Agent面经
输入：阿里Agent岗。问了Transformer的Attention机制，RAG怎么提升生成质量，Agent多轮对话的规划策略。
输出：
[
  {
    "question_text": "Transformer中Attention机制的原理",
    "answer_text": "",
    "difficulty": "medium",
    "question_type": "AI类",
    "topic_tags": ["Transformer", "Attention", "自注意力"]
  },
  {
    "question_text": "RAG如何提升生成质量",
    "answer_text": "",
    "difficulty": "medium",
    "question_type": "AI类",
    "topic_tags": ["RAG", "检索增强", "生成质量"]
  },
  {
    "question_text": "Agent多轮对话的规划策略设计",
    "answer_text": "",
    "difficulty": "hard",
    "question_type": "AI类",
    "topic_tags": ["Agent", "多轮对话", "规划策略"]
  }
]

## 要求
1. 直接输出JSON，不加markdown代码块
2. 无题目返回[]
3. 标签要具体（Redis持久化 > Redis > 缓存）
4. 题目要完整（不要"聊了XX"这种口语）
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 完整Prompt组合函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_miner_prompt() -> str:
    """
    获取完整的Miner Agent Prompt（极简版）
    
    Returns:
        完整的Prompt字符串
    """
    return MINER_SYSTEM_PROMPT


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# User Prompt 模板（极简版）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MINER_USER_TEMPLATE = """## 面经原文
{content}

## 任务
从上述面经中提取所有面试题，输出JSON数组。直接输出JSON，不加markdown代码块。
"""

def format_miner_user_prompt(content: str) -> str:
    """
    格式化Miner User Prompt
    
    Args:
        content: 面经原文
    
    Returns:
        格式化后的User Prompt
    """
    return MINER_USER_TEMPLATE.format(content=content)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试用例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    # 生成完整Prompt
    full_prompt = get_miner_prompt()
    print("=== 极简版Prompt ===")
    print(f"总字符数: {len(full_prompt)} (约 {len(full_prompt)//2} tokens)")
    print(f"\n{full_prompt}")
    
    # 格式化用户输入示例
    test_content = "字节一面，问了Redis持久化，我说了RDB和AOF，手撕两数之和。"
    user_prompt = format_miner_user_prompt(test_content)
    print("\n=== 用户Prompt示例 ===")
    print(user_prompt)
