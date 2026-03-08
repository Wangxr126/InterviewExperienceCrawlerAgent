# Prompt 管理规范

## 📁 目录结构

```
backend/prompts/
├── README.md                    # 本文件
├── extractor_prompt.py          # 题目提取器Prompt
├── architect_prompt.py          # 知识架构师Prompt
├── interviewer_prompt.py        # 面试官Prompt
└── versions/                    # 历史版本（可选）
    ├── extractor_v1.0.py
    ├── extractor_v1.1.py
    └── ...
```

## 🎯 设计原则

### 五要素框架

所有Prompt必须包含以下五个要素：

1. **角色（Role）**：定义模型是谁，边界是什么
2. **任务（Task）**：定义模型要完成什么
3. **约束（Constraints）**：定义禁止、优先级、风格、长度、来源限定
4. **输入（Inputs）**：定义有哪些输入块，各自可信度，分隔符与字段规范
5. **输出（Outputs）**：定义输出结构，引用规则，兜底与澄清回问

### RAG场景特殊技巧（适用于Interviewer）

1. **限定知识来源**：只能用参考资料
2. **处理信息冲突**：时间优先
3. **引用质量标准**：没有引用就不输出
4. **澄清与兜底策略**：先尝试澄清，再兜底
5. **防止Prompt注入**：指令优先级，参考资料只提供事实

## 📝 Prompt文件规范

### 文件结构

每个Prompt文件必须包含：

```python
"""
{Agent名称} Prompt（按五要素框架设计）
版本：v{版本号}
最后更新：{日期}
"""

# 1. 五要素框架
{AGENT}_SYSTEM_PROMPT = """..."""

# 2. 详细规则（可选）
{AGENT}_RULES = """..."""

# 3. 示例（可选）
{AGENT}_EXAMPLES = """..."""

# 4. 工具说明（可选）
{AGENT}_TOOLS = """..."""

# 5. 组合函数
def get_{agent}_prompt() -> str:
    """获取完整Prompt"""
    pass

# 6. User Prompt模板
{AGENT}_USER_TEMPLATE = """..."""

def format_{agent}_user_prompt(...) -> str:
    """格式化User Prompt"""
    pass
```

### 命名规范

- 文件名：`{agent}_prompt.py`（小写，下划线分隔）
- 常量名：`{AGENT}_SYSTEM_PROMPT`（大写，下划线分隔）
- 函数名：`get_{agent}_prompt()`（小写，下划线分隔）

### 版本号规范

- 格式：`v{major}.{minor}.{patch}`
- Major：重大变更（不兼容）
- Minor：功能增加（兼容）
- Patch：Bug修复（兼容）

## 🔄 版本管理

### Git管理

```bash
# 提交Prompt变更
git add backend/prompts/
git commit -m "feat(prompt): 优化Extractor Prompt，添加RAG原则"
git push

# 查看Prompt历史
git log backend/prompts/extractor_prompt.py

# 对比版本差异
git diff v1.0 v1.1 backend/prompts/extractor_prompt.py
```

### 版本标签

```bash
# 创建版本标签
git tag -a prompt-v1.0 -m "Prompt v1.0: 初始版本"
git push origin prompt-v1.0

# 查看所有版本
git tag -l "prompt-*"

# 回退到特定版本
git checkout prompt-v1.0 backend/prompts/
```

## 📊 Prompt评估

### 评估维度

1. **准确性**：输出是否符合预期
2. **稳定性**：多次运行结果是否一致
3. **鲁棒性**：异常输入是否能正确处理
4. **效率**：Token使用是否合理

### 评估方法

```python
# 1. 单元测试
def test_extractor_prompt():
    prompt = get_extractor_prompt()
    assert "角色" in prompt
    assert "任务" in prompt
    assert "约束" in prompt

# 2. A/B测试
def ab_test_prompt(old_prompt, new_prompt, test_cases):
    old_results = [call_llm(old_prompt, case) for case in test_cases]
    new_results = [call_llm(new_prompt, case) for case in test_cases]
    compare_results(old_results, new_results)

# 3. 人工评估
def manual_review(prompt, samples):
    for sample in samples:
        result = call_llm(prompt, sample)
        score = human_evaluate(result)
        print(f"Sample: {sample}, Score: {score}")
```

