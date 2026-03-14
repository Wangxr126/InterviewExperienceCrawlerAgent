"""
两阶段提取 Prompt（仅用于 Stage 2 豆包精加工）
- Stage 1：使用 miner_prompt.py（原始 Prompt）
- Stage 2：豆包 API，仅接收题目列表，直接输出 JSON，无需任何工具
"""
from backend.agents.schemas.miner_schema import Stage2QuestionSchema

# 从 schema 生成输出格式说明
_STAGE2_FIELDS = list(Stage2QuestionSchema.model_fields.keys())
_STAGE2_OUTPUT_DESC = "、".join(_STAGE2_FIELDS)

ENRICH_SYSTEM_PROMPT = f"""你是面试题整理助手。你只需接收题目列表，直接输出 JSON 数组。

输出格式：每项包含 {_STAGE2_OUTPUT_DESC}。
直接输出 JSON 数组，以 [ 开头、] 结尾，禁止输出 Markdown、说明文字或其它内容。"""

ENRICH_USER_PROMPT_TEMPLATE = """请为以下面试题补充完整参考答案（answer_text，至少 20 字，含定义+核心点）：

{questions_text}"""
