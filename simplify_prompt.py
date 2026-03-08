import re

with open('backend/services/crawler/question_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 新的简化提示词
new_system_prompt = '''EXTRACT_SYSTEM_PROMPT = """你是面经提取专家，从面经原文中提取所有面试题，输出 JSON 数组。

## 提取规则
1. 只提取原文中的题目，不编造
2. 口语化题目改写为标准问题（如「聊了Redis」→「请介绍Redis的应用场景」）
3. 从叙述中提取答案片段（如「我说了RDB和AOF」→ answer_text填"RDB、AOF"）
4. 无答案的开放题可给出参考答案

## 题目识别
- 编号：1. 2. ① ② 一、二、
- 关键词：「问了」「手写」「手撕」「聊了」「介绍」
- 分号分隔：「问了RAG；CoT是什么」→ 2道题

## 过滤无效内容
- 过渡语：「然后」「接下来」「还有」
- 情绪：「好难」「麻了」「凉了」
- 流程：「面试官很和善」「共XX分钟」
- 少于8字且无技术词汇

## question_type分类
算法类：DP编程题、回溯编程题、贪心编程题、图算法题、树算法题、链表题、数组题、其他算法题
AI/ML：LLM原理题、LLM算法题、模型结构题、模型训练题、RAG题、Agent题、CV题、NLP题
工程类：系统设计题、数据库题、缓存题、消息队列题、微服务题、性能优化题、并发编程题
基础类：操作系统题、计算机网络题、数据结构题、编程语言题
软技能：项目经验题、行为题、HR题

## 输出格式
直接输出JSON数组，不加markdown代码块。
格式：[{"question_text":"题目","answer_text":"答案","difficulty":"easy/medium/hard","question_type":"分类","topic_tags":["标签"],"company":"","position":""}]
无关帖子输出：{"reason":"帖子与面经无关"}
无题目输出：[]"""'''

new_template = '''EXTRACT_PROMPT_TEMPLATE = """## 面经原文
{content}

## 任务
从上面原文提取所有面试题，输出JSON数组。公司：{company}，岗位：{position}"""'''

# 替换系统提示词
pattern1 = r'EXTRACT_SYSTEM_PROMPT = """.*?"""'
content = re.sub(pattern1, new_system_prompt, content, flags=re.DOTALL)

# 删除 EXTRACT_FORMAT_HINT
pattern2 = r'\nEXTRACT_FORMAT_HINT = """.*?"""\n'
content = re.sub(pattern2, '\n', content, flags=re.DOTALL)

# 替换模板
pattern3 = r'EXTRACT_PROMPT_TEMPLATE = """.*?"""'
content = re.sub(pattern3, new_template, content, flags=re.DOTALL)

# 修复调用处（移除 format_hint 参数）
content = content.replace(
    'format_hint=EXTRACT_FORMAT_HINT,',
    ''
)
content = content.replace(
    '{format_hint}',
    ''
)

# 简化用户提示词的调用
old_call = '''user_prompt = EXTRACT_PROMPT_TEMPLATE.format(
        platform="牛客网" if platform == "nowcoder" else "小红书",
        company=company or "未知",
        position=position or "未知",
        difficulty=difficulty or "适中",
        content=truncated,
        format_hint=EXTRACT_FORMAT_HINT,
    )'''

new_call = '''user_prompt = EXTRACT_PROMPT_TEMPLATE.format(
        company=company or "未知",
        position=position or "未知",
        content=truncated,
    )'''

content = content.replace(old_call, new_call)

with open('backend/services/crawler/question_extractor.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('[OK] 提示词已简化！')
print('')
print('主要改进：')
print('1. 系统提示词从 ~1500字 缩减到 ~600字（减少60%）')
print('2. 移除冗余的格式提示（EXTRACT_FORMAT_HINT）')
print('3. 用户提示词简化，移除平台、难度等冗余信息')
print('4. 保留核心功能：题目识别、分类、过滤规则')
print('')
print('预期效果：')
print('- 减少token消耗，提升响应速度')
print('- 提示词更清晰，LLM理解更准确')
print('- 题目提取准确度应该会提升')