## 🔧 优化迭代流程

### 1. 从bad case出发

```
发现问题 → 分析原因 → 针对性修改 → 测试验证 → 部署上线
```

### 2. 用A/B测试验证效果

```python
# 准备测试用例
test_cases = [
    {"input": "...", "expected": "..."},
    {"input": "...", "expected": "..."},
]

# 运行A/B测试
results = ab_test_prompt(
    old_prompt=get_extractor_prompt_v1(),
    new_prompt=get_extractor_prompt_v2(),
    test_cases=test_cases
)

# 分析结果
print(f"准确率提升: {results['accuracy_improvement']}")
print(f"Token节省: {results['token_saved']}")
```

### 3. 用Prompt体检清单确保没有遗漏

- [ ] 是否包含五要素？
- [ ] 是否有明确的禁止事项？
- [ ] 是否有优先级排序？
- [ ] 是否有长度限制？
- [ ] 是否有来源限定？
- [ ] 是否有输出格式示例？
- [ ] 是否有异常处理？
- [ ] 是否有RAG原则（如果适用）？

### 4. 把Prompt当代码一样管理，做版本控制

```bash
# 创建新分支
git checkout -b prompt/improve-extractor

# 修改Prompt
vim backend/prompts/extractor_prompt.py

# 提交变更
git add backend/prompts/extractor_prompt.py
git commit -m "feat(prompt): 优化Extractor题目识别规则"

# 合并到主分支
git checkout main
git merge prompt/improve-extractor
```

## 📚 最佳实践

### 1. 保持简洁

- 避免冗余描述
- 使用列表和表格
- 突出重点信息

### 2. 提供示例

- Few-shot examples
- 正例和反例
- 边界情况

### 3. 明确约束

- 禁止事项
- 优先级
- 长度限制
- 来源限定

### 4. 可测试性

- 输出格式明确
- 可量化的标准
- 易于验证

### 5. 可维护性

- 模块化设计
- 注释清晰
- 版本管理

## 🚀 使用示例

### Extractor

```python
from backend.prompts.extractor_prompt import (
    get_extractor_prompt,
    format_extractor_user_prompt
)

# 获取System Prompt
system_prompt = get_extractor_prompt(include_examples=True)

# 格式化User Prompt
user_prompt = format_extractor_user_prompt(content="面经原文...")

# 调用LLM
response = llm.call(system_prompt, user_prompt)
```

### Architect

```python
from backend.prompts.architect_prompt import (
    get_architect_prompt,
    format_architect_user_prompt
)

# 获取System Prompt
system_prompt = get_architect_prompt()

# 格式化User Prompt
user_prompt = format_architect_user_prompt(
    meta={"company": "字节跳动", ...},
    questions=[...]
)

# 调用Agent
response = architect_agent.run(user_prompt)
```

### Interviewer

```python
from backend.prompts.interviewer_prompt import (
    get_interviewer_prompt,
    format_interviewer_user_prompt
)

# 获取System Prompt
system_prompt = get_interviewer_prompt()

# 格式化User Prompt（包含RAG检索结果）
user_prompt = format_interviewer_user_prompt(
    user_info={"tech_stack": "Java", ...},
    reference_materials="题库检索结果...",
    user_request="推荐Redis相关的题目"
)

# 调用Agent
response = interviewer_agent.run(user_prompt)
```

## 📖 参考资料

- [Prompt Engineering Guide](https://www.promptingguide.ai/)
- [OpenAI Best Practices](https://platform.openai.com/docs/guides/prompt-engineering)
- [Anthropic Prompt Library](https://docs.anthropic.com/claude/prompt-library)

## 🔄 更新日志

### v1.0 (2024-03-08)
- 初始版本
- 创建Extractor、Architect、Interviewer三个Prompt
- 应用五要素框架
- 为Interviewer添加RAG原则

---

**维护者**：AI Team  
**最后更新**：2024-03-08
