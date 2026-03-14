"""
两阶段提取 Prompt
- Stage 1：使用 miner_prompt.py 的输入和输出（不变）
- Stage 2：豆包 API，仅将题目整理为 FAQ 格式，输出格式由 Stage2OutputSchema 定义
"""
from backend.agents.schemas.miner_schema import Stage2QuestionSchema

# 从 schema 生成输出格式说明
_STAGE2_FIELDS = list(Stage2QuestionSchema.model_fields.keys())
_STAGE2_OUTPUT_DESC = "、".join(_STAGE2_FIELDS)

ENRICH_SYSTEM_PROMPT = f"""将面试题整理为 FAQ 格式，直接输出 JSON 结果。每项包含 {_STAGE2_OUTPUT_DESC}。"""

ENRICH_USER_PROMPT_TEMPLATE = "{questions_text}"
