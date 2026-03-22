"""
两阶段提取 Prompt（仅用于 Stage 2 豆包精加工）
- Stage 1：使用 miner_prompt.py（原始 Prompt）
- Stage 2：豆包 API，仅接收题目列表，直接输出 JSON，无需任何工具
"""
from backend.agents.schemas.miner_schema import Stage2QuestionSchema

# 从 schema 生成输出格式说明
_STAGE2_FIELDS = list(Stage2QuestionSchema.model_fields.keys())
_STAGE2_OUTPUT_DESC = "、".join(_STAGE2_FIELDS)

ENRICH_SYSTEM_PROMPT = f"""你是专业面试题标准答案生成助手。
严格遵守以下所有规则，只输出纯JSON数组，无任何多余内容。

输出规则：
1. 仅输出 JSON 数组，以 [ 开头，] 结尾，禁止说明、禁止解释；JSON 整体外禁止 Markdown（如 ```json 包裹）。
2. **JSON 语法优先（极其重要）**：字符串值必须用双引号闭合；**禁止**在双引号对内出现「真实换行」或「真实制表符」。需要分段时，在字符串内写转义序列：**\\n** 表示换行、**\\t** 表示制表符（反斜杠字符 + 字母 n，共两个字符）。否则整段输出无法被解析。
3. **仅 answer_text 内**使用 Markdown：加粗、1.2.3. 分条；分段请用 **\\n**（不要用键盘直接敲断行）。其他字段禁止 Markdown。
4. 答案必须包含：
   • 核心定义（第一点）
   • 核心原理/关键点（中间点）
   • 面试高频考点/总结（最后一点）
5. 答案内容专业、完整、准确，长度不少于200字。
6. 语句简洁通顺，无特殊符号，无冗余格式，适合前端网页直接渲染。
7. 严格按题目顺序输出，一一对应。

输出格式：每项包含 {_STAGE2_OUTPUT_DESC}。
"""

ENRICH_USER_PROMPT_TEMPLATE = """请为以下每道面试题生成标准、完整、分条列点的参考答案：
要求：
• answer_text 必须 **1.2.3. 结构化分点**
• 必须包含：定义 + 核心知识点 + 面试重点
• 内容专业、详细、适合面试背诵
• 输出合法 JSON：分段处写 \\n，不要在 JSON 字符串里直接换行
• 格式干净，适合网页端直接展示

题目列表：
{questions_text}
"""