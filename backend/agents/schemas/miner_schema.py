"""
Miner Agent 数据模型（Pydantic Schema）
用于结构化输出和数据验证
"""
from typing import List, Literal
from pydantic import BaseModel, Field, RootModel, field_validator


class QuestionSchema(BaseModel):
    """单个面试题的结构化模型"""
    
    question_text: str = Field(
        description="标准问句（中文，完整），如：请介绍 Redis 的持久化机制",
        min_length=5,
    )
    
    answer_text: str = Field(
        description=(
            "参考答案（中文，完整）。要求：\n"
            "1. 至少 20 字（特殊情况可放宽至 10 字）\n"
            "2. 包含定义 + 核心原理 + 应用场景/优缺点\n"
            "3. 原文有答案时完整提取，无答案时补充详细参考回答\n"
            "4. 系统设计题需保留架构分层、技术选型、实现逻辑"
        ),
        min_length=10,
    )
    
    difficulty: Literal["easy", "medium", "hard"] = Field(
        description="难度等级，只能是 easy / medium / hard 之一"
    )
    
    question_type: Literal["算法类", "AI类", "工程类", "基础类", "软技能"] = Field(
        description="题目类型，只能是：算法类 / AI类 / 工程类 / 基础类 / 软技能"
    )
    
    topic_tags: List[str] = Field(
        description="2-4 个主题标签，如 ['Redis', '持久化', 'RDB', 'AOF']",
        min_length=2,
        max_length=4,
    )
    
    company: str = Field(
        default="",
        description=(
            "公司全称（优先从标题提取，无则填空字符串）。\n"
            "规范：字节/ByteDance → '字节跳动'，阿里/ali → '阿里巴巴'，腾讯/tencent → '腾讯'。\n"
            "禁止填写模糊表述（如'大厂'、'互联网公司'）"
        ),
    )
    
    position: str = Field(
        default="",
        description="岗位名称（不确定填空字符串），如：后端开发、算法工程师"
    )
    
    @field_validator("answer_text")
    @classmethod
    def validate_answer_length(cls, v: str) -> str:
        """验证答案长度（至少 10 字）"""
        if len(v.strip()) < 10:
            raise ValueError(f"答案过短（{len(v)} 字），至少需要 10 字。请补充完整答案（定义+原理+应用）")
        return v.strip()
    
    @field_validator("topic_tags")
    @classmethod
    def validate_tags_count(cls, v: List[str]) -> List[str]:
        """验证标签数量（2-4 个）"""
        if not (2 <= len(v) <= 4):
            raise ValueError(f"标签数量错误（{len(v)} 个），必须是 2-4 个")
        return v
    
    @field_validator("company")
    @classmethod
    def validate_company(cls, v: str) -> str:
        """验证公司名称（禁止模糊表述）"""
        forbidden = ["大厂", "互联网公司", "某公司", "XX公司"]
        if v and any(word in v for word in forbidden):
            raise ValueError(f"公司名称不能使用模糊表述：{v}。请填写具体公司全称或留空")
        return v.strip()


class QuestionListSchema(BaseModel):
    """面试题列表的结构化模型"""
    
    questions: List[QuestionSchema] = Field(
        description="提取到的所有面试题列表",
        min_length=1,
    )
    
    @field_validator("questions")
    @classmethod
    def validate_questions_not_empty(cls, v: List[QuestionSchema]) -> List[QuestionSchema]:
        """验证题目列表不为空"""
        if not v:
            raise ValueError("至少需要提取 1 道面试题")
        return v


# ============================================================================
# 用于两阶段提取的简化模型
# ============================================================================

class RoughQuestionSchema(BaseModel):
    """第一阶段：粗提取模型（只提取题目和原始答案片段）"""
    
    question_text: str = Field(
        description="标准问句（中文，完整）",
        min_length=5,
    )
    
    raw_answer: str = Field(
        description="原文中的答案片段（原样提取，不补充）。如果原文无答案，填空字符串",
        default="",
    )
    
    difficulty: Literal["easy", "medium", "hard"] = Field(
        description="难度等级"
    )
    
    question_type: Literal["算法类", "AI类", "工程类", "基础类", "软技能"] = Field(
        description="题目类型"
    )
    
    topic_tags: List[str] = Field(
        description="2-4 个主题标签",
        min_length=2,
        max_length=4,
    )
    
    company: str = Field(default="", description="公司全称")
    position: str = Field(default="", description="岗位名称")


class RoughQuestionListSchema(BaseModel):
    """第一阶段：粗提取列表"""
    
    questions: List[RoughQuestionSchema] = Field(
        description="粗提取的面试题列表",
        min_length=1,
    )


# ============================================================================
# Stage 2 输出格式
# ============================================================================


class Stage2QuestionSchema(BaseModel):
    """Stage 2 单题输出（FAQ 格式）"""

    question_text: str = Field(description="标准问句")
    answer_text: str = Field(description="完整参考答案（至少 20 字）")


class Stage2OutputSchema(RootModel[List[Stage2QuestionSchema]]):
    """Stage 2 输出格式：纯 JSON 数组，每项为 FAQ 格式"""
